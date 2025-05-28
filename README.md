# VirtoLang Language Reference & User Guide

VirtoLang is a Python-inspired, modern scripting language with curly-brace blocks, dynamic typing, and a focus on readability and power. This document covers all major features, syntax, and error handling in VirtoLang.

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

---

## 1. Variables
Assign variables using Python-style assignment (no `var` keyword needed):
```vlang
x = 5
name = "VirtoLang"
```

## 2. Data Types
- Numbers: `n = 42`
- Strings: `s = 'hello'` or `t = "world"`
- Booleans: `true`, `false`
- Null: `null`
- Lists: `nums = [1, 2, 3]`
- Dictionaries: `d = dict()`

## 3. Printing
Use `print()` to output values:
```vlang
print("Hello, world!")
print(x)
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
Single or double quotes, supports escape sequences:
```vlang
s = 'hello\nworld'
t = "She said, \"hi!\""
```

## 7. Lists
List literals with brackets:
```vlang
nums = [1, 2, 3, 4]
```

## 8. Dictionaries
Create and use dictionaries:
```vlang
d = dict()
dict_set(d, "key", 123)
print(dict_get(d, "key"))
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
For-each over lists:
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

## 13. Imports & Packages
Import other VirtoLang files or packages:
```vlang
import mymodule      # Imports mymodule.vlang
import "C:/path/to/file"  # Imports file.vlang from a path
```

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

## 15. Built-in Functions
- `print`, `len`, `str`, `int`, `type`, `input`, `range`, `sum`, `min`, `max`, `abs`, `sorted`, `reverse`, `append`, `pop`, `dict`, `dict_get`, `dict_set`, `dict_keys`, `dict_values`, `slice`, `random`, `randint`, `sleep`, `time`, `now`, `strftime`, `argv`, `help`, `set`, `tuple`, `open`, `read`, `write`, `close`, `run`, `run_async`, `async`, `await`, `exit`, `Error`

## 16. Error Messages & Debugging
VirtoLang provides clear, user-friendly error messages with code context and suggestions.

### Example: Invalid Logical Operator
```vlang
if (5 not 3) {
    print("TRUE")
} else {
    print("FALSE")
}
```
**Error Output:**
```
SyntaxError: Expected 'in' or 'is' after 'not' in condition. Did you mean 'not in' or 'is not'?
  File "ai.vlang", line 1, col 7
    if (5 not 3){
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

For more information, see the README or ask for help. Happy coding with VirtoLang!
