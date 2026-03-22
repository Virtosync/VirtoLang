# VirtoLang Language Reference & User Guide (v3)

VirtoLang v3 focuses on deep Python interoperability, simplification of the built-in surface, and major performance improvements. The language retains VirtoLang's curly-brace block syntax while allowing direct use of Python builtins and any installed Python packages. This guide covers installation, language features, syntax, error handling, migration notes, and examples updated for v3.

---

## Key Features (v3)

- **Full Python integration:** VirtoLang will fall back to Python builtins (e.g., `len`, `sum`, `open`, `json`) and lets you `import` any installed Python package (for example, `requests`, `numpy`, `pandas`, `tkinter`).
- **Curly-brace block syntax:** Blocks use `{` and `}`; conditions and loop headers do not use surrounding parentheses. Statements do not require semicolons.
- **Performance overhaul:** Lexer/parsing optimizations and faster interpreter dispatch for large speed improvements.
- **Smaller core built-ins:** Many previously-provided language-specific helpers were removed in favor of using Python packages; prefer Python modules for HTTP, GUI, and advanced utilities.
- **Robust error handling:** `try`/`except`/`finally` remains supported with clear messages and context.
- **Classes and functions:** Define classes and functions using VirtoLang syntax; Python objects and callables are first-class.
- **Command-line interface:** Run `.vlang` files directly with the `vlang` CLI.

---

## Installation

1. **Download the Installer:**
   - Go to the `install` folder in this repository.
   - Choose your desired version (e.g., `v2`).
   - Click on `virtolang-installer.exe`.
   - Click the **Raw** button to download and run the installer.
   - Follow the prompts to complete installation.

2. **Verify Installation:**
   - Open a terminal or command prompt.
   - Run: `vlang --version` or `vlang` to check that VirtoLang is installed.

---

## Getting Started

Create a new file with the `.vlang` extension, for example, `hello.vlang`.

```vlang
print("Hello, world!")
```

Run your script from the terminal:

```
vlang hello.vlang
```

---

## Table of Contents

- [1. Variables](#1-variables)
- [2. Data Types](#2-data-types)
- [3. Printing](#3-printing)
- [4. Arithmetic & Comparison](#4-arithmetic--comparison)
- [5. Boolean Logic](#5-boolean-logic)
- [6. Strings](#6-strings)
- [7. Lists](#7-lists)
- [8. Dictionaries](#8-dictionaries)
- [9. Functions](#9-functions)
- [10. Control Flow](#10-control-flow)
- [11. Loops](#11-loops)
- [12. Exception Handling](#12-exception-handling)
- [13. Imports & Packages](#13-imports--packages)
- [14. Async & Await](#14-async--await)
- [15. Built-in Functions](#15-built-in-functions)
- [16. Error Messages & Debugging](#16-error-messages--debugging)
- [17. Example Programs](#17-example-programs)
- [18. Advanced Usage](#18-advanced-usage)
- [19. Speed & Performance](#19-speed--performance)
- [20. Troubleshooting](#20-troubleshooting)

---

## 1. Variables

Assign variables using Python-style assignment (no `var` keyword needed):

```vlang
x = 5
name = "VirtoLang"
```

Variables are dynamically typed and can be reassigned to any type.

## 2. Data Types

- **Numbers:**
  ```vlang
  n = 42
  pi = 3.1415
  ```
- **Strings:**
  ```vlang
  s = 'hello'
  t = "world"
  ```
- **Booleans:** `true`, `false`
- **Null:** `null`
- **Lists:**
  ```vlang
  nums = [1, 2, 3]
  ```
- **Dictionaries:**
  ```vlang
  d = dict()
  dict_set(d, "key", 123)
  print(dict_get(d, "key"))
  ```
- **Sets & Tuples:**
  ```vlang
  s = set(1, 2, 3)
  t = tuple(1, 2, 3)
  ```

## 3. Printing

Use `print()` to output values:

```vlang
print("Hello, world!")
print(x)
print("Sum:", 2 + 2)
```

## 4. Arithmetic & Comparison

Supports `+`, `-`, `*`, `/`, `==`, `!=`, `<`, `>`, `<=`, `>=`, `%`, `mod`, `pow`, `abs`, etc. Conditions use no surrounding parentheses:

```vlang
y = 6
print(y / 2)  # prints 3.0
if y >= 3 and y < 10 {
    print("In range")
}
print(mod(10, 3))  # 1
print(pow(2, 8))   # 256.0
```

## 5. Boolean Logic

Use `and`, `or`, `not`, and boolean literals. Conditions do not use parentheses:

```vlang
if true and not false {
    print("Booleans work!")
}
```

Supports Python-style logical operators:

- `not in`, `is not`, `in`, `is`

## 6. Strings

Single or double quotes, supports escape sequences:

```vlang
s = 'hello\nworld'
t = "She said, \"hi!\""
print(s)
print(t)
```

String concatenation and built-ins:

```vlang
name = "Virto"
greeting = "Hello, " + name
print(greeting)
print(upper(greeting))
print(lower(greeting))
print(replace(greeting, "Hello", "Hi"))
print(split(greeting, ", "))
print(join(["a", "b", "c"], ","))
```

## 7. Lists

List literals with brackets:

```vlang
nums = [1, 2, 3, 4]
print(nums[0])  # 1
append(nums, 5)
print(nums)
print(len(nums))
print(sorted(nums))
print(reverse(nums))
```

## 8. Dictionaries

Create and use dictionaries:

```vlang
d = dict()
dict_set(d, "key", 123)
print(dict_get(d, "key"))
print(dict_keys(d))
print(dict_values(d))
```

## 9. Functions

Define and call functions (no parentheses around headers):

```vlang
def greet(name) {
    print("Hello, " + name)
}
greet("Zack")

def add(a, b) {
    return a + b
}
print(add(2, 3))
```

Note: v3 does not provide a native `async`/`await` language keyword. For asynchronous programming, import and use Python's `asyncio` and related libraries from VirtoLang.

## 10. Control Flow

### If / Else (no `elif`)

VirtoLang v3 does not include `elif`. Use `else` with a nested `if` for else-if behavior. Conditions do not use parentheses:

```vlang
if x > 0 {
    print("Positive")
} else {
    if x == 0 {
        print("Zero")
    } else {
        print("Negative")
    }
}
```

## 11. Loops

### While Loops

Loop headers do not use parentheses:

```vlang
i = 0
while i < 5 {
    print(i)
    i = i + 1
}
```

### For Loops

For-each over lists (no parentheses around header):

```vlang
items = [1, 2, 3]
for item in items {
    print(item)
}
```

## 12. Exception Handling

VirtoLang supports Python-style exception handling:

```vlang
try {
    raise Error("Something went wrong!")
} except Error as e {
    print("Caught error:", e)
} finally {
    print("Cleanup!")
}
```

- Use `raise` to throw errors.
- Use `try`/`except`/`finally` for error handling.
- Use `as` to bind the exception to a variable.
- The built-in `Error` class can be used or subclassed.

### More Exception Examples

```vlang
try {
    x = 1 / 0
} except Error as e {
    print("Caught error:", e)
}

try {
    raise Error("fail!")
} except Error as e {
    print(e)
}
```

## 13. Imports & Packages

Import other VirtoLang files or packages:

```vlang
import mymodule      # Imports mymodule.vlang or mymodule/__init__.vlang
import "C:/path/to/file"  # Imports file.vlang from a path
```

- When importing a package, VirtoLang looks for `__init__.vlang` in the package directory.
- You can organize code into packages and modules for reuse.

## 14. Async & Concurrency

v3 no longer provides language-level `async`/`await` keywords. Use Python's `asyncio` and other concurrency libraries by importing them from VirtoLang. Example (run Python coroutines via `asyncio`):

```vlang
import asyncio

# create event loop and run coroutine using Python APIs
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
# use Python coroutine objects via imported modules
```

For many advanced async patterns use Python libraries directly.

## 15. Built-ins and Python interoperability

v3 intentionally reduces the number of language-specific built-ins. Many utilities are now provided by Python builtins or installed packages; import them directly from VirtoLang. Examples below use Python modules where appropriate.

- General helpers: `print`, `len`, `str`, `int`, `type`, `input`, `range`, `sum`, `min`, `max`, `abs`, `sorted`
- Math and stdlib: use Python modules (`import math`, `import json`, etc.)
- Random/time: use Python's `random` and `time` modules

Example using Python stdlib and packages:

```vlang
print(len([1,2,3]))
import math
print(math.sqrt(16))
import requests
resp = requests.get("https://httpbin.org/get")
print(resp.status_code)
```

If a named function is not found in VirtoLang scope, the interpreter will attempt to resolve it via Python builtins.

## 16. Error Messages & Debugging

VirtoLang provides clear, user-friendly error messages with code context and suggestions. Condition syntax uses no parentheses; examples below show the v3 style.

### Example: Invalid Logical Operator

```vlang
if 5 not in [3] {
    print("TRUE")
} else {
    print("FALSE")
}
```

If you see a syntax error about `not` usage, use `not in` for membership and `is not` for identity.

### Example: Exception Handling

```vlang
try {
    raise Error("fail!")
} except Error as e {
    print(e)
}
```

## 17. Example Programs

### Hello World

```vlang
print("Hello, world!")
```

### FizzBuzz (v3 block style)

```vlang
for i in range(1, 16) {
    if i % 3 == 0 and i % 5 == 0 {
        print("FizzBuzz")
    } else {
        if i % 3 == 0 {
            print("Fizz")
        } else {
            if i % 5 == 0 {
                print("Buzz")
            } else {
                print(i)
            }
        }
    }
}
```

---

## 18. Advanced Usage

### File I/O

```vlang
f = open("test.txt", "w")
write(f, "Hello!")
close(f)

f = open("test.txt", "r")
print(read(f))
close(f)
```

### Custom Error Classes

```vlang
def MyError(msg) {
    Error.__init__(self, msg)
}
try {
    raise MyError("custom!")
} except MyError as e {
    print("Custom error:", e)
}
```

### Using Packages

Organize your code into folders with an `__init__.vlang` file. Import using:

```vlang
import mypackage
```

---

## 19. Speed & Performance

VirtoLang is now highly optimized for speed:

- **Fast tokenization and parsing**: Optimized regex, minimal recursion, efficient AST traversal.
- **Efficient interpreter dispatch**: Uses fast lookups, caching, and minimal overhead.
- **Async/await and concurrency**: Leverages Python's asyncio and threading for parallelism.
- **Compiled module support**: You can import and use compiled Python modules for speed.
- **Batch execution**: Run multiple scripts or tasks in parallel.
- **Profiling and debugging tools**: Use `virto_profile`, `virto_timeit`, and more to optimize your code.

##### Please note that it will be slower compare to other languages as it's an interpreted language made with an interpreted language.

---

## 20. Troubleshooting

- **SyntaxError:** Check for missing braces `{}` or parentheses `()`.
- **RuntimeError:** Check variable names and function calls.
- **ImportError:** Ensure the file or package exists and is in the correct location.
- **Async Issues:** Use `await` with async functions and tasks.
- **Performance Issues:** Use built-in profiling and concurrency tools.
- **Still stuck?** See the README or open an issue on GitHub.

---

## 21. CLI

- `vlang --version` | Gets the currently installed VirtoLang version.
- `vlang -V` | Gets the currently installed VirtoLang version.
- `vlang -C "print('test')"` | Runs code directly from the CLI. (Will print "test")
- `vlang --code "print('test')"` | Runs code directly from the CLI. (Will print "test")
- `vlang main.vlang`

---

For more information, see the README or ask for help. Happy coding with VirtoLang!
