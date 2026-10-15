from interpreter import *
import argparse as ap


def main():
    parser = ap.ArgumentParser(description="The CLI for VirtoLang")
    parser.add_argument("file", help="The source file to run")
    args = parser.parse_args()

    if not args.file.endswith(".vlang"):
        print("Error: Source file must have a .vlang extension")
        return

    with open(args.file, "r") as f:
        source_code = f.read()

    interpreter = Interpreter(source_code)
    interpreter.run()


if __name__ == "__main__":
    main()
