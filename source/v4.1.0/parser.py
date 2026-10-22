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
                 | return | raise | break | continue | assignment | expression
    block       := "{" (statement | ";")* "}"
    separators  := statements may be separated by whitespace, newlines or ";"

Operator precedence, from loosest to tightest binding::

    or
    and
    not
    comparisons   ==  !=  <  >  <=  >=  in  not in   (chainable: a < b < c)
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
_ASSIGNABLE_TAGS = frozenset(("VAR", "ATTR", "INDEX"))


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
            "IMPORT": self._parse_import,
            "FROM": self._parse_from_import,
            "RETURN": self._parse_return,
            "RAISE": self._parse_raise,
            "BREAK": self._parse_break,
            "CONTINUE": self._parse_continue,
        }

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
        """Skip any number of ``;`` separators (empty statements are allowed)."""
        while self._check("SEMICOLON"):
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
        """``from m import a [as x][, b]``  ->  ``("FROMIMPORT", m, name, alias)``."""
        self.consume()
        module = self._parse_dotted_name("Expected module name after from")
        self._expect("IMPORT", "Expected import after from")
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

        The value is optional only when ``return`` is followed by ``;`` or
        ``}`` (or the end of the file).
        """
        self.consume()
        token = self.peek()
        if token is None or token[0] in ("SEMICOLON", "RBRACE"):
            return ("RETURN", None)
        return ("RETURN", self.parse_expression())

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

    # --- control flow ---------------------------------------------------

    def _parse_if(self):
        """``if cond { } [elif cond { }]* [else { }]``.

        Produces ``("IF", condition, then_block, else_block_or_None)``.
        ``elif`` and ``else if`` become a nested ``IF`` in the else slot.
        """
        keyword = self.consume()[1]  # "if" or "elif"
        condition = self.parse_expression()
        then_block = self._parse_block(
            f"Expected {{ after {keyword} condition", f"Expected }} after {keyword} body"
        )
        else_block = None
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

    def _parse_for(self):
        """``for name in iterable { }``  ->  ``("FOR", target, iterable, block)``.

        ``target`` is a single name (string) or, for ``for a, b in ...``,
        a tuple of names that each item is unpacked into.
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
        return ("FOR", target, iterable, body)

    # --- definitions ------------------------------------------------------

    def _parse_function(self):
        """``def name(a, b=default) { }``.

        Produces ``("FUNCDEF", name, [param names], body, {param: default_expr})``.
        """
        self.consume()
        name = self._expect_identifier("Expected function name")
        self._expect("LPAREN", "Expected ( after function name")
        params = []
        defaults = {}
        while not self._check("RPAREN"):
            param = self._expect_identifier("Expected parameter name")
            params.append(param)
            if self._check("ASSIGN"):
                self.pos += 1
                defaults[param] = self.parse_expression()
            elif defaults:
                raise SyntaxError("Parameter without default follows default parameter")
            if self._check("COMMA"):
                self.pos += 1
                continue
            break
        self._expect("RPAREN", "Expected ) after params")
        body = self._parse_block(
            "Expected { for function body", "Expected } after function body"
        )
        return ("FUNCDEF", name, params, body, defaults)

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
        try_block = self._parse_block("Expected { after try", "Expected } after try body")
        handlers = []
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
        finally_block = None
        if self._check("FINALLY"):
            self.consume()
            finally_block = self._parse_block(
                "Expected { after finally", "Expected } after finally body"
            )
        return ("TRY", try_block, handlers, finally_block)

    # --- assignments and expression statements ----------------------------

    def _parse_expression_statement(self):
        """Parse an expression, or an assignment if ``=``/``+=``/... follows.

        * ``target = value``   -> ``("ASSIGN_LHS", target, value)``
        * ``target += value``  -> ``("AUGASSIGN", "+=", target, value)``
        * otherwise the bare expression node is returned.

        A target must be a variable, an attribute (``a.b``) or an index
        (``a[i]``).
        """
        expression = self.parse_expression()
        token = self.peek()
        if token is None:
            return expression
        if token[0] == "ASSIGN" or token[0] in _AUGMENTED_OPERATORS:
            if not (isinstance(expression, tuple) and expression[0] in _ASSIGNABLE_TAGS):
                raise SyntaxError("Invalid assignment target")
            self.consume()
            value = self.parse_expression()
            if token[0] == "ASSIGN":
                return ("ASSIGN_LHS", expression, value)
            return ("AUGASSIGN", _AUGMENTED_OPERATORS[token[0]], expression, value)
        return expression

    # ------------------------------------------------------------------
    # Expressions (lowest precedence first)
    # ------------------------------------------------------------------

    def parse_semicolon_eol(self):
        """Consume one optional ``;`` (kept for backwards compatibility)."""
        if self._check("SEMICOLON"):
            self.consume()

    def parse_expression(self):
        """Parse a full expression and record where it starts."""
        start = self.pos
        return self._mark(self.parse_or(), start)

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
        if "f" in lowered:
            return self._postfix(("FSTRING", literal[1:-1], prefix, literal[0]))
        if lowered.startswith("re"):
            return self._postfix(("REGEX", literal[1:-1]))
        value = ast.literal_eval(text)
        return self._postfix(value)

    def _parse_list(self):
        """``[a, b, c]``  ->  ``("LIST", [a, b, c])`` (trailing comma allowed)."""
        self.consume()
        items = []
        while not self._check("RBRACKET"):
            items.append(self.parse_expression())
            if self._check("COMMA"):
                self.pos += 1
                continue
            break
        self._expect("RBRACKET", "Expected ]")
        return ("LIST", items)

    def _parse_dict(self):
        """``{k: v, ...}``  ->  ``("DICT", [(k, v), ...])`` (trailing comma allowed)."""
        self.consume()
        pairs = []
        while not self._check("RBRACE"):
            key = self.parse_expression()
            self._expect("COLON", "Expected : after dictionary key")
            pairs.append((key, self.parse_expression()))
            if self._check("COMMA"):
                self.pos += 1
                continue
            break
        self._expect("RBRACE", "Expected }")
        return ("DICT", pairs)

    def _parse_parenthesised(self):
        """``( expr )`` groups; ``(a, b)`` / ``()`` / ``(a,)`` build tuples."""
        self.consume()
        if self._check("RPAREN"):
            self.consume()
            return ("TUPLE", [])
        first = self.parse_expression()
        if self._check("COMMA"):
            items = [first]
            while self._check("COMMA"):
                self.pos += 1
                if self._check("RPAREN"):
                    break
                items.append(self.parse_expression())
            self._expect("RPAREN", "Expected )")
            return ("TUPLE", items)
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
        """
        args = []
        kwargs = []
        while not self._check("RPAREN"):
            following = (
                self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else None
            )
            if self._check("IDENTIFIER") and following and following[0] == "ASSIGN":
                name = self.consume()[1]
                self.consume()
                kwargs.append((name, self.parse_expression()))
            else:
                if kwargs:
                    raise SyntaxError("Positional argument follows keyword argument")
                args.append(self.parse_expression())
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
                node = ("CALL", node, args, kwargs)
            elif kind == "DOT":
                self.consume()
                name = self._expect_identifier("Expected attribute name after .")
                node = ("ATTR", node, name)
            elif kind == "LBRACKET":
                self.consume()
                node = ("INDEX", node, self._parse_subscript())
            else:
                return node
