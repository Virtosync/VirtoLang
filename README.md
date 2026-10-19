# VirtoLang

VirtoLang is a small interpreted language with Python-style expressions and
curly-brace blocks. It is implemented in Python and can call Python built-ins,
import Python modules, and work with Python objects.

This guide describes the syntax currently implemented by the interpreter. It
does not imply full Python-language compatibility: VirtoLang has its own
parser, and some Python syntax and features are not available.

## Contents

- [Getting started](#getting-started)
- [Running a program](#running-a-program)
- [Language basics](#language-basics)
- [Strings and formatting](#strings-and-formatting)
- [Collections and Python objects](#collections-and-python-objects)
- [Functions and classes](#functions-and-classes)
- [Control flow](#control-flow)
- [Exceptions](#exceptions)
- [Python interoperability](#python-interoperability)
- [Errors and diagnostics](#errors-and-diagnostics)
- [Current language boundaries](#current-language-boundaries)
- [Development and tests](#development-and-tests)

## Getting started

Create a text file named `hello.vlang`:

```vlang
name = "VirtoLang"
print(f"Hello, {name}!")
```

Run it from a terminal:

```powershell
vlang hello.vlang
```

If you are running from a source checkout with Python installed:

```powershell
python vlang.py hello.vlang
```

On Windows, the installer adds `vlang.exe` to `PATH`. The executable and its
companion `_internal` directory must remain together.

## Running a program

The CLI takes one `.vlang` source file:

```text
vlang path\to\program.vlang
```

The file extension is required. The CLI prints output from calls such as
`print(...)`; a failing program exits with a non-zero status and writes its
diagnostic to standard error.

## Language basics

### Statements, comments, and blocks

Statements are separated by whitespace or newlines; semicolon statement
separators are not supported. Use `#` for a comment:

```vlang
# A simple assignment
count = 3
```

Blocks use braces. Indentation is for readability and does not define blocks:

```vlang
if count > 0 {
    print("There are items")
}
```

### Values and variables

Variables are created by assigning to a name. The currently supported literal
forms include integers, decimal and scientific-notation numbers, strings,
booleans, `None`, and lists:

```vlang
whole = 42
fraction = 3.14159
small = 1.2e-3
message = "hello"
enabled = true
missing = None
items = [1, 2, 3]
```

`true` and `True` both mean `True`; `false` and `False` both mean `False`.
`none` and `None` both mean `None`.

Variables are dynamically typed and may be reassigned:

```vlang
value = 10
value = "ten"
```

### Operators and expressions

The parser supports these arithmetic operators:

| Operator | Meaning |
| --- | --- |
| `+` | Addition or compatible-value concatenation |
| `-` | Subtraction |
| `*` | Multiplication |
| `/` | Division |

Augmented assignment is supported for `+=`, `-=`, `*=`, `/=`, and `%=`:

```vlang
total = 10
total += 5
```

Comparison operators are `==`, `!=`, `<`, `>`, `<=`, and `>=`. Boolean
expressions use `and`, `or`, and `not`; `and` and `or` short-circuit:

```vlang
if total >= 10 and not false {
    print(total)
}
```

Parentheses can group expressions:

```vlang
result = (2 + 3) * 4
```

`+` follows Python's operand rules. For example, adding two strings works, but
adding a string and a number raises a `TypeError`:

```vlang
label = "Count: " + str(total)
```

## Strings and formatting

Single- and double-quoted strings support common backslash escapes:

```vlang
quoted = "She said, \"hello\""
lines = "first\nsecond"
```

Raw strings preserve backslashes:

```vlang
path = r"C:\new\folder"
print(path)
```

Formatted strings support expressions, conversions, escaped braces, and
Python's format-spec mini-language:

```vlang
name = "VirtoLang"
price = 12.3456
width = 10

print(f"Hello, {name}!")
print(f"Price: ${price:.2f}")
print(f"Aligned: {price:>{width}.2f}")
print(f"Debug: {name=}")
print(f"Representation: {name!r}")
print(f"Literal braces: {{ and }}")
```

Conversions `!s`, `!r`, and `!a` are supported. Format specifications are
delegated to Python's `format()` implementation, so supported alignment,
precision, and numeric presentation options follow Python's format rules.
Nested fields can supply dynamic format values, for example
`f"{price:{width}.2f}"`.

Raw formatted strings combine raw literal text with evaluated fields:

```vlang
file_name = "report"
print(rf"C:\exports\{file_name}.txt")
```

String literals and string variables can use Python string methods, including
`.format()`:

```vlang
print("Price: ${:.2f}".format(price))
print("  hello  ".strip())
print("virto".upper())
```

## Collections and Python objects

### Lists

Lists support indexing, assignment to an index, and Python list methods:

```vlang
numbers = [1, 2, 3]
print(numbers[0])
numbers.append(4)
numbers[1] = 20
print(len(numbers))
print(sorted(numbers))
```

List literals can contain expressions and can be passed to Python functions.

### Dictionaries

Create dictionaries with Python's `dict()` built-in, then access and assign
entries by key:

```vlang
settings = dict()
settings["theme"] = "dark"
print(settings["theme"])
print(settings.get("language", "en"))
```

Dictionary literal syntax (`{"key": value}`) is not currently implemented.

### Python objects

Attribute access and indexed access are supported on Python values returned by
built-ins, imports, and method calls:

```vlang
import math
print(math.sqrt(81))
```

## Functions and classes

### Functions

Define functions with `def`, a comma-separated list of parameter names, and a
braced body. Calls currently use positional arguments:

```vlang
def greet(name) {
    print(f"Hello, {name}!")
}

def add(left, right) {
    return left + right
}

greet("Ada")
print(add(2, 3))
```

`return` exits the function and returns its expression's value.

### Classes

Classes use a braced body. Methods take an explicit first parameter, commonly
named `self`:

```vlang
class Counter {
    def __init__(self, start) {
        self.value = start
    }

    def increment(self) {
        self.value += 1
        return self.value
    }
}

counter = Counter(4)
print(counter.increment())
```

The language's ordinary class implementation is intentionally lightweight;
it is not a complete implementation of Python's class and inheritance model.
Exception subclasses are supported as described below.

## Control flow

### `if` and `else`

Conditions do not require parentheses. There is no `elif` keyword; nest an
`if` inside `else` when another condition is needed:

```vlang
if score >= 90 {
    print("A")
} else {
    if score >= 80 {
        print("B")
    } else {
        print("Keep practicing")
    }
}
```

### `while`

```vlang
count = 0
while count < 3 {
    print(count)
    count += 1
}
```

### `for`

`for` iterates over an expression that produces an iterable:

```vlang
for item in ["red", "green", "blue"] {
    print(item)
}

for number in range(3) {
    print(number)
}
```

`break` and `continue` statements are not currently implemented.

## Exceptions

VirtoLang supports `try`, typed and bare `except` handlers, and `finally`.
Handlers are checked in order, and `finally` runs whether the try body
succeeds, raises an unhandled exception, or returns from a function:

```vlang
try {
    value = 10 / divisor
} except ZeroDivisionError as error {
    print("The divisor cannot be zero:", error)
} except Error as error {
    print("Other error:", error)
} finally {
    print("Finished")
}
```

A bare handler catches any regular exception:

```vlang
try {
    raise Error("Something went wrong")
} except {
    print("An error was caught")
}
```

`Error` is an alias for Python's base `Exception` class. Raise an exception
instance:

```vlang
raise Error("Invalid configuration")
```

Custom exceptions can subclass `Error`:

```vlang
class ValidationError(Error) {
    def __init__(self, message) {
        self.message = message
    }
}

try {
    raise ValidationError("A name is required")
} except ValidationError as error {
    print(error)
}
```

Python's built-in exception classes can also be used in `except` clauses, such
as `ValueError`, `TypeError`, and `ZeroDivisionError`.

## Python interoperability

VirtoLang can call Python built-ins and import Python modules available to the
runtime. Use `import name` or `from module import name`:

```vlang
import math
from time import time

print(len([1, 2, 3]))
print(math.sqrt(16))
print(time())
```

Third-party packages must be installed in the Python environment used by
VirtoLang. An onedir executable includes its Python runtime; package
availability depends on how that executable was built.

VirtoLang is not a Python source runner. The parser implements a subset of
Python-like expressions and control flow; imported Python functions and objects
are interoperable, but Python syntax that the VirtoLang parser does not
recognize cannot be placed directly in a `.vlang` file.

## Errors and diagnostics

When a `.vlang` program fails in the CLI, VirtoLang reports the source file,
line and column, a source excerpt with a caret, the error type and message, and
a suggested fix for common problems. It suppresses Python tracebacks from the
interpreter internals.

For example, an incompatible string operation:

```vlang
print("Count: " + 3)
```

is reported as a `TypeError` with a suggestion to convert the value using
`str(...)` or interpolate it in an f-string.

The caret identifies the lexer token or enclosing statement associated with
the error. For runtime errors, it may point to the start of the statement
rather than the exact operator or subexpression.

Suggestions are best-effort hints for common errors; they do not replace
reading the message and checking the source code.

## Current language boundaries

VirtoLang is actively evolving. The following are examples of Python features
that are not currently part of the language syntax:

- `elif`, `break`, and `continue`
- Dictionary literals
- Keyword arguments in VirtoLang-defined function calls
- Python compound syntax such as `with`, `lambda`, comprehensions, and
  `async`/`await`
- Full Python class inheritance and metaclass behavior

The exact supported syntax is defined by the parser and may change between
releases.

## Development and tests

Run the regression suite from the project root:

```powershell
python -m unittest discover -s tests -v
```

On Windows, the repository's virtual environment can be used directly:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

To build the Windows onedir executable, install PyInstaller in the selected
Python environment and run:

```powershell
python buildscript.py
```

The executable is produced in `dist\vlang\`; keep the executable and its
`_internal` directory together when distributing it.

## Release notes

See [release notes.md](./release%20notes.md) for recent user-facing changes.
