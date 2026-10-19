from lexer import *
from parser import *
import lexer
import re
import importlib
import builtins


class _ReturnSignal:
    def __init__(self, value):
        self.value = value


def _find_fstring_field_end(value, start):
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


class Interpreter:
    def __init__(self, code, filename="<string>"):
        self.source = code
        self.filename = filename
        self.error_location = None
        self.lexer = Lexer(code)
        tokens = self.lexer.tokenize()
        self.parser = Parser(
            tokens,
            self.lexer.locations,
            self.lexer._location(len(code)),
        )
        # Initialize variables with any functions provided by the lexer functable
        try:
            self.variables = dict(lexer._functable_)
        except Exception:
            self.variables = {}
        self.variables["Error"] = Exception

    def evaluate(self, node):
        previous_location = self.error_location
        location = self.parser.node_locations.get(id(node))
        if location is not None:
            self.error_location = location
        try:
            result = self._evaluate(node)
        except Exception:
            raise
        else:
            self.error_location = previous_location
            return result

    def _evaluate(self, node):
        # primitive literals
        if isinstance(node, (int, float, str, bytes, bool)):
            return node
        # None
        if node is None:
            return None

        # block of statements
        if isinstance(node, tuple) and node[0] == "BLOCK":
            _, stmts = node
            result = None
            for s in stmts:
                result = self.evaluate(s)
                if isinstance(result, _ReturnSignal):
                    return result
            return result

        if isinstance(node, tuple):
            tag = node[0]
            # variable node
            if tag == "VAR":
                _, name = node
                if name in self.variables:
                    return self.variables[name]
                return getattr(builtins, name, None)
            if tag == "ATTR":
                _, base, name = node
                obj = self.evaluate(base)
                # instance objects are dicts with '__class__'
                if isinstance(obj, dict) and "__class__" in obj:
                    # instance attribute
                    if name in obj:
                        return obj[name]
                    # look up in class members
                    class_def = obj.get("__class__")
                    if class_def and class_def[0] == "CLASSDEF":
                        members = class_def[2]
                        if name in members:
                            val = members[name]
                            # if it's a user function, return a bound method
                            if isinstance(val, tuple) and val and val[0] == "USERFUNC":

                                def make_bound(func_tuple, inst):
                                    def bound(*args, **kwargs):
                                        _, params, body, closure = func_tuple
                                        saved_vars = dict(self.variables)
                                        self.variables = dict(closure)
                                        for n, v in zip(params, [inst] + list(args)):
                                            self.variables[n] = v
                                        res = self.evaluate(body)
                                        self.variables = saved_vars
                                        if isinstance(res, _ReturnSignal):
                                            return res.value
                                        return res

                                    return bound

                                return make_bound(val, obj)
                            return val
                # fallback to python getattr or dict lookup
                try:
                    return getattr(obj, name)
                except Exception:
                    if isinstance(obj, dict) and name in obj:
                        return obj[name]
                    raise
            if tag == "INDEX":
                _, base, idx = node
                b = self.evaluate(base)
                i = self.evaluate(idx)
                return b[i]
            if tag == "LIST":
                _, items = node
                return [self.evaluate(i) for i in items]
            if tag == "FUNCDEF":
                _, fname, params, body = node
                closure = dict(self.variables)
                self.variables[fname] = ("USERFUNC", params, body, closure)
                return None
            if tag == "RETURN":
                _, expr = node
                val = self.evaluate(expr)
                return _ReturnSignal(val)
            if tag == "FOR":
                _, varname, iterable_node, block = node
                iterable = self.evaluate(iterable_node)
                result = None
                for val in iterable:
                    self.variables[varname] = val
                    r = self.evaluate(block)
                    if isinstance(r, _ReturnSignal):
                        return r
                    result = r
                return result
            if tag == "IMPORT":
                _, module_name, alias = node
                mod = importlib.import_module(module_name)
                name = alias if alias is not None else module_name
                self.variables[name] = mod
                return None
            if tag == "FROMIMPORT":
                _, module_name, obj_name, alias = node
                mod = importlib.import_module(module_name)
                obj = getattr(mod, obj_name)
                name = alias if alias is not None else obj_name
                self.variables[name] = obj
                return None
            if tag == "ASSIGN":
                _, name, expr = node
                value = self.evaluate(expr)
                self.variables[name] = value
                return None
            if tag == "ASSIGN_LHS":
                _, lhs, expr = node
                value = self.evaluate(expr)
                # lhs can be VAR, ATTR, INDEX
                if lhs[0] == "VAR":
                    _, name = lhs
                    self.variables[name] = value
                    return None
                if lhs[0] == "ATTR":
                    _, base, name = lhs
                    obj = self.evaluate(base)
                    # instances are dict-like
                    if isinstance(obj, dict) and "__class__" in obj:
                        obj[name] = value
                        return None
                    setattr(obj, name, value)
                    return None
                if lhs[0] == "INDEX":
                    _, base, idx = lhs
                    b = self.evaluate(base)
                    i = self.evaluate(idx)
                    b[i] = value
                    return None
                raise ValueError(f"Invalid assignment target: {lhs}")

            if tag == "AUGASSIGN":
                _, op, lhs, expr = node
                rhs = self.evaluate(expr)
                # VAR
                if lhs[0] == "VAR":
                    _, name = lhs
                    cur = self.variables.get(name)
                    if op == "+=":
                        val = cur + rhs
                    elif op == "-=":
                        val = cur - rhs
                    elif op == "*=":
                        val = cur * rhs
                    elif op == "/=":
                        val = cur / rhs
                    elif op == "%=":
                        val = cur % rhs
                    else:
                        raise ValueError(f"Unsupported aug assign: {op}")
                    self.variables[name] = val
                    return None
                # ATTR
                if lhs[0] == "ATTR":
                    _, base, name = lhs
                    obj = self.evaluate(base)
                    # instance dict
                    if isinstance(obj, dict) and "__class__" in obj:
                        cur = obj.get(name)
                        if op == "+=":
                            val = cur + rhs
                        elif op == "-=":
                            val = cur - rhs
                        elif op == "*=":
                            val = cur * rhs
                        elif op == "/=":
                            val = cur / rhs
                        elif op == "%=":
                            val = cur % rhs
                        else:
                            raise ValueError(f"Unsupported aug assign: {op}")
                        obj[name] = val
                        return None
                    # python object
                    cur = getattr(obj, name)
                    if op == "+=":
                        val = cur + rhs
                    elif op == "-=":
                        val = cur - rhs
                    elif op == "*=":
                        val = cur * rhs
                    elif op == "/=":
                        val = cur / rhs
                    elif op == "%=":
                        val = cur % rhs
                    else:
                        raise ValueError(f"Unsupported aug assign: {op}")
                    setattr(obj, name, val)
                    return None
                # INDEX
                if lhs[0] == "INDEX":
                    _, base, idx = lhs
                    b = self.evaluate(base)
                    i = self.evaluate(idx)
                    cur = b[i]
                    if op == "+=":
                        val = cur + rhs
                    elif op == "-=":
                        val = cur - rhs
                    elif op == "*=":
                        val = cur * rhs
                    elif op == "/=":
                        val = cur / rhs
                    elif op == "%=":
                        val = cur % rhs
                    else:
                        raise ValueError(f"Unsupported aug assign: {op}")
                    b[i] = val
                    return None
                raise ValueError(f"Invalid aug assignment target: {lhs}")

            if tag == "CLASS":
                _, class_name, body, base_names = node
                # evaluate class body in a temporary scope so defs become members
                saved = dict(self.variables)
                temp = dict(saved)
                self.variables = temp
                try:
                    self.evaluate(body)
                finally:
                    self.variables = saved
                # members are the names introduced in temp but not in saved
                members = {k: v for k, v in temp.items() if k not in saved}
                bases = []
                for base_name in base_names:
                    base = self.variables.get(base_name)
                    if base is None:
                        base = getattr(builtins, base_name, None)
                    if not isinstance(base, type):
                        raise TypeError(
                            f"Base class {base_name!r} is not a class"
                        )
                    bases.append(base)

                if bases and any(
                    issubclass(base, BaseException) for base in bases
                ):
                    namespace = {"__module__": "__main__"}
                    if "__init__" not in members:
                        def initialize(instance, *args):
                            Exception.__init__(instance, *args)

                        namespace["__init__"] = initialize

                    for name, member in members.items():
                        if (
                            isinstance(member, tuple)
                            and member
                            and member[0] == "USERFUNC"
                        ):
                            _, params, method_body, closure = member

                            def make_method(method_params, method_body, method_closure):
                                def method(instance, *args):
                                    if len(method_params) != len(args) + 1:
                                        raise TypeError(
                                            "Method call with wrong number of args"
                                        )
                                    saved_vars = self.variables
                                    self.variables = dict(method_closure)
                                    self.variables[method_params[0]] = instance
                                    for param, value in zip(
                                        method_params[1:], args
                                    ):
                                        self.variables[param] = value
                                    try:
                                        result = self.evaluate(method_body)
                                    finally:
                                        self.variables = saved_vars
                                    if isinstance(result, _ReturnSignal):
                                        return result.value
                                    return result

                                return method

                            namespace[name] = make_method(
                                params, method_body, closure
                            )
                        else:
                            namespace[name] = member
                    error_class = type(class_name, tuple(bases), namespace)
                    self.variables[class_name] = error_class
                else:
                    class_def = ("CLASSDEF", class_name, members)
                    self.variables[class_name] = class_def
                return None

            if tag == "TRY":
                _, try_block, excepts, finally_block = node
                pending_error = None
                result = None
                try:
                    try:
                        result = self.evaluate(try_block)
                    except Exception as error:
                        for exception_type_node, alias, handler in excepts:
                            if exception_type_node is None:
                                matches = True
                            else:
                                exception_type = self.evaluate(exception_type_node)
                                if not isinstance(exception_type, type) or not issubclass(
                                    exception_type, BaseException
                                ):
                                    raise TypeError(
                                        "except clause must name an exception class"
                                    )
                                matches = isinstance(error, exception_type)
                            if not matches:
                                continue

                            missing = object()
                            previous_alias = (
                                self.variables.get(alias, missing)
                                if alias
                                else missing
                            )
                            if alias:
                                self.variables[alias] = error
                            try:
                                result = self.evaluate(handler)
                            finally:
                                if alias:
                                    if previous_alias is missing:
                                        self.variables.pop(alias, None)
                                    else:
                                        self.variables[alias] = previous_alias
                            break
                        else:
                            raise
                except BaseException as error:
                    pending_error = error

                finally_result = None
                if finally_block is not None:
                    finally_result = self.evaluate(finally_block)
                if isinstance(finally_result, _ReturnSignal):
                    return finally_result
                if pending_error is not None:
                    raise pending_error
                return result

            if tag == "IF":
                _, cond, then_block, else_block = node
                if self.evaluate(cond):
                    return self.evaluate(then_block)
                if else_block is not None:
                    return self.evaluate(else_block)
                return None

            if tag == "WHILE":
                _, cond, block = node
                result = None
                while self.evaluate(cond):
                    r = self.evaluate(block)
                    if isinstance(r, _ReturnSignal):
                        return r
                    result = r
                return result
            if tag == "FSTRING":
                _, inner, prefix, quote = node
                raw = "r" in prefix.lower()
                parts = []
                literal = []
                index = 0

                def append_literal():
                    if not literal:
                        return
                    text = "".join(literal)
                    parts.append(
                        text if raw else ast.literal_eval(quote + text + quote)
                    )
                    literal.clear()

                while index < len(inner):
                    char = inner[index]
                    if (
                        char == "{"
                        and index + 1 < len(inner)
                        and inner[index + 1] == "{"
                    ):
                        literal.append("{")
                        index += 2
                        continue
                    if (
                        char == "}"
                        and index + 1 < len(inner)
                        and inner[index + 1] == "}"
                    ):
                        literal.append("}")
                        index += 2
                        continue
                    if char == "}":
                        raise SyntaxError("f-string: single '}' is not allowed")
                    if char != "{":
                        literal.append(char)
                        index += 1
                        continue

                    append_literal()
                    end = _find_fstring_field_end(inner, index + 1)
                    field = inner[index + 1 : end]
                    expression, conversion, format_spec = _split_fstring_field(field)
                    expression = expression.strip()
                    if not expression:
                        raise SyntaxError("f-string: empty expression not allowed")

                    debug_text = None
                    if expression.endswith("=") and not expression.endswith(
                        ("==", "!=", "<=", ">=")
                    ):
                        debug_text = expression
                        expression = expression[:-1].rstrip()
                        if conversion is None and format_spec is None:
                            conversion = "r"

                    field_ast = Parser(Lexer(expression).tokenize()).parse()
                    value = self.evaluate(field_ast)
                    if conversion is not None:
                        if len(conversion) != 1 or conversion[0] not in (
                            "s",
                            "r",
                            "a",
                        ):
                            raise SyntaxError(
                                "f-string: invalid conversion character"
                            )
                        value = {"s": str, "r": repr, "a": ascii}[conversion](value)

                    spec = ""
                    if format_spec is not None:
                        spec = self.evaluate(
                            ("FSTRING", format_spec, prefix, quote)
                        )
                    formatted = format(value, spec)
                    if debug_text is not None:
                        formatted = f"{debug_text}{formatted}"
                    parts.append(formatted)
                    index = end + 1

                append_literal()
                result = "".join(parts)
                if "b" in prefix.lower():
                    return result.encode("utf-8")
                return result
            if tag == "REGEX":
                _, pattern = node
                return re.compile(pattern)
            if tag == "RAISE":
                _, expr = node
                msg = self.evaluate(expr)
                if isinstance(msg, BaseException):
                    raise msg
                raise RuntimeError(str(msg))
            if tag == "UNARY":
                _, op, expr = node
                val = self.evaluate(expr)
                if op == "+":
                    return +val
                if op == "-":
                    return -val
            if tag == "NOT":
                _, expr = node
                return not self.evaluate(expr)
            if tag == "AND":
                _, left, right = node
                lv = self.evaluate(left)
                if not lv:
                    return lv
                return self.evaluate(right)
            if tag == "OR":
                _, left, right = node
                lv = self.evaluate(left)
                if lv:
                    return lv
                return self.evaluate(right)
            if tag == "CALL":
                _, func_node, args = node
                evaluated_args = [self.evaluate(a) for a in args]
                # resolve function or class object
                func_obj = (
                    self.evaluate(func_node)
                    if isinstance(func_node, tuple)
                    else self.variables.get(func_node)
                )
                # class instantiation: if func_obj is a CLASSDEF tuple, create instance
                if (
                    isinstance(func_obj, tuple)
                    and func_obj
                    and func_obj[0] == "CLASSDEF"
                ):
                    _, class_name, members = func_obj
                    inst = {"__class__": func_obj}
                    # if constructor exists, call it as USERFUNC with self + args
                    ctor = members.get("__init__")
                    if isinstance(ctor, tuple) and ctor and ctor[0] == "USERFUNC":
                        _, params, body, closure = ctor
                        saved_vars = dict(self.variables)
                        self.variables = dict(closure)
                        # bind self then remaining args
                        for n, v in zip(params, [inst] + evaluated_args):
                            self.variables[n] = v
                        res = self.evaluate(body)
                        self.variables = saved_vars
                        if isinstance(res, _ReturnSignal):
                            # ignore return from __init__
                            pass
                    return inst
                # user functions
                if (
                    isinstance(func_obj, tuple)
                    and func_obj
                    and func_obj[0] == "USERFUNC"
                ):
                    _, params, body, closure = func_obj
                    if len(params) != len(evaluated_args):
                        raise TypeError("Function call with wrong number of args")
                    saved_vars = dict(self.variables)
                    self.variables = dict(closure)
                    for n, v in zip(params, evaluated_args):
                        self.variables[n] = v
                    res = self.evaluate(body)
                    self.variables = saved_vars
                    if isinstance(res, _ReturnSignal):
                        return res.value
                    return res
                # then try python callables
                func = func_obj
                if callable(func):
                    return func(*evaluated_args)
                # fallback: try builtin tables if func_node is a name
                if isinstance(func_node, tuple) and func_node[0] == "VAR":
                    name = func_node[1]
                    try:
                        func = lexer._builtins_.get(name)
                    except Exception:
                        func = None
                    if func is None:
                        try:
                            import builtins as _pybuiltins

                            func = getattr(_pybuiltins, name, None)
                        except Exception:
                            func = None
                    if callable(func):
                        return func(*evaluated_args)
                raise ValueError(f"Unknown function: {func_node}")

            # binary operators
            if tag in ("+", "-", "*", "/"):
                _, left, right = node
                left_val = self.evaluate(left)
                right_val = self.evaluate(right)
                if tag == "+":
                    return left_val + right_val
                if tag == "-":
                    return left_val - right_val
                if tag == "*":
                    return left_val * right_val
                if tag == "/":
                    return left_val / right_val
            if tag == "COMPARE":
                _, op, left, right = node
                l = self.evaluate(left)
                r = self.evaluate(right)
                if op == "==":
                    return l == r
                if op == "!=":
                    return l != r
                if op == "<":
                    return l < r
                if op == ">":
                    return l > r
                if op == "<=":
                    return l <= r
                if op == ">=":
                    return l >= r

        raise ValueError(f"Invalid node: {node}")

    def run(self):
        ast = self.parser.parse()
        result = self.evaluate(ast)
        # Only print non-None results. builtin `print` will output itself.
        if result is not None and not isinstance(result, _ReturnSignal):
            print(result)
