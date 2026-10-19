from interpreter import *
import argparse as ap
import sys


def _error_suggestion(error):
    message = str(error).lower()
    if isinstance(error, ZeroDivisionError):
        return "Check the divisor and ensure it is not zero."
    if isinstance(error, TypeError) and "concatenate str" in message:
        return (
            "Convert the non-string value with str(value), or use an "
            "f-string such as f\"{value}\"."
        )
    if isinstance(error, TypeError):
        return "Check the value types and number of arguments expected by this operation."
    if isinstance(error, KeyError):
        return "Check that the requested key exists before reading it."
    if isinstance(error, IndexError):
        return "Check that the index is within the collection's valid range."
    if isinstance(error, AttributeError):
        return "Check the attribute name and confirm that the value provides that attribute."
    if isinstance(error, NameError) or "unknown function" in message:
        return (
            "Check the spelling and make sure the name is defined or the "
            "required module has been imported."
        )
    if isinstance(error, FileNotFoundError):
        return "Check that the file path exists and that you have permission to read it."
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
    if location is None:
        location = getattr(error, "vlang_location", None)

    if location is not None:
        line_number, column = location
        lines = source.splitlines()
        print(
            f'  File "{filename}", line {line_number}, column {column}',
            file=sys.stderr,
        )
        if 1 <= line_number <= len(lines):
            line = lines[line_number - 1]
            gutter_width = len(str(line_number))
            expanded_line = line.expandtabs(4)
            expanded_prefix = line[: max(column - 1, 0)].expandtabs(4)
            print(
                f"  {line_number:>{gutter_width}} | {expanded_line}",
                file=sys.stderr,
            )
            print(
                f"  {' ' * gutter_width} | "
                f"{' ' * len(expanded_prefix)}^",
                file=sys.stderr,
            )

    print(f"VirtoLang {type(error).__name__}: {error}", file=sys.stderr)
    suggestion = _error_suggestion(error)
    if suggestion:
        print(f"Suggestion: {suggestion}", file=sys.stderr)


def main():
    parser = ap.ArgumentParser(description="The CLI for VirtoLang")
    parser.add_argument("file", help="The source file to run")
    args = parser.parse_args()

    if not args.file.endswith(".vlang"):
        print(
            "VirtoLang error: source file must have a .vlang extension",
            file=sys.stderr,
        )
        return 2

    source_code = ""
    interpreter = None
    try:
        with open(args.file, "r", encoding="utf-8") as f:
            source_code = f.read()

        interpreter = Interpreter(source_code, filename=args.file)
        interpreter.run()
    except Exception as exc:
        _print_language_error(
            exc,
            args.file,
            source_code,
            interpreter.error_location if interpreter is not None else None,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
