VirtoLang Documentation
=======================

VirtoLang is a Python-inspired language using curly braces `{}` for code blocks (instead of colons/indentation) and supports many familiar constructs. Below are the features and syntax you can use:

---

**1. Variables**
- Declare with `var`:
  var x = 5
  var name = 'VirtoLang'

**2. Printing**
- Use `print()`:
  print('Hello, world!')
  print(x)

**3. Functions**
- Define with `def` and call with parentheses:
  def greet(name) {
    print('Hello, ' + name)
  }
  greet('Zack')

**4. Return Statements**
- Functions can return values:
  def add(a, b) {
    return a + b
  }
  var result = add(2, 3)
  print(result)

**5. If / Elif / Else**
- Use parentheses for conditions and curly braces for blocks:
  if (x > 0) {
    print('Positive')
  } elif (x == 0) {
    print('Zero')
  } else {
    print('Negative')
  }

**6. While Loops**
- Standard while loop:
  var i = 0
  while (i < 5) {
    print(i)
    var i = i + 1
  }

**7. For Loops**
- For-each over lists:
  var items = [1, 2, 3]
  for (item in items) {
    print(item)
  }

**8. Lists**
- List literals with brackets:
  var nums = [1, 2, 3, 4]

**9. Arithmetic & Comparison**
- +, -, *, / (integer division), ==, !=, <, >, <=, >=:
  var y = 6
  print(y / 2)  # prints 3
  if (y >= 3 and y < 10) {
    print('In range')
  }

**10. Boolean Logic**
- Use `and`, `or`, `not`, and boolean literals:
  if (true and not false) {
    print('Booleans work!')
  }

**11. Strings**
- Single or double quotes:
  var s = 'hello'
  var t = "world"
  print(s + ' ' + t)

**12. Comments**
- Single line: # This is a comment
- Block: /* This is a block comment */

**13. Function Calls**
- Call user-defined functions:
  def add(a, b) {
    return a + b
  }
  print(add(2, 3))

**14. Imports**
- Import other VirtoLang files from the current directory (filename without extension):
  import mymodule
  # This will run mymodule.vlang and make its functions/variables available

**15. Async/Await/Run/Run_Async as Language Constructs**
VirtoLang now supports Python-style async/await and file execution as first-class language features:

- `async def foo(x) { ... }` defines an async function.
- `await <expr>` can be used as a statement or expression to await a task or async function.
- `run <filename>` runs another .vlang file synchronously as a statement.
- `run_async <filename>` runs another .vlang file asynchronously as a statement, returning a task/future.

### Examples

```
async def async_hello(name) {
    print("Hello, " + name)
    return 42
}

task = async_hello("Virto")
result = await task
print(result)

run "test1.vlang"
task2 = run_async "test2.vlang"
await task2
```

You can mix async/await with other language features, and use them in both top-level code and inside functions.

See the rest of this document for more details on function definitions, statements, and built-ins.

---

**Notes:**
- Use `{}` for all code blocks (functions, if, loops, etc.).
- No indentation or colons required for blocks.
- Semicolons are optional; use newlines to separate statements.
- Only integer arithmetic is supported for now.
- Variable scope is global except for function parameters.
- Functions can now return values using `return`.
- Boolean logic and comparison operators are supported.

---

**Example Program:**

def greet(name) {
  print('Hello, ' + name)
}

def add(a, b) {
  return a + b
}

var result = add(5, 7)
print(result)

greet('World')

var nums = [1, 2, 3]
for (n in nums) {
  print(n)
}

if (1 < 2 and true) {
  print('Math and booleans work!')
}

---

For more features or questions, ask the developer!
