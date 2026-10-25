# Release Notes

These notes cover the changes in this release.

## 5.1.0 — Performance improvements

### Performance

- **Cached closure compiler:** AST nodes are compiled once into Python
  closures and cached. Loops, function calls, arithmetic, comparisons,
  assignments, and attribute and index access avoid repeated interpreter
  dispatch. Function bodies are compiled once and reused.
- **Faster method calls:** bound method calls avoid an intermediate wrapper.
- Local microbenchmark results (milliseconds; lower is better):

  | Benchmark | Before | After |
  | --- | --- | --- |
  | recursive `fib(24)` | 870 | ~400–540 |
  | `for` loop, 300k iterations | 546 | ~160 |
  | `while` loop, 200k iterations | 390 | ~100 |
  | list/dict operations | 497 | ~230 |
  | method calls | 597 | ~410 |
  | string work | 185 | ~130 |

  Results vary by machine and run. Runtime errors continue to report source
  locations.
