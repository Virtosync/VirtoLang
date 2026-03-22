# VirtoLang Language Reference & User Guide (v3)

VirtoLang v3 is a major release focused on deep Python interoperability, simplification, and a large performance overhaul. The language keeps the familiar VirtoLang syntax while allowing you to use the full Python standard library and any installed Python packages directly from your VirtoLang scripts.

Note: VirtoLang uses curly-brace block delimiters (`{` and `}`) rather than Python's colon + indentation style. You do not need semicolons to terminate statements — use `if cond { ... }` style blocks (no parentheses around conditions). `elif` is not available in v3; use `else` with a nested `if` for else-if behavior.

---

## Key Highlights (v3)

- **Full Python integration:** Any Python builtin or installed package can be imported and used directly from VirtoLang using the normal `import` / `from ... import ...` forms. This replaces many custom language-specific built-ins by leaning on the Python ecosystem while preserving VirtoLang syntax.
- **Massive performance improvements:** Lexer and parser optimizations (manual string scanning, reduced regex overhead), faster AST evaluation paths, and streamlined callable dispatch produce significant speedups versus v2.x.
- **Simplified built-ins surface:** Rather than shipping large, language-specific built-in wrappers for HTTP, GUI, and other facilities, v3 exposes Python modules (e.g., `requests`, `tkinter`, `http`, `colorama`) which you can import and use directly.
- **Cleaner runtime model:** Importing Python modules uses `importlib`, Python callables and classes are first-class and callable directly from VirtoLang code.
- **Backward-compat notes:** Some v2.x conveniences (native `async/await` keywords and certain custom built-in wrappers) were removed in favor of using Python's `asyncio` and directly imported modules. See "Removed / Changed" below.

---

## What Changed From v2.x

- You can now call Python builtins directly (e.g., `sum`, `len`, `open`, `json`, `math.sqrt`). The interpreter will fallback to Python builtins when a named function isn't found in VirtoLang scope.
- You can `import` any installed Python package (for example, `requests`, `numpy`, `pandas`, `tkinter`) and use it normally from your VirtoLang code.
- Many previously provided language-specific helpers have been intentionally slimmed down or removed; use Python packages for advanced functionality.
- The lexer and parser have been reworked for improved robustness and speed.

---

## Installation

Follow the same installation steps as earlier versions (see `install/`). After installation, ensure any third-party Python packages you plan to use are installed in the same Python environment used by VirtoLang.

Verify installation:

```
vlang --version
vlang example.vlang
```

---

## Examples (V3)

Using Python builtins:

```vlang
print(len([1,2,3]))
print(sum([1,2,3]))
print(sorted([3,1,2]))
```

Importing and using Python packages (requests example):

```vlang
import requests
resp = requests.get("https://httpbin.org/get")
print(resp.status_code)
print(resp.text)
```

Using the Python standard library:

```vlang
import math
print(math.sqrt(16))

import json
data = json.loads('{"a":1}')
print(data)
```

If you need async behavior, use Python's `asyncio` via an imported module and call its APIs from VirtoLang code (example below).

```vlang
import asyncio

def sync_worker(){
	print("sync work")
}
# call Python API from VirtoLang; run event loop manually in Python interop
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
# run coroutine using Python's APIs
# note: orchestrating complex async flows across VirtoLang and Python may require small Python glue code
```

Control flow and functions (VirtoLang block style):

```vlang
def greet(name){
	print("Hello, " + name)
}

if len([1,2,3]) > 2 {
	greet("Zack")
} else {
	if len([]) == 0 {
		print("Empty")
	} else {
		print("Other")
	}
}

for i in [1,2,3] {
	print(i)
}

while false {
	# loop won't run
}
```

---

## Removals / Breaking Changes

- **Native `async`/`await` keywords removed:** v3 does not provide a built-in VirtoLang `async`/`await` syntax. Use Python's `asyncio` and native Python coroutines by importing and invoking them from VirtoLang.
- **Language-specific wrappers removed/trimmed:** Pre-packaged helpers (e.g., bespoke `http_*` built-ins, builtin `tk_*` helpers, custom color helpers) may not be present as named VirtoLang built-ins anymore; instead import the corresponding Python packages, e.g., `requests`, `tkinter`, `colorama`.
- **Some v2-only convenience functions are no longer guaranteed;** if you relied on a v2.x helper, replace it with the equivalent Python package or a small compatibility wrapper in your codebase.

---

## Migration Tips

- Replace calls to removed built-ins by importing the appropriate Python package. For HTTP code: `import requests` and use `requests.get/post` etc.
- Replace VirtoLang async code with Python `asyncio` usage if you need evented concurrency.
- If you used GUI helpers, use `import tkinter` and standard Python GUI patterns.

---

## Compatibility & Notes

- VirtoLang v3 runs inside the Python environment; ensure packages are installed in the same environment.
- The interpreter uses Python callables and modules directly; loading failure or mismatched versions are subject to Python's import semantics.
- The language still uses VirtoLang syntax for blocks, class and function definitions, and expression semantics described in earlier docs, but delegates many utilities to Python.

---

## Where to go next

- See `install/` for platform-specific installers.
- Try converting small v2.x scripts to v3 by swapping builtin calls for Python imports, and run `vlang yourscript.vlang`.

Happy coding with VirtoLang v3!

