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
- [Classes](#classes)
- [Exceptions](#exceptions)
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

| Command | What it does |
| --- | --- |
| `vlang file.vlang` | Run a program. |
| `vlang` | Run `main.vlang` from the current folder. |
| `vlang -c file.vlang` | Check the syntax without running the program. |
| `vlang -e "print(1 + 2)"` | Run code given directly on the command line. |
| `vlang -r` | Start the [interactive shell](#the-interactive-shell-repl). |
| `vlang -r file.vlang` | Run a program, then open the shell with its variables and functions available. |
| `vlang -v` | Show the version. |
| `vlang -h` | Show help. |

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
VirtoLang 4.1.0 interactive shell (Python 3.14.3 on win32)
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

| Command | Meaning |
| --- | --- |
| `:help` | Show help. |
| `:vars` | List everything you have defined. |
| `:reset` | Clear the session and start fresh. |
| `:exit` | Leave the shell. `exit()` and `quit()` also work. |

## Language basics

### Statements, semicolons and comments

Statements are normally written one per line, but whitespace and line breaks
do not matter to the parser. You can end a statement with a semicolon (`;`) to
put several statements on one line, or to write an entire program on a single
line:

```vlang
a = 1; b = 2; print(a + b)
```

Semicolons are optional and can be repeated or left at the end of a line. They
also work inside blocks:

```vlang
if a < b { print("a is smaller"); a = b }
```

Because line breaks do not end statements, use a semicolon if a new statement
starts with `(`, `[`, `+` or `-` and could be mistaken for a continuation of
the previous line.

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

| Operator | Meaning |
| --- | --- |
| `+` `-` `*` `/` | Add, subtract, multiply, divide |
| `//` | Floor division |
| `%` | Remainder |
| `**` | Power (`2 ** 10` is `1024`) |
| `==` `!=` `<` `>` `<=` `>=` | Comparison |
| `in`, `not in` | Membership test (`3 in [1, 2, 3]`) |
| `and`, `or`, `not` | Boolean logic (`and` / `or` short-circuit) |

Comparisons can be chained, as in Python: `0 < x < 10`.

Augmented assignment is supported for `+=`, `-=`, `*=`, `/=`, `//=`, `%=` and
`**=`. Parentheses group expressions:

```vlang
total = 10
total += 5
result = (2 + 3) * 4
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
  statement.
- Functions can call themselves (recursion) and can be defined inside other
  functions. Inner functions can read the variables of the function around
  them.
- Variables assigned inside a function are local to that function.
- VirtoLang functions can be passed to Python functions, for example
  `sorted(words, key=length_of)`.

```vlang
def factorial(n) {
    if n <= 1 { return 1 }
    return n * factorial(n - 1)
}

print(factorial(10))
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

| Function | What it does |
| --- | --- |
| `read_file(path)` / `read_lines(path)` | Read a text file as one string / a list of lines. |
| `write_file(path, text)` / `append_file(path, text)` | Replace / add to a file (parent folders are created). |
| `read_bytes(path)` / `write_bytes(path, data)` | Binary file access. |
| `file_exists(path)`, `is_file(path)`, `is_dir(path)` | Check what a path is. |
| `list_dir(path=".")` | Sorted names inside a folder. |
| `make_dir(path)` | Create a folder (and parents). |
| `delete_file(path)` | Delete a file, or a folder and its contents. |
| `copy_file(src, dst)`, `move_file(src, dst)` | Copy, move or rename. |
| `join_path(...)`, `cwd()` | Build a path, get the current folder. |

### JSON and CSV

| Function | What it does |
| --- | --- |
| `json_parse(text)` / `json_stringify(value, indent=None)` | Convert between JSON text and values. |
| `read_json(path)` / `write_json(path, value)` | Load or save a JSON file. |
| `read_csv(path)` | Read a CSV with a header row into a list of dicts. |
| `write_csv(path, rows)` | Write a list of dicts as a CSV. |
| `pretty(value)` | Indented text for dicts and lists. |

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

| Function | What it does |
| --- | --- |
| `sleep(seconds)` | Pause the program. |
| `now(fmt="%Y-%m-%d %H:%M:%S")`, `today()` | Current local time / date as text. |
| `timestamp()`, `format_time(seconds, fmt)` | Unix time and formatting it. |
| `random_int(low, high)` | Random whole number (both ends included). |
| `random_float()`, `random_choice(items)`, `shuffle(items)` | Random helpers. |
| `uuid()` | A new unique ID. |
| `sha256(value)`, `md5(value)` | Hash text or bytes as hex. |
| `base64_encode(value)` / `base64_decode(text)` | Base64 conversion. |

### System and utilities

| Function | What it does |
| --- | --- |
| `run(command)` | Run a command; returns `output`, `error`, `code` and `ok`. |
| `env(name, default=None)` | Read an environment variable. |
| `args()` | Command-line arguments given to VirtoLang. |
| `open_url(url)` | Open a page in the default browser. |
| `clamp(value, low, high)` | Keep a number within limits. |
| `to_int(value, default=0)`, `to_float(value, default=0.0)` | Convert without errors. |
| `deep_copy(value)` | Fully independent copy of a list or dict. |
| `list_builtins()` | List all of the functions on this page. |

`run("...")` executes through the system shell, so only pass it text you trust.

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

VirtoLang is still growing. These Python features are not available yet:

- `lambda`, list/dict comprehensions, `with`, `async` / `await`, decorators
- `is` / `is not`, set literals, and unpacking assignments such as `a, b = b, a`
- `global` / `nonlocal` (a function cannot reassign a variable of an outer
  scope)
- `super()` and keyword-only / variable-length parameters (`*args`, `**kwargs`)
- Multi-line (triple-quoted) strings

## Release notes

See [RELEASE_NOTES.md](./RELEASE_NOTES.md) for the list of changes in each
release.
