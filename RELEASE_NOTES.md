# Release Notes

These notes cover the changes in this release.

## 5.0.0 — 2026-10-23 — Expressive syntax and resource management

### Language features

- **Lambda expressions:** create short functions inline, such as
  `double = lambda value: value * 2`. Lambdas support positional parameters,
  closures, and use as callbacks passed to Python functions.
- **Conditional expressions:** choose a value inline with
  `label = "adult" if age >= 18 else "child"`. Only the selected branch is
  evaluated. The parser distinguishes this form from a following braced
  `if` statement even though newlines do not end statements.
- **Identity comparisons:** added `is` and `is not` for checking whether two
  values are the same object. Use `==` and `!=` to compare values.
- **Collection comprehensions:** list, set, and dictionary comprehensions
  support nested `for` clauses and `if` filters. Their loop variables live in
  an isolated scope and do not leak into surrounding code.
- **Set literals:** `{1, 2, 3}` creates a set. `{}` remains an empty
  dictionary; use `set()` for an empty set.
- **Tuple unpacking assignment:** assign several names with
  `first, second = pair` or `first, second = 1, 2`. Nested tuple targets are
  supported. An invalid value count fails before any target variables change.
- **Context managers:** `with manager as value { ... }` guarantees exit when
  the block finishes or raises. Multiple managers are allowed, and
  VirtoLang-defined classes can implement `__enter__` and `__exit__`.
- **`async` / `await`:** `async def` functions run on Python's asyncio. `await`
  works inside async functions and at the top level of a program, and
  `async for` / `async with` are supported. Async generator functions can
  combine `await` and `yield`, and support asynchronous iteration, `asend`,
  `athrow` and `aclose`. New helpers: `async_run`, `async_sleep`, `gather`
  and `create_task`.
- **Generators:** generator expressions such as `(n * n for n in values)` are
  lazy. Functions containing `yield` return generators and support
  `yield from`, `.send()`, `.throw()` and `.close()`.
- **Decorators:** `@decorator` and `@decorator(args)` on functions and
  classes, stackable. New ready-made decorators: `@memoize`, `@timed` and
  `@retry(times)`.
- **Starred unpacking and spreading:** `first, *rest = values`,
  `*head, last = values`, `f(*items, **options)`, and spreading inside list,
  tuple, set and dictionary literals (`[0, *items]`, `{**defaults, "a": 1}`).
- **Flexible parameters:** `*args`, `**kwargs` and keyword-only parameters
  (after `*`), plus positional-only parameters (before `/`).
- **`global` and `nonlocal`:** functions can reassign variables of the
  program or of an enclosing function.
- **Classes and descriptors:** `super()` continues method lookup in base
  classes. VirtoLang methods support `@property`, property setters and
  `@staticmethod`, as well as class decorators.
- **Logical newlines:** newlines end statements, while newlines inside
  parentheses and square brackets continue an expression. Semicolons remain
  available for multiple statements on one line.
- **Triple-quoted strings:** multi-line `"""..."""` and `'''...'''` strings,
  including f-string and raw variants; the REPL keeps reading lines until
  the string is closed.
- **Small additions:** `pass`, `assert`, `del`, and the walrus operator
  `name := value`.

### Reliability and verification

- Added regression coverage for each new syntax feature, callback
  interoperability, comprehension variable scope, resource cleanup,
  unpacking failures, async/await, generators, decorators and scoping
  (`tests/test_language_v5_advanced.py`).
- Added a test that parses every VirtoLang code example in the public README.
- Verified that the CLI, existing sample program, and existing built-ins
  continue to work with the new parser and evaluator behavior.

### Performance

- Collection comprehensions build results without repeatedly dispatching
  statement and block nodes. In a local 5,000-item squares microbenchmark,
  a list comprehension took about 0.011 seconds per run versus 0.021 seconds
  for a loop with `append`; actual results depend on the machine and program.

### Documentation and version

- Updated the public README with language examples and the supported-feature
  boundaries for 5.0.
- Bumped the CLI version to **5.0.0** for this major language release.

### Compatibility notes

- `async`, `await`, `yield`, `global`, `nonlocal`, `pass`, `assert` and `del`
  are now reserved words and can no longer be used as variable or function
  names.
- Function definitions now carry an extra field in the AST; code that builds
  or inspects `FUNCDEF` nodes directly must account for it.
- Generators and `async def` bodies run on helper threads that hand control
  back and forth (only one runs at a time), so each pausable function call
  costs more than a normal call.
- `yield from` is not allowed inside an async generator. Use `async for` to
  forward values from another asynchronous iterator.
- Newlines now delimit statements. Wrap multiline expressions in parentheses,
  square brackets, or dictionary braces; use `;` to keep multiple statements
  on one line.
