import re

token_regex = [
    ("NUM", r"\d+"),
    # augmented assignment operators
    ("PLUSEQ", r"\+="),
    ("MINUSEQ", r"-="),
    ("TIMESEQ", r"\*="),
    ("DIVEQ", r"/="),
    ("MODEQ", r"%="),
    ("PLUS", r"\+"),
    ("MINUS", r"\-"),
    ("DIVIDE", r"\/"),
    ("MULTIPLY", r"\*"),
    ("WHITESPACE", r"\s"),
    ("COMMENT", r"#.*"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("COMMA", r","),
    # support optional prefix letters (b, r, u, f) before the quotes
    # safer string literal pattern: handles escapes and prevents spanning newlines
    ("STRING", r"(?:[bBrRuUfF]{0,2})?(?:\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*')"),
    ("LBRACE", r"\{"),
    ("RBRACE", r"\}"),
    ("LBRACKET", r"\["),
    ("RBRACKET", r"\]"),
    ("DOT", r"\."),
    # Keywords should come before IDENTIFIER so they're recognized correctly
    ("IF", r"\bif\b"),
    ("IMPORT", r"\bimport\b"),
    ("FROM", r"\bfrom\b"),
    ("AS", r"\bas\b"),
    ("IN", r"\bin\b"),
    ("AND", r"\band\b"),
    ("OR", r"\bor\b"),
    ("NOT", r"\bnot\b"),
    ("RAISE", r"\braise\b"),
    ("TRY", r"\btry\b"),
    ("EXCEPT", r"\bexcept\b"),
    ("FINALLY", r"\bfinally\b"),
    ("CLASS", r"\bclass\b"),
    ("ELSE", r"\belse\b"),
    ("WHILE", r"\bwhile\b"),
    ("FOR", r"\bfor\b"),
    ("FUNCTION", r"\bdef\b"),
    ("RETURN", r"\breturn\b"),
    ("TRUE", r"\bTrue\b|\btrue\b"),
    ("FALSE", r"\bFalse\b|\bfalse\b"),
    ("NONE", r"\bNone\b|\bnone\b"),
    ("IDENTIFIER", r"[a-zA-Z_][a-zA-Z0-9_]*"),
    # put multi-char operators before single-char ASSIGN
    ("EQUALS", r"=="),
    ("NOT_EQUALS", r"!="),
    ("LESS_EQUAL", r"<="),
    ("GREATER_EQUAL", r">="),
    ("LESS_THAN", r"<"),
    ("GREATER_THAN", r">"),
    ("ASSIGN", r"="),
]

# Normalize __builtins__ to a dict
if isinstance(__builtins__, dict):
    _builtins_ = dict(__builtins__)
else:
    _builtins_ = dict(__builtins__.__dict__)


class BuiltinFunction:
    def __init__(self, func):
        self.func = func

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def __repr__(self):
        return f"<builtin function {self.func.__name__}>"


def _test_func(*args):
    return "This is a test function"


# Non python built-in functions that are built into the language can be added here
_functable_ = {
    "test": BuiltinFunction(_test_func),
}

# Make a shallow copy of builtin callables and extend with our functable
_builtins_.update({k: v for k, v in _functable_.items()})


class Lexer:
    def __init__(self, code):
        self.code = code
        self.tokens = []
        self.pos = 0

    def tokenize(self):
        while self.pos < len(self.code):
            # fast-path: manual string scanning to avoid regex catastrophic backtracking
            ch = self.code[self.pos]
            # detect optional prefix letters followed by a quote
            if ch.isalpha():
                # lookahead for short prefix (e.g., b, r, f, br, fr)
                j = self.pos
                while j < len(self.code) and self.code[j].isalpha():
                    j += 1
                if (
                    j < len(self.code)
                    and self.code[j] in ('"', "'")
                    and j - self.pos <= 2
                ):
                    start = self.pos
                    # consume prefix
                    self.pos = j
                    quote = self.code[self.pos]
                    self.pos += 1
                    escape = False
                    while self.pos < len(self.code):
                        c = self.code[self.pos]
                        if escape:
                            escape = False
                            self.pos += 1
                            continue
                        if c == "\\":
                            escape = True
                            self.pos += 1
                            continue
                        if c == quote:
                            self.pos += 1
                            break
                        if c == "\n":
                            # do not allow multiline strings in this simpler lexer
                            break
                        self.pos += 1
                    self.tokens.append(("STRING", self.code[start : self.pos]))
                    continue
            elif ch in ('"', "'"):
                # no prefix
                start = self.pos
                quote = ch
                self.pos += 1
                escape = False
                while self.pos < len(self.code):
                    c = self.code[self.pos]
                    if escape:
                        escape = False
                        self.pos += 1
                        continue
                    if c == "\\":
                        escape = True
                        self.pos += 1
                        continue
                    if c == quote:
                        self.pos += 1
                        break
                    if c == "\n":
                        break
                    self.pos += 1
                self.tokens.append(("STRING", self.code[start : self.pos]))
                continue

            match = None
            for token_type, regex in token_regex:
                # skip the regex STRING entry because we handle strings manually
                if token_type == "STRING":
                    continue
                pattern = re.compile(regex)
                match = pattern.match(self.code, self.pos)
                if match:
                    # Ignore whitespace and comments
                    if token_type not in ("WHITESPACE", "COMMENT"):
                        self.tokens.append((token_type, match.group(0)))
                    self.pos = match.end()
                    break
            if not match:
                raise SyntaxError(f"Unexpected character: {self.code[self.pos]}")
        return self.tokens
