"""VirtoLang interpreter.

The interpreter is the final stage of the pipeline::

    source text --> Lexer --> tokens --> Parser --> AST --> Interpreter

It walks the abstract syntax tree built by ``parser.py`` and executes it.
Every AST node is a tuple tagged with its kind (``("IF", ...)``,
``("CALL", ...)``, ...) or a plain literal value.  ``Interpreter.evaluate``
looks the tag up in a dispatch table and calls the matching ``_eval_*``
method, which returns the node's value.

Key ideas for readers new to the code
-------------------------------------
* **Scopes.** Variables live in ``Scope`` objects chained together.  Reading
  a name searches the current scope and then its parents (finally the Python
  builtins); assigning always writes to the current scope.  Each function
  call gets a new scope whose parent is the scope the function was defined
  in, which is what makes closures and recursion work.
* **Control-flow signals.** ``return``, ``break`` and ``continue`` are not
  Python exceptions.  Executing them produces a signal object that is passed
  back up through blocks until a function or loop consumes it.
* **Python interop.** VirtoLang values *are* Python values (ints, strings,
  lists, dicts, modules...), so any Python function can be called directly.
  User-defined functions and classes are wrapped in objects that behave like
  normal Python callables, so Python code can call them too.
"""

import ast
import asyncio
from contextlib import ExitStack
import importlib
import operator
import re
import threading

import lexer
from lexer import Lexer
from parser import Parser

_MISSING = object()


# ---------------------------------------------------------------------------
# Control-flow signals
# ---------------------------------------------------------------------------


class _ControlSignal:
    """Base class for values that unwind execution (return/break/continue)."""

    __slots__ = ()


class _ReturnSignal(_ControlSignal):
    """Produced by ``return``; carries the value being returned."""

    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value


class _BreakSignal(_ControlSignal):
    """Produced by ``break``; consumed by the nearest enclosing loop."""

    __slots__ = ()


class _ContinueSignal(_ControlSignal):
    """Produced by ``continue``; consumed by the nearest enclosing loop."""

    __slots__ = ()


# ``break`` and ``continue`` carry no data, so one shared instance each is enough.
_BREAK = _BreakSignal()
_CONTINUE = _ContinueSignal()
_SIGNAL_CLASSES = frozenset((_BreakSignal, _ContinueSignal, _ReturnSignal))


# ---------------------------------------------------------------------------
# Operator tables
# ---------------------------------------------------------------------------

_BINARY_OPERATORS = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
    "//": operator.floordiv,
    "%": operator.mod,
    "**": operator.pow,
}

_AUGMENTED_OPERATORS = {
    "+=": operator.add,
    "-=": operator.sub,
    "*=": operator.mul,
    "/=": operator.truediv,
    "//=": operator.floordiv,
    "%=": operator.mod,
    "**=": operator.pow,
}

_COMPARE_OPERATORS = {
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
    "<=": operator.le,
    ">=": operator.ge,
    "in": lambda left, right: left in right,
    "not in": lambda left, right: left not in right,
}

_UNARY_OPERATORS = {"+": operator.pos, "-": operator.neg}

# f-string conversion flags: f"{value!r}"
_CONVERSIONS = {"s": str, "r": repr, "a": ascii}

# Node tags that are statements.  In the REPL only *expression* statements
# (anything not listed here) have their value echoed back to the user.
STATEMENT_TAGS = frozenset(
    (
        "BLOCK",
        "IF",
        "WHILE",
        "FOR",
        "FUNCDEF",
        "CLASS",
        "TRY",
        "IMPORT",
        "FROMIMPORT",
        "RETURN",
        "RAISE",
        "BREAK",
        "CONTINUE",
        "ASSIGN_LHS",
        "AUGASSIGN",
        "WITH",
        "ASYNCFOR",
        "ASYNCWITH",
        "DECORATED",
        "PASS",
        "ASSERT",
        "DEL",
        "GLOBAL",
        "NONLOCAL",
    )
)


# ---------------------------------------------------------------------------
# f-string helpers
# ---------------------------------------------------------------------------


def _find_fstring_field_end(value, start):
    """Return the index of the ``}`` that closes the field starting at ``start``.

    ``start`` points just after the opening ``{``.  Nested braces and quoted
    strings inside the field are skipped correctly.
    """
    depth = 1
    quote = None
    escaped = False
    for index in range(start, len(value)):
        char = value[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    raise SyntaxError("f-string: unmatched '{'")


def _split_fstring_field(field):
    """Split the text of an f-string field into its three parts.

    ``"value!r:>10"`` becomes ``("value", "r", ">10")``.  A missing
    conversion or format spec is returned as ``None``.  Only a ``!`` or ``:``
    outside brackets and quotes counts as a separator (so ``a != b`` and
    ``d["k:v"]`` are left alone).
    """
    depths = {"(": 0, "[": 0, "{": 0}
    closing = {")": "(", "]": "[", "}": "{"}
    quote = None
    escaped = False
    for index, char in enumerate(field):
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
        elif char in depths:
            depths[char] += 1
        elif char in closing:
            depths[closing[char]] -= 1
        elif not any(depths.values()):
            if char == "!" and not field.startswith("!=", index):
                conversion = field[index + 1 :]
                if ":" in conversion:
                    conversion, format_spec = conversion.split(":", 1)
                    return field[:index], conversion, format_spec
                return field[:index], conversion, None
            if char == ":":
                return field[:index], None, field[index + 1 :]
    return field, None, None


# ---------------------------------------------------------------------------
# Runtime objects
# ---------------------------------------------------------------------------


class Scope:
    """A table of variables plus a link to the enclosing scope.

    Attributes:
        vars: ``{name: value}`` for names defined directly in this scope.
        parent: The enclosing ``Scope`` (``None`` for the global scope).
        redirects: ``None`` normally.  After ``global x`` / ``nonlocal x`` it
            maps the name to the ``Scope`` that really owns the variable, so
            assignments inside this scope are written there instead.
        function: The ``UserFunction`` executing in this scope, if any.
    """

    __slots__ = ("vars", "parent", "redirects", "function")

    def __init__(self, parent=None, initial=None, function=None):
        self.vars = initial if initial is not None else {}
        self.parent = parent
        self.redirects = None
        self.function = function

    def lookup(self, name):
        """Find ``name`` in this scope or an enclosing one, else ``_MISSING``."""
        scope = self
        while scope is not None:
            if name in scope.vars:
                return scope.vars[name]
            scope = scope.parent
        return _MISSING


class UserFunction:
    """A function defined in VirtoLang with ``def``.

    Instances are ordinary Python callables, so they can be passed to Python
    functions such as ``sorted(items, key=my_function)``.

    Attributes:
        interpreter: The interpreter that runs the function body.
        name: Function name (used in error messages).
        params: Positional parameter names, in order.
        defaults: ``{param_name: default_value}`` for optional parameters
            (including keyword-only ones).
        body: The function's AST block.
        closure: The ``Scope`` the function was defined in.
        vararg: Name collecting extra positional arguments (``*args``) or ``None``.
        kwonly: Names of keyword-only parameters (those after ``*``).
        kwarg: Name collecting extra keyword arguments (``**kwargs``) or ``None``.
        is_async: True for ``async def`` (calling gives an awaitable).
        is_generator: True if the body uses ``yield`` (calling gives a generator).
        special: True when advanced parameter, async, or generator features are
            used; plain functions skip all the extra work on every call.
    """

    __slots__ = (
        "interpreter", "name", "params", "defaults", "body", "closure",
        "vararg", "kwonly", "kwarg", "is_async", "is_generator", "special",
        "posonly", "is_async_generator", "defining_class", "body_fn",
    )

    def __init__(self, interpreter, name, params, defaults, body, closure, extras=None):
        self.interpreter = interpreter
        self.name = name
        self.params = params
        self.defaults = defaults
        self.body = body
        self.closure = closure
        extras = extras or {}
        self.posonly = extras.get("posonly", ())
        self.vararg = extras.get("vararg")
        self.kwonly = extras.get("kwonly", ())
        self.kwarg = extras.get("kwarg")
        self.is_async = extras.get("async", False)
        self.is_generator = extras.get("generator", False)
        self.is_async_generator = extras.get("async_generator", False)
        self.defining_class = None
        # Compiled closure of ``body``; built on the first call.
        self.body_fn = None
        self.special = bool(extras)

    def __call__(self, *args, **kwargs):
        return self.interpreter.call_user_function(self, args, kwargs)

    def __repr__(self):
        return f"<function {self.name}>"


# ---------------------------------------------------------------------------
# Fibers: pausable function bodies (used by generators and async functions)
# ---------------------------------------------------------------------------


class _Fiber:
    """Runs a function body on its own thread so it can pause and resume.

    The tree-walking interpreter keeps its state on the Python call stack, so
    a body that executes ``yield`` or ``await`` cannot simply return.  Instead
    it runs on a helper thread; exactly one thread runs at any moment (control
    is handed back and forth with semaphores), so no locking is needed.

    Attributes:
        is_async: True when the fiber drives an ``async def``.
        is_async_generator: True when the fiber can pause at both ``await`` and
            ``yield`` expressions.
        finished: True once the body returned or raised.
    """

    _STACK_SIZE = 64 * 1024 * 1024

    def __init__(self, interpreter, body, is_async=False, is_async_generator=False):
        self._interpreter = interpreter
        self._body = body
        self.is_async = is_async
        self.is_async_generator = is_async_generator
        self.loop = None
        self.finished = False
        self._thread = None
        self._wake_fiber = threading.Semaphore(0)
        self._wake_caller = threading.Semaphore(0)
        self._inbox = (None, None)
        self._outbox = None
        self._scope = None

    def _run(self):
        if self.loop is not None:
            # Let asyncio helpers such as create_task see the driving loop.
            asyncio._set_running_loop(self.loop)
        try:
            self._outbox = ("return", self._body())
        except BaseException as error:
            self._outbox = ("error", error)
        self.finished = True
        self._wake_caller.release()

    def resume(self, value=None, error=None):
        """Continue the body; returns ``("yield", v)`` or ``("return", v)``.

        ``value`` is delivered as the result of the pending ``yield``/``await``
        and ``error`` is raised there instead.  Exceptions escaping the body
        are re-raised in the caller.
        """
        if self.finished:
            raise RuntimeError("fiber already finished")
        interpreter = self._interpreter
        saved = (interpreter.scope, interpreter.error_location, interpreter._fiber)
        interpreter._fiber = self
        self._inbox = (value, error)
        if self._thread is None:
            if error is not None:
                self.finished = True
                interpreter.scope, interpreter.error_location, interpreter._fiber = saved
                raise error
            previous_size = threading.stack_size(self._STACK_SIZE)
            try:
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()
            finally:
                threading.stack_size(previous_size)
        else:
            self._wake_fiber.release()
        self._wake_caller.acquire()
        interpreter.scope, interpreter.error_location, interpreter._fiber = saved
        kind, payload = self._outbox
        if kind == "error":
            raise payload
        return kind, payload

    def suspend(self, kind, payload):
        """Called on the fiber thread: pause and hand ``payload`` to the caller.

        Returns the value sent by the next ``resume`` (or raises its error).
        """
        interpreter = self._interpreter
        self._scope = interpreter.scope
        self._outbox = (kind, payload)
        self._wake_caller.release()
        self._wake_fiber.acquire()
        interpreter.scope = self._scope
        value, error = self._inbox
        if error is not None:
            raise error
        return value


class VirtoGenerator:
    """The iterator returned by calling a function that contains ``yield``.

    Supports ``for`` loops, ``next(gen)``, and the usual ``send``/``throw``/
    ``close`` methods.
    """

    def __init__(self, interpreter, function, local):
        self._fiber = _Fiber(interpreter, lambda: interpreter._run_body(function, local))
        self._name = function.name
        self._started = False

    def __iter__(self):
        return self

    def __next__(self):
        return self.send(None)

    def send(self, value):
        """Resume the generator, delivering ``value`` to the paused ``yield``."""
        fiber = self._fiber
        if fiber.finished:
            raise StopIteration
        if not self._started and value is not None:
            raise TypeError("can't send a non-None value to a just-started generator")
        self._started = True
        kind, payload = fiber.resume(value)
        if kind == "return":
            raise StopIteration(payload)
        return payload

    def throw(self, error):
        """Raise ``error`` inside the generator at its paused ``yield``."""
        if isinstance(error, type):
            error = error()
        fiber = self._fiber
        if fiber.finished:
            raise error
        self._started = True
        kind, payload = fiber.resume(None, error)
        if kind == "return":
            raise StopIteration(payload)
        return payload

    def close(self):
        """Stop the generator early (runs its ``finally`` blocks)."""
        fiber = self._fiber
        if fiber.finished or not self._started:
            fiber.finished = True
            return
        try:
            fiber.resume(None, GeneratorExit())
        except (GeneratorExit, StopIteration):
            pass

    def __repr__(self):
        return f"<generator {self._name}>"


class VirtoAsyncGenerator:
    """The asynchronous iterator returned by an async generator function."""

    def __init__(self, interpreter, function, local):
        self._fiber = _Fiber(
            interpreter,
            lambda: interpreter._run_body(function, local),
            is_async=True,
            is_async_generator=True,
        )
        self._name = function.name
        self._started = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.asend(None)

    async def asend(self, value):
        fiber = self._fiber
        if fiber.finished:
            raise StopAsyncIteration
        if not self._started and value is not None:
            raise TypeError("can't send a non-None value to a just-started async generator")
        self._started = True
        return await self._drive(value=value)

    async def _drive(self, value=None, error=None, closing=False):
        fiber = self._fiber
        while True:
            kind, payload = fiber.resume(value, error)
            value = error = None
            if kind == "return":
                if closing:
                    return
                raise StopAsyncIteration
            if kind == "async_yield":
                if closing:
                    raise RuntimeError("async generator ignored GeneratorExit")
                return payload
            if kind != "await":
                raise RuntimeError(f"invalid async generator suspension: {kind}")
            try:
                value = await payload
            except BaseException as caught:
                error = caught

    async def athrow(self, error):
        if isinstance(error, type):
            error = error()
        if self._fiber.finished:
            raise error
        self._started = True
        return await self._drive(error=error)

    async def aclose(self):
        fiber = self._fiber
        if fiber.finished or not self._started:
            fiber.finished = True
            return
        try:
            await self._drive(error=GeneratorExit(), closing=True)
        except GeneratorExit:
            return

    def __repr__(self):
        return f"<async_generator {self._name}>"


class BoundMethod:
    """A ``UserFunction`` with its first parameter (``self``) pre-filled."""

    __slots__ = ("function", "instance")

    def __init__(self, function, instance):
        self.function = function
        self.instance = instance

    def __call__(self, *args, **kwargs):
        return self.function(self.instance, *args, **kwargs)

    def __repr__(self):
        return f"<bound method {self.function.name}>"


class VirtoSuper:
    """Resolve attributes after the class whose method is currently running."""

    __slots__ = ("owner", "receiver")

    def __init__(self, owner, receiver):
        self.owner = owner
        self.receiver = receiver

    def __getattr__(self, name):
        receiver = self.receiver
        cls = (
            object.__getattribute__(receiver, "__vclass__")
            if isinstance(receiver, VirtoInstance)
            else receiver
        )
        member = cls.find_member_after(self.owner, name)
        if member is _MISSING:
            raise AttributeError(f"no superclass attribute {name!r}")
        return _bind_class_member(member, receiver)


class VirtoClass:
    """A class defined in VirtoLang with ``class``.

    Calling the class creates a ``VirtoInstance`` and runs its ``__init__``
    method (if it has one).

    Attributes:
        name: Class name.
        members: ``{name: value}`` of everything defined in the class body.
        bases: Parent ``VirtoClass`` objects, searched left to right.
    """

    __slots__ = ("name", "members", "bases")

    def __init__(self, name, members, bases=()):
        self.name = name
        self.members = members
        self.bases = tuple(bases)

    def find_member(self, name):
        """Look ``name`` up on this class, then on its bases; else ``_MISSING``."""
        if name in self.members:
            return self.members[name]
        for base in self.bases:
            found = base.find_member(name)
            if found is not _MISSING:
                return found
        return _MISSING

    def find_member_after(self, owner, name):
        """Find a member in the depth-first base order after ``owner``."""
        passed_owner = False
        visited = set()
        pending = [self]
        while pending:
            cls = pending.pop(0)
            if cls in visited:
                continue
            visited.add(cls)
            if passed_owner and name in cls.members:
                return cls.members[name]
            if cls is owner:
                passed_owner = True
            pending[0:0] = list(cls.bases)
        return _MISSING

    def __getattr__(self, name):
        member = self.find_member(name)
        if member is _MISSING:
            raise AttributeError(f"class {self.name!r} has no attribute {name!r}")
        return _bind_class_member(member, self)

    def __call__(self, *args, **kwargs):
        instance = VirtoInstance(self)
        initializer = self.find_member("__init__")
        if isinstance(initializer, UserFunction):
            initializer(instance, *args, **kwargs)
        return instance

    def __repr__(self):
        return f"<class {self.name}>"


class VirtoInstance:
    """An object created from a ``VirtoClass``.

    Attribute reads check the instance's own attributes first and then the
    class (binding methods to the instance).  Attribute writes always go to
    the instance.  If the class defines ``__str__`` or ``__repr__`` they are
    used by ``print`` and ``repr``.
    """

    # Names use double underscores on both sides so user attributes can never
    # collide with them (and Python does not name-mangle them).
    __slots__ = ("__vclass__", "__vattrs__")

    def __init__(self, cls):
        object.__setattr__(self, "__vclass__", cls)
        object.__setattr__(self, "__vattrs__", {})

    def __getattr__(self, name):
        # Only called when normal lookup fails, i.e. for user-defined names.
        attrs = object.__getattribute__(self, "__vattrs__")
        cls = object.__getattribute__(self, "__vclass__")
        member = cls.find_member(name)
        if isinstance(member, property):
            return member.__get__(self, type(self))
        if name in attrs:
            return attrs[name]
        if member is not _MISSING:
            return _bind_class_member(member, self)
        raise AttributeError(f"'{cls.name}' object has no attribute '{name}'")

    def __setattr__(self, name, value):
        cls = object.__getattribute__(self, "__vclass__")
        member = cls.find_member(name)
        if isinstance(member, property):
            member.__set__(self, value)
            return
        object.__getattribute__(self, "__vattrs__")[name] = value

    def __delattr__(self, name):
        cls = object.__getattribute__(self, "__vclass__")
        member = cls.find_member(name)
        if isinstance(member, property):
            member.__delete__(self)
            return
        attrs = object.__getattribute__(self, "__vattrs__")
        try:
            del attrs[name]
        except KeyError:
            raise AttributeError(
                f"'{cls.name}' object has no attribute '{name}'"
            ) from None

    def __enter__(self):
        cls = object.__getattribute__(self, "__vclass__")
        method = cls.find_member("__enter__")
        if not isinstance(method, UserFunction):
            raise AttributeError(f"'{cls.name}' object has no __enter__ method")
        return method(self)

    def __exit__(self, exception_type, exception, traceback):
        cls = object.__getattribute__(self, "__vclass__")
        method = cls.find_member("__exit__")
        if not isinstance(method, UserFunction):
            return False
        return bool(method(self, exception_type, exception, traceback))

    def _call_special(self, method_name):
        cls = object.__getattribute__(self, "__vclass__")
        method = cls.find_member(method_name)
        if isinstance(method, UserFunction):
            return method(self)
        return _MISSING

    def __str__(self):
        result = self._call_special("__str__")
        return self.__repr__() if result is _MISSING else str(result)

    def __repr__(self):
        result = self._call_special("__repr__")
        if result is _MISSING:
            cls = object.__getattribute__(self, "__vclass__")
            return f"<{cls.name} object>"
        return str(result)


def _bind_class_member(member, receiver):
    """Apply VirtoLang's method binding and Python's built-in descriptors."""
    if isinstance(member, property):
        if isinstance(receiver, VirtoClass):
            return member
        return member.__get__(receiver, type(receiver))
    if isinstance(member, (staticmethod, classmethod)):
        if isinstance(member, staticmethod):
            return member.__get__(receiver, type(receiver))
        if isinstance(receiver, VirtoClass):
            if isinstance(member.__func__, UserFunction):
                return BoundMethod(member.__func__, receiver)
            return member.__get__(None, type(receiver))
        return member.__get__(receiver, type(receiver))
    if isinstance(member, UserFunction):
        if isinstance(receiver, VirtoInstance):
            return BoundMethod(member, receiver)
        return member
    return member


# ---------------------------------------------------------------------------
# The interpreter
# ---------------------------------------------------------------------------


class Interpreter:
    """Executes VirtoLang source code.

    Typical use::

        interpreter = Interpreter('print(1 + 2)', filename="demo.vlang")
        interpreter.run()

    The same interpreter object can be fed more code with ``load`` /
    ``run_repl_line``; variables and functions persist between calls, which is
    how the interactive REPL works.

    Attributes:
        source: The source text most recently loaded.
        filename: Name shown in error messages.
        error_location: ``(line, column)`` of the node being evaluated when an
            error was raised, or ``None``.  Used to draw the caret in errors.
        globals: The global ``Scope``.
        scope: The scope code is currently executing in.
    """

    def __init__(self, code="", filename="<string>"):
        self.source = code
        self.filename = filename
        self.error_location = None
        self.lexer = None
        self.parser = None
        # id(node) -> (line, column), filled in by the parser.
        self.node_locations = {}
        # Cache of f-strings already split into literal text and fields.
        self._fstring_cache = {}

        initial = dict(lexer._functable_)
        initial["Error"] = Exception
        self.globals = Scope(initial=initial)
        self.scope = self.globals
        # The fiber (generator / async body) currently running, if any.
        self._fiber = None

        # Node tag -> method that evaluates that kind of node.
        self._dispatch = {
            "BLOCK": self._eval_block,
            "VAR": self._eval_var,
            "ATTR": self._eval_attr,
            "INDEX": self._eval_index,
            "SLICE": self._eval_slice,
            "LIST": self._eval_list,
            "LIST_S": self._eval_list_spread,
            "TUPLE": self._eval_tuple,
            "TUPLE_S": self._eval_tuple_spread,
            "DICT": self._eval_dict,
            "DICT_S": self._eval_dict_spread,
            "SET": self._eval_set,
            "SET_S": self._eval_set_spread,
            "GENEXP": self._eval_genexp,
            "YIELD": self._eval_yield,
            "YIELDFROM": self._eval_yield_from,
            "AWAIT": self._eval_await,
            "WALRUS": self._eval_walrus,
            "DECORATED": self._eval_decorated,
            "GLOBAL": self._eval_global,
            "NONLOCAL": self._eval_nonlocal,
            "PASS": lambda node: None,
            "ASSERT": self._eval_assert,
            "DEL": self._eval_del,
            "ASYNCFOR": self._eval_async_for,
            "ASYNCWITH": self._eval_async_with,
            "CALL_S": self._eval_call_spread,
            "LISTCOMP": self._eval_listcomp,
            "SETCOMP": self._eval_setcomp,
            "DICTCOMP": self._eval_dictcomp,
            "LAMBDA": self._eval_lambda,
            "CONDITIONAL": self._eval_conditional,
            "FUNCDEF": self._eval_funcdef,
            "RETURN": self._eval_return,
            "BREAK": lambda node: _BREAK,
            "CONTINUE": lambda node: _CONTINUE,
            "FOR": self._eval_for,
            "WHILE": self._eval_while,
            "IF": self._eval_if,
            "IMPORT": self._eval_import,
            "FROMIMPORT": self._eval_from_import,
            "ASSIGN_LHS": self._eval_assign,
            "AUGASSIGN": self._eval_augassign,
            "CLASS": self._eval_class,
            "TRY": self._eval_try,
            "WITH": self._eval_with,
            "FSTRING": self._eval_fstring,
            "REGEX": self._eval_regex,
            "RAISE": self._eval_raise,
            "UNARY": self._eval_unary,
            "NOT": self._eval_not,
            "AND": self._eval_and,
            "OR": self._eval_or,
            "CALL": self._eval_call,
            "COMPARE": self._eval_compare,
            "CMPCHAIN": self._eval_compare_chain,
        }
        for symbol in _BINARY_OPERATORS:
            self._dispatch[symbol] = self._eval_binary

        # id(node) -> (node, closure); holding the node keeps its id unique.
        self._compiled = {}
        self._compile_loc = None
        # Node tag -> method building that node's closure (see _compile).
        self._compilers = {
            "BLOCK": self._compile_block,
            "VAR": self._compile_var,
            "COMPARE": self._compile_compare,
            "UNARY": self._compile_unary,
            "NOT": self._compile_not,
            "AND": self._compile_and,
            "OR": self._compile_or,
            "CONDITIONAL": self._compile_conditional,
            "IF": self._compile_if,
            "WHILE": self._compile_while,
            "FOR": self._compile_for,
            "RETURN": self._compile_return,
            "ASSIGN_LHS": self._compile_assign,
            "AUGASSIGN": self._compile_augassign,
            "ATTR": self._compile_attr,
            "INDEX": self._compile_index,
            "LIST": self._compile_list,
            "TUPLE": self._compile_tuple,
            "DICT": self._compile_dict,
            "CALL": self._compile_call,
            "BREAK": lambda node, loc: (lambda: _BREAK),
            "CONTINUE": lambda node, loc: (lambda: _CONTINUE),
        }

    @property
    def variables(self):
        """The global variables as a plain dict (convenient for embedding)."""
        return self.globals.vars

    # ------------------------------------------------------------------
    # Loading and running source code
    # ------------------------------------------------------------------

    def load(self, code=None):
        """Lex and parse ``code`` (default: the code given at construction).

        Returns the list of top-level statement nodes.  Raises ``SyntaxError``
        (with a ``vlang_location`` attribute) for invalid source.
        """
        if code is None:
            code = self.source
        self.source = code
        self.lexer = Lexer(code)
        tokens = self.lexer.tokenize()
        self.parser = Parser(tokens, self.lexer.locations, self.lexer._location(len(code)))
        statements = self.parser.parse_program()
        self.node_locations = self.parser.node_locations
        return statements

    def check(self, code=None):
        """Parse the code without running it (used by ``vlang --check``)."""
        self.load(code)

    def run(self):
        """Run the source given at construction.

        Like a calculator, the value of the program's final statement is
        printed if it is not ``None``.
        """
        statements = self.load()
        node = statements[0] if len(statements) == 1 else ("BLOCK", statements)
        result = self.evaluate(node)
        if result is not None and not isinstance(result, _ControlSignal):
            print(result)

    def run_repl_line(self, code):
        """Run one chunk of interactive input and return the values to echo.

        Only expression statements that produce a value other than ``None``
        are returned, mirroring Python's REPL (assignments, loops and
        function calls returning ``None`` echo nothing).
        """
        self.error_location = None
        echoed = []
        for statement in self.load(code):
            result = self.evaluate(statement)
            is_expression = not (
                isinstance(statement, tuple) and statement[0] in STATEMENT_TAGS
            )
            if is_expression and result is not None and not isinstance(
                result, _ControlSignal
            ):
                echoed.append(result)
        return echoed

    # ------------------------------------------------------------------
    # Core evaluation
    # ------------------------------------------------------------------

    def evaluate(self, node):
        """Evaluate one AST node and return its value.

        Literals (numbers, strings, ``None``...) evaluate to themselves.  Any
        other node is compiled once into a Python closure (see the "Closure
        compiler" section below); later evaluations of the same node just call
        that closure, which is much faster than walking the tree each time.
        """
        if node.__class__ is tuple:
            entry = self._compiled.get(id(node))
            if entry is None:
                entry = self._compiled[id(node)] = (node, self._compile(node))
            return entry[1]()
        if node is None or isinstance(node, (int, float, str, bytes)):
            return node
        raise ValueError(f"Invalid node: {node}")

    # ------------------------------------------------------------------
    # Closure compiler
    # ------------------------------------------------------------------
    #
    # Each hot node kind is turned into a zero-argument Python function that
    # already knows its children (as closures), operator and source location.
    # Running it needs no dispatch-table lookups.  Kinds without a dedicated
    # compiler fall back to their ``_eval_*`` method (``_compile_generic``).
    #
    # Error locations: a closure records its node's location in
    # ``self.error_location`` just before the operation that can fail, so a
    # failure is reported at the innermost node (like the tree walker did).

    def _child(self, node):
        """Return a zero-argument closure that evaluates ``node``."""
        if node.__class__ is tuple:
            entry = self._compiled.get(id(node))
            if entry is None:
                entry = self._compiled[id(node)] = (node, self._compile(node))
            return entry[1]
        if node is None or isinstance(node, (int, float, str, bytes)):
            return lambda: node
        raise ValueError(f"Invalid node: {node}")

    def _compile(self, node):
        """Build the closure for one tuple node."""
        tag = node[0]
        # Nodes the parser did not mark inherit the location of their parent.
        loc = (
            self.node_locations.get(id(node))
            or self._compile_loc
            or self.error_location
        )
        maker = self._compilers.get(tag)
        if maker is None and tag in _BINARY_OPERATORS:
            maker = self._compile_binary
        if maker is None or loc is None:
            return self._compile_generic(node, loc)
        outer = self._compile_loc
        self._compile_loc = loc
        try:
            return maker(node, loc)
        finally:
            self._compile_loc = outer

    def _compile_generic(self, node, loc):
        """Fallback: run the node's ``_eval_*`` method with location tracking."""
        handler = self._dispatch.get(node[0])
        if handler is None:

            def invalid():
                raise ValueError(f"Invalid node: {node}")

            return invalid
        interp = self

        def generic():
            previous = interp.error_location
            if loc is not None:
                interp.error_location = loc
            result = handler(node)
            interp.error_location = previous
            return result

        return generic

    def _compile_var(self, node, loc):
        name = node[1]
        interp = self
        builtin_names = lexer._builtins_

        def var():
            scope = interp.scope
            while scope is not None:
                variables = scope.vars
                if name in variables:
                    return variables[name]
                scope = scope.parent
            try:
                return builtin_names[name]
            except KeyError:
                interp.error_location = loc
                raise NameError(f"name {name!r} is not defined") from None

        return var

    def _compile_block(self, node, loc):
        statements = [self._child(statement) for statement in node[1]]
        if not statements:
            return lambda: None
        if len(statements) == 1:
            return statements[0]
        signals = _SIGNAL_CLASSES

        def block():
            result = None
            for statement in statements:
                result = statement()
                if result.__class__ in signals:
                    return result
            return result

        return block

    def _compile_operation(self, operation, left_node, right_node, loc):
        """Closure for ``left <operation> right`` (arithmetic and comparisons)."""
        left = self._child(left_node)
        interp = self
        if right_node.__class__ is not tuple:
            constant = right_node

            def operation_with_constant():
                a = left()
                try:
                    return operation(a, constant)
                except Exception:
                    interp.error_location = loc
                    raise

            return operation_with_constant
        right = self._child(right_node)

        def operation_closure():
            a = left()
            b = right()
            try:
                return operation(a, b)
            except Exception:
                interp.error_location = loc
                raise

        return operation_closure

    def _compile_binary(self, node, loc):
        return self._compile_operation(_BINARY_OPERATORS[node[0]], node[1], node[2], loc)

    def _compile_compare(self, node, loc):
        _, symbol, left, right = node
        if symbol == "is":
            operation = operator.is_
        elif symbol == "is not":
            operation = operator.is_not
        else:
            operation = _COMPARE_OPERATORS[symbol]
        return self._compile_operation(operation, left, right, loc)

    def _compile_unary(self, node, loc):
        operation = _UNARY_OPERATORS[node[1]]
        operand = self._child(node[2])
        interp = self

        def unary():
            value = operand()
            try:
                return operation(value)
            except Exception:
                interp.error_location = loc
                raise

        return unary

    def _compile_not(self, node, loc):
        operand = self._child(node[1])
        return lambda: not operand()

    def _compile_and(self, node, loc):
        left = self._child(node[1])
        right = self._child(node[2])

        def and_():
            value = left()
            if not value:
                return value
            return right()

        return and_

    def _compile_or(self, node, loc):
        left = self._child(node[1])
        right = self._child(node[2])

        def or_():
            value = left()
            if value:
                return value
            return right()

        return or_

    def _compile_conditional(self, node, loc):
        _, condition, value, fallback = node
        condition = self._child(condition)
        value = self._child(value)
        fallback = self._child(fallback)
        return lambda: value() if condition() else fallback()

    def _compile_if(self, node, loc):
        _, condition, then_block, else_block = node
        condition = self._child(condition)
        then_block = self._child(then_block)
        if else_block is None:

            def if_():
                if condition():
                    return then_block()
                return None

            return if_
        else_block = self._child(else_block)

        def if_else():
            if condition():
                return then_block()
            return else_block()

        return if_else

    def _compile_while(self, node, loc):
        condition = self._child(node[1])
        body = self._child(node[2])

        def while_():
            result = None
            while condition():
                outcome = body()
                if outcome is _BREAK:
                    break
                if outcome is _CONTINUE:
                    continue
                if outcome.__class__ is _ReturnSignal:
                    return outcome
                result = outcome
            return result

        return while_

    def _compile_for(self, node, loc):
        _, target, iterable_node, block = node
        iterable_closure = self._child(iterable_node)
        body = self._child(block)
        interp = self
        single_target = isinstance(target, str)

        def for_():
            iterable = iterable_closure()
            interp.error_location = loc
            scope = interp.scope
            variables = scope.vars
            direct = single_target and scope.redirects is None
            result = None
            for item in iterable:
                if direct:
                    variables[target] = item
                else:
                    interp._bind_loop_target(target, item)
                outcome = body()
                if outcome is _BREAK:
                    break
                if outcome is _CONTINUE:
                    continue
                if outcome.__class__ is _ReturnSignal:
                    return outcome
                result = outcome
            return result

        return for_

    def _compile_return(self, node, loc):
        value = self._child(node[1])
        return lambda: _ReturnSignal(value())

    def _compile_assign(self, node, loc):
        _, target, expression = node
        value_closure = self._child(expression)
        interp = self
        kind = target[0]
        if kind == "VAR":
            name = target[1]

            def assign_var():
                value = value_closure()
                scope = interp.scope
                if scope.redirects is None:
                    scope.vars[name] = value
                else:
                    interp._store(name, value)

            return assign_var
        if kind == "ATTR":
            obj_closure = self._child(target[1])
            attribute = target[2]

            def assign_attribute():
                value = value_closure()
                obj = obj_closure()
                interp.error_location = loc
                setattr(obj, attribute, value)

            return assign_attribute
        if kind == "INDEX":
            container_closure = self._child(target[1])
            index_closure = self._child(target[2])

            def assign_index():
                value = value_closure()
                container = container_closure()
                index = index_closure()
                interp.error_location = loc
                container[index] = value

            return assign_index
        return self._compile_generic(node, loc)

    def _compile_augassign(self, node, loc):
        _, op_text, target, expression = node
        apply = _AUGMENTED_OPERATORS.get(op_text)
        kind = target[0]
        if apply is None or kind not in ("VAR", "ATTR", "INDEX"):
            return self._compile_generic(node, loc)
        rhs_closure = self._child(expression)
        interp = self
        if kind == "VAR":
            name = target[1]

            def augment_var():
                rhs = rhs_closure()
                scope = interp.scope
                variables = scope.vars
                if name in variables:
                    current = variables[name]
                else:
                    interp.error_location = loc
                    current = interp._lookup(name)
                try:
                    new_value = apply(current, rhs)
                except Exception:
                    interp.error_location = loc
                    raise
                if scope.redirects is None:
                    variables[name] = new_value
                else:
                    interp._store(name, new_value)

            return augment_var
        if kind == "ATTR":
            obj_closure = self._child(target[1])
            attribute = target[2]

            def augment_attribute():
                rhs = rhs_closure()
                obj = obj_closure()
                interp.error_location = loc
                setattr(obj, attribute, apply(getattr(obj, attribute), rhs))

            return augment_attribute
        container_closure = self._child(target[1])
        index_closure = self._child(target[2])

        def augment_index():
            rhs = rhs_closure()
            container = container_closure()
            index = index_closure()
            interp.error_location = loc
            container[index] = apply(container[index], rhs)

        return augment_index

    def _compile_attr(self, node, loc):
        obj_closure = self._child(node[1])
        name = node[2]
        interp = self

        def attribute():
            obj = obj_closure()
            interp.error_location = loc
            try:
                return getattr(obj, name)
            except AttributeError:
                # Convenience: ``config.key`` also reads ``config["key"]`` on dicts.
                if obj.__class__ is dict and name in obj:
                    return obj[name]
                if isinstance(obj, dict) and name in obj:
                    return obj[name]
                raise

        return attribute

    def _compile_index(self, node, loc):
        container_closure = self._child(node[1])
        index_closure = self._child(node[2])
        interp = self

        def index():
            container = container_closure()
            key = index_closure()
            interp.error_location = loc
            return container[key]

        return index

    def _compile_list(self, node, loc):
        items = [self._child(item) for item in node[1]]
        return lambda: [item() for item in items]

    def _compile_tuple(self, node, loc):
        items = [self._child(item) for item in node[1]]
        return lambda: tuple([item() for item in items])

    def _compile_dict(self, node, loc):
        pairs = [(self._child(k), self._child(v)) for k, v in node[1]]
        return lambda: {key(): value() for key, value in pairs}

    def _compile_call(self, node, loc):
        _, func_node, arg_nodes, kwarg_nodes = node
        func_closure = self._child(func_node)
        arg_closures = [self._child(arg) for arg in arg_nodes]
        kwarg_closures = [(name, self._child(value)) for name, value in kwarg_nodes]
        interp = self
        call_user_function = self.call_user_function
        super_builtin = lexer._builtins_.get("super")

        def invoke(func, args, kwargs):
            interp.error_location = loc
            if func.__class__ is UserFunction:
                return call_user_function(func, args, kwargs)
            if func.__class__ is BoundMethod:
                return call_user_function(
                    func.function, [func.instance, *args], kwargs
                )
            if func is super_builtin and not args and not kwargs:
                function = interp.scope.function
                if function is not None and function.defining_class is not None:
                    receiver = interp.scope.vars.get(
                        function.params[0] if function.params else None, _MISSING
                    )
                    if receiver is not _MISSING:
                        return VirtoSuper(function.defining_class, receiver)
                return func()
            if not callable(func):
                raise TypeError(f"'{type(func).__name__}' object is not callable")
            if kwargs:
                return func(*args, **kwargs)
            return func(*args)

        count = len(arg_closures)
        if kwarg_closures:

            def call_with_keywords():
                func = func_closure()
                args = [arg() for arg in arg_closures]
                kwargs = {name: value() for name, value in kwarg_closures}
                return invoke(func, args, kwargs)

            return call_with_keywords
        if count == 0:
            return lambda: invoke(func_closure(), [], None)
        if count == 1:
            only = arg_closures[0]

            def call_one():
                func = func_closure()
                return invoke(func, [only()], None)

            return call_one
        if count == 2:
            first, second = arg_closures

            def call_two():
                func = func_closure()
                a = first()
                return invoke(func, [a, second()], None)

            return call_two

        def call_many():
            func = func_closure()
            return invoke(func, [arg() for arg in arg_closures], None)

        return call_many

    def _lookup(self, name):
        """Resolve a variable name through the scope chain, then the builtins."""
        scope = self.scope
        while scope is not None:
            variables = scope.vars
            if name in variables:
                return variables[name]
            scope = scope.parent
        try:
            return lexer._builtins_[name]
        except KeyError:
            raise NameError(f"name {name!r} is not defined") from None

    # ------------------------------------------------------------------
    # Names, attributes and indexing
    # ------------------------------------------------------------------

    def _eval_var(self, node):
        return self._lookup(node[1])

    def _eval_attr(self, node):
        obj = self.evaluate(node[1])
        name = node[2]
        try:
            return getattr(obj, name)
        except AttributeError:
            # Convenience: ``config.key`` also reads ``config["key"]`` on dicts.
            if isinstance(obj, dict) and name in obj:
                return obj[name]
            raise

    def _eval_index(self, node):
        return self.evaluate(node[1])[self.evaluate(node[2])]

    def _eval_slice(self, node):
        _, lower, upper, step = node
        return slice(
            self.evaluate(lower) if lower is not None else None,
            self.evaluate(upper) if upper is not None else None,
            self.evaluate(step) if step is not None else None,
        )

    # ------------------------------------------------------------------
    # Collection literals
    # ------------------------------------------------------------------

    def _eval_list(self, node):
        return [self.evaluate(item) for item in node[1]]

    def _eval_tuple(self, node):
        return tuple(self.evaluate(item) for item in node[1])

    def _eval_dict(self, node):
        return {self.evaluate(key): self.evaluate(value) for key, value in node[1]}

    def _eval_set(self, node):
        """Evaluate a set literal, removing duplicate values."""
        return {self.evaluate(item) for item in node[1]}

    # --- spreads (*items / **mapping) and generator expressions -----------

    def _spread_items(self, items):
        """Evaluate items, expanding every ``("STAR", expr)`` in place."""
        result = []
        for item in items:
            if item.__class__ is tuple and item[0] == "STAR":
                result.extend(self.evaluate(item[1]))
            else:
                result.append(self.evaluate(item))
        return result

    def _eval_list_spread(self, node):
        return self._spread_items(node[1])

    def _eval_tuple_spread(self, node):
        return tuple(self._spread_items(node[1]))

    def _eval_set_spread(self, node):
        return set(self._spread_items(node[1]))

    def _eval_dict_spread(self, node):
        result = {}
        for key, value in node[1]:
            if key is None:
                result.update(self.evaluate(value))
            else:
                result[self.evaluate(key)] = self.evaluate(value)
        return result

    def _eval_genexp(self, node):
        """A lazy generator expression: items are computed as they are consumed."""
        _, expression, clauses = node
        scope = Scope(self.scope)
        first_iterable = iter(self.evaluate(clauses[0][1]))

        def in_scope(subnode):
            saved = self.scope
            self.scope = scope
            try:
                return self.evaluate(subnode)
            finally:
                self.scope = saved

        def visit(index, iterable):
            target, iterable_node, filters = clauses[index]
            for item in iterable:
                if isinstance(target, str):
                    scope.vars[target] = item
                else:
                    values = list(item)
                    if len(values) != len(target):
                        raise ValueError(
                            f"cannot unpack {len(values)} value(s) into "
                            f"{len(target)} name(s)"
                        )
                    scope.vars.update(zip(target, values))
                if not all(in_scope(condition) for condition in filters):
                    continue
                if index + 1 == len(clauses):
                    yield in_scope(expression)
                else:
                    yield from visit(index + 1, iter(in_scope(clauses[index + 1][1])))

        return visit(0, first_iterable)

    # --- yield / await ------------------------------------------------------

    def _eval_yield(self, node):
        fiber = self._fiber
        if fiber is None or (fiber.is_async and not fiber.is_async_generator):
            raise SyntaxError("'yield' outside a generator function")
        value = self.evaluate(node[1]) if node[1] is not None else None
        return fiber.suspend(
            "async_yield" if fiber.is_async_generator else "yield", value
        )

    def _eval_yield_from(self, node):
        """``yield from items``: re-yield everything; evaluates to the sub-generator's return value."""
        fiber = self._fiber
        if fiber is None or fiber.is_async:
            raise SyntaxError("'yield from' outside a generator function")
        iterator = iter(self.evaluate(node[1]))
        while True:
            try:
                item = next(iterator)
            except StopIteration as stop:
                return stop.value
            fiber.suspend("yield", item)

    def _await(self, awaitable):
        """Wait for ``awaitable``.

        Inside an ``async def`` this pauses only the current task so others
        can run.  At the top level of a program it simply runs the awaitable
        to completion on a temporary event loop.
        """
        fiber = self._fiber
        if fiber is not None and fiber.is_async:
            return fiber.suspend("await", awaitable)

        async def wait():
            return await awaitable

        return asyncio.run(wait())

    def _eval_await(self, node):
        return self._await(self.evaluate(node[1]))

    def _bind_loop_target(self, target, item):
        """Assign one loop item to a name or tuple of names."""
        if isinstance(target, str):
            self._store(target, item)
            return
        values = list(item)
        if len(values) != len(target):
            raise ValueError(
                f"cannot unpack {len(values)} value(s) into {len(target)} name(s)"
            )
        for name, element in zip(target, values):
            self._store(name, element)

    def _eval_async_for(self, node):
        """``async for item in source { }``: awaits each step of an async iterator."""
        _, target, iterable_node, block = node
        source = self.evaluate(iterable_node)
        iterator = source.__aiter__()
        result = None
        while True:
            try:
                item = self._await(iterator.__anext__())
            except StopAsyncIteration:
                break
            self._bind_loop_target(target, item)
            outcome = self.evaluate(block)
            if outcome is _BREAK:
                break
            if outcome is _CONTINUE:
                continue
            if outcome.__class__ is _ReturnSignal:
                return outcome
            result = outcome
        return result

    def _eval_async_with(self, node):
        """``async with manager as name { }`` using ``__aenter__``/``__aexit__``."""
        _, managers, body = node
        entered = []
        pending = None
        result = None
        try:
            for expression, target in managers:
                manager = self.evaluate(expression)
                value = self._await(manager.__aenter__())
                entered.append(manager)
                if target is not None:
                    self._store(target, value)
            result = self.evaluate(body)
        except BaseException as error:
            pending = error
        for manager in reversed(entered):
            if pending is None:
                self._await(manager.__aexit__(None, None, None))
            elif self._await(
                manager.__aexit__(type(pending), pending, pending.__traceback__)
            ):
                pending = None
        if pending is not None:
            raise pending
        return result

    def _eval_comprehension(self, clauses, append_value):
        """Evaluate shared ``for``/``if`` clauses for collection comprehensions."""
        saved_scope = self.scope
        self.scope = Scope(saved_scope)

        def visit(index):
            if index == len(clauses):
                append_value()
                return

            target, iterable_node, filters = clauses[index]
            for item in self.evaluate(iterable_node):
                if isinstance(target, str):
                    self.scope.vars[target] = item
                else:
                    values = list(item)
                    if len(values) != len(target):
                        raise ValueError(
                            f"cannot unpack {len(values)} value(s) into "
                            f"{len(target)} name(s)"
                        )
                    self.scope.vars.update(zip(target, values))
                if all(self.evaluate(condition) for condition in filters):
                    visit(index + 1)

        try:
            visit(0)
        finally:
            self.scope = saved_scope

    def _eval_listcomp(self, node):
        """Evaluate a list comprehension into a new list."""
        _, expression, clauses = node
        result = []
        self._eval_comprehension(clauses, lambda: result.append(self.evaluate(expression)))
        return result

    def _eval_setcomp(self, node):
        """Evaluate a set comprehension into a new set."""
        _, expression, clauses = node
        result = set()
        self._eval_comprehension(clauses, lambda: result.add(self.evaluate(expression)))
        return result

    def _eval_dictcomp(self, node):
        """Evaluate a dictionary comprehension into a new dictionary."""
        _, key_node, value_node, clauses = node
        result = {}

        def add_pair():
            result[self.evaluate(key_node)] = self.evaluate(value_node)

        self._eval_comprehension(clauses, add_pair)
        return result

    # ------------------------------------------------------------------
    # Blocks and control flow
    # ------------------------------------------------------------------

    def _eval_block(self, node):
        """Run statements in order; stop early if one returns/breaks/continues."""
        result = None
        for statement in node[1]:
            result = self.evaluate(statement)
            if isinstance(result, _ControlSignal):
                return result
        return result

    def _eval_if(self, node):
        _, condition, then_block, else_block = node
        if self.evaluate(condition):
            return self.evaluate(then_block)
        if else_block is not None:
            return self.evaluate(else_block)
        return None

    def _eval_while(self, node):
        _, condition, block = node
        result = None
        while self.evaluate(condition):
            outcome = self.evaluate(block)
            if outcome is _BREAK:
                break
            if outcome is _CONTINUE:
                continue
            if outcome.__class__ is _ReturnSignal:
                return outcome
            result = outcome
        return result

    def _eval_for(self, node):
        _, target, iterable_node, block = node
        iterable = self.evaluate(iterable_node)
        scope = self.scope
        variables = scope.vars
        direct = scope.redirects is None
        single_target = isinstance(target, str)
        result = None
        for item in iterable:
            if single_target:
                if direct:
                    variables[target] = item
                else:
                    self._store(target, item)
            else:
                values = list(item)
                if len(values) != len(target):
                    raise ValueError(
                        f"cannot unpack {len(values)} value(s) into {len(target)} name(s)"
                    )
                for name, element in zip(target, values):
                    self._store(name, element)
            outcome = self.evaluate(block)
            if outcome is _BREAK:
                break
            if outcome is _CONTINUE:
                continue
            if outcome.__class__ is _ReturnSignal:
                return outcome
            result = outcome
        return result

    def _eval_return(self, node):
        return _ReturnSignal(self.evaluate(node[1]))

    def _eval_try(self, node):
        """``try`` / ``except`` / ``finally``.

        The try body runs first.  If it raises, handlers are checked in order
        and the first one whose type matches runs (a handler with no type
        matches everything).  ``finally`` always runs afterwards; an error
        that no handler caught is re-raised once it finishes.
        """
        _, try_block, handlers, finally_block = node
        pending_error = None
        result = None
        try:
            try:
                result = self.evaluate(try_block)
            except Exception as error:
                for type_node, alias, handler_block in handlers:
                    if type_node is not None:
                        exception_type = self.evaluate(type_node)
                        if not isinstance(exception_type, type) or not issubclass(
                            exception_type, BaseException
                        ):
                            raise TypeError("except clause must name an exception class")
                        if not isinstance(error, exception_type):
                            continue
                    result = self._run_handler(alias, error, handler_block)
                    break
                else:
                    raise
        except BaseException as error:
            pending_error = error

        if finally_block is not None:
            finally_result = self.evaluate(finally_block)
            if isinstance(finally_result, _ControlSignal):
                return finally_result
        if pending_error is not None:
            raise pending_error
        return result

    def _eval_with(self, node):
        """Enter context managers in order and always exit them in reverse order."""
        _, managers, body = node
        with ExitStack() as stack:
            for expression, target in managers:
                value = stack.enter_context(self.evaluate(expression))
                if target is not None:
                    self._store(target, value)
            return self.evaluate(body)

    def _run_handler(self, alias, error, block):
        """Run an ``except`` block with ``alias`` temporarily bound to ``error``."""
        variables = self.scope.vars
        previous = variables.get(alias, _MISSING) if alias else _MISSING
        if alias:
            variables[alias] = error
        try:
            return self.evaluate(block)
        finally:
            if alias:
                if previous is _MISSING:
                    variables.pop(alias, None)
                else:
                    variables[alias] = previous

    def _eval_decorated(self, node):
        """``@decorator`` above a ``def``/``class``: define it, then wrap it."""
        _, decorators, definition = node
        wrappers = [self.evaluate(decorator) for decorator in decorators]
        self.evaluate(definition)
        name = definition[1]
        value = self._lookup(name)
        for wrapper in reversed(wrappers):
            value = wrapper(value)
        self._store(name, value)
        return None

    def _eval_global(self, node):
        """``global x``: assignments to ``x`` in this scope change the global."""
        scope = self.scope
        if scope is not self.globals:
            if scope.redirects is None:
                scope.redirects = {}
            for name in node[1]:
                scope.redirects[name] = self.globals
        return None

    def _eval_nonlocal(self, node):
        """``nonlocal x``: assignments change ``x`` in the nearest enclosing function."""
        scope = self.scope
        for name in node[1]:
            owner = scope.parent
            while owner is not None and owner is not self.globals and name not in owner.vars:
                owner = owner.parent
            if owner is None or owner is self.globals:
                raise SyntaxError(f"no binding for nonlocal {name!r} found")
            if scope.redirects is None:
                scope.redirects = {}
            scope.redirects[name] = owner
        return None

    def _eval_assert(self, node):
        _, condition, message = node
        if not self.evaluate(condition):
            if message is None:
                raise AssertionError()
            raise AssertionError(self.evaluate(message))
        return None

    def _eval_del(self, node):
        """``del name`` / ``del items[i]`` / ``del obj.attr``."""
        for target in node[1]:
            kind = target[0]
            if kind == "VAR":
                name = target[1]
                scope = self.scope
                if scope.redirects is not None and name in scope.redirects:
                    scope = scope.redirects[name]
                if name not in scope.vars:
                    raise NameError(f"name {name!r} is not defined")
                del scope.vars[name]
            elif kind == "INDEX":
                del self.evaluate(target[1])[self.evaluate(target[2])]
            else:
                delattr(self.evaluate(target[1]), target[2])
        return None

    def _eval_raise(self, node):
        value = self.evaluate(node[1])
        if isinstance(value, BaseException):
            raise value
        if isinstance(value, type) and issubclass(value, BaseException):
            raise value()
        raise RuntimeError(str(value))

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def _eval_import(self, node):
        _, module_name, alias = node
        module = importlib.import_module(module_name)
        if alias is not None:
            self._store(alias, module)
        else:
            # ``import a.b`` binds the top-level package name ``a``.
            top_level = module_name.split(".")[0]
            self._store(
                top_level,
                module if top_level == module_name else importlib.import_module(top_level),
            )
        return None

    def _eval_from_import(self, node):
        _, module_name, name, alias = node
        module = importlib.import_module(module_name)
        try:
            value = getattr(module, name)
        except AttributeError:
            # ``from package import submodule``
            value = importlib.import_module(f"{module_name}.{name}")
        self._store(alias if alias is not None else name, value)
        return None

    # ------------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------------

    def _eval_assign(self, node):
        """Evaluate an assignment, validating all unpacked values first."""
        _, target, expression = node
        value = self.evaluate(expression)
        if isinstance(target, tuple) and target[0] == "TUPLE":
            for variable, assigned_value in self._unpack_assignment(target, value):
                self._store(variable, assigned_value)
            return None
        self._assign_target(target, value)
        return None

    def _unpack_assignment(self, target, value):
        """Validate and flatten a tuple assignment before changing variables.

        One ``("STAR", name)`` target (``first, *rest = values``) collects the
        values left over by the other targets into a list.
        """
        values = list(value)
        targets = target[1]
        star_index = next(
            (i for i, child in enumerate(targets) if child[0] == "STAR"), None
        )
        if star_index is None:
            if len(values) != len(targets):
                raise ValueError(
                    f"cannot unpack {len(values)} value(s) into {len(targets)} name(s)"
                )
        else:
            if len(values) < len(targets) - 1:
                raise ValueError(
                    f"not enough values to unpack (expected at least "
                    f"{len(targets) - 1}, got {len(values)})"
                )
            after = len(targets) - star_index - 1
            middle_end = len(values) - after
            values = (
                values[:star_index]
                + [values[star_index:middle_end]]
                + values[middle_end:]
            )
            targets = [child[1] if child[0] == "STAR" else child for child in targets]
        assignments = []
        for child, item in zip(targets, values):
            if isinstance(child, tuple) and child[0] == "TUPLE":
                assignments.extend(self._unpack_assignment(child, item))
            elif isinstance(child, tuple) and child[0] == "VAR":
                assignments.append((child[1], item))
            else:
                raise SyntaxError("Only names can be used in unpacking assignment")
        return assignments

    def _assign_target(self, target, value):
        """Assign to one variable, attribute, or indexed collection item."""
        kind = target[0]
        if kind == "VAR":
            scope = self.scope
            if scope.redirects is None:
                scope.vars[target[1]] = value
            else:
                self._store(target[1], value)
        elif kind == "ATTR":
            setattr(self.evaluate(target[1]), target[2], value)
        elif kind == "INDEX":
            container = self.evaluate(target[1])
            container[self.evaluate(target[2])] = value
        else:
            raise ValueError(f"Invalid assignment target: {target}")

    def _eval_walrus(self, node):
        """``name := value`` assigns inside an expression and yields the value."""
        value = self.evaluate(node[2])
        self._store(node[1], value)
        return value

    def _eval_augassign(self, node):
        _, op_text, target, expression = node
        apply = _AUGMENTED_OPERATORS.get(op_text)
        if apply is None:
            raise ValueError(f"Unsupported aug assign: {op_text}")
        rhs = self.evaluate(expression)
        kind = target[0]
        if kind == "VAR":
            name = target[1]
            new_value = apply(self._lookup(name), rhs)
            scope = self.scope
            if scope.redirects is None:
                scope.vars[name] = new_value
            else:
                self._store(name, new_value)
        elif kind == "ATTR":
            obj = self.evaluate(target[1])
            setattr(obj, target[2], apply(getattr(obj, target[2]), rhs))
        elif kind == "INDEX":
            container = self.evaluate(target[1])
            index = self.evaluate(target[2])
            container[index] = apply(container[index], rhs)
        else:
            raise ValueError(f"Invalid aug assignment target: {target}")
        return None

    # ------------------------------------------------------------------
    # Functions and classes
    # ------------------------------------------------------------------

    def _eval_funcdef(self, node):
        _, name, params, body, defaults, extras = node
        # Default values are evaluated once, when the function is defined.
        default_values = {p: self.evaluate(expr) for p, expr in defaults.items()}
        function = UserFunction(
            self, name, params, default_values, body, self.scope, extras
        )
        self._store(name, function)
        return None

    def _eval_lambda(self, node):
        """Create a callable that evaluates the lambda body in its captured scope."""
        _, params, body = node
        return UserFunction(self, "<lambda>", params, {}, body, self.scope)

    def _store(self, name, value):
        """Bind ``name`` in the current scope, honouring ``global``/``nonlocal``."""
        scope = self.scope
        redirects = scope.redirects
        if redirects is not None and name in redirects:
            redirects[name].vars[name] = value
        else:
            scope.vars[name] = value

    def _bind_arguments(self, function, args, kwargs):
        """Match call arguments to parameters for functions using ``*``/``**``."""
        name = function.name
        params = function.params
        kwonly = function.kwonly
        local = {}
        if len(args) > len(params):
            if function.vararg is None:
                raise TypeError(
                    f"{name}() takes {len(params)} positional argument(s) "
                    f"but {len(args)} were given"
                )
            local[function.vararg] = tuple(args[len(params):])
            args = args[: len(params)]
        elif function.vararg is not None:
            local[function.vararg] = ()
        local.update(zip(params, args))
        extra = {}
        if kwargs:
            for key, value in kwargs.items():
                if key in function.posonly:
                    if function.kwarg is not None:
                        extra[key] = value
                        continue
                    raise TypeError(
                        f"{name}() got an unexpected keyword argument {key!r}"
                    )
                if key in params or key in kwonly:
                    if key in local:
                        raise TypeError(
                            f"{name}() got multiple values for argument {key!r}"
                        )
                    local[key] = value
                elif function.kwarg is not None:
                    extra[key] = value
                else:
                    raise TypeError(
                        f"{name}() got an unexpected keyword argument {key!r}"
                    )
        if function.kwarg is not None:
            local[function.kwarg] = extra
        for param in (*params, *kwonly):
            if param not in local:
                if param in function.defaults:
                    local[param] = function.defaults[param]
                elif param in kwonly:
                    raise TypeError(
                        f"{name}() missing required keyword-only argument: {param!r}"
                    )
                else:
                    raise TypeError(f"{name}() missing required argument: {param!r}")
        return local

    def _run_body(self, function, local):
        """Execute a function body in a fresh scope and return its result."""
        saved_scope = self.scope
        self.scope = Scope(function.closure, local, function)
        body = function.body_fn
        if body is None:
            body = function.body_fn = self._child(function.body)
        try:
            result = body()
        finally:
            self.scope = saved_scope
        if result.__class__ is _ReturnSignal:
            return result.value
        if result is _BREAK or result is _CONTINUE:
            keyword = "break" if result is _BREAK else "continue"
            raise SyntaxError(f"'{keyword}' outside loop")
        return result

    def _make_coroutine(self, function, local):
        """Wrap an ``async def`` call as a real Python coroutine.

        The body runs in a fiber; every ``await`` inside it pauses the fiber,
        and this coroutine awaits the same object on the asyncio event loop.
        """
        fiber = _Fiber(self, lambda: self._run_body(function, local), is_async=True)

        async def run_async_function():
            fiber.loop = asyncio.get_running_loop()
            value = error = None
            while True:
                kind, payload = fiber.resume(value, error)
                if kind == "return":
                    return payload
                value = error = None
                try:
                    value = await payload
                except BaseException as caught:
                    error = caught

        coroutine = run_async_function()
        coroutine.__name__ = function.name
        return coroutine

    def call_user_function(self, function, args, kwargs=None):
        """Call a ``UserFunction`` with positional ``args`` and keyword ``kwargs``.

        A fresh ``Scope`` (child of the function's defining scope) holds the
        parameters.  The value of a ``return`` statement is the result; with no
        ``return`` the value of the last statement is used.  Generator
        functions return a ``VirtoGenerator`` and async functions return a
        coroutine instead of running the body immediately.
        """
        if function.special:
            local = self._bind_arguments(function, args, kwargs)
            if function.is_async_generator:
                return VirtoAsyncGenerator(self, function, local)
            if function.is_generator:
                return VirtoGenerator(self, function, local)
            if function.is_async:
                return self._make_coroutine(function, local)
            return self._run_body(function, local)

        params = function.params
        if len(args) > len(params):
            raise TypeError(
                f"{function.name}() takes {len(params)} argument(s) "
                f"but {len(args)} were given"
            )
        local = dict(zip(params, args))
        if kwargs:
            for key, value in kwargs.items():
                if key not in params:
                    raise TypeError(
                        f"{function.name}() got an unexpected keyword argument {key!r}"
                    )
                if key in local:
                    raise TypeError(
                        f"{function.name}() got multiple values for argument {key!r}"
                    )
                local[key] = value
        if len(local) < len(params):
            for param in params:
                if param not in local:
                    if param not in function.defaults:
                        raise TypeError(
                            f"{function.name}() missing required argument: {param!r}"
                        )
                    local[param] = function.defaults[param]

        saved_scope = self.scope
        self.scope = Scope(function.closure, local, function)
        body = function.body_fn
        if body is None:
            body = function.body_fn = self._child(function.body)
        try:
            result = body()
        finally:
            self.scope = saved_scope
        if result.__class__ is _ReturnSignal:
            return result.value
        if result is _BREAK or result is _CONTINUE:
            keyword = "break" if result is _BREAK else "continue"
            raise SyntaxError(f"'{keyword}' outside loop")
        return result

    def _eval_class(self, node):
        _, class_name, body, base_names = node

        # Run the class body in its own scope; whatever it defines becomes a member.
        class_scope = Scope(self.scope)
        saved_scope = self.scope
        self.scope = class_scope
        try:
            self.evaluate(body)
        finally:
            self.scope = saved_scope
        members = class_scope.vars

        user_bases = []
        python_bases = []
        for base_name in base_names:
            base = self._lookup(base_name)
            if isinstance(base, VirtoClass):
                user_bases.append(base)
            elif isinstance(base, type):
                python_bases.append(base)
            else:
                raise TypeError(f"Base class {base_name!r} is not a class")

        if any(issubclass(base, BaseException) for base in python_bases):
            if user_bases:
                raise TypeError("Cannot mix VirtoLang classes with Python exception classes")
            self._store(
                class_name, self._make_exception_class(class_name, python_bases, members)
            )
        else:
            cls = VirtoClass(class_name, members, user_bases)
            for member in members.values():
                if isinstance(member, UserFunction):
                    member.defining_class = cls
                elif isinstance(member, (staticmethod, classmethod)):
                    function = member.__func__
                    if isinstance(function, UserFunction):
                        function.defining_class = cls
                elif isinstance(member, property):
                    for function in (member.fget, member.fset, member.fdel):
                        if isinstance(function, UserFunction):
                            function.defining_class = cls
            self._store(class_name, cls)
        return None

    def _make_exception_class(self, class_name, bases, members):
        """Build a real Python exception subclass from a VirtoLang class body.

        Exceptions must be genuine Python classes to be raised and caught, so
        the VirtoLang methods are wrapped as ordinary Python functions.
        """
        namespace = {"__module__": "__main__"}
        if "__init__" not in members:
            namespace["__init__"] = lambda instance, *args: Exception.__init__(
                instance, *args
            )
        for name, member in members.items():
            if isinstance(member, UserFunction):
                namespace[name] = self._wrap_method(member)
            else:
                namespace[name] = member
        return type(class_name, tuple(bases), namespace)

    @staticmethod
    def _wrap_method(function):
        def method(instance, *args, **kwargs):
            return function(instance, *args, **kwargs)

        method.__name__ = function.name
        return method

    # ------------------------------------------------------------------
    # Calls
    # ------------------------------------------------------------------

    def _eval_call(self, node):
        _, func_node, arg_nodes, kwarg_nodes = node
        func = self.evaluate(func_node)
        args = [self.evaluate(arg) for arg in arg_nodes]
        kwargs = (
            {name: self.evaluate(value) for name, value in kwarg_nodes}
            if kwarg_nodes
            else None
        )
        if func is lexer._builtins_.get("super") and not args and not kwargs:
            function = self.scope.function
            if function is not None and function.defining_class is not None:
                receiver = self.scope.vars.get(
                    function.params[0] if function.params else None, _MISSING
                )
                if receiver is not _MISSING:
                    return VirtoSuper(function.defining_class, receiver)
            return func()
        if func.__class__ is UserFunction:
            return self.call_user_function(func, args, kwargs)
        if not callable(func):
            raise TypeError(f"'{type(func).__name__}' object is not callable")
        if kwargs:
            return func(*args, **kwargs)
        return func(*args)

    def _eval_call_spread(self, node):
        """A call using ``*iterable`` and/or ``**mapping`` arguments."""
        _, func_node, arg_nodes, kwarg_nodes = node
        func = self.evaluate(func_node)
        args = self._spread_items(arg_nodes)
        kwargs = {}
        for name, value_node in kwarg_nodes:
            if name is None:
                for key, value in self.evaluate(value_node).items():
                    if key in kwargs:
                        raise TypeError(f"got multiple values for argument {key!r}")
                    kwargs[key] = value
            else:
                if name in kwargs:
                    raise TypeError(f"got multiple values for argument {name!r}")
                kwargs[name] = self.evaluate(value_node)
        if func.__class__ is UserFunction:
            return self.call_user_function(func, args, kwargs)
        if not callable(func):
            raise TypeError(f"'{type(func).__name__}' object is not callable")
        return func(*args, **kwargs)

    # ------------------------------------------------------------------
    # Operators
    # ------------------------------------------------------------------

    def _eval_binary(self, node):
        return _BINARY_OPERATORS[node[0]](self.evaluate(node[1]), self.evaluate(node[2]))

    def _eval_unary(self, node):
        _, symbol, operand = node
        return _UNARY_OPERATORS[symbol](self.evaluate(operand))

    def _eval_not(self, node):
        return not self.evaluate(node[1])

    def _eval_and(self, node):
        left = self.evaluate(node[1])
        if not left:
            return left
        return self.evaluate(node[2])

    def _eval_or(self, node):
        left = self.evaluate(node[1])
        if left:
            return left
        return self.evaluate(node[2])

    def _eval_compare(self, node):
        _, symbol, left, right = node
        left_value = self.evaluate(left)
        right_value = self.evaluate(right)
        if symbol == "is":
            return left_value is right_value
        if symbol == "is not":
            return left_value is not right_value
        return _COMPARE_OPERATORS[symbol](left_value, right_value)

    def _eval_compare_chain(self, node):
        """``a < b < c`` is ``a < b and b < c`` with ``b`` evaluated only once."""
        _, first, operations = node
        left = self.evaluate(first)
        for symbol, right_node in operations:
            right = self.evaluate(right_node)
            if symbol == "is":
                matches = left is right
            elif symbol == "is not":
                matches = left is not right
            else:
                matches = _COMPARE_OPERATORS[symbol](left, right)
            if not matches:
                return False
            left = right
        return True

    def _eval_conditional(self, node):
        """Evaluate only the selected branch of ``a if condition else b``."""
        _, condition, value, fallback = node
        return self.evaluate(value if self.evaluate(condition) else fallback)

    # ------------------------------------------------------------------
    # Strings
    # ------------------------------------------------------------------

    def _eval_regex(self, node):
        return re.compile(node[1])

    def _eval_fstring(self, node):
        """Evaluate an f-string such as ``f"Hello, {name!r:>10}"``.

        The string is split into literal text and fields once and cached; each
        evaluation then only evaluates the fields.
        """
        _, inner, prefix, quote = node
        key = (inner, prefix, quote)
        parts = self._fstring_cache.get(key)
        if parts is None:
            parts = self._fstring_cache[key] = self._compile_fstring(*key)

        output = []
        for part in parts:
            if part.__class__ is str:
                output.append(part)
                continue
            field_ast, conversion, spec_node, debug_text = part
            value = self.evaluate(field_ast)
            if conversion is not None:
                value = _CONVERSIONS[conversion](value)
            spec = self.evaluate(spec_node) if spec_node is not None else ""
            formatted = format(value, spec)
            if debug_text is not None:
                formatted = f"{debug_text}{formatted}"
            output.append(formatted)

        result = "".join(output)
        if "b" in prefix.lower():
            return result.encode("utf-8")
        return result

    def _compile_fstring(self, inner, prefix, quote):
        """Split f-string text into a list of parts.

        Each part is either a ``str`` (literal text, escapes already
        processed) or a tuple ``(field_ast, conversion, spec_node, debug_text)``
        describing a ``{...}`` field.
        """
        raw = "r" in prefix.lower()
        spec_prefix = prefix.replace("b", "").replace("B", "")
        parts = []
        literal = []

        def flush_literal():
            if literal:
                text = "".join(literal).replace("\r", "\\r").replace("\n", "\\n")
                parts.append(text if raw else ast.literal_eval(quote + text + quote))
                literal.clear()

        index = 0
        while index < len(inner):
            char = inner[index]
            following = inner[index + 1] if index + 1 < len(inner) else ""
            if char == "{" and following == "{":  # escaped {{
                literal.append("{")
                index += 2
                continue
            if char == "}" and following == "}":  # escaped }}
                literal.append("}")
                index += 2
                continue
            if char == "}":
                raise SyntaxError("f-string: single '}' is not allowed")
            if char != "{":
                literal.append(char)
                index += 1
                continue

            flush_literal()
            end = _find_fstring_field_end(inner, index + 1)
            expression, conversion, format_spec = _split_fstring_field(
                inner[index + 1 : end]
            )
            expression = expression.strip()
            if not expression:
                raise SyntaxError("f-string: empty expression not allowed")

            # f"{value=}" prints the source text too.
            debug_text = None
            if expression.endswith("=") and not expression.endswith(
                ("==", "!=", "<=", ">=")
            ):
                debug_text = expression
                expression = expression[:-1].rstrip()
                if conversion is None and format_spec is None:
                    conversion = "r"

            if conversion is not None and conversion not in _CONVERSIONS:
                raise SyntaxError("f-string: invalid conversion character")

            field_ast = Parser(Lexer(expression).tokenize()).parse()
            spec_node = (
                ("FSTRING", format_spec, spec_prefix, quote)
                if format_spec is not None
                else None
            )
            parts.append((field_ast, conversion, spec_node, debug_text))
            index = end + 1

        flush_literal()
        return parts
