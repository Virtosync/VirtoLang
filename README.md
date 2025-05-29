# VirtoLang Language Reference & User Guide

VirtoLang is a modern, Python-inspired scripting language with curly-brace blocks, dynamic typing, async/await, and robust error handling. This guide covers installation, language features, syntax, error handling, and advanced usage with full examples.

---

## Installation

1. **Download the Installer:**
   - Go to the `install` folder in this repository.
   - Choose your desired version (e.g., `v2`).
   - Click on `virtolang-installer.exe`.
   - Click the **Raw** button to download and run the installer.
   - Follow the prompts to complete the installation.

2. **Verify Installation:**
   - Open a terminal or command prompt (if it is already open, restart your terminal or command prompt or restart your computer).
   - Run: `vlang` to check that VirtoLang is installed.

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
- [19. Troubleshooting](#19-troubleshooting)

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

## 3. Printing
Use `print()` to output values:
```vlang
print("Hello, world!")
print(x)
print("Sum:", 2 + 2)
```

## 4. Arithmetic & Comparison
Supports `+`, `-`, `*`, `/`, `==`, `!=`, `<`, `>`, `<=`, `>=`:
```vlang
y = 6
print(y / 2)  # prints 3.0
if (y >= 3 and y < 10) {
    print("In range")
}
```

## 5. Boolean Logic
Use `and`, `or`, `not`, and boolean literals:
```vlang
if (true and not false) {
    print("Booleans work!")
}
```
Supports Python-style logical operators:
- `not in`, `is not`, `in`, `is`

## 6. Strings
Single or double quotes supports escape sequences:
```vlang
s = 'hello\nworld'
t = "She said, \"hi!\""
print(s)
print(t)
```
String concatenation:
```vlang
name = "Virto"
greeting = "Hello, " + name
print(greeting)
```

## 7. Lists
List literals with brackets:
```vlang
nums = [1, 2, 3, 4]
print(nums[0])  # 1
nums.append(5)
print(nums)
```

## 8. Dictionaries
Create and use dictionaries:
```vlang
d = dict()
dict_set(d, "key", 123)
print(dict_get(d, "key"))
print(dict_keys(d))
```

## 9. Functions
Define and call functions:
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
Supports async functions:
```vlang
async def foo(x) {
    print(x)
}
```
Return values are optional. Functions can be called before or after their definition.

## 10. Control Flow
### If / Elif / Else
```vlang
if (x > 0) {
    print("Positive")
} elif (x == 0) {
    print("Zero")
} else {
    print("Negative")
}
```

## 11. Loops
### While Loops
```vlang
i = 0
while (i < 5) {
    print(i)
    i = i + 1
}
```
### For Loops
For each over lists:
```vlang
items = [1, 2, 3]
for (item in items) {
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
- You can organise code into packages and modules for reuse.

## 14. Async & Await
VirtoLang supports async/await and running files. Use function call syntax for `run` and `run_async`:
```vlang
async def async_hello(name) {
    print("Hello, " + name)
    return 42
}
task = async_hello("Virto")
result = await task
print(result)

run("test1.vlang")
task2 = run_async("test2.vlang")
await task2
```
- `run(filename)` executes another .vlang file synchronously, sharing variables and functions.
- `run_async(filename)` executes another .vlang file asynchronously and returns a task.
- Use `await` to wait for async functions or tasks.

### More Async Examples
```vlang
async def slow_add(a, b) {
    await sleep(1)
    return a + b
}
task = slow_add(2, 3)
print("Waiting...")
result = await task
print("Result:", result)
```

## 15. Built-in Functions
VirtoLang includes a rich set of built-in functions:
- `print`, `len`, `str`, `int`, `type`, `input`, `range`, `sum`, `min`, `max`, `abs`, `sorted`, `reverse`, `append`, `pop`, `dict`, `dict_get`, `dict_set`, `dict_keys`, `dict_values`, `slice`, `random`, `randint`, `sleep`, `time`, `now`, `strftime`, `argv`, `help`, `set`, `tuple`, `open`, `read`, `write`, `close`, `run`, `run_async`, `async`, `await`, `exit`, `Error`

### Example: Using Built-ins
```vlang
print(len([1,2,3]))
print(type(123))
print(str(123))
print(random())
```

## 16. Error Messages & Debugging
VirtoLang provides clear, user-friendly error messages with code context and suggestions.

### Example: Invalid Logical Operator
```vlang
if (5 is not 3) {
    print("TRUE")
} else {
    print("FALSE")
}
```
**Error Output:**
```
SyntaxError: Expected 'in' or 'is' after 'not' in condition. Did you mean 'not in' or 'is not'?
  File "ai.vlang", line 1, col 7
    if (5 is not 3){
          ^
```
**How to Fix:**
- Use `not in` for membership: `if (5 not in [3]) { ... }`
- Use `is not` for identity: `if (x is not y) { ... }`

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

### FizzBuzz
```vlang
for (i in range(1, 16)) {
    if (i % 3 == 0 and i % 5 == 0) {
        print("FizzBuzz")
    } elif (i % 3 == 0) {
        print("Fizz")
    } elif (i % 5 == 0) {
        print("Buzz")
    } else {
        print(i)
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
Organise your code into folders with an `__init__.vlang` file. Import using:
```vlang
import mypackage
```

## 19. Troubleshooting
- **SyntaxError:** Check for missing braces `{}` or parentheses `()`.
- **RuntimeError:** Check variable names and function calls.
- **ImportError:** Ensure the file or package exists and is in the correct location.
- **Async Issues:** Use `await` with async functions and tasks.
- **Still stuck?** See the README or open an issue on GitHub.

---

For more information, see the README or ask for help. Happy coding with VirtoLang!
