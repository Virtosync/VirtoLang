# VirtoLang

VirtoLang is a small, easy-to-read scripting language with Python-style
expressions and curly-brace blocks. It runs on top of Python, so your programs
can call any Python built-in, import any installed Python module, and work with
Python objects directly.

```vlang
name = "VirtoLang"
print(f"Hello, {name}!")
```

> VirtoLang has its own parser. It looks familiar to Python users, but it is
> **not** a Python source runner, and some Python syntax is not available. This
> guide documents what is implemented today.

## Contents

- [Installation](#installation)
- [Running code](#running-code)
- [The interactive shell (REPL)](#the-interactive-shell-repl)
- [Language basics](#language-basics)
- [Strings and formatting](#strings-and-formatting)
- [Collections](#collections)
- [Control flow](#control-flow)
- [Functions](#functions)
- [Generators, async and unpacking](#generators-async-and-unpacking)
- [Classes](#classes)
- [Exceptions](#exceptions)
- [Modules and packages](#modules-and-packages)
- [Virtual environments](#virtual-environments)
- [Using Python from VirtoLang](#using-python-from-virtolang)
- [Built-in functions](#built-in-functions)
- [Error messages](#error-messages)
- [Limitations](#limitations)
- [Release notes](#release-notes)

## Installation

**Windows installer:** run the VirtoLang installer. It adds `vlang.exe` to your
`PATH`, so `vlang` works from any terminal. Keep `vlang.exe` and its
`_internal` folder together if you move them.

**From source:** you only need Python 3.10 or newer. Download the project and
run it with Python:

```powershell
python vlang.py hello.vlang
```

Check your installation:

```powershell
vlang --version
```

## Running code

Create a file ending in `.vlang`, for example `hello.vlang`:

```vlang
print("Hello from VirtoLang!")
```

Run it:

```powershell
vlang hello.vlang
```

### Command-line options

| Command                       | What it does                                                                   |
| ----------------------------- | ------------------------------------------------------------------------------ |
| `vlang file.vlang`            | Run a program.                                                                 |
| `vlang`                       | Run `main.vlang` from the current folder.                                      |
| `vlang -c file.vlang`         | Check the syntax without running the program.                                  |
| `vlang -e "print(1 + 2)"`     | Run code given directly on the command line.                                   |
| `vlang -r`                    | Start the [interactive shell](#the-interactive-shell-repl).                    |
| `vlang -r file.vlang`         | Run a program, then open the shell with its variables and functions available. |
| `vlang --create-venv DIR`     | Create a [virtual environment](#virtual-environments) in `DIR`.                |
| `vlang --venv DIR file.vlang` | Run a program using the packages of the environment in `DIR`.                  |
| `vlang --paths`               | Show where VirtoLang looks for modules.                                        |
| `vlang -v`                    | Show the version.                                                              |
| `vlang -h`                    | Show help.                                                                     |

Options can be written in lower or upper case (`-r` or `-R`) or in long form
(`--repl`, `--check`, `--execute`, `--version`).

If a program fails, the error is written to standard error and `vlang` exits
with a non-zero status, which makes it easy to use in scripts.

## The interactive shell (REPL)

Start the shell with:

```powershell
vlang -r
```

You can type statements and expressions and see the result immediately, like
Python's interactive shell. Variables, functions and classes you define stay
available for the rest of the session.

```text
VirtoLang 5.1.0 interactive shell (Python 3.14.3 on win32)
Type ":help" for help, or exit() to quit.
>>> x = 6
>>> x * 7
42
>>> def square(n) {
...     return n * n
... }
>>> square(x)
36
>>> "hello".upper()
'HELLO'
>>> a = 1; b = 2; a + b
3
```

- **Multi-line input.** If a `{`, `(` or `[` is still open, the shell shows the
  `...` prompt and keeps reading until everything is closed.
- **Values are echoed** when an expression produces something other than
  `None`. Assignments, loops and `print(...)` calls do not echo anything.
- **Errors do not end the session.** The error is shown and you can carry on.
- **`else`, `elif`, `except` and `finally` must start on the same line as the
  closing `}`** (for example `} else {`) so the shell knows the statement
  continues.
- **Ctrl-C** cancels the line you are typing. **Ctrl-D** (Linux/macOS) or
  **Ctrl-Z then Enter** (Windows) leaves the shell.

Shell commands start with a colon:

| Command  | Meaning                                           |
| -------- | ------------------------------------------------- |
| `:help`  | Show help.                                        |
| `:vars`  | List everything you have defined.                 |
| `:reset` | Clear the session and start fresh.                |
| `:exit`  | Leave the shell. `exit()` and `quit()` also work. |

## Language basics

### Statements, semicolons and comments

Statements end at a newline. You can use a semicolon (`;`) to put several
statements on one line, or to write an entire program on a single line:

```vlang
a = 1; b = 2; print(a + b)
```

Semicolons can be repeated or left at the end of a line. Newlines inside
parentheses and square brackets continue an expression; multiline dictionaries
are also supported. Newlines separate statements inside blocks:

```vlang
if a < b { print("a is smaller"); a = b }
```

Comments start with `#` and continue to the end of the line:

```vlang
# This is a comment
count = 3  # so is this
```

### Blocks

Blocks are wrapped in braces. Indentation is only for readability:

```vlang
if count > 0 {
    print("There are items")
}
```

### Variables and values

Assign to a name to create a variable. Variables are dynamically typed and can
be reassigned to a different type.

```vlang
whole = 42
fraction = 3.14159
small = 1.2e-3
message = "hello"
enabled = true
missing = None
items = [1, 2, 3]
```

`true` / `True`, `false` / `False` and `none` / `None` are all accepted.
Using a name that has not been defined is a `NameError`.

### Operators

| Operator                    | Meaning                                               |
| --------------------------- | ----------------------------------------------------- |
| `+` `-` `*` `/`             | Add, subtract, multiply, divide                       |
| `//`                        | Floor division                                        |
| `%`                         | Remainder                                             |
| `**`                        | Power (`2 ** 10` is `1024`)                           |
| `==` `!=` `<` `>` `<=` `>=` | Comparison                                            |
| `is`, `is not`              | Identity (whether two names refer to the same object) |
| `in`, `not in`              | Membership test (`3 in [1, 2, 3]`)                    |
| `and`, `or`, `not`          | Boolean logic (`and` / `or` short-circuit)            |

Comparisons can be chained, as in Python: `0 < x < 10`.
Use `is None` when checking for an absent value; use `==` for ordinary value
comparison.

Conditional expressions choose one of two values:

```vlang
label = "adult" if age >= 18 else "child"
```

Augmented assignment is supported for `+=`, `-=`, `*=`, `/=`, `//=`, `%=` and
`**=`. Parentheses group expressions:

```vlang
total = 10
total += 5
result = (2 + 3) * 4
```

Tuple unpacking assigns several names in one statement. The number of values
must match the number of names:

```vlang
first, second = "red", "blue";
(width, height) = (800, 600)
```

`+` follows Python's rules: two strings can be joined, but a string and a
number cannot. Convert the number first:

```vlang
label = "Count: " + str(total)
```

## Strings and formatting

Strings use single or double quotes and support the usual backslash escapes.
Raw strings (prefix `r`) keep backslashes as written:

```vlang
quoted = "She said, \"hello\""
path = r"C:\new\folder"
```

Formatted strings (prefix `f`) embed expressions in braces and support
conversions (`!s`, `!r`, `!a`), Python format specifications, `{name=}` debug
output, and literal braces written as `{{` and `}}`:

```vlang
name = "VirtoLang"
price = 12.3456
width = 10

print(f"Hello, {name}!")
print(f"Price: ${price:.2f}")
print(f"Aligned: {price:>{width}.2f}")
print(f"Debug: {name=}")
print(f"Representation: {name!r}")
```

Strings are Python strings, so all of Python's string methods are available:

```vlang
print("  hello  ".strip())
print("virto".upper())
print("Price: ${:.2f}".format(price))
```

Prefix a string with `re` (for example `re"[a-z]+"`) to create a compiled
regular expression.

Triple-quoted strings (`"""..."""` or `'''...'''`) can span several lines and
may contain quotes. They also work as f-strings (`f"""..."""`):

```vlang
poem = """Roses are red,
Violets are "blue"."""

name = "Ada"
letter = f"""Dear {name},
Welcome to VirtoLang!"""
print(poem)
print(letter)
```

## Collections

### Lists

```vlang
numbers = [1, 2, 3]
numbers.append(4)
numbers[1] = 20
print(numbers[0], len(numbers), sorted(numbers))
```

### Slicing

Strings, lists and tuples can be sliced with `[start:stop:step]`:

```vlang
letters = ["a", "b", "c", "d", "e"]
print(letters[1:3])     # ['b', 'c']
print(letters[::-1])    # reversed
print("virtolang"[:5])  # virto
```

### Dictionaries

```vlang
settings = {"theme": "dark", "size": 12}
settings["language"] = "en"
print(settings["theme"])
print(settings.get("missing", "default"))

for key, value in settings.items() {
    print(key, value)
}
```

### Sets

Set literals hold unique values. Use `set()` to create an empty set; `{}` is an
empty dictionary:

```vlang
unique = {1, 2, 2, 3}
print(unique)  # {1, 2, 3}
empty_set = set()
```

### Comprehensions

List, set, and dictionary comprehensions build collections from an iterable.
They support nested `for` clauses and `if` filters. Their loop variables are
local to the comprehension and do not overwrite surrounding variables:

```vlang
squares = [n * n for n in range(10) if n % 2 == 0]
coordinates = {(x, y) for x in [1, 2] for y in [3, 4]}
by_name = {name: len(name) for name in ["Ada", "Grace"]}
```

### Tuples

```vlang
point = (3, 4)
print(point[0])
```

Collections are ordinary Python objects, so every Python method for them is
available.

## Control flow

### `if`, `elif`, `else`

```vlang
if score >= 90 {
    print("A")
} elif score >= 80 {
    print("B")
} else {
    print("Keep practicing")
}
```

Conditions do not need parentheses. `else if` also works.

### `while`

```vlang
count = 0
while count < 3 {
    print(count)
    count += 1
}
```

### `for`

`for` loops over anything iterable. Use two or more names to unpack each item:

```vlang
for color in ["red", "green", "blue"] {
    print(color)
}

for index, color in enumerate(["red", "green"]) {
    print(index, color)
}
```

### `break` and `continue`

```vlang
for n in range(10) {
    if n % 2 == 0 { continue }
    if n > 7 { break }
    print(n)
}
```

## Functions

Define functions with `def`. Parameters can have default values, and arguments
can be passed by position or by name:

```vlang
def greet(name, punctuation="!") {
    return f"Hello, {name}{punctuation}"
}

print(greet("Ada"))
print(greet("Ada", punctuation="?"))
```

- `return` ends the function and gives back a value; a bare `return;` returns
  `None`. A function without `return` gives back the value of its last
  statement. Comma-separated return values form a tuple.
- Functions can call themselves (recursion) and can be defined inside other
  functions. Inner functions can read the variables of the function around
  them.
- Variables assigned inside a function are local to that function.
- VirtoLang functions can be passed to Python functions, for example
  `sorted(words, key=length_of)`.
- Short functions can be written with `lambda`. Lambdas accept positional
  parameters and capture their surrounding scope:

```vlang
double = lambda value: value * 2
print(double(21))
print(sorted([3, 1, 2], key=lambda value: -value))
```

```vlang
def factorial(n) {
    if n <= 1 { return 1 }
    return n * factorial(n - 1)
}

print(factorial(10))
```

### Variable-length and keyword-only parameters

`*args` collects extra positional arguments into a tuple and `**kwargs`
collects extra named arguments into a dictionary. Parameters after `*` (or
after `*args`) can only be passed by name:

```vlang
def report(title, *values, sep=", ", **options) {
    print(title + ": " + sep.join(str(v) for v in values), options)
}

report("Scores", 90, 85, 77, sep=" | ", verbose=true)

def connect(host, *, port, secure=false) {
    return f"{host}:{port} secure={secure}"
}

print(connect("localhost", port=8080))
```

Parameters before `/` are positional-only: callers must pass them by position.
Parameters after `/` can be passed by position or name:

```vlang
def divide(numerator, denominator, /, precision=2) {
    return round(numerator / denominator, precision)
}

print(divide(10, 3, precision=3))
```

Use `*` and `**` when calling to spread a list or dictionary into arguments.
The same `*` / `**` spread works inside list, tuple, set and dictionary
literals:

```vlang
numbers = [1, 2, 3]
options = {"sep": "-"}
print(*numbers, **options)

combined = [0, *numbers, 4]
defaults = {"color": "red", "size": 1}
custom = {**defaults, "size": 3}
```

### Changing outer variables: `global` and `nonlocal`

Assigning inside a function normally creates a local variable. Declare a name
`global` to change the program-level variable, or `nonlocal` to change a
variable of the enclosing function:

```vlang
total = 0

def add(amount) {
    global total
    total += amount
}

def make_counter() {
    count = 0
    def step() {
        nonlocal count
        count += 1
        return count
    }
    return step
}

add(5)
counter = make_counter()
counter()
print(total, counter())
```

### Decorators

A decorator is a function that takes a function and returns a replacement.
Put `@decorator` on the line above a `def` or `class`. Decorators can take
arguments and be stacked; the one nearest the `def` is applied first:

```vlang
def shout(function) {
    def wrapper(*args, **kwargs) {
        return str(function(*args, **kwargs)).upper() + "!"
    }
    return wrapper
}

def repeat(times) {
    def decorator(function) {
        def wrapper(*args) {
            return [function(*args) for _ in range(times)]
        }
        return wrapper
    }
    return decorator
}

@shout
def hello(name) { return "hello " + name }

@repeat(2)
def ping() { return "ping" }

print(hello("ada"), ping())
```

Ready-made decorators: `@memoize` (cache results), `@timed` (print how long a
call took) and `@retry(times)` (try again if the function raises).

## Generators, async and unpacking

### Generator expressions and `yield`

A generator expression is a lazy comprehension written with parentheses. It
produces items only as they are needed, so it is ideal for large ranges and
for passing straight to functions such as `sum`, `any` or `max`:

```vlang
squares = (n * n for n in range(1000000))
print(next(squares), next(squares))
print(sum(n for n in range(10) if n % 2 == 0))
```

A function that uses `yield` becomes a generator. Each call to `next()` (or
each step of a `for` loop) runs the body up to the next `yield`. Use
`yield from` to hand over to another iterable, and `x = yield value` to
receive values sent with `.send()`:

```vlang
def countdown(start) {
    while start > 0 {
        yield start
        start -= 1
    }
}

def launch() {
    yield from countdown(3)
    yield "liftoff"
}

print(list(launch()))
```

### `async` and `await`

`async def` defines a function that can pause at `await` while other tasks
run. Calling it returns an awaitable; use `await` inside another `async def`,
or at the top level of a program. Helpers: `async_run(coroutine)`,
`async_sleep(seconds)`, `gather(...)` (run several at once) and
`create_task(coroutine)` (start in the background):

```vlang
async def fetch(name, delay) {
    await async_sleep(delay)
    return f"{name} done"
}

async def main() {
    results = await gather(fetch("a", 0.2), fetch("b", 0.1))
    print(results)
}

async_run(main())
```

`async for` and `async with` work with objects that define `__aiter__` /
`__anext__` and `__aenter__` / `__aexit__`. Async generator functions may
combine `await` with `yield` and produce an asynchronous iterator:

```vlang
async def pages(count) {
    for page in range(count) {
        await async_sleep(0)
        yield page
    }
}

async def collect_pages() {
    result = []
    async for page in pages(3) {
        result.append(page)
    }
    return result
}

print(async_run(collect_pages()))
```

Use `await generator.asend(value)` to send a value, `await generator.athrow(error)`
to raise an exception at its current suspension point, or
`await generator.aclose()` to finish it and run pending `finally` blocks.
`yield from` is not allowed in an async generator.

### Starred unpacking

`*name` on the left of an assignment collects the leftover values into a list:

```vlang
first, *rest = [1, 2, 3, 4];
*head, last = [1, 2, 3];
a, *middle, b = [1, 2, 3, 4, 5];
print(first, rest, head, last, a, middle, b)
```

Newlines end statements, so starred unpacking can start on its own line
without an extra semicolon.

### More small statements

- `pass` does nothing (an explicit empty body).
- `assert condition, "message"` raises `AssertionError` when false.
- `del items[0]`, `del name`, `del obj.attr` remove entries or variables.
- `name := value` assigns inside an expression: `if (n := len(items)) > 3 { ... }`.

```vlang
items = [5, 6, 7]
assert len(items) == 3, "expected three items"
del items[0]
if (n := len(items)) > 1 { print("more than one:", n) }
```

## Classes

```vlang
class Counter {
    def __init__(self, start) {
        self.value = start
    }

    def increment(self) {
        self.value += 1
        return self.value
    }

    def __str__(self) {
        return f"Counter({self.value})"
    }
}

counter = Counter(4)
print(counter.increment())  # 5
print(counter)              # Counter(5)
```

Methods take an explicit first parameter, conventionally named `self`.
`__init__` runs when an object is created, and `__str__` / `__repr__` control
how it is printed.

Classes can inherit from other VirtoLang classes:

```vlang
class Animal {
    def __init__(self, name) { self.name = name }
    def speak(self) { return "..." }
}

class Dog(Animal) {
    def speak(self) { return f"{self.name} says woof" }
}

print(Dog("Rex").speak())
```

Use `super()` inside an instance method to call the next implementation in
the base-class lookup order. VirtoLang methods also support Python's
`@property`, `@property.setter`, and `@staticmethod` descriptors:

```vlang
class Animal {
    def __init__(self, name) { self._name = name }
    @property
    def name(self) { return self._name }
    @name.setter
    def name(self, value) { self._name = value }
    @staticmethod
    def kind() { return "animal" }
}

class Dog(Animal) {
    def speak(self) { return super().name + " says woof" }
}

dog = Dog("Rex")
dog.name = "Fido"
print(dog.speak(), Dog.kind())
```

### Statement boundaries

A newline ends a statement, so statements no longer need semicolons. Use
semicolons when placing multiple statements on one line. Newlines inside
parentheses and square brackets are treated as expression continuations:

```vlang
total = (
    10
    + 5
)
items = [
    "first",
    "second",
]
print(total, items)
```

## Exceptions

`try` runs code that might fail. Matching `except` blocks handle the error and
`finally` always runs afterwards:

```vlang
try {
    value = 10 / divisor
} except ZeroDivisionError as error {
    print("The divisor cannot be zero:", error)
} except Error as error {
    print("Something else went wrong:", error)
} finally {
    print("Finished")
}
```

A bare `except { ... }` catches any regular error. `Error` is VirtoLang's name
for Python's base `Exception`, and Python's built-in exceptions such as
`ValueError` and `KeyError` can be used by name.

### Managing resources

Use `with` to ensure a resource is released even if the block raises an error.
The value after `as` is available inside the block:

```vlang
with open("notes.txt", "w") as file {
    file.write("Saved safely")
}
```

VirtoLang classes can also act as context managers by implementing
`__enter__` and `__exit__`.

Raise an error with `raise`, and create your own by subclassing `Error`:

```vlang
class ValidationError(Error) {
    def __init__(self, message) {
        self.message = message
    }
}

try {
    raise ValidationError("A name is required")
} except ValidationError as error {
    print(error.message)
}
```

## Modules and packages

Any `.vlang` file is a module. Put `tools.vlang` next to your program and
import it by name:

```vlang
import tools
from tools import greet as hello

print(tools.VERSION)
hello("Ada")
```

A folder containing an `__init__.vlang` file is a **package**. Its
`__init__.vlang` runs the first time the package is imported, and the files
inside become submodules:

```text
app.vlang
shapes/
    __init__.vlang
    circle.vlang
    square.vlang
```

```vlang
import shapes.circle
from shapes import square
from shapes.circle import area as circle_area
from shapes import *
```

Inside a package, use relative imports:

```vlang
from . import square
from .circle import area
from ..common import helpers
```

Other things to know:

- `from module import *` imports every public name, or the names listed in
  the module's `__all__` list.
- `__name__` is `"__main__"` in the program you run and the module's name
  inside an imported module, so `if __name__ == "__main__" { main() }` works.
- `__file__` and `__package__` describe where the module came from.
- Modules run once and are cached. Circular imports are supported.
- Errors inside a module point to that module's own file and line.
- Namespace packages (folders without `__init__.vlang`) are not supported.

### Where modules are found

Top-level names are looked up in this order:

1. The folder of the running program (the current folder in the shell).
2. Folders listed in the `VIRTOLANG_PATH` environment variable.
3. The `packages` folder: the active [virtual environment](#virtual-environments)'s
   if there is one, otherwise the global `packages` folder next to VirtoLang
   (override it with `VIRTOLANG_PACKAGES`).
4. Python modules and installed Python packages.

A package folder wins over a `name.vlang` file of the same name. Run
`vlang --paths` to see the exact folders in use.

## Virtual environments

A virtual environment gives a project its own `packages` folder, separate from
the global one.

```powershell
vlang --create-venv .venv
.venv\Scripts\activate        # or: source .venv/bin/activate
```

`activate` scripts are provided for `cmd` (`activate.bat`), PowerShell
(`activate.ps1`) and sh (`activate`). You don't have to activate it: a `.venv`
or `venv` folder created by VirtoLang is found automatically in your program's
folder or any parent, and you can also choose one explicitly:

```powershell
vlang --venv .venv app.vlang
```

When an environment is active, only its `packages` folder is searched, so
projects stay isolated. Package managers written in VirtoLang can use these
built-ins:

| Function              | What it does                                           |
| --------------------- | ------------------------------------------------------ |
| `packages_dir()`      | The `packages` folder imports are currently read from. |
| `venv_dir()`          | The active virtual environment folder, or `none`.      |
| `module_paths()`      | The list of folders searched for modules.              |
| `module_path(name)`   | The file a module would be loaded from, or `none`.     |
| `create_venv(folder)` | Create a virtual environment and return its path.      |

## Using Python from VirtoLang

All of Python's built-in functions (`print`, `len`, `range`, `sorted`, `open`,
`enumerate`...) are available. Import modules with `import` and `from ... import`:

```vlang
import math
import os.path
from time import time as now

print(math.sqrt(16))
print(os.path.basename("/tmp/report.txt"))
print(now())

from collections import Counter as WordCounter, deque
```

Third-party packages work too, as long as they are installed in the Python
environment VirtoLang is running with. The Windows installer bundles its own
Python runtime, so only the modules included with it are available there.

## Built-in functions

On top of Python's own built-ins, VirtoLang ships ready-to-use functions for
jobs that normally take a lot of code. They need no `import`. Type
`list_builtins()` in the shell to see every name.

### Files and folders

| Function                                             | What it does                                          |
| ---------------------------------------------------- | ----------------------------------------------------- |
| `read_file(path)` / `read_lines(path)`               | Read a text file as one string / a list of lines.     |
| `write_file(path, text)` / `append_file(path, text)` | Replace / add to a file (parent folders are created). |
| `read_bytes(path)` / `write_bytes(path, data)`       | Binary file access.                                   |
| `file_exists(path)`, `is_file(path)`, `is_dir(path)` | Check what a path is.                                 |
| `list_dir(path=".")`                                 | Sorted names inside a folder.                         |
| `make_dir(path)`                                     | Create a folder (and parents).                        |
| `delete_file(path)`                                  | Delete a file, or a folder and its contents.          |
| `copy_file(src, dst)`, `move_file(src, dst)`         | Copy, move or rename.                                 |
| `join_path(...)`, `cwd()`                            | Build a path, get the current folder.                 |

### JSON and CSV

| Function                                                  | What it does                                       |
| --------------------------------------------------------- | -------------------------------------------------- |
| `json_parse(text)` / `json_stringify(value, indent=None)` | Convert between JSON text and values.              |
| `read_json(path)` / `write_json(path, value)`             | Load or save a JSON file.                          |
| `read_csv(path)`                                          | Read a CSV with a header row into a list of dicts. |
| `write_csv(path, rows)`                                   | Write a list of dicts as a CSV.                    |
| `pretty(value)`                                           | Indented text for dicts and lists.                 |

```vlang
write_json("config.json", {"theme": "dark", "size": 12})
config = read_json("config.json")
print(config["theme"])
```

### HTTP requests

`http_get`, `http_post`, `http_put`, `http_delete` and the general
`http_request(method, url, ...)` return a response with `status`, `ok`, `text`,
`content` (bytes), `headers` and `url`, plus `.json()` and `.raise_for_status()`.

```vlang
response = http_get("https://api.github.com/repos/python/cpython")
if response.ok {
    print(response.json()["stargazers_count"])
}

http_get("https://example.com/search", params={"q": "virtolang"})
http_post("https://example.com/api", json={"name": "Ada"})
http_post("https://example.com/form", data={"user": "ada"})
download("https://example.com/file.zip", "file.zip")
```

Options: `headers={...}`, `params={...}` (query string), `data=` (form dict, text
or bytes), `json=` and `timeout=` (seconds). Error statuses such as 404 do not
raise; check `response.ok`. Connection failures and timeouts do raise.
`url_encode(...)` and `url_decode(...)` help build addresses by hand.

### Web server

`serve(routes, port=8000)` starts a web server and runs until you press Ctrl-C.
`routes` is a dict mapping paths to a reply or a function, or a single function
that handles every request.

```vlang
def hello(request) {
    return {"hello": request.query.get("name", "world")}
}

def save(request) {
    data = request.json()
    return ({"saved": data}, 201)
}

serve({
    "/": "<h1>Welcome to VirtoLang</h1>",
    "/hello": hello,
    "POST /save": save,
    "*": ("Page not found", 404)
}, port=8080)
```

- A key is a path (`"/about"`), a method and path (`"POST /save"`), or `"*"` as
  the fallback.
- A handler receives a request with `method`, `path`, `query` (dict), `headers`,
  `body` (text), `content` (bytes), `client`, and the methods `.json()` and
  `.form()`.
- A reply can be text (sent as HTML if it starts with `<`), a dict or list
  (sent as JSON), bytes, or a tuple `(body, status)` /
  `(body, status, headers)`.
- It listens on `127.0.0.1` (this computer only) by default. Use
  `host="0.0.0.0"` to allow other devices, only on networks you trust.
- Requests are handled one at a time.

### Windows and dialogs (GUI)

`window(title, width, height)` creates a desktop window. Add controls from top
to bottom, then call `show()`. Each control returns an object with `get()` and
`set(value)`.

```vlang
win = window("Greeter", 320, 200)
name = win.entry()
output = win.label("")

def greet() {
    output.set("Hello, " + name.get() + "!")
}

win.button("Greet", greet)
win.show()
```

Controls: `label(text)`, `button(text, function)`, `entry(text)`,
`textbox(text)`, `checkbox(text, checked)`, `dropdown(options)` and
`slider(low, high)`. Windows also have `after(ms, function)` for timers,
`title(text)` and `close()`. Controls have `disable()` and `enable()`.

Ready-made dialogs: `message_box(text)`, `ask_yes_no(question)` (True/False),
`ask_text(prompt)` (text or `None`), `choose_file()`, `choose_save_file()` and
`choose_folder()` (a path or `None`).

The GUI uses Python's `tkinter`, which is included with most Python installs.

### Time, random, hashing and encoding

| Function                                                   | What it does                              |
| ---------------------------------------------------------- | ----------------------------------------- |
| `sleep(seconds)`                                           | Pause the program.                        |
| `now(fmt="%Y-%m-%d %H:%M:%S")`, `today()`                  | Current local time / date as text.        |
| `timestamp()`, `format_time(seconds, fmt)`                 | Unix time and formatting it.              |
| `random_int(low, high)`                                    | Random whole number (both ends included). |
| `random_float()`, `random_choice(items)`, `shuffle(items)` | Random helpers.                           |
| `uuid()`                                                   | A new unique ID.                          |
| `sha256(value)`, `md5(value)`                              | Hash text or bytes as hex.                |
| `base64_encode(value)` / `base64_decode(text)`             | Base64 conversion.                        |

### System and utilities

| Function                                                   | What it does                                               |
| ---------------------------------------------------------- | ---------------------------------------------------------- |
| `run(command)`                                             | Run a command; returns `output`, `error`, `code` and `ok`. |
| `env(name, default=None)`                                  | Read an environment variable.                              |
| `args()`                                                   | Command-line arguments given to VirtoLang.                 |
| `open_url(url)`                                            | Open a page in the default browser.                        |
| `clamp(value, low, high)`                                  | Keep a number within limits.                               |
| `to_int(value, default=0)`, `to_float(value, default=0.0)` | Convert without errors.                                    |
| `deep_copy(value)`                                         | Fully independent copy of a list or dict.                  |
| `list_builtins()`                                          | List all of the functions on this page.                    |

### Async helpers and decorators

| Function                     | What it does                                                 |
| ---------------------------- | ------------------------------------------------------------ |
| `async_run(coroutine)`       | Run an `async def` call to completion; returns its result.   |
| `await async_sleep(seconds)` | Pause the current task without blocking others.              |
| `await gather(a(), b())`     | Run several async calls together; returns a list of results. |
| `create_task(coroutine)`     | Start an async call in the background.                       |
| `@memoize`                   | Decorator: cache results for repeated arguments.             |
| `@timed`                     | Decorator: print how long each call takes.                   |
| `@retry(times, delay=0)`     | Decorator: call again if the function raises.                |

`run("...")` executes through the system shell, so only pass it text you trust.

### Lists, dictionaries and functional helpers

| Function                                                                                                                                       | What it does                               |
| ---------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| `first(items, default)`, `last(items, default)`, `take(items, n)`, `drop(items, n)`                                                            | Pick items from the ends.                  |
| `chunk(items, size)`, `flatten(items, depth=1)`, `flat_map(fn, items)`                                                                         | Reshape lists (`depth=-1` flattens fully). |
| `unique(items)`, `compact(items)`, `reverse(items)`, `rotate(items, n)`, `transpose(rows)`, `repeat(value, n)`                                 | Tidy and rearrange.                        |
| `group_by(items, fn)`, `count_by(items, fn)`, `partition(items, fn)`, `counter(items)`, `most_common(items, n)`                                | Group and count.                           |
| `pluck(items, key)`, `sort_by(items, fn)`, `min_by`, `max_by`, `sum_by`                                                                        | Work with records.                         |
| `find(items, fn)`, `find_index`, `every`, `some`, `count_if`, `index_of`                                                                       | Search.                                    |
| `reduce(fn, items, start)`, `accumulate(items)`, `product(items)`, `pairwise(items)`, `sliding_window(items, n)`                               | Fold and walk lists.                       |
| `union`, `intersection`, `difference`, `sample(items, n)`, `zip_dict(keys, values)`                                                            | Set-style helpers.                         |
| `merge(a, b)`, `deep_merge(a, b)`, `pick(d, keys)`, `omit(d, keys)`, `invert(d)`, `map_values(d, fn)`, `map_keys(d, fn)`, `filter_dict(d, fn)` | Dictionary helpers.                        |
| `get_path(data, "a.b.0")`, `set_path(data, "a.b", value)`                                                                                      | Read/write nested data.                    |
| `compose(f, g)`, `pipe(value, f, g)`, `partial(fn, ...)`, `once(fn)`, `identity`, `constant`, `noop`, `tap`, `default(value, fallback)`        | Functional tools.                          |
| `measure(fn)`, `benchmark(fn, runs)`, `stopwatch()`                                                                                            | Timing.                                    |
| `parallel_map(fn, items, workers)`, `run_in_thread(fn)`, `every_seconds(n, fn, times)`                                                         | Concurrency and scheduling.                |
| `type_name`, `is_number`, `is_string`, `is_list`, `is_dict`, `is_none`, `is_empty`, `is_numeric_string`                                        | Type checks.                               |

### Text and regular expressions

| Function                                                                                                                  | What it does           |
| ------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| `snake_case`, `kebab_case`, `camel_case`, `pascal_case`, `title_case`, `slugify`                                          | Change naming style.   |
| `truncate`, `pad_left`, `pad_right`, `center_text`, `wrap_text`, `indent_text`, `dedent_text`                             | Layout.                |
| `words`, `lines`, `count_words`, `is_blank`, `is_palindrome`, `remove_prefix`, `remove_suffix`                            | Inspect text.          |
| `strip_html`, `html_escape`, `html_unescape`                                                                              | HTML text.             |
| `levenshtein(a, b)`, `similarity(a, b)`, `closest_match(word, options)`                                                   | Fuzzy matching.        |
| `regex_find_all`, `regex_replace`, `regex_split`, `regex_test`, `regex_groups`                                            | Regular expressions.   |
| `extract_numbers`, `extract_emails`, `extract_urls`, `is_email`, `is_url`                                                 | Pull data out of text. |
| `number_format(1234.5)`, `ordinal(3)`, `pluralize(2, "file")`, `human_size(bytes)`, `human_duration(seconds)`, `roman(n)` | Friendly formatting.   |
| `random_string`, `random_token`, `random_password`                                                                        | Secure random text.    |
| `colorize(text, "red")`, `progress_bar(done, total)`, `table(rows)`, `print_table(rows)`                                  | Terminal output.       |

### Math and statistics

| Function                                                                                                                                                         | What it does     |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------- |
| `sqrt`, `floor`, `ceil`, `trunc`, `log`, `log2`, `log10`, `exp`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`, `radians`, `degrees`, `hypot`, `distance` | Math functions.  |
| `pi`, `tau`, `inf`, `nan`                                                                                                                                        | Constants.       |
| `gcd`, `lcm`, `factorial`, `isqrt`, `is_prime`, `primes(limit)`, `prime_factors`, `fibonacci(n)`                                                                 | Number theory.   |
| `combinations`, `permutations`, `cartesian_product`, `combinations_count`, `permutations_count`                                                                  | Counting.        |
| `mean`, `median`, `mode`, `stdev`, `variance`, `percentile(values, p)`                                                                                           | Statistics.      |
| `sign`, `lerp`, `map_range`, `percent`, `is_close`, `to_bool`, `to_base(n, base)`                                                                                | Small helpers.   |
| `random_bool`, `random_gauss`, `random_seed`, `random_color`, `roll("2d6")`                                                                                      | More randomness. |

### Dates, files and data

| Function                                                                                                                 | What it does                                           |
| ------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------ |
| `parse_time(text, fmt)`, `add_days`, `add_time`, `diff_days`, `diff_seconds`, `utc_now`, `from_timestamp`                | Date arithmetic.                                       |
| `weekday_name`, `month_name`, `is_leap_year`, `days_in_month`, `calendar_text`, `time_ago`                               | Calendar helpers.                                      |
| `file_size`, `file_name`, `file_stem`, `file_ext`, `parent_dir`, `abs_path`, `modified_time`, `count_lines`, `file_hash` | File information.                                      |
| `home_dir`, `temp_dir`, `temp_file`, `touch`, `rename`, `delete_dir`, `copy_dir`, `glob_files`, `walk_dir`, `disk_usage` | Folders and paths.                                     |
| `zip_folder`, `unzip`                                                                                                    | Archives.                                              |
| `read_toml`, `toml_parse`, `read_ini`, `csv_parse`, `csv_stringify`                                                      | More data formats.                                     |
| `sqlite_query(path, sql, params)`, `sqlite_exec(path, sql, params)`                                                      | Use a SQLite database; queries return a list of dicts. |

### Encoding, network and system

| Function                                                                                                                                  | What it does                 |
| ----------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| `sha1`, `sha512`, `hmac_sha256`, `crc32`, `hex_encode`, `hex_decode`, `base32_encode`, `base32_decode`, `compress`, `decompress`, `rot13` | Hashing and encoding.        |
| `url_parse`, `url_join`, `query_string`                                                                                                   | Work with URLs.              |
| `http_json(url)`, `dns_lookup`, `local_ip`, `port_open(host, port)`, `is_online()`                                                        | Network helpers.             |
| `os_name`, `hostname`, `username`, `cpu_count`, `pid`, `python_version`, `env_set`, `env_all`, `which`                                    | About this computer.         |
| `read_int`, `read_float`, `confirm`, `choose(prompt, options)`, `get_password`                                                            | Terminal input.              |
| `log_info`, `log_warn`, `log_error`, `clear_screen`, `beep`, `clipboard_get`, `clipboard_set`                                             | Logging and desktop helpers. |

Some of these names (such as `first`, `lines` or `mode`) are common variable
names. You can still use them: assigning a value simply replaces the built-in
in your program.

## Error messages

When a program fails, VirtoLang shows where the problem is, what went wrong,
and a hint for common mistakes:

```text
  File "demo.vlang", line 2, column 7
  2 | print("Count: " + 3)
    |       ^
VirtoLang TypeError: can only concatenate str (not "int") to str
Suggestion: Convert the non-string value with str(value), or use an f-string such as f"{value}".
```

For runtime errors, the caret marks the start of the statement or expression
that failed, which is not always the exact operator.

## Limitations

VirtoLang uses braces for code blocks rather than Python's indentation-based
blocks. Positional-only parameters, `super()`, property/static method
descriptors, async generators and logical newline statement boundaries are
supported.

## Release notes

See [RELEASE_NOTES.md](./RELEASE_NOTES.md) for the list of changes in each
release.
