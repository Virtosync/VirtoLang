# Release Notes

These notes cover the changes in this release.

## 6.1.0 — Built-ins, performance optimisation and packaging

### New built-ins

- `computer_size`, `computer_duration`, `unroman`,
  for converting back from the human counterpaerts.

### Building executables

- `vlang build app.vlang [flags]` builds a standalone executable with
  PyInstaller. The program, its `.vlang` files and the `packages` folder are
  bundled; imported Python modules are detected. Unrecognised flags are passed
  to PyInstaller, so every PyInstaller option works. VirtoLang's own options
  are `-o/--output`, `--keep-temp` and `--no-check`.
- Executables are built as a fast-starting folder by default; `--onefile`
  makes a single `.exe` (slower to start because it unpacks on every launch).
- Faster start-up: `asyncio` is now imported only when async code runs.
- New built-in `build_exe(path, *flags, sources=, flags=, output=, name=, onefile=, windowed=, icon=)`.
- Function calls accept keyword arguments written `name: value` as well as - PyInstaller is installed automatically when missing.
- Linux/macOS packaging: `vlang.spec` is cross-platform and
  `packaging/build_unix.sh` builds a `.tar.gz` with an install script.
- Packages are packaged in onedir mode automatically.You can pass the --onefile flag to use onefile mode instead of onedir mode.

### Notes

- Lazy imported modules in the interpreter to decrease startup time.

- Updated the Pi, and Tau constants to more precise decimals.
