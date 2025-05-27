import os
import sys
import argparse as a
import ctypes

packages = {
    "test": {"version": "1.0.0", "code": "print('Hello from test package!')"},
    "example": {"version": "2.0.0", "code": "print('Hello from example package!')"},
    "sample": {"version": "0.1.0", "code": "print('Hello from sample package!')"},
    "demo": {"version": "3.5.1", "code": "print('Hello from demo package!')"},
    "utility": {"version": "0.9.9", "code": "print('Hello from utility package!')"},
    "advanced": {"version": "1.2.3", "code": "print('Hello from advanced package!')"},
    "basic": {"version": "0.0.1", "code": "print('Hello from basic package!')"},
}

def is_admin():
    """Check if the script is running with admin privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def elevate_to_admin():
    """Re-run the script with admin privileges."""
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit()


def install(package_name, package_version):
    install_dir = os.path.join(os.getenv("VLANG_PATH"), "packages")
    package_dir = os.path.join(install_dir, package_name)
    if not os.path.exists(install_dir):
        os.makedirs(install_dir)
    if not os.path.exists(package_dir):
        os.makedirs(package_dir)

    if package_name not in packages:
        print(f"Package '{package_name}' not found.")
        return

    if packages[package_name]["version"] != package_version:
        print(
            f"Package '{package_name}' version mismatch. Expected {packages[package_name]['version']}, got {package_version}."
        )
        return

    package_code = packages[package_name]["code"]
    package_file = os.path.join(package_dir, f"__init__.vlang")
    with open(package_file, "w") as f:
        f.write(package_code)
    print(f"Package '{package_name}' version {package_version} installed successfully.")
    
def uninstall(package_name):
    install_dir = os.path.join(os.getenv("VLANG_PATH"), "packages")
    package_dir = os.path.join(install_dir, package_name)
    print(f"Uninstalling package: {package_name}")
    print(f"Install directory: {install_dir}")
    print(f"Package directory: {package_dir}")
    if os.path.exists(package_dir):
        try:
            import stat
            for root, dirs, files in os.walk(package_dir, topdown=False):
                for name in files:
                    file_path = os.path.join(root, name)
                    print(f"Removing file: {file_path}")
                    try:
                        os.chmod(file_path, stat.S_IWRITE)
                        os.remove(file_path)
                    except Exception as e:
                        print(f"Failed to remove file {file_path}: {e}")
                for name in dirs:
                    dir_path = os.path.join(root, name)
                    print(f"Removing dir: {dir_path}")
                    try:
                        os.rmdir(dir_path)
                    except Exception as e:
                        print(f"Failed to remove dir {dir_path}: {e}")
            print(f"Removing package dir: {package_dir}")
            try:
                os.rmdir(package_dir)
            except Exception as e:
                print(f"Failed to remove package dir {package_dir}: {e}")
            print(f"Package '{package_name}' uninstalled successfully.")
        except Exception as e:
            print(f"Failed to uninstall package '{package_name}': {e}")
    else:
        print(f"Package '{package_name}' not found.")
    
def main():
    parser = a.ArgumentParser(description="VirtoLang Package Manager")
    parser.add_argument("command", choices=["install", "uninstall", "update"], help="Command to run")
    parser.add_argument("name", help="Name of the package to install")
    parser.add_argument("version", nargs="?", default=None, help="Version of the package to install (optional for uninstall)")

    args = parser.parse_args()

    if args.command == "install":
        if not args.version:
            print("You must specify a version to install.")
            return
        install(args.name, args.version)
    elif args.command == "uninstall":
        uninstall(args.name)
    elif args.command == "update":
        if not args.version:
            print("You must specify a version to update.")
            return
        print(f"Updating package '{args.name}' to version {args.version}...")
        uninstall(args.name)
        install(args.name, args.version)
        
if __name__ == "__main__":
    if not os.getenv("VLANG_PATH"):
        print("VLANG_PATH environment variable is not set. Please set it to the installation directory.")
        sys.exit(1)
    elevate_to_admin()
    main()
