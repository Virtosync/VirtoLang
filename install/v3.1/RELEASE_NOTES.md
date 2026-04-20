# VirtoLang v3.1 – Release Notes (major)

Release date: (update as appropriate)

## Overview

VirtoLang v3.1 is a major release that emphasizes Python interoperability and performance. Instead of maintaining many custom, language-specific built-ins, v3.1 exposes Python builtins and installed packages directly to VirtoLang scripts while keeping the VirtoLang syntax for definitions, blocks, classes, and expressions.

Note: VirtoLang uses curly-brace `{}` block delimiters instead of Python's colon + indentation. Semicolons are not required to terminate statements; use `if cond { ... }` style blocks (no parentheses around conditions). `elif` is not available; use `else` with a nested `if` for else-if behavior.

## Major New Features & Improvements

- **Full access to Python built-ins:** VirtoLang will fallback to Python builtins (like `len`, `sum`, `open`, `json`, etc.) when a function name is not defined in the VirtoLang scope.
- **Import any installed Python package:** `import` and `from ... import ...` use Python's `importlib` under the hood; you can import and use libraries such as `requests`, `numpy`, `pandas`, `tkinter`, and more directly.
- **Performance overhaul:** Lexer and parser optimizations (manual string handling to avoid regex overhead for strings, faster token scanning), and improved interpreter dispatch give large speed improvements across tokenization and evaluation.
- **Simplified built-ins:** Rather than shipping many specialized helpers as language built-ins, v3.1 relies on the Python ecosystem. This reduces duplication and improves flexibility.

## Examples

Importing and using `requests`:

```vlang
import requests
resp = requests.get("https://httpbin.org/get")
print(resp.status_code)
```

Using Python builtins directly:

```vlang
print(sum([1,2,3]))
```

Small VirtoLang examples (block syntax):

```vlang
def add(a, b){
	return a + b
}

if (add(1,2) == 3) {
	print("math ok")
}
```

## Removals & Breaking Changes

- **Native `async`/`await` removal:** The custom VirtoLang `async`/`await` keywords and related native runtime support were removed. Use Python's `asyncio` (imported into VirtoLang) for asynchronous patterns.
- **Language-specific helper functions removed/trimmed:** If you previously used `http_*`, `tk_*`, or similar bespoke built-ins, migrate to Python packages like `requests`, `tkinter`, and `colorama`.
- **Some v2.x convenience functions are deprecated:** Check existing scripts for direct calls to v2-only helpers and replace them with Python equivalents or add small compatibility wrappers.

## Migration Guide

- Replace `http_get/post` style built-ins with `import requests` and corresponding `requests` calls.
- For GUI work, replace `tk_*` built-ins with `import tkinter` usage.
- For asynchronous programs, move to `asyncio` and run the event loop from Python APIs.

## Notes for Developers

- Ensure your Python environment has required packages installed before running scripts that import them.
- Expect some scripts to run faster under v3.1 due to parse/token improvements and optimized interpreter paths; measure with your real workloads.

## Acknowledgements

Thanks to contributors and users who tested integration with several widely used Python packages during the migration to v3.1.
