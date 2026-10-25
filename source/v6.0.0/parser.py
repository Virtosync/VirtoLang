"""VirtoLang parser.

The parser is the second stage of the interpreter pipeline::

    source text --> Lexer --> tokens --> Parser --> AST --> Interpreter

It reads the flat token list produced by the lexer and builds an *abstract
syntax tree* (AST).  The tree is made of plain Python values:

* Literals are stored as themselves: ``42``, ``3.5``, ``"text"``, ``True``,
  ``None``.
* Everything else is a tuple whose first item is a *tag* naming the kind of
  node, followed by that node's children, e.g. ``("+", left, right)`` or
  ``("IF", condition, then_block, else_block)``.

The full list of node tags is documented next to each ``parse_*`` method
below and consumed by ``interpreter.py``.

Grammar overview (loosely)::

    program     := statement*
    statement   := if | while | for | def | class | try | import | from
                 | with | return | raise | break | continue | assignment | expression
    block       := "{" (statement | NEWLINE | ";")* "}"
    separators  := NEWLINE | ";"
    continuation := newlines inside parentheses, brackets, or dictionary literals

Operator precedence, from loosest to tightest binding::

    or
    and
    not
    comparisons   ==  !=  <  >  <=  >=  in  not in   (chainable: a < b < c)
                 is  is not
    conditional expressions: value_if_true if condition else value_if_false
    + -
    * / // %
    unary + -
    **            (right associative)
    calls, attribute access .name, indexing [i], slicing [a:b:c]
"""

import ast

# Tokens that turn an expression statement into an augmented assignment,
# mapped to the operator text stored in the AST.
_AUGMENTED_OPERATORS = {
    "PLUSEQ": "+=",
    "MINUSEQ": "-=",
    "TIMESEQ": "*=",
    "DIVEQ": "/=",
    "MODEQ": "%=",
    "FLOORDIVEQ": "//=",
    "POWEQ": "**=",
}

# Token types that are comparison operators.
_COMPARISON_TOKENS = frozenset(
    (
        "EQUALS",
        "NOT_EQUALS",
        "LESS_THAN",
        "GREATER_THAN",
        "LESS_EQUAL",
        "GREATER_EQUAL",
    )
)

# Node tags that may appear on the left-hand side of an assignment.
_ASSIGNABLE_TAGS = frozenset(("VAR", "ATTR", "INDEX", "TUPLE"))


class Parser:
    """Turns a token list into an abstract syntax tree.

    Args:
        tokens: The ``(type, text)`` tuples from ``Lexer.tokenize``.
        locations: Optional ``(line, column)`` for each token (parallel to
            ``tokens``); used to attach source positions to nodes and errors.
        eof_location: Position to report for errors at the end of the input.

    Attributes:
        node_locations: Maps ``id(node)`` to the ``(line, column)`` where that
            node starts.  The interpreter uses it to point at the right place
            when a runtime error occurs.
        pos: Index of the next unread token.
    """

    def __init__(self, tokens, locations=None, eof_location=None):
        self.tokens = tokens
        self.locations = locations or []
        self.eof_location = eof_location
        self.node_locations = {}
        self.pos = 0
        # Statement keyword token type -> method that parses that statement.
        self._statement_parsers = {
            "IF": self._parse_if,
            "WHILE": self._parse_while,
            "FOR": self._parse_for,
            "FUNCTION": self._parse_function,
            "CLASS": self._parse_class,
            "TRY": self._parse_try,
            "WITH": self._parse_with,
            "IMPORT": self._parse_import,
            "FROM": self._parse_from_import,
            "RETURN": self._parse_return,
            "RAISE": self._parse_raise,
            "BREAK": self._parse_break,
            "CONTINUE": self._parse_continue,
            "ASYNC": self._parse_async,
            "AT": self._parse_decorated,
            "GLOBAL": self._parse_scope_declaration,
            "NONLOCAL": self._parse_scope_declaration,
            "PASS": self._parse_pass,
            "ASSERT": self._parse_assert,
            "DEL": self._parse_del,
        }
        # One entry per enclosing ``def`` being parsed: {"async": bool, "generator": bool}.
        self._function_stack = []

    # ------------------------------------------------------------------
    # Token helpers
    # ------------------------------------------------------------------

    def _location_at(self, position):
        """Return the ``(line, column)`` of the token at ``position``."""
        if self.locations:
            if position < len(self.locations):
                return self.locations[position]
            if self.eof_location is not None:
                return self.eof_location
            return self.locations[-1]
        return self.eof_location or (1, 1)

    def peek(self):
        """Return the next token without consuming it (``None`` at the end)."""
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def consume(self):
        """Return the next token and advance past it (``None`` at the end)."""
        token = self.peek()
        if token is not None:
            self.pos += 1
        return token

    def _check(self, token_type):
        """True if the next token has the given type."""
        token = self.peek()
        return token is not None and token[0] == token_type

    def _expect(self, token_type, message):
        """Consume a token of the given type or raise ``SyntaxError(message)``."""
        token = self.peek()
        if token is None or token[0] != token_type:
            raise SyntaxError(message)
        self.pos += 1
        return token

    def _expect_identifier(self, message):
        """Consume an identifier token and return its text."""
        return self._expect("IDENTIFIER", message)[1]

    def _skip_semicolons(self):
        """Skip statement separators and empty semicolon statements."""
        while self._check("SEMICOLON") or self._check("NEWLINE"):
            self.pos += 1

    def _mark(self, node, start):
        """Remember that ``node`` begins at token index ``start`` and return it."""
        if isinstance(node, tuple):
            self.node_locations[id(node)] = self._location_at(start)
        return node

    # ------------------------------------------------------------------
    # Program and statements
    # ------------------------------------------------------------------

    def parse_program(self):
        """Parse the whole token stream and return the list of statements."""
        statements = []
        while True:
            self._skip_semicolons()
            if self.peek() is None:
                break
            statements.append(self.parse_statement())
        return statements

    def parse(self):
        """Parse the whole token stream into a single AST node.

        A program with exactly one statement returns that statement's node;
        anything else is wrapped in ``("BLOCK", [statements])``.
        """
        nodes = self.parse_program()
        if len(nodes) == 1:
            return nodes[0]
        return ("BLOCK", nodes)

    def parse_statement(self):
        """Parse one statement, recording its source location.

        Any ``SyntaxError`` raised without a position gets the position of the
        token where parsing stopped.
        """
        start = self.pos
        try:
            node = self._parse_statement()
        except SyntaxError as error:
            if not hasattr(error, "vlang_location"):
                error.vlang_location = self._location_at(self.pos)
            raise
        return self._mark(node, start)

    def _parse_statement(self):
        token = self.peek()
        if token is None:
            raise SyntaxError("Unexpected end of input")
        kind = token[0]

        # Clearer messages for a dangling else/elif.
        if kind == "ELSE":
            raise SyntaxError("Unexpected else without matching if")
        if kind == "ELIF":
            raise SyntaxError("Unexpected elif without matching if")

        handler = self._statement_parsers.get(kind)
        if handler is not None:
            return handler()
        return self._parse_expression_statement()

    def _parse_block(self, open_message, close_message):
        """Parse ``{ statement* }`` and return ``("BLOCK", [statements])``.

        Semicolons between (or after) statements are allowed, which makes
        one-line blocks such as ``if x { a = 1; b = 2 }`` possible.
        """
        self._expect("LBRACE", open_message)
        body = []
        while True:
            self._skip_semicolons()
            token = self.peek()
            if token is None or token[0] == "RBRACE":
                break
            body.append(self.parse_statement())
        self._expect("RBRACE", close_message)
        return ("BLOCK", body)

    # --- imports -------------------------------------------------------

    def _parse_dotted_name(self, message):
        """Parse ``name`` or ``package.module`` and return it as one string."""
        parts = [self._expect_identifier(message)]
        while self._check("DOT"):
            self.pos += 1
            parts.append(self._expect_identifier("Expected name after ."))
        return ".".join(parts)

    def _parse_optional_alias(self):
        """Parse an optional ``as name`` suffix; return the name or ``None``."""
        if self._check("AS"):
            self.pos += 1
            return self._expect_identifier("Expected alias after as")
        return None

    def _parse_import(self):
        """``import a [as x][, b [as y]]``  ->  ``("IMPORT", module, alias)``."""
        self.consume()
        nodes = []
        while True:
            module = self._parse_dotted_name("Expected module name after import")
            nodes.append(("IMPORT", module, self._parse_optional_alias()))
            if self._check("COMMA"):
                self.pos += 1
                continue
            break
        return nodes[0] if len(nodes) == 1 else ("BLOCK", nodes)

    def _parse_from_import(self):
        """``from m import a [as x][, b]``  ->  ``("FROMIMPORT", m, name, alias)``.

        ``m`` may be relative (``.sibling``, ``..pkg.mod`` or just ``.``) and
        ``name`` may be ``*`` to import every public name.
        """
        self.consume()
        dots = ""
        while self._check("DOT"):
            self.pos += 1
            dots += "."
        if dots and self._check("IMPORT"):
            module = dots
        else:
            module = dots + self._parse_dotted_name("Expected module name after from")
        self._expect("IMPORT", "Expected import after from")
        if self._check("MULTIPLY"):
            self.pos += 1
            return ("FROMIMPORT", module, "*", None)
        nodes = []
        while True:
            name = self._expect_identifier("Expected name after from X import")
            nodes.append(("FROMIMPORT", module, name, self._parse_optional_alias()))
            if self._check("COMMA"):
                self.pos += 1
                continue
            break
        return nodes[0] if len(nodes) == 1 else ("BLOCK", nodes)

    # --- simple keyword statements --------------------------------------

    def _parse_return(self):
        """``return [expr]``  ->  ``("RETURN", expr_or_None)``.

        The value is optional only when ``return`` is followed by a statement
        separator, ``}``, or the end of the file.
        """
        self.consume()
        token = self.peek()
        if token is None or token[0] in ("SEMICOLON", "NEWLINE", "RBRACE"):
            return ("RETURN", None)
        return ("RETURN", self._parse_expression_list())

    def _parse_raise(self):
        """``raise expr``  ->  ``("RAISE", expr)``."""
        self.consume()
        return ("RAISE", self.parse_expression())

    def _parse_break(self):
        """``break``  ->  ``("BREAK",)``."""
        self.consume()
        return ("BREAK",)

    def _parse_continue(self):
        """``continue``  ->  ``("CONTINUE",)``."""
        self.consume()
        return ("CONTINUE",)

    def _parse_pass(self):
        """``pass``  ->  ``("PASS",)`` (a statement that does nothing)."""
        self.consume()
        return ("PASS",)

    def _parse_assert(self):
        """``assert cond [, message]``  ->  ``("ASSERT", cond, message_or_None)``."""
        self.consume()
        condition = self.parse_expression()
        message = None
        if self._check("COMMA"):
            self.consume()
            message = self.parse_expression()
        return ("ASSERT", condition, message)

    def _parse_del(self):
        """``del a, b[0], c.x``  ->  ``("DEL", [targets])``."""
        self.consume()
        targets = []
        while True:
            target = self.parse_or()
            if not (
                isinstance(target, tuple) and target[0] in ("VAR", "ATTR", "INDEX")
            ):
                raise SyntaxError("Invalid target for del")
            targets.append(target)
            if not self._check("COMMA"):
                break
            self.consume()
        return ("DEL", targets)

    def _parse_scope_declaration(self):
        """``global a, b`` / ``nonlocal a, b``  ->  ``("GLOBAL"|"NONLOCAL", [names])``."""
        tag = "GLOBAL" if self.consume()[0] == "GLOBAL" else "NONLOCAL"
        names = [self._expect_identifier("Expected a variable name")]
        while self._check("COMMA"):
            self.consume()
            names.append(self._expect_identifier("Expected a variable name after ,"))
        return (tag, names)

    def _parse_async(self):
        """``async def`` / ``async for`` / ``async with``."""
        self.consume()
        token = self.peek()
        kind = token[0] if token else None
        if kind == "FUNCTION":
            return self._parse_function(is_async=True)
        if kind in ("FOR", "WITH"):
            if self._function_stack and not self._function_stack[-1]["async"]:
                raise SyntaxError(f"'async {token[1]}' outside async function")
            return self._parse_for(True) if kind == "FOR" else self._parse_with(True)
        raise SyntaxError("Expected def, for or with after async")

    def _parse_decorated(self):
        """``@decorator`` lines followed by a ``def`` or ``class``.

        Produces ``("DECORATED", [decorator expressions], definition_node)``.
        Decorators are applied bottom-up, like Python.
        """
        decorators = []
        while self._check("AT"):
            self.consume()
            decorators.append(self.parse_expression())
            while self._check("NEWLINE"):
                self.consume()
        definition = self._parse_statement()
        if not (
            isinstance(definition, tuple) and definition[0] in ("FUNCDEF", "CLASS")
        ):
            raise SyntaxError("Decorators must be followed by def or class")
        return ("DECORATED", decorators, definition)

    # --- control flow ---------------------------------------------------

    def _parse_if(self):
        """``if cond { } [elif cond { }]* [else { }]``.

        Produces ``("IF", condition, then_block, else_block_or_None)``.
        ``elif`` and ``else if`` become a nested ``IF`` in the else slot.
        """
        keyword = self.consume()[1]  # "if" or "elif"
        condition = self.parse_expression()
        then_block = self._parse_block(
            f"Expected {{ after {keyword} condition",
            f"Expected }} after {keyword} body",
        )
        else_block = None
        while self._check("NEWLINE"):
            self.consume()
        if self._check("ELIF"):
            else_block = self._parse_if()
        elif self._check("ELSE"):
            self.consume()
            if self._check("IF"):
                else_block = self.parse_statement()
            else:
                else_block = self._parse_block(
                    "Expected { after else", "Expected } after else body"
                )
        return ("IF", condition, then_block, else_block)

    def _parse_while(self):
        """``while cond { }``  ->  ``("WHILE", condition, block)``."""
        self.consume()
        condition = self.parse_expression()
        body = self._parse_block(
            "Expected { after while condition", "Expected } after while body"
        )
        return ("WHILE", condition, body)

    def _parse_for(self, is_async=False):
        """``for name in iterable { }``  ->  ``("FOR", target, iterable, block)``.

        ``target`` is a single name (string) or, for ``for a, b in ...``,
        a tuple of names that each item is unpacked into.  ``async for``
        produces an ``ASYNCFOR`` node of the same shape.
        """
        self.consume()
        names = [self._expect_identifier("Expected identifier after for")]
        while self._check("COMMA"):
            self.pos += 1
            names.append(self._expect_identifier("Expected identifier after ,"))
        self._expect("IN", "Expected in in for")
        iterable = self.parse_expression()
        body = self._parse_block("Expected { after for", "Expected } after for body")
        target = names[0] if len(names) == 1 else tuple(names)
        return ("ASYNCFOR" if is_async else "FOR", target, iterable, body)

    # --- definitions ------------------------------------------------------

    def _parse_function(self, is_async=False):
        """``def name(a, b=1, *args, key, opt=2, **kwargs) { }``.

        Produces ``("FUNCDEF", name, [positional names], body, {name: default_expr},
        extras)``.  ``extras`` is ``None`` for plain functions, otherwise a dict
        with ``posonly``, ``vararg``, ``kwonly`` (names after ``*``), ``kwarg``,
        ``async`` and ``generator`` entries.
        """
        self.consume()
        name = self._expect_identifier("Expected function name")
        self._expect("LPAREN", "Expected ( after function name")
        params = []
        defaults = {}
        kwonly = []
        vararg = kwarg = None
        seen_star = False
        posonly_count = None
        while not self._check("RPAREN"):
            if kwarg is not None:
                raise SyntaxError("No parameters may follow **kwargs")
            if self._check("DIVIDE"):
                if seen_star or posonly_count is not None or not params:
                    raise SyntaxError("Invalid positional-only parameter separator")
                self.consume()
                posonly_count = len(params)
            elif self._check("POWER"):
                self.consume()
                kwarg = self._expect_identifier("Expected name after **")
            elif self._check("MULTIPLY"):
                if seen_star:
                    raise SyntaxError("Only one * parameter is allowed")
                self.consume()
                seen_star = True
                if self._check("IDENTIFIER"):
                    vararg = self.consume()[1]
                elif not self._check("COMMA"):
                    raise SyntaxError("Expected name or , after *")
            else:
                param = self._expect_identifier("Expected parameter name")
                if param in params or param in kwonly or param in (vararg, kwarg):
                    raise SyntaxError(f"Duplicate parameter name {param!r}")
                has_default = False
                if self._check("ASSIGN"):
                    self.pos += 1
                    defaults[param] = self.parse_expression()
                    has_default = True
                if seen_star:
                    kwonly.append(param)
                else:
                    if not has_default and defaults:
                        raise SyntaxError(
                            "Parameter without default follows default parameter"
                        )
                    params.append(param)
            if self._check("COMMA"):
                self.pos += 1
                continue
            break
        self._expect("RPAREN", "Expected ) after params")
        if seen_star and vararg is None and not kwonly:
            raise SyntaxError("Named parameter required after bare *")
        if posonly_count is None:
            posonly_count = 0

        context = {"async": is_async, "generator": False}
        self._function_stack.append(context)
        try:
            body = self._parse_block(
                "Expected { for function body", "Expected } after function body"
            )
        finally:
            self._function_stack.pop()
        extras = None
        if (
            posonly_count
            or vararg
            or kwonly
            or kwarg
            or is_async
            or context["generator"]
        ):
            extras = {
                "posonly": tuple(params[:posonly_count]),
                "vararg": vararg,
                "kwonly": tuple(kwonly),
                "kwarg": kwarg,
                "async": is_async,
                "generator": context["generator"],
                "async_generator": is_async and context["generator"],
            }
        return ("FUNCDEF", name, params, body, defaults, extras)

    def _parse_class(self):
        """``class Name[(Base, ...)] { }``  ->  ``("CLASS", name, block, [bases])``."""
        self.consume()
        name = self._expect_identifier("Expected class name after class")
        bases = []
        if self._check("LPAREN"):
            self.pos += 1
            while not self._check("RPAREN"):
                bases.append(self._expect_identifier("Expected base class name"))
                if self._check("COMMA"):
                    self.pos += 1
                    continue
                break
            self._expect("RPAREN", "Expected ) after base classes")
        body = self._parse_block(
            "Expected { for class body", "Expected } after class body"
        )
        return ("CLASS", name, body, bases)

    def _parse_try(self):
        """``try { } except [Type] [as name] { } ... [finally { }]``.

        Produces ``("TRY", try_block, handlers, finally_block_or_None)`` where
        each handler is ``(type_expr_or_None, alias_or_None, block)``.
        """
        self.consume()
        try_block = self._parse_block(
            "Expected { after try", "Expected } after try body"
        )
        handlers = []
        while self._check("NEWLINE"):
            self.consume()
        while self._check("EXCEPT"):
            self.consume()
            exception_type = None
            alias = None
            if not self._check("LBRACE") and not self._check("AS"):
                exception_type = self.parse_expression()
            if self._check("AS"):
                self.pos += 1
                alias = self._expect_identifier("Expected name after as")
            body = self._parse_block(
                "Expected { after except", "Expected } after except body"
            )
            handlers.append((exception_type, alias, body))
            while self._check("NEWLINE"):
                self.consume()
        finally_block = None
        if self._check("FINALLY"):
            self.consume()
            finally_block = self._parse_block(
                "Expected { after finally", "Expected } after finally body"
            )
        return ("TRY", try_block, handlers, finally_block)

    def _parse_with(self, is_async=False):
        """Parse ``with manager [as name], ... { body }`` (``async with`` too)."""
        self.consume()
        managers = []
        while True:
            manager = self.parse_or()
            target = None
            if self._check("AS"):
                self.consume()
                target = self._expect_identifier("Expected name after as")
            managers.append((manager, target))
            if not self._check("COMMA"):
                break
            self.consume()
        body = self._parse_block(
            "Expected { after with items", "Expected } after with body"
        )
        return ("ASYNCWITH" if is_async else "WITH", managers, body)

    # --- assignments and expression statements ----------------------------

    def _parse_expression_statement(self):
        """Parse an expression, or an assignment if ``=``/``+=``/... follows.

        * ``target = value``   -> ``("ASSIGN_LHS", target, value)``
        * ``target += value``  -> ``("AUGASSIGN", "+=", target, value)``
        * otherwise the bare expression node is returned.

        A target must be a variable, an attribute (``a.b``) or an index
        (``a[i]``).
        """
        # A comma-separated bare name list (optionally with one ``*rest``) is an
        # assignment target only when an equals sign follows.
        if self._check("IDENTIFIER") or self._check("MULTIPLY"):
            end = self.pos
            targets = []
            starred = 0
            tokens = self.tokens
            size = len(tokens)
            while end < size:
                if (
                    tokens[end][0] == "MULTIPLY"
                    and end + 1 < size
                    and tokens[end + 1][0] == "IDENTIFIER"
                ):
                    targets.append(("STAR", ("VAR", tokens[end + 1][1])))
                    starred += 1
                    end += 2
                elif tokens[end][0] == "IDENTIFIER":
                    targets.append(("VAR", tokens[end][1]))
                    end += 1
                else:
                    break
                if end < size and tokens[end][0] == "COMMA":
                    end += 1
                    continue
                break
            if len(targets) > 1 and end < size and tokens[end][0] == "ASSIGN":
                if starred > 1:
                    raise SyntaxError("Only one starred name is allowed in unpacking")
                self.pos = end + 1
                return ("ASSIGN_LHS", ("TUPLE", targets), self._parse_expression_list())

        expression = self.parse_expression()
        token = self.peek()
        if token is None:
            return expression
        if token[0] == "ASSIGN" or token[0] in _AUGMENTED_OPERATORS:
            if not (
                isinstance(expression, tuple) and expression[0] in _ASSIGNABLE_TAGS
            ):
                raise SyntaxError("Invalid assignment target")
            self.consume()
            value = self._parse_expression_list()
            if token[0] == "ASSIGN":
                return ("ASSIGN_LHS", expression, value)
            return ("AUGASSIGN", _AUGMENTED_OPERATORS[token[0]], expression, value)
        return expression

    def _parse_expression_list(self):
        """Parse a comma-separated value list as a tuple expression."""
        first = self.parse_expression()
        if not self._check("COMMA"):
            return first
        values = [first]
        while self._check("COMMA"):
            self.consume()
            if (
                self.peek() is None
                or self._check("SEMICOLON")
                or self._check("NEWLINE")
                or self._check("RBRACE")
            ):
                break
            values.append(self.parse_expression())
        return ("TUPLE", values)

    def _conditional_else_ahead(self):
        """Distinguish a ternary ``if`` from the next braced if-statement.

        A newline is a statement boundary unless the lexer identified it as an
        expression continuation. A complete ``condition { block } else
        { block }`` can therefore follow an expression without a semicolon.
        """
        depth = 0
        previous = None
        for index in range(self.pos, len(self.tokens)):
            kind = self.tokens[index][0]
            if depth == 0:
                if kind == "ELSE":
                    return True
                if kind in ("SEMICOLON", "NEWLINE", "RBRACE"):
                    return False
                if kind == "LBRACE":
                    # A dictionary can be the whole condition or follow a
                    # boolean operator; a brace after a completed condition
                    # opens the body of a compound if statement.
                    if previous not in ("IF", "AND", "OR", "NOT", "LPAREN"):
                        return False
                    depth += 1
                    previous = kind
                    continue
            if kind in ("LPAREN", "LBRACKET", "LBRACE"):
                depth += 1
            elif kind in ("RPAREN", "RBRACKET", "RBRACE"):
                depth -= 1
            previous = kind
        return False

    # ------------------------------------------------------------------
    # Expressions (lowest precedence first)
    # ------------------------------------------------------------------

    def parse_semicolon_eol(self):
        """Consume one optional ``;`` (kept for backwards compatibility)."""
        if self._check("SEMICOLON"):
            self.consume()

    def parse_expression(self):
        """Parse a lambda, conditional expression, yield, or ordinary expression."""
        start = self.pos
        if self._check("YIELD"):
            return self._mark(self._parse_yield(), start)
        if self._check("LAMBDA"):
            self.consume()
            params = []
            if not self._check("COLON"):
                while True:
                    params.append(self._expect_identifier("Expected lambda parameter"))
                    if not self._check("COMMA"):
                        break
                    self.consume()
            self._expect("COLON", "Expected : after lambda parameters")
            body = self.parse_expression()
            return self._mark(("LAMBDA", params, body), start)

        if (
            self._check("IDENTIFIER")
            and self.pos + 1 < len(self.tokens)
            and self.tokens[self.pos + 1][0] == "WALRUS"
        ):
            name = self.consume()[1]
            self.consume()
            return self._mark(("WALRUS", name, self.parse_expression()), start)

        value = self.parse_or()
        if self._check("IF") and self._conditional_else_ahead():
            self.consume()
            condition = self.parse_or()
            self._expect("ELSE", "Expected else in conditional expression")
            fallback = self.parse_expression()
            return self._mark(("CONDITIONAL", condition, value, fallback), start)
        return value

    def _parse_yield(self):
        """``yield [value]`` / ``yield from iterable``; only valid inside ``def``."""
        if not self._function_stack:
            raise SyntaxError("'yield' outside function")
        self._function_stack[-1]["generator"] = True
        self.consume()
        if self._check("FROM"):
            if self._function_stack[-1]["async"]:
                raise SyntaxError("'yield from' is not allowed in an async function")
            self.consume()
            return ("YIELDFROM", self.parse_expression())
        token = self.peek()
        if token is None or token[0] in (
            "SEMICOLON",
            "NEWLINE",
            "RBRACE",
            "RPAREN",
            "RBRACKET",
            "COMMA",
        ):
            return ("YIELD", None)
        return ("YIELD", self._parse_expression_list())

    def parse_or(self):
        """``a or b``  ->  ``("OR", a, b)`` (left associative)."""
        start = self.pos
        node = self.parse_and()
        while self._check("OR"):
            self.consume()
            node = self._mark(("OR", node, self.parse_and()), start)
        return node

    def parse_and(self):
        """``a and b``  ->  ``("AND", a, b)`` (left associative)."""
        start = self.pos
        node = self.parse_not()
        while self._check("AND"):
            self.consume()
            node = self._mark(("AND", node, self.parse_not()), start)
        return node

    def parse_not(self):
        """``not a``  ->  ``("NOT", a)``."""
        if self._check("NOT"):
            start = self.pos
            self.consume()
            return self._mark(("NOT", self.parse_not()), start)
        return self.parse_compare()

    def _comparison_operator(self):
        """Consume and return a comparison operator's text, or ``None``.

        Handles ``==  !=  <  >  <=  >=  in`` and the two-token ``not in``.
        """
        token = self.peek()
        if token is None:
            return None
        if token[0] in _COMPARISON_TOKENS:
            self.pos += 1
            return token[1]
        if token[0] == "IN":
            self.pos += 1
            return "in"
        if token[0] == "NOT":
            following = (
                self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else None
            )
            if following is not None and following[0] == "IN":
                self.pos += 2
                return "not in"
        if token[0] == "IS":
            self.pos += 1
            if self._check("NOT"):
                self.pos += 1
                return "is not"
            return "is"
        return None

    def parse_compare(self):
        """Comparisons, which can be chained like in Python.

        ``a < b``       ->  ``("COMPARE", "<", a, b)``
        ``a < b < c``   ->  ``("CMPCHAIN", a, [("<", b), ("<", c)])``
        """
        start = self.pos
        left = self.parse_add()
        operations = []
        while True:
            operator = self._comparison_operator()
            if operator is None:
                break
            operations.append((operator, self.parse_add()))
        if not operations:
            return left
        if len(operations) == 1:
            operator, right = operations[0]
            return self._mark(("COMPARE", operator, left, right), start)
        return self._mark(("CMPCHAIN", left, operations), start)

    def parse_add(self):
        """``a + b`` and ``a - b``  ->  ``("+", a, b)`` / ``("-", a, b)``."""
        start = self.pos
        node = self.parse_term()
        while True:
            token = self.peek()
            if token is not None and token[0] in ("PLUS", "MINUS"):
                self.pos += 1
                node = self._mark((token[1], node, self.parse_term()), start)
            else:
                return node

    def _starts_unpacking_statement(self):
        """True if the ``*`` at the cursor begins a new line holding ``*a, b = ...``.

        This protects unpacking syntax if a starred target reaches expression
        parsing as a multiplication operator.
        """
        pos = self.pos
        if pos == 0 or pos >= len(self.locations):
            return False
        if self.locations[pos][0] <= self.locations[pos - 1][0]:
            return False
        tokens = self.tokens
        size = len(tokens)
        while pos < size:
            if tokens[pos][0] == "MULTIPLY":
                pos += 1
            if pos >= size or tokens[pos][0] != "IDENTIFIER":
                return False
            pos += 1
            if pos < size and tokens[pos][0] == "COMMA":
                pos += 1
                continue
            return pos < size and tokens[pos][0] == "ASSIGN"
        return False

    def parse_term(self):
        """``a * b``, ``a / b``, ``a // b``, ``a % b``  ->  ``(op, a, b)``."""
        start = self.pos
        node = self.parse_unary()
        while True:
            token = self.peek()
            if token is not None and token[0] in (
                "MULTIPLY",
                "DIVIDE",
                "FLOORDIV",
                "MODULO",
            ):
                if token[0] == "MULTIPLY" and self._starts_unpacking_statement():
                    return node
                self.pos += 1
                node = self._mark((token[1], node, self.parse_unary()), start)
            else:
                return node

    def parse_unary(self):
        """Prefix ``+``, ``-`` and ``not``  ->  ``("UNARY", op, a)`` / ``("NOT", a)``."""
        token = self.peek()
        if token is None:
            raise SyntaxError("Unexpected end of input")
        start = self.pos
        if token[0] in ("PLUS", "MINUS"):
            self.pos += 1
            return self._mark(("UNARY", token[1], self.parse_unary()), start)
        if token[0] == "NOT":
            self.pos += 1
            return self._mark(("NOT", self.parse_unary()), start)
        if token[0] == "AWAIT":
            if self._function_stack and not self._function_stack[-1]["async"]:
                raise SyntaxError("'await' outside async function")
            self.pos += 1
            return self._mark(("AWAIT", self.parse_power()), start)
        return self.parse_power()

    def parse_power(self):
        """``a ** b``  ->  ``("**", a, b)``; right associative, binds tighter
        than a unary minus on its left (``-2 ** 2`` is ``-4``)."""
        start = self.pos
        base = self.parse_primary()
        if self._check("POWER"):
            self.consume()
            return self._mark(("**", base, self.parse_unary()), start)
        return base

    def parse_factor(self):
        """Backwards-compatible alias for ``parse_unary``."""
        return self.parse_unary()

    def parse_primary(self):
        """Parse a literal, name, list, dict, tuple or parenthesised expression,
        followed by any calls / attribute accesses / subscripts."""
        start = self.pos
        token = self.peek()
        if token is None:
            raise SyntaxError("Unexpected end of input")
        kind = token[0]

        if kind == "NUM":
            self.pos += 1
            text = token[1]
            if "." in text or "e" in text or "E" in text:
                return float(text)
            return int(text)
        if kind == "STRING":
            self.pos += 1
            return self._mark(self._string_node(token[1]), start)
        if kind == "TRUE":
            self.pos += 1
            return True
        if kind == "FALSE":
            self.pos += 1
            return False
        if kind == "NONE":
            self.pos += 1
            return None
        if kind == "IDENTIFIER":
            self.pos += 1
            return self._mark(self._postfix(("VAR", token[1])), start)
        if kind == "LBRACKET":
            return self._mark(self._postfix(self._parse_list()), start)
        if kind == "LBRACE":
            return self._mark(self._postfix(self._parse_dict()), start)
        if kind == "LPAREN":
            return self._mark(self._postfix(self._parse_parenthesised()), start)
        raise SyntaxError(f"Unexpected token {token[1]!r}")

    def _string_node(self, text):
        """Convert a STRING token into a value or node.

        * plain / bytes / raw strings become the Python ``str``/``bytes`` value
          (with any trailing ``.method()`` postfix applied afterwards);
        * ``f"..."`` becomes ``("FSTRING", inner_text, prefix, quote)``;
        * ``re"..."`` becomes ``("REGEX", pattern_text)``.
        """
        quote_index = next((i for i, ch in enumerate(text) if ch in "'\""), 0)
        prefix = text[:quote_index]
        literal = text[quote_index:]
        lowered = prefix.lower()
        width = 3 if literal[:3] in ('"""', "'''") and len(literal) >= 6 else 1
        if "f" in lowered:
            return self._postfix(("FSTRING", literal[width:-width], prefix, literal[0]))
        if lowered.startswith("re"):
            return self._postfix(("REGEX", literal[width:-width]))
        value = ast.literal_eval(text)
        return self._postfix(value)

    def _parse_element(self):
        """Parse one list/tuple/set item: an expression or ``*iterable``."""
        if self._check("MULTIPLY"):
            self.consume()
            return ("STAR", self.parse_or())
        return self.parse_expression()

    @staticmethod
    def _is_star(node):
        """True if ``node`` is a ``("STAR", expr)`` spread."""
        return node.__class__ is tuple and node[0] == "STAR"

    def _has_star(self, items):
        """True if any item is a ``("STAR", expr)`` spread."""
        return any(self._is_star(item) for item in items)

    def _parse_list(self):
        """Parse a list literal or list comprehension."""
        self.consume()
        items = []
        if not self._check("RBRACKET"):
            first = self._parse_element()
            if self._check("FOR") and not self._is_star(first):
                clauses = self._parse_comprehension_clauses()
                self._expect("RBRACKET", "Expected ] after comprehension")
                return ("LISTCOMP", first, clauses)
            items.append(first)
            while self._check("COMMA"):
                self.pos += 1
                if self._check("RBRACKET"):
                    break
                items.append(self._parse_element())
        self._expect("RBRACKET", "Expected ]")
        return ("LIST_S" if self._has_star(items) else "LIST", items)

    def _parse_dict_entries(self, pairs):
        """Parse the remaining ``, key: value`` / ``, **mapping`` entries."""
        while self._check("COMMA"):
            self.consume()
            if self._check("RBRACE"):
                break
            if self._check("POWER"):
                self.consume()
                pairs.append((None, self.parse_or()))
                continue
            key = self.parse_expression()
            self._expect("COLON", "Expected : after dictionary key")
            pairs.append((key, self.parse_expression()))
        self._expect("RBRACE", "Expected }")
        spread = any(key is None for key, _ in pairs)
        return ("DICT_S" if spread else "DICT", pairs)

    def _parse_dict(self):
        """Parse a dict/set literal or a dict/set comprehension."""
        self.consume()
        if self._check("RBRACE"):
            self.consume()
            return ("DICT", [])
        if self._check("POWER"):
            self.consume()
            return self._parse_dict_entries([(None, self.parse_or())])

        first = self._parse_element()
        if self._check("COLON") and not self._is_star(first):
            self.consume()
            first_value = self.parse_expression()
            if self._check("FOR"):
                clauses = self._parse_comprehension_clauses()
                self._expect("RBRACE", "Expected } after comprehension")
                return ("DICTCOMP", first, first_value, clauses)
            return self._parse_dict_entries([(first, first_value)])

        if self._check("FOR") and not self._is_star(first):
            clauses = self._parse_comprehension_clauses()
            self._expect("RBRACE", "Expected } after comprehension")
            return ("SETCOMP", first, clauses)

        items = [first]
        while self._check("COMMA"):
            self.consume()
            if self._check("RBRACE"):
                break
            items.append(self._parse_element())
        self._expect("RBRACE", "Expected }")
        return ("SET_S" if self._has_star(items) else "SET", items)

    def _parse_comprehension_clauses(self):
        """Parse one or more ``for target in iterable [if condition]`` clauses."""
        clauses = []
        while self._check("FOR"):
            self.consume()
            names = [self._expect_identifier("Expected name after for")]
            while self._check("COMMA"):
                self.consume()
                names.append(self._expect_identifier("Expected name after ,"))
            self._expect("IN", "Expected in in comprehension")
            iterable = self.parse_or()
            filters = []
            while self._check("IF"):
                self.consume()
                filters.append(self.parse_or())
            target = names[0] if len(names) == 1 else tuple(names)
            clauses.append((target, iterable, filters))
        return clauses

    def _parse_parenthesised(self):
        """``( expr )`` groups; ``(a, b)`` / ``()`` / ``(a,)`` build tuples."""
        self.consume()
        if self._check("RPAREN"):
            self.consume()
            return ("TUPLE", [])
        first = self._parse_element()
        if self._check("FOR") and not self._is_star(first):
            clauses = self._parse_comprehension_clauses()
            self._expect("RPAREN", "Expected ) after generator expression")
            return ("GENEXP", first, clauses)
        if self._check("COMMA") or self._is_star(first):
            items = [first]
            while self._check("COMMA"):
                self.pos += 1
                if self._check("RPAREN"):
                    break
                items.append(self._parse_element())
            self._expect("RPAREN", "Expected )")
            return ("TUPLE_S" if self._has_star(items) else "TUPLE", items)
        self._expect("RPAREN", "Expected )")
        return first

    def _parse_subscript(self):
        """Parse what is inside ``[...]``: an index or a slice ``a:b:c``.

        Returns the index expression, or ``("SLICE", lower, upper, step)``.
        """
        lower = None
        if not self._check("COLON"):
            lower = self.parse_expression()
        if not self._check("COLON"):
            self._expect("RBRACKET", "Expected ] after index")
            return lower
        self.consume()
        upper = step = None
        if not self._check("COLON") and not self._check("RBRACKET"):
            upper = self.parse_expression()
        if self._check("COLON"):
            self.consume()
            if not self._check("RBRACKET"):
                step = self.parse_expression()
        self._expect("RBRACKET", "Expected ] after index")
        return ("SLICE", lower, upper, step)

    def _parse_call_arguments(self):
        """Parse call arguments after ``(``; returns ``(positional, keyword)``.

        ``keyword`` is a list of ``(name, expr)`` pairs from ``name=value``.
        ``*items`` becomes ``("STAR", expr)`` in ``positional`` and ``**mapping``
        becomes ``(None, expr)`` in ``keyword``.  A lone ``f(x for x in y)``
        argument becomes a ``GENEXP`` node.
        """
        args = []
        kwargs = []
        while not self._check("RPAREN"):
            following = (
                self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else None
            )
            if self._check("POWER"):
                self.consume()
                kwargs.append((None, self.parse_expression()))
            elif self._check("MULTIPLY"):
                self.consume()
                if any(name is None for name, _ in kwargs):
                    raise SyntaxError("Iterable argument follows ** argument")
                args.append(("STAR", self.parse_expression()))
            elif self._check("IDENTIFIER") and following and following[0] == "ASSIGN":
                name = self.consume()[1]
                self.consume()
                kwargs.append((name, self.parse_expression()))
            else:
                if kwargs:
                    raise SyntaxError("Positional argument follows keyword argument")
                value = self.parse_expression()
                if self._check("FOR"):
                    if args:
                        raise SyntaxError(
                            "Generator expression must be the only argument"
                        )
                    clauses = self._parse_comprehension_clauses()
                    value = ("GENEXP", value, clauses)
                args.append(value)
            if self._check("COMMA"):
                self.pos += 1
                continue
            break
        self._expect("RPAREN", "Expected ) after call")
        return args, kwargs

    def _postfix(self, node):
        """Apply trailing ``(...)``, ``.name`` and ``[...]`` to ``node``.

        * call      -> ``("CALL", func, [args], [(name, value), ...])``
        * attribute -> ``("ATTR", obj, name)``
        * subscript -> ``("INDEX", obj, index_or_slice)``
        """
        while True:
            token = self.peek()
            if token is None:
                return node
            kind = token[0]
            if kind == "LPAREN":
                self.consume()
                args, kwargs = self._parse_call_arguments()
                special = self._has_star(args) or any(
                    name is None for name, _ in kwargs
                )
                node = ("CALL_S" if special else "CALL", node, args, kwargs)
            elif kind == "DOT":
                self.consume()
                name = self._expect_identifier("Expected attribute name after .")
                node = ("ATTR", node, name)
            elif kind == "LBRACKET":
                self.consume()
                node = ("INDEX", node, self._parse_subscript())
            else:
                return node
