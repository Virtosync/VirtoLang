# Release Notes

These notes cover the changes in this release.

## 6.2.0 — Program arguments

- `vlang app.vlang install pkg` now passes everything after the file name to
  the program. `args()`, `sys.argv` and Python's `argparse` (`parse_args()`)
  all see them, so command-line tools such as package managers can be written
  in VirtoLang. Options after the file name (even `--help`) go to the program,
  not to `vlang`. `vlang -r app.vlang x y` also works, and `--` ends vlang's
  own options.
- Executables built with `vlang build` receive their command-line arguments
  the same way.