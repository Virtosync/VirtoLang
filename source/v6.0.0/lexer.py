"""VirtoLang lexer (tokenizer).

The lexer is the first stage of the interpreter pipeline::

    source text --> Lexer --> tokens --> Parser --> AST --> Interpreter

It turns raw source text such as ``x = 1 + 2`` into a flat list of *tokens*,
which are ``(token_type, text)`` tuples like ``("IDENTIFIER", "x")``.
Whitespace and ``#`` comments are discarded.  For every token the lexer also
records the ``(line, column)`` where it started, so later stages can point at
the exact place in the source when reporting an error.
"""

import builtins
import re
from bisect import bisect_right

import vstdlib

# ---------------------------------------------------------------------------
# Token definitions
# ---------------------------------------------------------------------------

# Ordered ``(token_type, regex)`` pairs.  The lexer tries them in this order
# and uses the first one that matches, so longer operators must come before
# shorter ones that share a prefix (for example ``**=`` before ``**`` before
# ``*``).  String literals are *not* listed here: they are scanned by hand in
# ``Lexer.tokenize`` because they can carry prefixes and escape sequences.
token_regex = [
    # Numbers: 42, 3.14, .5, 1e10, 2.5E-3
    ("NUM", r"(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?"),
    # Whitespace and comments (both are thrown away after matching)
    ("WHITESPACE", r"[ \t\f\v]+"),
    ("NEWLINE", r"\r\n|\r|\n"),
    ("COMMENT", r"#.*"),
    # Augmented assignment operators (x += 1, ...)
    ("POWEQ", r"\*\*="),
    ("FLOORDIVEQ", r"//="),
    ("PLUSEQ", r"\+="),
    ("MINUSEQ", r"-="),
    ("TIMESEQ", r"\*="),
    ("DIVEQ", r"/="),
    ("MODEQ", r"%="),
    # Arithmetic operators
    ("POWER", r"\*\*"),
    ("FLOORDIV", r"//"),
    ("PLUS", r"\+"),
    ("MINUS", r"-"),
    ("DIVIDE", r"/"),
    ("MULTIPLY", r"\*"),
    ("MODULO", r"%"),
    # Comparison operators (multi-character ones first)
    ("EQUALS", r"=="),
    ("NOT_EQUALS", r"!="),
    ("LESS_EQUAL", r"<="),
    ("GREATER_EQUAL", r">="),
    ("LESS_THAN", r"<"),
    ("GREATER_THAN", r">"),
    ("ASSIGN", r"="),
    # Punctuation
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("LBRACE", r"\{"),
    ("RBRACE", r"\}"),
    ("LBRACKET", r"\["),
    ("RBRACKET", r"\]"),
    ("COMMA", r","),
    ("WALRUS", r":="),
    ("COLON", r":"),
    ("SEMICOLON", r";"),
    ("AT", r"@"),
    ("DOT", r"\."),
    # Identifiers; reserved words are re-labelled using KEYWORDS below
    ("IDENTIFIER", r"[a-zA-Z_][a-zA-Z0-9_]*"),
]

# Reserved words.  An identifier whose text is a key here gets the listed
# token type instead of "IDENTIFIER".  ``true``/``false``/``none`` are
# accepted in lower case as well as Python's capitalised spelling.
KEYWORDS = {
    "if": "IF",
    "elif": "ELIF",
    "else": "ELSE",
    "while": "WHILE",
    "for": "FOR",
    "in": "IN",
    "break": "BREAK",
    "continue": "CONTINUE",
    "def": "FUNCTION",
    "return": "RETURN",
    "class": "CLASS",
    "import": "IMPORT",
    "from": "FROM",
    "as": "AS",
    "and": "AND",
    "or": "OR",
    "not": "NOT",
    "is": "IS",
    "lambda": "LAMBDA",
    "raise": "RAISE",
    "try": "TRY",
    "with": "WITH",
    "except": "EXCEPT",
    "finally": "FINALLY",
    "async": "ASYNC",
    "await": "AWAIT",
    "yield": "YIELD",
    "global": "GLOBAL",
    "nonlocal": "NONLOCAL",
    "pass": "PASS",
    "assert": "ASSERT",
    "del": "DEL",
    "True": "TRUE",
    "true": "TRUE",
    "False": "FALSE",
    "false": "FALSE",
    "None": "NONE",
    "none": "NONE",
}

# Token types that are matched but never emitted.
_SKIPPED_TOKENS = frozenset(("WHITESPACE", "COMMENT"))

# One big regex built from ``token_regex``.  Each alternative is a named group
# whose name is the token type, so ``match.lastgroup`` tells us what matched.
_token_pattern = re.compile(
    "|".join(f"(?P<{name}>{regex})" for name, regex in token_regex)
)

# String literals may start with a short prefix such as ``f``, ``r``, ``b``,
# ``rf`` or ``re`` (``re"..."`` is a regular-expression literal).
_STRING_PREFIX_RE = re.compile(r"([A-Za-z]{1,2})[\"']")
_STRING_PREFIXES = frozenset(("b", "r", "u", "f", "br", "rb", "fr", "rf", "re"))

# Matches the *rest* of a string literal starting at its opening quote.
# Backslash escapes are honoured and a string may not span a newline (unless
# the newline is escaped).  The closing quote is optional so that an
# unterminated string produces a token that the parser can report on.
_STRING_BODY = {
    '"': re.compile(r'"(?:[^"\\\n]|\\[\s\S])*"?'),
    "'": re.compile(r"'(?:[^'\\\n]|\\[\s\S])*'?"),
}

# Triple-quoted strings (\"\"\"...\"\"\" or '''...''') may span many lines.
_TRIPLE_BODY = {
    '"': re.compile(r'"""(?:[^"\\]|\\[\s\S]|"(?!""))*(?:""")?'),
    "'": re.compile(r"'''(?:[^'\\]|\\[\s\S]|'(?!''))*(?:''')?"),
}

# ---------------------------------------------------------------------------
# Builtin function tables
# ---------------------------------------------------------------------------

# Every Python builtin (print, len, range, ...) is available to VirtoLang
# programs.  This is a plain dict so name lookups are fast.
_builtins_ = dict(vars(builtins))


class BuiltinFunction:
    """Wrapper that gives a plain Python callable a readable ``repr``.

    Functions written in Python that should appear as built-in VirtoLang
    functions can be wrapped in this class and registered in ``_functable_``.
    """

    def __init__(self, func):
        self.func = func

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def __repr__(self):
        return f"<builtin function {self.func.__name__}>"


# Extra built-in functions implemented in Python can be added to this table.
# They become global variables of every program and override Python builtins
# of the same name.
_functable_ = {}

# VirtoLang's own built-ins (files, HTTP, GUI, ...) live in vstdlib.py.  They
# go into the fallback table so they cost nothing until a program uses them.
_builtins_.update(vstdlib.FUNCTIONS)
_builtins_.update(_functable_)


# ---------------------------------------------------------------------------
# The lexer itself
# ---------------------------------------------------------------------------


class Lexer:
    """Converts VirtoLang source text into a list of tokens.

    Usage::

        lexer = Lexer('x = 1 + 2')
        tokens = lexer.tokenize()   # [("IDENTIFIER", "x"), ("ASSIGN", "="), ...]
        lexer.locations             # [(1, 1), (1, 3), ...]  (line, column)

    Attributes:
        code: The full source text being tokenized.
        tokens: ``(type, text)`` tuples produced by ``tokenize``.
        locations: ``(line, column)`` for each token, parallel to ``tokens``.
            Lines and columns both start at 1.
        pos: Current read position (index into ``code``).
    """

    def __init__(self, code):
        self.code = code
        self.tokens = []
        self.locations = []
        self.pos = 0
        # Index of the first character of every line; used to convert a flat
        # position into a (line, column) pair with a binary search.
        self._line_starts = [0]
        self._line_starts.extend(
            index + 1 for index, char in enumerate(code) if char == "\n"
        )

    def _location(self, position):
        """Return the 1-based ``(line, column)`` of a position in the source."""
        line_index = bisect_right(self._line_starts, position) - 1
        return line_index + 1, position - self._line_starts[line_index] + 1

    def _error(self, message, position):
        """Build a ``SyntaxError`` that remembers where in the source it happened."""
        error = SyntaxError(message)
        error.vlang_location = self._location(position)
        return error

    def _string_start(self, position):
        """Return the index of the opening quote if a string literal starts here.

        A literal starts either directly with a quote character or with a
        recognised prefix (``f"..."``, ``rb'...'``, ``re"..."``...).  Returns
        ``None`` when the text at ``position`` is not the start of a string.
        """
        char = self.code[position]
        if char == '"' or char == "'":
            return position
        # Only a few letters can begin a prefix, so skip the regex otherwise.
        if char in "bBrRuUfF":
            match = _STRING_PREFIX_RE.match(self.code, position)
            if match and match.group(1).lower() in _STRING_PREFIXES:
                return match.end() - 1
        return None

    def tokenize(self):
        """Scan the whole source and return the list of tokens.

        Raises:
            SyntaxError: if a character cannot start any token.  The error
                carries a ``vlang_location`` attribute with the position.
        """
        code = self.code
        length = len(code)
        tokens = self.tokens = []
        locations = self.locations = []
        pos = self.pos = 0
        match_token = _token_pattern.match
        delimiters = []
        previous_kind = None
        at_statement_start = True

        while pos < length:
            # --- string literals (handled by hand, see _STRING_BODY) ---
            quote_index = self._string_start(pos)
            if quote_index is not None:
                quote = code[quote_index]
                if code.startswith(quote * 3, quote_index):
                    body = _TRIPLE_BODY[quote].match(code, quote_index)
                else:
                    body = _STRING_BODY[quote].match(code, quote_index)
                tokens.append(("STRING", code[pos : body.end()]))
                locations.append(self._location(pos))
                pos = body.end()
                continue

            # --- everything else is matched by the combined regex ---
            match = match_token(code, pos)
            if match is None:
                raise self._error(f"Unexpected character: {code[pos]!r}", pos)

            token_type = match.lastgroup
            text = match.group(0)
            if token_type == "NEWLINE":
                if not any(
                    kind in ("LPAREN", "LBRACKET", "DICT") for kind in delimiters
                ):
                    tokens.append(("NEWLINE", text))
                    locations.append(self._location(pos))
                    at_statement_start = True
                pos = match.end()
                continue
            if token_type not in _SKIPPED_TOKENS:
                if token_type == "IDENTIFIER":
                    token_type = KEYWORDS.get(text, "IDENTIFIER")
                tokens.append((token_type, text))
                locations.append(self._location(pos))
                if token_type in ("LPAREN", "LBRACKET"):
                    delimiters.append(token_type)
                elif token_type == "LBRACE":
                    dict_starters = {
                        "ASSIGN",
                        "RETURN",
                        "COMMA",
                        "LPAREN",
                        "LBRACKET",
                        "COLON",
                        "WALRUS",
                        "YIELD",
                        "IF",
                        "NOT",
                        "AND",
                        "OR",
                        "IS",
                        "IN",
                    }
                    delimiters.append(
                        "DICT"
                        if at_statement_start or previous_kind in dict_starters
                        else "BLOCK"
                    )
                elif token_type in ("RPAREN", "RBRACKET", "RBRACE"):
                    if delimiters:
                        delimiters.pop()
                previous_kind = token_type
                at_statement_start = token_type == "SEMICOLON"
            pos = match.end()

        self.pos = pos
        return tokens
