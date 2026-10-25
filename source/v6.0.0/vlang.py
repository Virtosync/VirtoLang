"""VirtoLang command-line interface.

Usage examples::

    vlang program.vlang          run a program
    vlang -c program.vlang       check the syntax only, do not run
    vlang -e "print(1 + 2)"      run code given on the command line
    vlang -r                     start the interactive shell (REPL)
    vlang -r program.vlang       run a program, then stay in the shell with
                                 its variables and functions available

This module also contains the REPL (read-eval-print loop) and the code that
prints friendly error messages with a source excerpt and a suggested fix.
"""

import argparse as ap
import os
import platform
import sys

import vmodules
from interpreter import Interpreter
from lexer import Lexer

VERSION = "6.0.0"

# Prompts used by the interactive shell.
PROMPT = ">>> "
CONTINUATION_PROMPT = "... "

REPL_HELP = """\
VirtoLang interactive shell
  Type a statement or expression and press Enter to run it.
  Blocks may span lines: the shell keeps asking for input (prompt "...")
  until every { } ( ) [ ] is closed.  Several statements can share a line
  when separated by ";".

Shell commands:
  :help     show this message
  :vars     list the variables and functions you have defined
  :reset    forget everything and start with a clean session
  :exit     leave the shell (also exit(), quit(), Ctrl-Z + Enter / Ctrl-D)
"""


# ---------------------------------------------------------------------------
# Error reporting
# ---------------------------------------------------------------------------


def _error_suggestion(error):
    """Return a short human-friendly hint for a common error, else ``None``."""
    message = str(error).lower()
    if isinstance(error, ZeroDivisionError):
        return "Check the divisor and ensure it is not zero."
    if isinstance(error, RecursionError):
        return (
            "A function is calling itself without stopping; check its exit condition."
        )
    if isinstance(error, TypeError) and "concatenate str" in message:
        return (
            "Convert the non-string value with str(value), or use an "
            'f-string such as f"{value}".'
        )
    if isinstance(error, TypeError):
        return (
            "Check the value types and number of arguments expected by this operation."
        )
    if isinstance(error, KeyError):
        return "Check that the requested key exists before reading it."
    if isinstance(error, IndexError):
        return "Check that the index is within the collection's valid range."
    if isinstance(error, AttributeError):
        return "Check the attribute name and confirm that the value provides that attribute."
    if isinstance(error, ModuleNotFoundError):
        return (
            "Check the spelling. VirtoLang looks for name.vlang or name/__init__.vlang "
            "in the program's folder, VIRTOLANG_PATH and the packages folder "
            "(see: vlang --paths), then for Python modules."
        )
    if isinstance(error, ImportError):
        return "Check that the module defines the name you are importing."
    if isinstance(error, NameError) or "unknown function" in message:
        return (
            "Check the spelling and make sure the name is defined or the "
            "required module has been imported."
        )
    if isinstance(error, FileNotFoundError):
        return (
            "Check that the file path exists and that you have permission to read it."
        )
    if isinstance(error, SyntaxError):
        if "expected {" in message:
            return "Add a '{' to start this block and a matching '}' to close it."
        if "expected )" in message:
            return "Add the missing ')' and check that parentheses are balanced."
        if "expected ]" in message:
            return "Add the missing ']' and check that brackets are balanced."
        if "expected }" in message:
            return "Add the missing '}' to close this block."
        if "f-string" in message:
            return "Check that each formatted-string field has matching braces and a valid conversion or format spec."
        return "Check the syntax near the highlighted column, including spelling and punctuation."
    return None


def _print_language_error(error, filename, source, location=None):
    """Print an error to stderr in VirtoLang's friendly format.

    The output looks like::

          File "demo.vlang", line 3, column 7
          3 | print(1 / 0)
            |       ^
        VirtoLang ZeroDivisionError: division by zero
        Suggestion: Check the divisor and ensure it is not zero.

    Args:
        error: The exception that was raised.
        filename: Name shown in the ``File "..."`` line.
        source: Full source text, used to show the offending line.
        location: ``(line, column)`` to point at.  If omitted, the position
            stored on the exception itself (syntax errors) is used.
    """
    # Syntax errors in an imported file carry their own location (and file).
    exact = getattr(error, "vlang_location", None)
    if exact is not None:
        location = exact

    if location is not None:
        line_number, column = location[0], location[1]
        if len(location) > 2:
            filename, source = location[2]
        lines = source.splitlines()
        print(
            f'  File "{filename}", line {line_number}, column {column}',
            file=sys.stderr,
        )
        if 1 <= line_number <= len(lines):
            line = lines[line_number - 1]
            gutter_width = len(str(line_number))
            # Tabs are expanded so the caret lines up with the printed text.
            expanded_line = line.expandtabs(4)
            expanded_prefix = line[: max(column - 1, 0)].expandtabs(4)
            print(
                f"  {line_number:>{gutter_width}} | {expanded_line}",
                file=sys.stderr,
            )
            print(
                f"  {' ' * gutter_width} | " f"{' ' * len(expanded_prefix)}^",
                file=sys.stderr,
            )

    print(f"VirtoLang {type(error).__name__}: {error}", file=sys.stderr)
    suggestion = _error_suggestion(error)
    if suggestion:
        print(f"Suggestion: {suggestion}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Interactive shell (REPL)
# ---------------------------------------------------------------------------


class _ExitCommand:
    """The ``exit`` / ``quit`` object available inside the REPL.

    Calling it leaves the shell.  Typing just ``exit`` prints a reminder, like
    Python's own shell does.
    """

    def __init__(self, name):
        self.name = name

    def __call__(self, code=0):
        raise SystemExit(code)

    def __repr__(self):
        return f"Use {self.name}() or Ctrl-Z + Enter (Ctrl-D on Linux/macOS) to exit"


def _new_repl_interpreter():
    """Create a fresh interpreter configured for interactive use."""
    interpreter = Interpreter(filename="<repl>")
    interpreter.globals.vars["exit"] = _ExitCommand("exit")
    interpreter.globals.vars["quit"] = _ExitCommand("quit")
    # Remember the starting names so ``:vars`` can list only the user's own.
    interpreter.initial_names = set(interpreter.globals.vars)
    return interpreter


def _needs_more_input(source):
    """True if ``source`` has an unclosed ``{``, ``(`` or ``[``.

    The REPL uses this to decide between running the input now and asking
    for another line (so multi-line ``if``/``def``/``class`` blocks work).
    Lexing errors return ``False`` so they are reported immediately.
    """
    try:
        tokens = Lexer(source).tokenize()
    except SyntaxError:
        return False
    depth = 0
    for token_type, text in tokens:
        if token_type in ("LBRACE", "LPAREN", "LBRACKET"):
            depth += 1
        elif token_type in ("RBRACE", "RPAREN", "RBRACKET"):
            depth -= 1
        elif token_type == "STRING":
            # An unterminated triple-quoted string continues on the next line.
            body = text.lstrip("bBrRuUfFeE")
            if body[:3] in ('"""', "'''") and (len(body) < 6 or body[-3:] != body[:3]):
                return True
    return depth > 0


def _read_source():
    """Read one complete chunk of input from the user.

    Returns the text, ``""`` if the user cancelled with Ctrl-C, or ``None`` at
    end of input (Ctrl-D / Ctrl-Z).
    """
    try:
        source = input(PROMPT)
    except EOFError:
        print()
        return None
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt")
        return ""

    while (
        source.strip()
        and not source.lstrip().startswith(":")
        and _needs_more_input(source)
    ):
        try:
            source += "\n" + input(CONTINUATION_PROMPT)
        except EOFError:
            print()
            return None
        except KeyboardInterrupt:
            print("\nKeyboardInterrupt")
            return ""
    return source


def _run_shell_command(command, interpreter):
    """Handle a ``:command``.  Returns the (possibly new) interpreter, or
    ``None`` if the shell should exit."""
    name = command.strip().lower()
    if name in (":exit", ":quit", ":q"):
        return None
    if name in (":help", ":h", ":?"):
        print(REPL_HELP)
    elif name == ":reset":
        print("Session reset.")
        return _new_repl_interpreter()
    elif name == ":vars":
        names = sorted(
            n
            for n in interpreter.globals.vars
            if n not in interpreter.initial_names and not n.startswith("__")
        )
        if not names:
            print("(nothing defined yet)")
        for n in names:
            print(f"{n} = {interpreter.globals.vars[n]!r}")
    else:
        print(f"Unknown command {command.strip()!r}. Type :help for a list.")
    return interpreter


def run_repl(interpreter=None):
    """Run the interactive shell until the user exits.

    Args:
        interpreter: An existing interpreter whose variables should be
            available in the shell (used by ``vlang -r file.vlang``).  A new
            one is created if omitted.

    Each input is parsed and executed in the same interpreter, so variables,
    functions and classes persist between lines.  Errors are printed and the
    shell keeps going.
    """
    try:
        import readline  # noqa: F401  (enables arrow-key history where available)
    except ImportError:
        pass

    if interpreter is None:
        interpreter = _new_repl_interpreter()
    else:
        interpreter.filename = "<repl>"
        interpreter.initial_names = set()
        interpreter.globals.vars.setdefault("exit", _ExitCommand("exit"))
        interpreter.globals.vars.setdefault("quit", _ExitCommand("quit"))

    print(
        f"VirtoLang {VERSION} interactive shell "
        f"(Python {platform.python_version()} on {sys.platform})"
    )
    print('Type ":help" for help, or exit() to quit.')

    while True:
        source = _read_source()
        if source is None:
            return 0
        if not source.strip():
            continue
        if source.lstrip().startswith(":"):
            interpreter = _run_shell_command(source, interpreter)
            if interpreter is None:
                return 0
            continue

        try:
            for value in interpreter.run_repl_line(source):
                print(repr(value))
        except KeyboardInterrupt:
            print("\nKeyboardInterrupt")
        except Exception as exc:
            _print_language_error(exc, "<repl>", source, interpreter.error_location)


# ---------------------------------------------------------------------------
# Command-line entry point
# ---------------------------------------------------------------------------


def _build_argument_parser():
    """Define the command-line options."""
    parser = ap.ArgumentParser(
        prog="vlang",
        description="The CLI for VirtoLang. With no options, runs main.vlang.",
    )
    parser.add_argument(
        "file",
        help="The .vlang source file to run (or the code itself when used with -e)",
        nargs="?",
        default=None,
    )
    parser.add_argument(
        "-v", "-V", "--version", action="version", version=f"VirtoLang {VERSION}"
    )
    parser.add_argument(
        "-c",
        "-C",
        "--check",
        action="store_true",
        help="Check the syntax of the source file without executing it",
    )
    parser.add_argument(
        "-e",
        "-E",
        "--execute",
        action="store_true",
        help="Treat the argument as code to run instead of a file name",
    )
    parser.add_argument(
        "-r",
        "-R",
        "--repl",
        action="store_true",
        help="Start an interactive REPL session (after running FILE, if given)",
    )
    parser.add_argument(
        "--venv",
        metavar="DIR",
        help="Run with the VirtoLang virtual environment in DIR "
        "(its packages folder is used instead of the global one)",
    )
    parser.add_argument(
        "--create-venv",
        metavar="DIR",
        help="Create a new virtual environment in DIR and exit",
    )
    parser.add_argument(
        "--paths",
        action="store_true",
        help="Show where imports are searched for and which environment is active",
    )
    return parser


def _show_paths():
    """Print the module search folders (``vlang --paths``)."""
    venv = vmodules.find_venv()
    print(f"Virtual environment: {venv or '(none active)'}")
    print(f"Packages folder:     {vmodules.packages_dir()}")
    print("Imports are searched in this order:")
    for number, folder in enumerate(vmodules.search_paths(), 1):
        print(f"  {number}. {folder}")
    print("  then Python modules")
    return 0


def _handle_venv_options(args):
    """Act on ``--create-venv`` / ``--venv`` / ``--paths``.

    Returns an exit status when the command is finished, else ``None``.
    """
    if args.create_venv:
        try:
            venv = vmodules.create_venv(args.create_venv, VERSION)
        except OSError as exc:
            print(f"VirtoLang error: {exc}", file=sys.stderr)
            return 1
        print(f"Created VirtoLang environment: {venv}")
        print(vmodules.activation_hint(venv))
        return 0
    if args.venv:
        venv = os.path.abspath(args.venv)
        if not vmodules.is_venv(venv):
            print(
                f"VirtoLang error: {venv} is not a VirtoLang environment "
                f"(create one with: vlang --create-venv {args.venv})",
                file=sys.stderr,
            )
            return 2
        # Child processes started with run() inherit the environment too.
        os.environ["VIRTOLANG_VENV"] = venv
    if args.paths:
        return _show_paths()
    return None


def _execute(source, filename, check_only=False):
    """Run (or just parse) ``source``.  Returns ``(interpreter, exit_status)``."""
    interpreter = Interpreter(source, filename=filename)
    try:
        if check_only:
            interpreter.check()
            print(f"{filename}: syntax OK")
        else:
            interpreter.run()
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt", file=sys.stderr)
        return interpreter, 130
    except Exception as exc:
        _print_language_error(exc, filename, source, interpreter.error_location)
        return interpreter, 1
    return interpreter, 0


def main(argv=None):
    """Entry point.  Returns the process exit status (0 on success)."""
    args = _build_argument_parser().parse_args(argv)

    status = _handle_venv_options(args)
    if status is not None:
        return status

    # Deeply recursive VirtoLang functions need more Python stack frames than
    # the default limit allows.
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 100000))

    # Mode 1: code given directly on the command line.
    if args.execute:
        if args.file is None:
            print("VirtoLang error: -e requires the code to run", file=sys.stderr)
            return 2
        interpreter, status = _execute(args.file, "<string>", args.check)
        if args.repl and status == 0 and not args.check:
            return run_repl(interpreter)
        return status

    # Mode 2: only -r, so go straight to the shell.
    if args.file is None and args.repl:
        return run_repl()

    # Mode 3: run (or check) a source file.
    filename = args.file or "main.vlang"
    if not filename.endswith(".vlang"):
        print(
            "VirtoLang error: source file must have a .vlang extension",
            file=sys.stderr,
        )
        return 2

    try:
        # utf-8-sig also accepts files saved with a BOM by Windows editors.
        with open(filename, "r", encoding="utf-8-sig") as f:
            source = f.read()
    except OSError as exc:
        _print_language_error(exc, filename, "")
        return 1

    interpreter, status = _execute(source, filename, args.check)
    if args.repl and status == 0 and not args.check:
        return run_repl(interpreter)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
