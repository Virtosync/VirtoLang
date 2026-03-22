from lexer import *
from parser import *
import lexer
import re
import importlib


class _ReturnSignal:
    def __init__(self, value):
        self.value = value


class Interpreter:
    def __init__(self, code):
        self.lexer = Lexer(code)
        self.parser = Parser(self.lexer.tokenize())
        # Initialize variables with any functions provided by the lexer functable
        try:
            self.variables = dict(lexer._functable_)
        except Exception:
            self.variables = {}

    def evaluate(self, node):
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
                return self.variables.get(name)
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
                _, class_name, body = node
                # evaluate class body in a temporary scope so defs become members
                saved = dict(self.variables)
                temp = dict(saved)
                self.variables = temp
                self.evaluate(body)
                # members are the names introduced in temp but not in saved
                members = {k: v for k, v in temp.items() if k not in saved}
                self.variables = saved
                class_def = ("CLASSDEF", class_name, members)
                self.variables[class_name] = class_def
                return None

            if tag == "TRY":
                _, try_block, excepts, finally_block = node
                res = None
                try:
                    res = self.evaluate(try_block)
                except Exception as e:
                    # handle except blocks in order; ex_name binds exception object if provided
                    handled = False
                    for ex_name, ex_block in excepts:
                        saved = dict(self.variables)
                        if ex_name:
                            self.variables[ex_name] = e
                        r = self.evaluate(ex_block)
                        self.variables = saved
                        handled = True
                        if isinstance(r, _ReturnSignal):
                            if finally_block:
                                self.evaluate(finally_block)
                            return r
                        break
                    if not handled:
                        if finally_block:
                            self.evaluate(finally_block)
                        raise
                else:
                    if finally_block:
                        self.evaluate(finally_block)
                    return res

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
                _, inner, prefix = node

                def replace(m):
                    expr = m.group(1)
                    p = Parser(Lexer(expr).tokenize())
                    astn = p.parse()
                    val = self.evaluate(astn)
                    return str(val)

                result = re.sub(r"\{([^}]+)\}", replace, inner)
                if "b" in prefix.lower():
                    return result.encode("utf-8")
                return result
            if tag == "REGEX":
                _, pattern = node
                return re.compile(pattern)
            if tag == "RAISE":
                _, expr = node
                msg = self.evaluate(expr)
                raise RuntimeError(msg)
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
