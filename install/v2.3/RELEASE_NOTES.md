# VirtoLang v2.3 – Release Notes (June 12, 2025)

## Major Features

- **Python-like Syntax**: Curly-brace blocks, dynamic typing, familiar operators, and Pythonic data structures (lists, dicts, sets, tuples).
- **Async/Await**: Native support for asynchronous functions, tasks, and file execution.
- **Robust Error Handling**: Python-style `try`/`except`/`finally`, custom exceptions, and clear, user-friendly error messages.
- **Functions & Classes**: Define and call both synchronous and asynchronous functions, with support for return values and parameters.
- **Advanced Modules**: Built-in support for HTTP requests, file I/O, date/time, random, math, and more.
- **Import System**: Import other VirtoLang files or packages, with flexible path and package support.
- **Comprehensions, Lambdas, Match Statements**: (Planned/partial support)
- **Optimized Interpreter**: Fast tokenization, parsing, and execution, with local variable lookups and minimal overhead.
- **Extensible**: Easy to add new built-in functions and modules.
- **Command-line Interface**: Run `.vlang` files directly from the terminal.
- **Clear Error Messages**: With code context and suggestions.

## New in v2.3

- **Improved Error Handling**: Parser and runtime errors now provide clear, context-rich messages and avoid attribute errors.
- **Modulus Operator (%)**: Full support for the `%` operator in expressions and arithmetic.
- **Logical Operators**: Expressions now support `and`, `or`, and `not` with correct precedence and short-circuiting.
- **Pythonic Range**: The built-in `range` function now accepts 1, 2, or 3 arguments, matching Python’s signature.
- **For-Loop Parsing**: For-loops now correctly parse the `in` keyword and support Python-style iteration.
- **Compatibility**: FizzBuzz and other Pythonic code samples now run without parser or interpreter errors.
- **General Stability**: Numerous bug fixes and improvements for a smoother development experience.

## Example: FizzBuzz in VirtoLang

```vlang
for (i in range(1, 101)) {
    if (i % 15 == 0) {
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

For full documentation, see the README in this directory.
