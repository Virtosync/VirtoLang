# Release Notes

These notes cover the changes in this release.

## 4.1.0 — 2026-10-22 — Interactive shell, new syntax, and built-in functions

### Interactive shell (REPL)

- Added `vlang -r` to start an interactive shell. Variables, functions, and
  classes persist between lines, and expression results are echoed.
- Input continues on `...` lines until all `{`, `(`, and `[` are closed, so
  multi-line blocks can be typed naturally.
- Errors are reported without ending the session.
- Added shell commands: `:help`, `:vars`, `:reset`, and `:exit` (`exit()` and
  `quit()` also work).
- `vlang -r file.vlang` runs a program and then opens the shell with its
  variables available.
- In the shell, `else`, `elif`, `except`, and `finally` must start on the same
  line as the preceding `}`.

### Command-line options

- `-c` / `--check` now checks syntax without running the program.
- `-e` / `--execute` now runs code given on the command line.
- Source files saved with a UTF-8 byte-order mark (BOM) now load correctly.
- Pressing Ctrl-C during a program exits cleanly with status 130.
- Unreadable or missing source files are reported with the standard error
  format.

### Language additions

- **Semicolons:** statements can be separated by `;`, at the top level and
  inside blocks, so a whole program can be written on one line. Repeated and
  trailing semicolons are allowed.
- **Control flow:** added `elif`, `break`, and `continue`. A bare `return`
  returns `None`.
- **Collections:** added dictionary literals (`{"key": value}`), tuples, and
  slicing (`items[1:3]`, `text[::-1]`).
- **Operators:** added `%`, `//`, and `**`, with augmented forms `//=` and
  `**=`. Added `in` and `not in`, and chained comparisons such as
  `0 < x < 10`.
- **Functions:** added default parameter values and keyword arguments for
  VirtoLang-defined functions. VirtoLang functions can now be passed to Python
  functions, for example `sorted(words, key=measure)`.
- **Loops:** `for` can unpack several names, such as
  `for index, value in enumerate(items)`.
- **Imports:** added dotted module names (`import os.path`) and several names
  in one statement (`from collections import Counter, deque`).
- **Classes:** VirtoLang classes can inherit from other VirtoLang classes, and
  `__str__` / `__repr__` control how instances are printed.
- `raise SomeError` now works with an exception class as well as an instance.

### Built-in functions

New built-ins are available in every program without an `import`. Call
`list_builtins()` to list them.

- **Files and folders:** `read_file`, `read_lines`, `write_file`, `append_file`,
  `read_bytes`, `write_bytes`, `file_exists`, `is_file`, `is_dir`, `list_dir`,
  `make_dir`, `delete_file`, `copy_file`, `move_file`, `join_path`, `cwd`.
- **JSON and CSV:** `json_parse`, `json_stringify`, `read_json`, `write_json`,
  `read_csv`, `write_csv`, `pretty`.
- **HTTP client:** `http_get`, `http_post`, `http_put`, `http_delete`,
  `http_request`, `download`, `url_encode`, `url_decode`.
- **Web server:** `serve` for routing requests to text, HTML, JSON, or
  function handlers.
- **GUI:** `window` (labels, buttons, entries, text boxes, checkboxes,
  drop-downs, sliders, timers) plus `message_box`, `ask_yes_no`, `ask_text`,
  `choose_file`, `choose_save_file`, and `choose_folder`.
- **Time, random, hashing, and encoding:** `sleep`, `timestamp`, `now`,
  `today`, `format_time`, `random_int`, `random_float`, `random_choice`,
  `shuffle`, `uuid`, `sha256`, `md5`, `base64_encode`, `base64_decode`.
- **System and utilities:** `run`, `env`, `args`, `open_url`, `clamp`,
  `to_int`, `to_float`, `deep_copy`.

### Fixes

- Recursive functions now work, and the recursion limit was raised so deep
  recursion succeeds. Runaway recursion reports a `RecursionError` with a
  suggestion.
- The `%` operator is now available; previously only `%=` existed.
- Using an undefined name now raises a `NameError` instead of silently
  producing `None`.
- Variables assigned inside a function are local to that function, and inner
  functions can read variables of the functions around them.
- Constructors and functions now raise a `TypeError` when called with the wrong
  number of arguments; extra constructor arguments were previously ignored.

### Performance

- Faster tokenizing through a single precompiled pattern and keyword table.
- Faster evaluation through a node dispatch table instead of an `if` chain.
- Formatted strings are parsed once and cached.
- Function calls no longer copy the entire variable table.

### Documentation

- Rewrote the README as a public user guide covering installation, the
  command line, the shell, the language, and every built-in function.
- Added documentation comments and docstrings throughout the source files.

### Compatibility notes

- Not yet supported: `lambda`, comprehensions, `with`, `async` / `await`,
  decorators, `is` / `is not`, set literals, tuple-unpacking assignment,
  `global` / `nonlocal`, `super()`, `*args` / `**kwargs`, and triple-quoted
  strings.
- The web server handles one request at a time.
- GUI functions require Python's `tkinter`.
- Code that relied on assigning to an outer function's variable from an inner
  function, or on undefined names evaluating to `None`, must be updated.

