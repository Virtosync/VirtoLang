# Release Notes

These notes cover the recent language and diagnostics updates. Previously
released performance optimizations are intentionally not included here.

## 2026-10-19 — Strings, diagnostics, and exceptions

### Strings and numeric literals

- Added raw strings with the `r` prefix and raw formatted strings with `rf`.
- Expanded formatted-string support with `!s`, `!r`, and `!a` conversions,
  escaped braces, debug fields, Python format specifications, and nested
  fields for dynamic width or precision.
- Enabled string methods on quoted literals, including calls such as
  `"Price: {:.2f}".format(price)`.
- Added decimal and scientific-notation numeric literals, such as `3.14`,
  `.5`, and `1e-3`.
- Confirmed that compatible string values can be joined with `+`. Mixing a
  string and a number still raises a `TypeError`; convert the number with
  `str(...)` or format it in a string instead.

### Error diagnostics

- Added source line and column information, a code excerpt, and a caret to
  command-line diagnostics.
- Added best-effort suggestions for common syntax and runtime errors.
- Kept Python implementation tracebacks out of ordinary CLI error output.
- Added an explicit note that runtime locations can identify the enclosing
  statement rather than the exact failing expression.

### Exceptions and classes

- Added base-class syntax for defining custom exceptions that inherit from
  `Error`.
- Added raising exception instances and matching handlers by exception type.
- Added multiple typed `except` handlers, optional exception aliases, and
  bare `except` handlers.
- Ensured `finally` executes after successful or failed try blocks and when
  control returns from a function.
- Preserved existing behavior for ordinary lightweight VirtoLang classes.

### Compatibility notes

- VirtoLang implements a subset of Python syntax; the additions do not make it
  a general Python parser.
- Ordinary user-defined classes do not have full Python inheritance behavior.
  The supported inheritance path is for custom exception classes.
- Unhandled CLI errors exit with a non-zero status and are reported on standard
  error.
