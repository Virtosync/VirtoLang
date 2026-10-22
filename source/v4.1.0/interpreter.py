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
import importlib
import operator
import re

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
    """

    __slots__ = ("vars", "parent")

    def __init__(self, parent=None, initial=None):
        self.vars = initial if initial is not None else {}
        self.parent = parent

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
        params: Parameter names, in order.
        defaults: ``{param_name: default_value}`` for optional parameters.
        body: The function's AST block.
        closure: The ``Scope`` the function was defined in.
    """

    __slots__ = ("interpreter", "name", "params", "defaults", "body", "closure")

    def __init__(self, interpreter, name, params, defaults, body, closure):
        self.interpreter = interpreter
        self.name = name
        self.params = params
        self.defaults = defaults
        self.body = body
        self.closure = closure

    def __call__(self, *args, **kwargs):
        return self.interpreter.call_user_function(self, args, kwargs)

    def __repr__(self):
        return f"<function {self.name}>"


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
        if name in attrs:
            return attrs[name]
        cls = object.__getattribute__(self, "__vclass__")
        member = cls.find_member(name)
        if member is not _MISSING:
            if isinstance(member, UserFunction):
                return BoundMethod(member, self)
            return member
        raise AttributeError(f"'{cls.name}' object has no attribute '{name}'")

    def __setattr__(self, name, value):
        object.__getattribute__(self, "__vattrs__")[name] = value

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

        # Node tag -> method that evaluates that kind of node.
        self._dispatch = {
            "BLOCK": self._eval_block,
            "VAR": self._eval_var,
            "ATTR": self._eval_attr,
            "INDEX": self._eval_index,
            "SLICE": self._eval_slice,
            "LIST": self._eval_list,
            "TUPLE": self._eval_tuple,
            "DICT": self._eval_dict,
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

        Literals (numbers, strings, ``None``...) evaluate to themselves.  The
        source location of tuple nodes is remembered so a failure can be
        reported precisely; on success the previous location is restored.
        """
        if node.__class__ is tuple:
            previous_location = self.error_location
            location = self.node_locations.get(id(node))
            if location is not None:
                self.error_location = location
            handler = self._dispatch.get(node[0])
            if handler is None:
                raise ValueError(f"Invalid node: {node}")
            result = handler(node)
            self.error_location = previous_location
            return result
        if node is None or isinstance(node, (int, float, str, bytes)):
            return node
        raise ValueError(f"Invalid node: {node}")

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
        variables = self.scope.vars
        single_target = isinstance(target, str)
        result = None
        for item in iterable:
            if single_target:
                variables[target] = item
            else:
                values = list(item)
                if len(values) != len(target):
                    raise ValueError(
                        f"cannot unpack {len(values)} value(s) into {len(target)} name(s)"
                    )
                variables.update(zip(target, values))
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
            self.scope.vars[alias] = module
        else:
            # ``import a.b`` binds the top-level package name ``a``.
            top_level = module_name.split(".")[0]
            self.scope.vars[top_level] = (
                module if top_level == module_name else importlib.import_module(top_level)
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
        self.scope.vars[alias if alias is not None else name] = value
        return None

    # ------------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------------

    def _eval_assign(self, node):
        _, target, expression = node
        value = self.evaluate(expression)
        kind = target[0]
        if kind == "VAR":
            self.scope.vars[target[1]] = value
        elif kind == "ATTR":
            setattr(self.evaluate(target[1]), target[2], value)
        elif kind == "INDEX":
            container = self.evaluate(target[1])
            container[self.evaluate(target[2])] = value
        else:
            raise ValueError(f"Invalid assignment target: {target}")
        return None

    def _eval_augassign(self, node):
        _, op_text, target, expression = node
        apply = _AUGMENTED_OPERATORS.get(op_text)
        if apply is None:
            raise ValueError(f"Unsupported aug assign: {op_text}")
        rhs = self.evaluate(expression)
        kind = target[0]
        if kind == "VAR":
            name = target[1]
            self.scope.vars[name] = apply(self._lookup(name), rhs)
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
        _, name, params, body, defaults = node
        # Default values are evaluated once, when the function is defined.
        default_values = {p: self.evaluate(expr) for p, expr in defaults.items()}
        self.scope.vars[name] = UserFunction(
            self, name, params, default_values, body, self.scope
        )
        return None

    def call_user_function(self, function, args, kwargs=None):
        """Call a ``UserFunction`` with positional ``args`` and keyword ``kwargs``.

        A fresh ``Scope`` (child of the function's defining scope) holds the
        parameters.  The value of a ``return`` statement is the result; with no
        ``return`` the value of the last statement is used.
        """
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
        self.scope = Scope(function.closure, local)
        try:
            result = self.evaluate(function.body)
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
            self.scope.vars[class_name] = self._make_exception_class(
                class_name, python_bases, members
            )
        else:
            self.scope.vars[class_name] = VirtoClass(class_name, members, user_bases)
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
        if func.__class__ is UserFunction:
            return self.call_user_function(func, args, kwargs)
        if not callable(func):
            raise TypeError(f"'{type(func).__name__}' object is not callable")
        if kwargs:
            return func(*args, **kwargs)
        return func(*args)

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
        return _COMPARE_OPERATORS[symbol](self.evaluate(left), self.evaluate(right))

    def _eval_compare_chain(self, node):
        """``a < b < c`` is ``a < b and b < c`` with ``b`` evaluated only once."""
        _, first, operations = node
        left = self.evaluate(first)
        for symbol, right_node in operations:
            right = self.evaluate(right_node)
            if not _COMPARE_OPERATORS[symbol](left, right):
                return False
            left = right
        return True

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
                text = "".join(literal)
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
