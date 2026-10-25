# Release Notes

These notes cover the changes in this release.

## 6.0.0 — Modules, packages and virtual environments

### Modules and packages

- Import VirtoLang files and folders, not just Python modules:
  `import tools`, `import shapes.circle`, `from shapes import square`.
- `__init__.vlang` turns a folder into a package.
- Relative imports: `from . import x`, `from .a import b`, `from ..pkg import y`.
- `from module import *`, honouring `__all__`.
- `__name__` (`"__main__"` in the running program), `__file__`, `__package__`.
- Modules are cached and circular imports work.
- Errors inside a module report that module's own file, line and source.
- Search order: program folder, `VIRTOLANG_PATH`, `packages` folder, Python.
- The global `packages` folder (formerly site-packages) is next to VirtoLang;
  override it with `VIRTOLANG_PACKAGES`.
- `global` and `nonlocal` inside a module refer to that module's variables.

### Virtual environments

- `vlang --create-venv DIR` creates an environment with its own `packages`
  folder and activate scripts for cmd, PowerShell and sh.
- `vlang --venv DIR file.vlang` runs with a given environment; `.venv` and
  `venv` folders are found automatically.
- `vlang --paths` shows the module search folders.
- An active environment replaces the global `packages` folder.

### New built-ins

- `packages_dir`, `venv_dir`, `module_paths`, `module_path`, `create_venv`,
  for package managers written in VirtoLang.

### Notes

- Namespace packages (folders without `__init__.vlang`) are not supported.
- Installers should create a `packages` folder next to `vlang.exe`.
