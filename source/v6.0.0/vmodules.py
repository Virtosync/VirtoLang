"""Where VirtoLang finds its own modules and packages, and virtual environments.

A *module* is a ``name.vlang`` file.  A *package* is a folder that contains an
``__init__.vlang`` file (run the first time the package is imported), and it
may hold more modules and sub-packages::

    myapp/
        main.vlang
        utils.vlang                 import utils
        shapes/
            __init__.vlang          import shapes
            circle.vlang            import shapes.circle

When a program says ``import name`` VirtoLang looks, in this order, in:

1. the folder of the running program (the current folder in the shell),
2. every folder listed in the ``VIRTOLANG_PATH`` environment variable,
3. the **packages folder** - the active virtual environment's ``packages``
   folder, or, when no environment is active, the global ``packages`` folder
   that sits next to VirtoLang itself,

and only then falls back to Python's own modules.

A *virtual environment* is a folder holding a ``vlang-venv.cfg`` marker file and
its own ``packages`` folder, so each project can keep its own packages.  It is
active when ``VIRTOLANG_VENV`` names it (``activate`` scripts and
``vlang --venv`` set this), or when a ``.venv`` / ``venv`` folder with the marker
is found in the program's folder or one of its parents.

This file only deals with the file system; the interpreter does the importing.
"""

import os
import sys

MODULE_EXTENSION = ".vlang"
PACKAGE_INIT = "__init__" + MODULE_EXTENSION
VENV_MARKER = "vlang-venv.cfg"
PACKAGES_DIRNAME = "packages"
# Folder names searched (in each parent folder) when looking for a venv.
VENV_CANDIDATES = (".venv", "venv")


def install_dir():
    """The folder VirtoLang itself is installed in."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def global_packages_dir():
    """The shared packages folder (``VIRTOLANG_PACKAGES`` overrides the default)."""
    override = os.environ.get("VIRTOLANG_PACKAGES")
    if override:
        return os.path.abspath(override)
    return os.path.join(install_dir(), PACKAGES_DIRNAME)


def is_venv(path):
    """True if ``path`` is a VirtoLang virtual environment folder."""
    return bool(path) and os.path.isfile(os.path.join(path, VENV_MARKER))


def find_venv(start_dir=None):
    """The active virtual environment folder, or ``None``.

    ``VIRTOLANG_VENV`` wins; otherwise ``.venv`` / ``venv`` is looked for in
    ``start_dir`` and then in each parent folder.
    """
    named = os.environ.get("VIRTOLANG_VENV")
    if named:
        named = os.path.abspath(named)
        return named if is_venv(named) else None
    folder = os.path.abspath(start_dir or os.getcwd())
    while True:
        for name in VENV_CANDIDATES:
            candidate = os.path.join(folder, name)
            if is_venv(candidate):
                return candidate
        parent = os.path.dirname(folder)
        if parent == folder:
            return None
        folder = parent


def packages_dir(start_dir=None):
    """Folder that packages are installed into right now (venv or global)."""
    venv = find_venv(start_dir)
    if venv:
        return os.path.join(venv, PACKAGES_DIRNAME)
    return global_packages_dir()


def search_paths(base_dir=None):
    """Folders searched for top-level modules, in priority order."""
    paths = []
    base = os.path.abspath(base_dir or os.getcwd())
    paths.append(base)
    for entry in os.environ.get("VIRTOLANG_PATH", "").split(os.pathsep):
        if entry.strip():
            paths.append(os.path.abspath(entry.strip()))
    paths.append(packages_dir(base))
    return paths


def find_in(folders, name):
    """Look for module ``name`` (one dotted part) inside ``folders``.

    Returns ``(file_path, is_package)`` or ``None``.  A package folder wins
    over a ``name.vlang`` file of the same name, as in Python.
    """
    for folder in folders:
        init = os.path.join(folder, name, PACKAGE_INIT)
        if os.path.isfile(init):
            return init, True
        plain = os.path.join(folder, name + MODULE_EXTENSION)
        if os.path.isfile(plain):
            return plain, False
    return None


# ---------------------------------------------------------------------------
# Creating virtual environments
# ---------------------------------------------------------------------------

_ACTIVATE_BAT = """@echo off
rem Activates the VirtoLang virtual environment in this folder.
set "VIRTOLANG_VENV={venv}"
set "_VL_OLD_PATH=%PATH%"
set "_VL_OLD_PROMPT=%PROMPT%"
set "PATH={venv};%PATH%"
set "PROMPT=({name}) %PROMPT%"
echo VirtoLang environment "{name}" is active. Run "deactivate" to leave it.
"""

_DEACTIVATE_BAT = """@echo off
if defined _VL_OLD_PATH set "PATH=%_VL_OLD_PATH%"
if defined _VL_OLD_PROMPT set "PROMPT=%_VL_OLD_PROMPT%"
set "VIRTOLANG_VENV="
set "_VL_OLD_PATH="
set "_VL_OLD_PROMPT="
"""

_ACTIVATE_PS1 = """# Activates the VirtoLang virtual environment in this folder.
# Use:  . .\\{folder}\\activate.ps1
$env:VIRTOLANG_VENV = "{venv}"
$global:_VlOldPrompt = $function:prompt
function global:deactivate {{
    $env:VIRTOLANG_VENV = $null
    $function:prompt = $global:_VlOldPrompt
    Remove-Item function:deactivate
}}
function global:prompt {{ "({name}) " + (& $global:_VlOldPrompt) }}
Write-Host 'VirtoLang environment "{name}" is active. Run "deactivate" to leave it.'
"""

_ACTIVATE_SH = """# Activates the VirtoLang virtual environment in this folder.
# Use:  source {folder}/activate
export VIRTOLANG_VENV="{venv}"
_VL_OLD_PS1="$PS1"
PS1="({name}) $PS1"
deactivate() {{
    unset VIRTOLANG_VENV
    PS1="$_VL_OLD_PS1"
    unset _VL_OLD_PS1
    unset -f deactivate
}}
echo 'VirtoLang environment "{name}" is active. Run "deactivate" to leave it.'
"""


def create_venv(path, version=None):
    """Create a virtual environment folder at ``path`` and return its full path.

    Raises ``FileExistsError`` if ``path`` already is a VirtoLang environment.
    """
    venv = os.path.abspath(path)
    if is_venv(venv):
        raise FileExistsError(f"{venv} is already a VirtoLang environment")
    os.makedirs(os.path.join(venv, PACKAGES_DIRNAME), exist_ok=True)
    values = {"venv": venv, "name": os.path.basename(venv), "folder": path}

    with open(os.path.join(venv, VENV_MARKER), "w", encoding="utf-8") as stream:
        stream.write(f"home = {install_dir()}\n")
        if version:
            stream.write(f"version = {version}\n")
    for filename, template, newline in (
        ("activate.bat", _ACTIVATE_BAT, "\r\n"),
        ("deactivate.bat", _DEACTIVATE_BAT, "\r\n"),
        ("activate.ps1", _ACTIVATE_PS1, "\r\n"),
        ("activate", _ACTIVATE_SH, "\n"),
    ):
        with open(
            os.path.join(venv, filename), "w", encoding="utf-8", newline=""
        ) as stream:
            stream.write(template.format(**values).replace("\n", newline))
    return venv


def activation_hint(venv):
    """One line telling the user how to activate ``venv`` in their shell."""
    folder = os.path.relpath(venv)
    if os.name == "nt":
        return f'Activate it with:  {os.path.join(folder, "activate.bat")}  (PowerShell: . {os.path.join(folder, "activate.ps1")})'
    return f"Activate it with:  source {os.path.join(folder, 'activate')}"
