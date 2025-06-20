# VirtoLang Interpreter - Main Implementation
#
# This file implements the VirtoLang interpreter, including the tokenizer, parser, built-in functions, and runtime.
# It is designed to be robust, extensible, and modern, supporting Python-like syntax, async/await, error handling, classes, and more.
#
# --------------------
# IMPORTS AND SETUP
# --------------------
import re  # Regular expressions for tokenizing code
import sys  # System functions (e.g., command-line args, exit)
import os  # File and path operations
import asyncio  # Async/await support
import time  # Time utilities
import random  # Random number utilities
import math  # Math functions
import argparse  # Command-line argument parsing
from colorama import init, Fore, Style, Back  # Colored terminal output
import requests  # HTTP requests (for built-in web functions)
from datetime import datetime  # Date/time utilities
import tkinter as tk
from tkinter import messagebox

__version__ = "2.4"

init(autoreset=True)  # Initialize colorama for colored output


# --------------------
# TOKEN CLASS
# --------------------
class Token:
    def __init__(self, kind, value, line, column):
        self.kind = kind  # The type of token (e.g., IDENTIFIER, NUMBER, etc.)
        self.value = value  # The value of the token (e.g., variable name, number)
        self.line = line  # Line number in the source code
        self.column = column  # Column number in the source code

    def __iter__(self):
        return iter((self.kind, self.value, self.line, self.column))

    def __getitem__(self, idx):
        return (self.kind, self.value, self.line, self.column)[idx]

    def __repr__(self):
        return f"Token({self.kind}, {self.value}, line={self.line}, col={self.column})"


# --------------------
# PARSER ERROR CLASS
# --------------------
class ParserError(Exception):
    def __init__(self, message, filename, token=None, code=None):
        self.message = message  # Error message
        self.filename = filename  # Filename (for error display)
        self.token = token  # Token where the error occurred
        self.code = code  # Source code (for error display)
        super().__init__(self.__str__())

    def __str__(self):
        # Only access .line and .column if token has those attributes
        if self.token and hasattr(self.token, "line") and hasattr(self.token, "column"):
            pointer = f"File \"{self.filename or '<input>'}\", line {self.token.line}, col {self.token.column}"
            code_line = ""
            if self.code:
                lines = self.code.splitlines()
                if 1 <= self.token.line <= len(lines):
                    code_line = lines[self.token.line - 1]
            return f"{Fore.RED}SyntaxError: {self.message}\n  {pointer}\n    {code_line}\n    {' '*(self.token.column-1)}^"
        return f"{Fore.RED}SyntaxError: {self.message}"


# --------------------
# ERROR CLASS
# --------------------
class Error(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message

    def __str__(self):
        return f"Error: {self.message}"


# --------------------
# ARGUMENT ERROR CLASS
# --------------------
class VirtoArgumentError(Exception):
    def __init__(self, message, filename=None, token=None, code=None):
        self.message = message
        self.filename = filename
        self.token = token
        self.code = code
        super().__init__(self.__str__())

    def __str__(self):
        pointer = f"File \"{self.filename or '<input>'}\""
        return f"{Fore.RED}ArgumentError: {self.message}\n  {pointer}"


# --------------------
# TOKENIZER
# --------------------
# Precompile token regex at module load for speed
_token_spec = [
    ("NUMBER", r"\d+"),
    ("PRINT", r"\bprint\b"),
    ("IF", r"\bif\b"),
    ("ASYNC", r"\basync\b"),
    ("AWAIT", r"\bawait\b"),
    ("ELSE", r"\belse\b"),
    ("ELIF", r"\belif\b"),
    ("WHILE", r"\bwhile\b"),
    ("FOR", r"\bfor\b"),
    ("RETURN", r"\breturn\b"),
    ("DEF", r"\bdef\b"),
    ("TRUE", r"\btrue\b"),
    ("FALSE", r"\bfalse\b"),
    ("NULL", r"\bnull\b"),
    ("IMPORT", r"\bimport\b"),
    ("WITH", r"\bwith\b"),
    ("AS", r"\bas\b"),
    ("IS", r"\bis\b"),
    ("IN", r"\bin\b"),
    ("NOT", r"\bnot\b"),
    ("STRING", r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''),
    ("LE", r"<="),
    ("GE", r">="),
    ("EQ", r"=="),
    ("NEQ", r"!="),
    ("LT", r"<"),
    ("GT", r">"),
    ("ASSIGN", r"="),
    ("IDENTIFIER", r"[a-zA-Z_]\w*"),
    ("PLUS", r"\+"),
    ("SKIP", r"[ \t]+"),
    ("NEWLINE", r"\n"),
    ("LBRACE", r"\{"),
    ("RBRACE", r"\}"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("MINUS", r"-"),
    ("MULTIPLY", r"\*"),
    ("C_COMMENT", r"//.*"),
    ("DIVIDE", r"/"),
    ("COMMA", r","),
    ("SEMICOLON", r";"),
    ("COLON", r":"),
    ("DOT", r"\."),
    ("AND", r"&&"),
    ("OR", r"\|\|"),
    ("BANG", r"!"),
    ("LBRACKET", r"\["),
    ("RBRACKET", r"\]"),
    ("COMMENT", r"#.*"),
    ("BLOCK_COMMENT", r"/\*.*?\\*/"),
    ("RAISE", r"raise"),
    ("TRY", r"try"),
    ("EXCEPT", r"except"),
    ("FINALLY", r"finally"),
    ("PERCENT", r"%"),
    ("MISMATCH", r"."),
]
_token_regex = re.compile(
    "|".join(f"(?P<{name}>{pattern})" for name, pattern in _token_spec), re.DOTALL
)


# --------------------
# TOKENIZE FUNCTION
# --------------------
def tokenize(code):
    """
    Convert source code string into a list of Token objects.
    Each token represents a meaningful element (number, identifier, symbol, etc.).
    """
    tokens = []
    regex = _token_regex
    line_num = 1
    line_start = 0
    for match in regex.finditer(code):
        kind = match.lastgroup
        value = match.group()
        start = match.start()
        end = match.end()
        column = start - line_start + 1
        if kind == "NEWLINE":
            line_num += 1
            line_start = end
            continue
        if kind == "SKIP":
            continue
        elif kind == "MISMATCH":
            raise ParserError(
                f"Unexpected character: {value}",
                Token(kind, value, line_num, column),
                code,
            )
        elif kind in ("COMMENT", "BLOCK_COMMENT", "C_COMMENT"):
            continue
        elif kind == "NUMBER":
            value = int(value)
        elif kind == "IDENTIFIER":
            # Check for keywords and convert to keyword token type
            keywords = (
                "if",
                "else",
                "elif",
                "while",
                "for",
                "return",
                "def",
                "true",
                "false",
                "null",
                "and",
                "or",
                "not",
                "print",
                "import",
                "with",
                "as",
                "async",
                "await",
                "try",
                "except",
                "finally",
                "raise",
            )
            if value in keywords:
                kind = value.upper()
        tokens.append(Token(kind, value, line_num, column))
    return tokens


# --------------------
# PARSER CLASS
# --------------------
class Parser:
    def __init__(self, filename, tokens, code=None):
        self.filename = filename
        self.tokens = tokens
        self.pos = 0
        self.code = code

    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def advance(self):
        self.pos += 1

    def match(self, *token_types):
        token = self.peek()
        if token and token.kind in token_types:
            self.advance()
            return token
        return None

    def error(self, message, token=None):
        if token is None:
            token = self.peek()
        # Always raise ParserError, not SyntaxError
        raise ParserError(message, self.filename, token, self.code)

    def parse(self):
        statements = []
        while self.peek():
            stmt = self.statement()
            if stmt:
                statements.append(stmt)
        return statements

    def statement(self):
        # Assignment: IDENTIFIER ASSIGN expression
        if self.peek() and self.peek().kind == "IDENTIFIER":
            # Lookahead for assignment
            if (
                self.pos + 1 < len(self.tokens)
                and self.tokens[self.pos + 1].kind == "ASSIGN"
            ):
                name_token = self.match("IDENTIFIER")
                self.match("ASSIGN")
                expr = self.expression()
                return ("assign", name_token[1], expr)
            # If next token is LPAREN, treat as function call statement (e.g., run(...), run_async(...))
            elif (
                self.pos + 1 < len(self.tokens)
                and self.tokens[self.pos + 1].kind == "LPAREN"
            ):
                expr = self.expression()
                return ("expr_stmt", expr)
        # async def ...
        elif self.peek() and self.peek().kind == "ASYNC":
            self.advance()  # consume ASYNC
            if not self.match("DEF"):
                self.error("Expected 'def' after 'async'")
            next_token = self.peek()
            if not next_token:
                self.error(
                    "Expected function name after 'async def', but found end of input"
                )
            if next_token.kind != "IDENTIFIER":
                self.error(
                    f"Expected function name after 'async def', but found {next_token.kind} ('{next_token.value}') instead",
                    next_token,
                )
            name_token = self.match("IDENTIFIER")
            name = name_token[1]
            if not self.match("LPAREN"):
                self.error("Expected '(' after function name")
            params = []
            if not self.match("RPAREN"):
                while True:
                    param_token = self.match("IDENTIFIER")
                    if not param_token:
                        self.error("Expected parameter name in function definition")
                    params.append(param_token[1])
                    if self.match("COMMA"):
                        continue
                    elif self.match("RPAREN"):
                        break
                    else:
                        self.error("Expected ',' or ')' in parameter list")
            if not self.match("LBRACE"):
                self.error("Expected '{' to start function body")
            body = self.block()
            return ("async_function_decl", name, params, body)
        elif self.match("DEF"):
            return self.function_declaration()
        elif self.match("IF"):
            return self.if_statement()
        elif self.match("WHILE"):
            return self.while_statement()
        elif self.match("FOR"):
            return self.for_statement()
        elif self.match("WITH"):
            return self.with_statement()
        elif self.match("PRINT"):
            return self.print_statement()
        elif self.match("IMPORT"):
            return self.import_statement()
        elif self.match("RETURN"):
            return self.return_statement()
        elif self.match("AWAIT"):
            return self.await_statement()
        elif self.match("TRY"):
            return self.try_statement()
        elif self.match("RAISE"):
            return self.raise_statement()
        else:
            return self.expression_statement()

    def raise_statement(self):
        expr = self.expression()
        return ("raise", expr)

    def import_statement(self):
        # Accept either IDENTIFIER or STRING after 'import'
        module_token = self.match("IDENTIFIER")
        if not module_token:
            module_token = self.match("STRING")
        if not module_token:
            raise SyntaxError(
                "Expected module name (identifier or string) after 'import'"
            )
        return ("import", module_token[1])

    def function_declaration(self):
        name = self.match("IDENTIFIER")
        if not name:
            self.error("Expected function name after 'def'")
        if not self.match("LPAREN"):
            self.error("Expected '(' after function name")
        params = []
        if not self.match("RPAREN"):
            while True:
                param = self.match("IDENTIFIER")
                if not param:
                    self.error("Expected parameter name in function definition")
                params.append(param[1])
                if self.match("COMMA"):
                    continue
                elif self.match("RPAREN"):
                    break
                else:
                    self.error("Expected ',' or ')' in parameter list")
        if not self.match("LBRACE"):
            self.error("Expected '{' to start function body")
        body = self.block()
        return ("function_decl", name[1], params, body)

    def if_statement(self):
        lparen = self.match("LPAREN")
        if not lparen:
            self.error("Expected '(' after 'if'", lparen)
        cond_start = self.pos
        try:
            cond = self.expression()
        except ParserError as e:
            # Special case: if user wrote 'not' without 'in' or 'is'
            token = self.peek()
            if token and token.kind == "NOT":
                self.error(
                    "Expected 'in' or 'is' after 'not' in condition. Did you mean 'not in' or 'is not'?",
                    token,
                )
            raise
        if not self.match("RPAREN"):
            token = self.peek()
            self.error(
                "Expected ')' after if condition. Make sure your condition is valid. Example: if (x not in y) {{ ... }}",
                token,
            )
        if not self.match("LBRACE"):
            token = self.peek()
            self.error("Expected '{' after if condition", token)
        then_block = self.block()
        elif_blocks = []
        while self.match("ELIF"):
            if not self.match("LPAREN"):
                self.error("Expected '(' after 'elif'")
            elif_cond = self.expression()
            if not self.match("RPAREN"):
                self.error("Expected ')' after elif condition")
            if not self.match("LBRACE"):
                self.error("Expected '{' after elif condition")
            elif_block = self.block()
            elif_blocks.append((elif_cond, elif_block))
        else_block = None
        if self.match("ELSE"):
            if not self.match("LBRACE"):
                self.error("Expected '{' after 'else'")
            else_block = self.block()
        return ("if", cond, then_block, elif_blocks, else_block)

    def while_statement(self):
        if not self.match("LPAREN"):
            raise SyntaxError("Expected '(' after 'while'")
        cond = self.expression()
        if not self.match("RPAREN"):
            raise SyntaxError("Expected ')' after while condition")
        if not self.match("LBRACE"):
            raise SyntaxError("Expected '{' after while condition")
        body = self.block()
        return ("while", cond, body)

    def for_statement(self):
        if not self.match("LPAREN"):
            raise SyntaxError("Expected '(' after 'for'")
        var = self.match("IDENTIFIER")
        if not var:
            raise SyntaxError("Expected variable name in for loop")
        # Match 'in' as a keyword token, not as an identifier
        if not self.match("IN"):
            self.error("Expected 'in' in for loop")
        iterable = self.expression()
        if not self.match("RPAREN"):
            raise SyntaxError("Expected ')' after for loop header")
        if not self.match("LBRACE"):
            raise SyntaxError("Expected '{' after for loop header")
        body = self.block()
        return ("for", var[1], iterable, body)

    def with_statement(self):
        if not self.match("LPAREN"):
            raise SyntaxError("Expected '(' after 'with'")
        expr = self.expression()
        if not self.match("AS"):
            raise SyntaxError("Expected 'as' in with statement")
        var = self.match("IDENTIFIER")
        if not var:
            raise SyntaxError("Expected variable name after 'as'")
        if not self.match("RPAREN"):
            raise SyntaxError("Expected ')' after with statement")
        if not self.match("LBRACE"):
            raise SyntaxError("Expected '{' after with statement")
        body = self.block()
        return ("with", expr, var[1], body)

    def block(self):
        stmts = []
        while not self.match("RBRACE"):
            if not self.peek():
                raise SyntaxError("Unclosed block")
            stmts.append(self.statement())
        return stmts

    def print_statement(self):
        lparen = self.match("LPAREN")
        if not lparen:
            raise SyntaxError("Expected '(' after 'print'")
        args = []
        if not self.match("RPAREN"):
            while True:
                args.append(self.expression())
                if self.match("COMMA"):
                    continue
                elif self.match("RPAREN"):
                    break
                else:
                    raise SyntaxError("Expected ',' or ')' after print argument")
        return ("print", args)

    def return_statement(self):
        expr = self.expression()
        return ("return", expr)

    def await_statement(self):
        expr = self.expression()
        return ("await_stmt", expr)

    def run_statement(self):
        filename_expr = self.expression()
        return ("run_stmt", filename_expr)

    def run_async_statement(self):
        filename_expr = self.expression()
        return ("run_async_stmt", filename_expr)

    def expression_statement(self):
        expr = self.expression()
        return ("expr_stmt", expr)

    def expression(self):
        return self.logic_or()

    def logic_or(self):
        node = self.logic_and()
        while self.match("OR"):
            right = self.logic_and()
            node = ("or", node, right)
        return node

    def logic_and(self):
        node = self.logic_not()
        while self.match("AND"):
            right = self.logic_not()
            node = ("and", node, right)
        return node

    def logic_not(self):
        if self.match("NOT"):
            expr = self.logic_not()
            return ("not", expr)
        return self.logic_is()

    def logic_is(self):
        node = self.logic_in()
        while True:
            if self.match("IS"):
                if self.match("NOT"):
                    right = self.logic_in()
                    node = ("is not", node, right)
                else:
                    right = self.logic_in()
                    node = ("is", node, right)
            else:
                break
        return node

    def logic_in(self):
        node = self.equality()
        while True:
            if self.match("NOT"):
                if self.match("IN"):
                    right = self.equality()
                    node = ("not in", node, right)
                else:
                    self.pos -= 1  # Unconsume NOT if not followed by IN
                    break
            elif self.match("IN"):
                right = self.equality()
                node = ("in", node, right)
            else:
                break
        return node

    def equality(self):
        node = self.comparison()
        while True:
            if self.match("EQ"):
                right = self.comparison()
                node = ("==", node, right)
            elif self.match("NEQ"):
                right = self.comparison()
                node = ("!=", node, right)
            else:
                break
        return node

    def comparison(self):
        node = self.additive()
        while True:
            if self.match("LT"):
                right = self.additive()
                node = ("<", node, right)
            elif self.match("LE"):
                right = self.additive()
                node = ("<=", node, right)
            elif self.match("GT"):
                right = self.additive()
                node = (">", node, right)
            elif self.match("GE"):
                right = self.additive()
                node = (">=", node, right)
            elif self.match("EQ"):
                right = self.additive()
                node = ("==", node, right)
            elif self.match("NEQ"):
                right = self.additive()
                node = ("!=", node, right)
            else:
                break
        return node

    def additive(self):
        node = self.term()
        while True:
            if self.match("PLUS"):
                right = self.term()
                node = ("+", node, right)
            elif self.match("MINUS"):
                right = self.term()
                node = ("-", node, right)
            else:
                break
        return node

    def term(self):
        node = self.factor()
        while True:
            if self.match("MULTIPLY"):
                right = self.factor()
                node = ("*", node, right)
            elif self.match("DIVIDE"):
                right = self.factor()
                node = ("/", node, right)
            elif self.match("PERCENT"):
                right = self.factor()
                node = ("%", node, right)
            else:
                break
        return node

    def factor(self):
        token = self.peek()
        if token[0] == "AWAIT":
            self.advance()
            expr = self.factor()
            return ("await_expr", expr)
        if token[0] == "NUMBER":
            self.advance()
            return ("number", token[1])
        elif token[0] == "IDENTIFIER":
            name = token[1]
            self.advance()
            # Check for function call
            if self.peek() and self.peek()[0] == "LPAREN":
                self.advance()  # skip LPAREN
                args = []
                if self.peek() and self.peek()[0] != "RPAREN":
                    while True:
                        args.append(self.expression())
                        if self.match("COMMA"):
                            continue
                        elif self.peek() and self.peek()[0] == "RPAREN":
                            break
                        else:
                            self.error("Expected ',' or ')' in function call")
                if not self.match("RPAREN"):
                    self.error("Expected ')' after function call arguments")
                return ("call", name, args)
            return ("identifier", name)
        elif token[0] == "STRING":
            self.advance()
            # Remove quotes
            return ("string", token[1][1:-1])
        elif token[0] == "LPAREN":
            self.advance()
            expr = self.expression()
            if not self.match("RPAREN"):
                self.error("Expected ')'")
            return expr
        elif token[0] == "LBRACKET":
            return self.list_literal()
        else:
            self.error(f"Unexpected token: {token}")

    def list_literal(self):
        self.match("LBRACKET")
        elements = []
        if not self.match("RBRACKET"):
            while True:
                elements.append(self.expression())
                if self.match("COMMA"):
                    continue
                elif self.match("RBRACKET"):
                    break
                else:
                    raise SyntaxError("Expected ',' or ']' in list literal")
        return ("list", elements)

    def try_statement(self):
        if not self.match("LBRACE"):
            self.error("Expected '{' after 'try'")
        try_block = self.block()
        except_blocks = []
        finally_block = None
        while self.match("EXCEPT"):
            exc_type = None
            exc_var = None
            # Optional exception type
            if self.peek() and self.peek().kind == "IDENTIFIER":
                exc_type = self.match("IDENTIFIER")[1]
            # Optional 'as' exc_var
            if self.match("AS"):
                var_token = self.match("IDENTIFIER")
                if not var_token:
                    self.error("Expected variable name after 'as' in except block")
                exc_var = var_token[1]
            if not self.match("LBRACE"):
                self.error("Expected '{' after 'except' block")
            except_block = self.block()
            except_blocks.append((exc_type, exc_var, except_block))
        if self.match("FINALLY"):
            if not self.match("LBRACE"):
                self.error("Expected '{' after 'finally'")
            finally_block = self.block()
        return ("try", try_block, except_blocks, finally_block)


# --------------------
# RETURN EXCEPTION CLASS
# --------------------
class ReturnException(Exception):
    def __init__(self, value):
        self.value = value


# --------------------
# INTERPRETER CLASS
# --------------------
class Interpreter:
    def __init__(self, filename=None):
        self.filename = filename
        self.env = {}
        self.functions = {}
        self.builtins = {
            "len": lambda x: len(x),
            "str": lambda x: str(x),
            "int": lambda x: int(x),
            "type": lambda x: type(x).__name__,
            "input": lambda prompt="": input(prompt),
            "range": lambda *args: list(range(*args)),
            "sum": lambda x: sum(x),
            "min": lambda x: min(x),
            "max": lambda x: max(x),
            "abs": lambda x: abs(x),
            "sorted": lambda x: sorted(x),
            "reverse": lambda x: list(reversed(x)),
            "append": lambda l, v: l.append(v) or l,
            "pop": lambda l: l.pop(),
            "http_get": lambda url: requests.get(url).text,
            "http_post": lambda url, data: requests.post(url, data=data).text,
            "http_put": lambda url, data: requests.put(url, data=data).text,
            "http_delete": lambda url: requests.delete(url).text,
            "http_head": lambda url: requests.head(url).headers,
            "http_options": lambda url: requests.options(url).headers,
            "http_patch": lambda url, data: requests.patch(url, data=data).text,
            "http_status": lambda response: response.status_code,
            "http_json": lambda response: response.json(),
            "http_text": lambda response: response.text,
            "http_headers": lambda response: response.headers,
            "http_url": lambda response: response.url,
            "http_ok": lambda response: response.ok,
            "http_raise_for_status": lambda response: response.raise_for_status(),
            "sin": lambda x: math.sin(x),
            "cos": lambda x: math.cos(x),
            "tan": lambda x: math.tan(x),
            "sqrt": lambda x: math.sqrt(x),
            "log": lambda x: math.log(x),
            "exp": lambda x: math.exp(x),
            "pow": lambda x, y: math.pow(x, y),
            "math_pi": lambda: math.pi,
            "math_e": lambda: math.e,
            "open": self._bif_open,
            "read": lambda f: f.read(),
            "write": lambda f, data: f.write(data),
            "close": lambda f: f.close(),
            # Dictionary support
            "dict": lambda: {},
            "dict_get": lambda d, k, default=None: d.get(k, default),
            "dict_set": lambda d, k, v: d.__setitem__(k, v) or d,
            "dict_keys": lambda d: list(d.keys()),
            "dict_values": lambda d: list(d.values()),
            # Slicing
            "slice": lambda x, start, end=None: x[start:end],
            # Random and time utilities
            "random": lambda: random.random(),
            "random_choice": lambda x: random.choice(x),
            "randint": lambda a, b: random.randint(a, b),
            "sleep": lambda s: time.sleep(s),
            "time": lambda: time.time(),
            # Date/time
            "now": lambda: datetime.now().isoformat(),
            "strftime": lambda fmt: datetime.now().strftime(fmt),
            # Command-line arguments
            "argv": lambda: sys.argv[1:],
            # Help/docstring
            "help": lambda x=None: (
                str(x.__doc__) if hasattr(x, "__doc__") else "No doc."
            ),
            # Set/tuple
            "set": lambda *args: set(args),
            "tuple": lambda *args: tuple(args),
            "run": self._bif_run,
            "run_async": self._bif_run_async,
            "async": self._bif_async,
            "await": self._bif_await,
            "exit": lambda code=0: sys.exit(code),
            "Error": Error,
            "square": lambda x: float(x * x),
            "mod": lambda x, y: x % y,
            "is_prime": lambda n: n > 1
            and all(n % i != 0 for i in range(2, int(n**0.5) + 1)),
            "join": lambda iterable, sep="": sep.join(map(str, iterable)),
            "split": lambda s, sep=None: s.split(sep),
            "strip": lambda s: s.strip(),
            "startswith": lambda s, prefix: s.startswith(prefix),
            "endswith": lambda s, suffix: s.endswith(suffix),
            "find": lambda s, sub: s.find(sub),
            "replace": lambda s, old, new: s.replace(old, new),
            "upper": lambda s: s.upper(),
            "lower": lambda s: s.lower(),
            "capitalize": lambda s: s.capitalize(),
            "title": lambda s: s.title(),
            "isalpha": lambda s: s.isalpha(),
            "isdigit": lambda s: s.isdigit(),
            "isalnum": lambda s: s.isalnum(),
            "isspace": lambda s: s.isspace(),
            "isupper": lambda s: s.isupper(),
            "islower": lambda s: s.islower(),
            "isnumeric": lambda s: s.isnumeric(),
            "superscript": lambda x: (
                str(x)
                .replace("0", "⁰")
                .replace("1", "¹")
                .replace("2", "²")
                .replace("3", "³")
                .replace("4", "⁴")
                .replace("5", "⁵")
                .replace("6", "⁶")
                .replace("7", "⁷")
                .replace("8", "⁸")
                .replace("9", "⁹")
            ),
            "subscript": lambda x: (
                str(x)
                .replace("0", "₀")
                .replace("1", "₁")
                .replace("2", "₂")
                .replace("3", "₃")
                .replace("4", "₄")
                .replace("5", "₅")
                .replace("6", "₆")
                .replace("7", "₇")
                .replace("8", "₈")
                .replace("9", "₉")
            ),
            "format": lambda s, *args, **kwargs: s.format(*args, **kwargs),
            "fstring": lambda s, **kwargs: s.format(**kwargs),
            "time_now": lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "time_sleep": lambda seconds: time.sleep(seconds),
            "time_timestamp": lambda: int(time.time()),
            "time_utcnow": lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            # Tkinter GUI
            "tk_root": lambda: tk.Tk(),
            "tk_label": lambda root, text: tk.Label(root, text=text),
            "tk_button": lambda root, text, command=None: tk.Button(
                root, text=text, command=command
            ),
            "tk_messagebox": lambda title, message: messagebox.showinfo(title, message),
            "tk_mainloop": lambda root: root.mainloop(),
            "tk_set_title": lambda root, title: root.title(title),
            "tk_mainloop": lambda root: root.mainloop(),
            # Colorama styling
            "colorama_fore": lambda color: getattr(Fore, color.upper(), Fore.RESET),
            "colorama_back": lambda color: getattr(Back, color.upper(), Back.RESET),
            "colorama_style": lambda style: getattr(
                Style, style.upper(), Style.RESET_ALL
            ),
        }
        self._async_tasks = []

    def _bif_open(self, filename, mode="r"):
        return open(filename, mode)

    async def _bif_run(self, filename):
        # Blocking run of another .vlang file (from within async context)
        with open(filename, "r") as f:
            code = f.read()
        tokens = tokenize(code)
        parser = Parser(filename, tokens, code=code)
        ast = parser.parse()
        interpreter = Interpreter()
        interpreter.env = self.env.copy()
        interpreter.functions = self.functions.copy()
        await interpreter.run(ast)
        self.env.update(interpreter.env)
        self.functions.update(interpreter.functions)

    async def _bif_run_async(self, filename):
        # Non-blocking run of another .vlang file (returns a task)
        async def run_file():
            with open(filename, "r") as f:
                code = f.read()
            tokens = tokenize(code)
            parser = Parser(filename, tokens, code=code)
            ast = parser.parse()
            interpreter = Interpreter()
            interpreter.env = self.env.copy()
            interpreter.functions = self.functions.copy()
            await interpreter.run(ast)

        return asyncio.create_task(run_file())

    def _bif_async(self, func, *args):
        # Schedule a function to run asynchronously
        loop = asyncio.get_event_loop()
        task = loop.run_in_executor(None, func, *args)
        self._async_tasks.append(task)
        return task

    def _bif_await(self, task):
        # Await a previously started async task
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(task)

    async def execute_block(self, block, env):
        # Use local variable for speed
        execute = self.execute
        result = None
        for stmt in block:
            result = await execute(stmt, env)
        return result

    async def execute(self, node, env=None):
        # Use local variables for hot lookups
        builtins = self.builtins
        functions = self.functions
        if node[0] == "assign":
            _, name, expr = node
            value = await self.execute(expr, env)
            env[name] = value
            return value
        elif node[0] == "function_decl":
            _, name, params, body = node

            async def func(*args):
                local_env = env.copy()
                for i, param in enumerate(params):
                    local_env[param] = args[i] if i < len(args) else None
                try:
                    return await self.execute_block(body, local_env)
                except ReturnException as ret:
                    return ret.value

            env[name] = func
            self.functions[name] = ("sync", params, body)
        elif node[0] == "async_function_decl":
            _, name, params, body = node

            async def async_func(*args):
                local_env = env.copy()
                for i, param in enumerate(params):
                    local_env[param] = args[i] if i < len(args) else None
                try:
                    return await self.execute_block(body, local_env)
                except ReturnException as ret:
                    return ret.value

            env[name] = async_func
            self.functions[name] = ("async", params, body)
        elif node[0] == "print":
            values = [await self.execute(arg, env) for arg in node[1]]
            print(*values)
        elif node[0] == "expr_stmt":
            return await self.execute(node[1], env)
        elif node[0] == "+":
            return await self.execute(node[1], env) + await self.execute(node[2], env)
        elif node[0] == "-":
            return await self.execute(node[1], env) - await self.execute(node[2], env)
        elif node[0] == "*":
            return await self.execute(node[1], env) * await self.execute(node[2], env)
        elif node[0] == "/":
            return await self.execute(node[1], env) / await self.execute(node[2], env)
        elif node[0] == "%":
            return await self.execute(node[1], env) % await self.execute(node[2], env)
        elif node[0] == "number":
            return node[1]
        elif node[0] == "identifier":
            val = env.get(node[1], builtins.get(node[1], None))
            if val is not None:
                return val
            raise VirtoRuntimeError(
                f"Undefined variable: {node[1]}", filename=self.filename
            )
        elif node[0] == "string":
            return node[1]
        elif node[0] == "if":
            _, cond, then_block, elif_blocks, else_block = node
            if await self.execute(cond, env):
                return await self.execute_block(then_block, env)
            for elif_cond, elif_body in elif_blocks:
                if await self.execute(elif_cond, env):
                    return await self.execute_block(elif_body, env)
            if else_block:
                return await self.execute_block(else_block, env)
        elif node[0] == "while":
            _, cond, body = node
            while await self.execute(cond, env):
                await self.execute_block(body, env)
        elif node[0] == "for":
            _, var, iterable, body = node
            it = await self.execute(iterable, env)
            for val in it:
                env[var] = val
                await self.execute_block(body, env)
        elif node[0] == "list":
            return [await self.execute(e, env) for e in node[1]]
        elif node[0] == "call":
            func = node[1]
            args = node[2]
            if func in builtins:
                bfunc = builtins[func]
                try:
                    result = bfunc(*[await self.execute(arg, env) for arg in args])
                    return result
                except (TypeError, ValueError) as e:
                    msg = str(e)
                    # Custom formatting for missing argument errors
                    if (
                        "missing 1 required positional argument" in msg
                        or "missing a required argument" in msg
                    ):
                        # Try to extract argument name
                        import re as _re

                        m = _re.search(
                            r"missing (?:1 required positional argument: |a required argument: )'([^']+)'",
                            msg,
                        )
                        argname = m.group(1) if m else None
                        if argname:
                            msg = f"{func}() missing required argument '{argname}'"
                        else:
                            msg = f"{func}() missing required argument"
                    elif "got an unexpected keyword argument" in msg:
                        m = _re.search(
                            r"got an unexpected keyword argument '([^']+)'", msg
                        )
                        argname = m.group(1) if m else None
                        if argname:
                            msg = f"{func}() got an unexpected keyword argument '{argname}'"
                        else:
                            msg = f"{func}() got an unexpected keyword argument"
                    elif "takes" in msg and "positional arguments" in msg:
                        # e.g. 'foo() takes 2 positional arguments but 3 were given'
                        msg = f"{func}() {msg}"
                    raise VirtoArgumentError(
                        f"Error in built-in function '{func}': {msg}",
                        filename=self.filename,
                    )
                except Exception as e:
                    raise VirtoRuntimeError(
                        f"Error in built-in function '{func}': {e}",
                        filename=self.filename,
                    )
            elif func in functions:
                ftype, params, body = functions[func]
                local_env = env.copy()
                for i, param in enumerate(params):
                    local_env[param] = (
                        await self.execute(args[i], env) if i < len(args) else None
                    )
                if ftype == "sync":
                    try:
                        for stmt in body:
                            await self.execute(stmt, local_env)
                    except ReturnException as re:
                        return re.value
                elif ftype == "async":

                    async def async_func():
                        try:
                            for stmt in body:
                                await self.execute(stmt, local_env)
                        except ReturnException as re:
                            return re.value

                    return await async_func()
                else:
                    raise VirtoRuntimeError(
                        f"Unknown function type: {ftype}", filename=self.filename
                    )
            else:
                raise VirtoRuntimeError(
                    f"Undefined function: {func}", filename=self.filename
                )
        elif node[0] == "import":
            module_name = node[1]
            vlang_path = os.environ.get("VLANG_PATH", os.getcwd())
            # Support quoted string import: import "C:/test"
            if (module_name.startswith('"') and module_name.endswith('"')) or (
                module_name.startswith("'") and module_name.endswith("'")
            ):
                # Remove quotes
                path = module_name[1:-1]
                if not path.endswith(".vlang"):
                    path += ".vlang"
                filename = path
                if not os.path.isfile(filename):
                    raise RuntimeError(f"Module path '{filename}' not found.")
            else:
                parts = module_name.split(".")
                search_paths = []
                found = False
                if len(parts) == 1:
                    # Try <VLANG_PATH>/packages/test/__init__.vlang
                    dir_init = os.path.join(
                        vlang_path, "packages", parts[0], "__init__.vlang"
                    )
                    search_paths.append(dir_init)
                    # Try <VLANG_PATH>/packages/test.vlang
                    file_mod = os.path.join(vlang_path, "packages", parts[0] + ".vlang")
                    search_paths.append(file_mod)
                    # Try test.vlang in the same directory as the current script
                    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
                        base_dir = os.path.dirname(os.path.abspath(sys.argv[1]))
                    else:
                        base_dir = os.getcwd()
                    local_file = os.path.join(base_dir, parts[0] + ".vlang")
                    search_paths.append(local_file)
                    for candidate in search_paths:
                        if os.path.isfile(candidate):
                            filename = candidate
                            found = True
                            break
                else:
                    # import foo.bar -> <VLANG_PATH>/packages/foo/bar.vlang
                    filename = os.path.join(
                        vlang_path, "packages", *parts[:-1], parts[-1] + ".vlang"
                    )
                    search_paths.append(filename)
                    if os.path.isfile(filename):
                        found = True
                if not found:
                    raise RuntimeError(
                        f"Module '{module_name}' not found. Searched: {search_paths}"
                    )
            with open(filename, "r") as f:
                code = f.read()
            tokens = tokenize(code)
            parser = Parser(tokens, code=code, filename=filename)
            ast = parser.parse()
            await self.execute_block(ast, env)
        elif node[0] == "with":
            resource = await self.execute(node[1], env)
            varname = node[2]
            body = node[3]
            old_env = env.copy()
            env[varname] = resource
            try:
                result = await self.execute_block(body, env)
            finally:
                if hasattr(resource, "close"):
                    resource.close()
            env.update(old_env)
            return result
        elif node[0] == "return":
            value = await self.execute(node[1], env)
            raise ReturnException(value)
        elif node[0] == "await_stmt":
            task = await self.execute(node[1], env)
            if hasattr(task, "__await__"):
                return await task
            return task
        elif node[0] == "run_stmt":
            _, filename_expr = node
            filename = await self.execute(filename_expr, env)
            await self.run_file(filename, env, is_async=False)
        elif node[0] == "run_async_stmt":
            _, filename_expr = node
            filename = await self.execute(filename_expr, env)
            return asyncio.create_task(self.run_file(filename, env, is_async=True))
        elif node[0] == "await_expr":
            _, expr = node
            task = await self.execute(expr, env)
            if hasattr(task, "__await__"):
                return await task
            return task
        elif node[0] == "or":
            return await self.execute(node[1], env) or await self.execute(node[2], env)
        elif node[0] == "and":
            return await self.execute(node[1], env) and await self.execute(node[2], env)
        elif node[0] == "==":
            return await self.execute(node[1], env) == await self.execute(node[2], env)
        elif node[0] == "!=":
            return await self.execute(node[1], env) != await self.execute(node[2], env)
        elif node[0] == "<":
            return await self.execute(node[1], env) < await self.execute(node[2], env)
        elif node[0] == "<=":
            return await self.execute(node[1], env) <= await self.execute(node[2], env)
        elif node[0] == ">":
            return await self.execute(node[1], env) > await self.execute(node[2], env)
        elif node[0] == ">=":
            return await self.execute(node[1], env) >= await self.execute(node[2], env)
        elif node[0] == "not":
            return not await self.execute(node[1], env)
        elif node[0] == "is":
            return await self.execute(node[1], env) is await self.execute(node[2], env)
        elif node[0] == "is not":
            return await self.execute(node[1], env) is not await self.execute(
                node[2], env
            )
        elif node[0] == "in":
            return await self.execute(node[1], env) in await self.execute(node[2], env)
        elif node[0] == "not in":
            return await self.execute(node[1], env) not in await self.execute(
                node[2], env
            )
        elif node[0] == "try":
            try_block = node[1]
            except_blocks = node[2]
            finally_block = node[3]
            try:
                result = await self.execute_block(try_block, env)
            except Exception as exc:
                handled = False
                for exc_type, exc_var, exc_block in except_blocks:
                    if exc_type is None or (type(exc).__name__ == exc_type):
                        local_env = env.copy()
                        if exc_var:
                            local_env[exc_var] = exc
                        await self.execute_block(exc_block, local_env)
                        handled = True
                        break
                if not handled:
                    raise
            finally:
                if finally_block:
                    await self.execute_block(finally_block, env)
            return None
        elif node[0] == "raise":
            exc = await self.execute(node[1], env)
            raise exc
        elif node[0] == "try":
            try_block = node[1]
            except_blocks = node[2]
            finally_block = node[3]
            try:
                result = await self.execute_block(try_block, env)
            except Exception as exc:
                handled = False
                for exc_type, exc_var, exc_block in except_blocks:
                    if exc_type is None or (type(exc).__name__ == exc_type):
                        local_env = env.copy()
                        if exc_var:
                            local_env[exc_var] = exc
                        await self.execute_block(exc_block, local_env)
                        handled = True
                        break
                if not handled:
                    raise
            finally:
                if finally_block:
                    await self.execute_block(finally_block, env)
            return None
        else:
            raise RuntimeError(f"Unknown AST node: {node}")

    async def run(self, ast):
        env = self.env.copy()
        await self.execute_block(ast, env)

    async def run_file(self, filename, env, is_async=False):
        # Load and execute another .vlang file, sharing env and functions
        with open(filename, "r") as f:
            code = f.read()
        tokens = tokenize(code)
        parser = Parser(filename, tokens, code=code)
        ast = parser.parse()
        interpreter = Interpreter(filename)
        # Share environment and functions
        interpreter.env = env.copy()
        interpreter.functions = self.functions.copy()
        if is_async:
            # For run_async, just run and return (as a task in caller)
            await interpreter.run(ast)
        else:
            # For run (sync), run and update caller's env and functions
            await interpreter.run(ast)
            env.update(interpreter.env)
            self.functions.update(interpreter.functions)


# --------------------
# RUNTIME ERROR CLASS
# --------------------
class VirtoRuntimeError(Exception):
    def __init__(self, message, filename, token=None, code=None):
        self.message = message
        self.token = token
        self.filename = filename
        self.code = code
        super().__init__(self.__str__())

    def __str__(self):
        # Only access .line and .column if token is not a string
        if self.token and not isinstance(self.token, str):
            pointer = f"File \"{self.filename or '<input>'}\", line {self.token.line}, col {self.token.column}"
            code_line = ""
            if self.code:
                lines = self.code.splitlines()
                if 1 <= self.token.line <= len(lines):
                    code_line = lines[self.token.line - 1]
            return f"{Fore.RED}RuntimeError: {self.message}\n  {pointer}\n    {code_line}\n    {' '*(self.token.column-1)}^"
        return f"{Fore.RED}RuntimeError: {self.message}"


# --------------------
# MAIN RUN FUNCTION
# --------------------
async def run(code, filename):
    tokens = tokenize(code)
    parser = Parser(filename, tokens, code=code)
    ast = parser.parse()
    interpreter = Interpreter(filename)
    await interpreter.run(ast)


# --------------------
# FILE RUNNER FUNCTION
# --------------------
def run_file(file):
    with open(file, "r") as f:
        code = f.read()
    asyncio.run(run(code, filename=file))


# --------------------
# COMMAND-LINE INTERFACE
# --------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VirtoLang")
    parser.add_argument("file", nargs="?", help="The file to run.")
    parser.add_argument("-C", help="Run code directly instead of a file.")
    parser.add_argument("--code", help="Run code directly instead of a file.")
    parser.add_argument(
        "--version", action="version", version=f"VirtoLang {__version__}"
    )
    parser.add_argument("-V", action="version", version=f"VirtoLang {__version__}")
    args = parser.parse_args()

    try:
        if args.code is not None:
            asyncio.run(run(args.code, filename="<inline>"))
        elif args.C is not None:
            asyncio.run(run(args.C, filename="<inline>"))
        elif args.file:
            if not os.path.isfile(args.file):
                print(f"{Fore.RED}Error: {args.file} is not a valid file.")
                sys.exit(1)
            if os.path.splitext(args.file)[1] != ".vlang":
                print(f"{Fore.RED}Error: {args.file} is not a .vlang file.")
                sys.exit(1)
            # Try running the file
            run_file(args.file)
        else:
            parser.print_usage()
            print(f"{Fore.RED}Error: Must provide a file or use -C/--code to run code.")
            sys.exit(1)
    except ParserError as e:
        print(f"{Fore.RED}{e}")
        sys.exit(1)
    except VirtoArgumentError as e:
        print(f"{Fore.RED}{e}")
        sys.exit(1)
    except VirtoRuntimeError as e:
        print(f"{Fore.RED}{e}")
        sys.exit(1)
    except Exception as e:
        print(f"{Fore.RED}Interpreter bug: {e}")
        # traceback.print_exc()
