import winreg as reg
import os
import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import ctypes
import sys

PRIVACY_POLICY = """
VirtoLang Privacy Policy & Terms of Service

By installing this software, you agree to the collection of minimal usage data for improving the language and tools. No personal data is collected. Use at your own risk. See virtolang.txt for full details.
"""


class InstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VirtoLang Installer")
        self.install_dir = tk.StringVar(value="C:\\Program Files\\VirtoLang")
        self.scope = tk.StringVar(value="user")
        self.create_widgets()

    def create_widgets(self):
        tk.Label(
            self.root,
            text="Welcome to the VirtoLang Installer",
            font=("Arial", 16, "bold"),
        ).pack(pady=10)
        tk.Label(self.root, text="Select installation type:").pack(anchor="w", padx=20)
        tk.Radiobutton(
            self.root, text="Just me (user)", variable=self.scope, value="user"
        ).pack(anchor="w", padx=40)
        tk.Radiobutton(
            self.root, text="All users (system)", variable=self.scope, value="system"
        ).pack(anchor="w", padx=40)
        tk.Label(self.root, text="Choose installation directory:").pack(
            anchor="w", padx=20, pady=(10, 0)
        )
        dir_frame = tk.Frame(self.root)
        dir_frame.pack(fill="x", padx=40)
        tk.Entry(dir_frame, textvariable=self.install_dir, width=40).pack(
            side="left", fill="x", expand=True
        )
        tk.Button(dir_frame, text="Browse", command=self.browse_dir).pack(
            side="left", padx=5
        )
        tk.Label(
            self.root,
            text="\nPrivacy Policy & Terms of Service:",
            font=("Arial", 10, "bold"),
        ).pack(anchor="w", padx=20, pady=(10, 0))
        policy_box = tk.Text(self.root, height=7, width=60, wrap="word")
        policy_box.insert("1.0", PRIVACY_POLICY)
        policy_box.config(state="disabled")
        policy_box.pack(padx=20, pady=(0, 10))
        self.accept_var = tk.IntVar()
        tk.Checkbutton(
            self.root,
            text="I accept the Privacy Policy & Terms of Service",
            variable=self.accept_var,
        ).pack(anchor="w", padx=20)
        tk.Button(self.root, text="Install", command=self.install).pack(pady=15)

    def browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.install_dir.get())
        if d:
            self.install_dir.set(d)

    def is_admin(self):
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            return False

    def install(self):
        if not self.accept_var.get():
            messagebox.showerror(
                "Error",
                "You must accept the Privacy Policy & Terms of Service to continue.",
            )
            return
        install_dir = self.install_dir.get()
        # Always normalize to Windows-style backslashes for env vars and PATH
        install_dir = install_dir.replace("/", "\\")
        scope = self.scope.get()
        if scope == "system" and not self.is_admin():
            messagebox.showerror(
                "Admin Privileges Required",
                "Installing for all users requires administrator privileges. Please run this installer as an administrator.",
            )
            self.root.quit()
            return
        try:
            # Create install dir and subfolders
            os.makedirs(install_dir, exist_ok=True)
            for sub in ["packages"]:
                os.makedirs(os.path.join(install_dir, sub), exist_ok=True)
            # Copy main.py, virtolang.txt, etc. to install dir
            if hasattr(sys, "_MEIPASS"):
                # Running as PyInstaller EXE
                resource_dir = sys._MEIPASS
            else:
                # Running as script
                resource_dir = os.path.dirname(os.path.abspath(__file__))

            for fname in ["vlang.exe", "VirtoLang-Transparent.ico", "vpm.exe"]:
                src = os.path.join(resource_dir, fname)
                dst = os.path.join(install_dir, fname)
                with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
                    fdst.write(fsrc.read())
            # Set VLANG_PATH env var
            self.set_env_var("VLANG_PATH", install_dir, scope)
            # Add to PATH
            self.add_to_path(install_dir, scope)
            messagebox.showinfo(
                "Success",
                f"VirtoLang installed to {install_dir}!\n\nYou may need to restart your shell or log out/in for PATH changes to take effect.",
            )
            self.root.quit()
        except Exception as e:
            messagebox.showerror("Install Error", str(e))

    def set_env_var(self, name, value, scope):
        if scope == "system":
            # Set system env var
            with reg.OpenKey(
                reg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment",
                0,
                reg.KEY_SET_VALUE,
            ) as key:
                reg.SetValueEx(key, name, 0, reg.REG_EXPAND_SZ, value)
        else:
            # Set user env var
            subprocess.run(["setx", name, value], shell=True)

    def add_to_path(self, dir_path, scope):
        if scope == "system":
            with reg.OpenKey(
                reg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment",
                0,
                reg.KEY_READ | reg.KEY_SET_VALUE,
            ) as key:
                path, _ = reg.QueryValueEx(key, "Path")
                if dir_path not in path:
                    new_path = path + ";" + dir_path
                    reg.SetValueEx(key, "Path", 0, reg.REG_EXPAND_SZ, new_path)
        else:
            # User PATH
            result = subprocess.run(
                ["powershell", "[Environment]::GetEnvironmentVariable('Path', 'User')"],
                capture_output=True,
                text=True,
            )
            path = result.stdout.strip()
            if dir_path not in path:
                new_path = path + ";" + dir_path
                subprocess.run(["setx", "Path", new_path], shell=True)


if __name__ == "__main__":
    root = tk.Tk()
    if hasattr(sys, "_MEIPASS"):
        icon_path = os.path.join(sys._MEIPASS, "VirtoLang-Transparent.ico")
    else:
        icon_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "VirtoLang-Transparent.ico"
        )
    root.iconbitmap(icon_path)
    app = InstallerApp(root)
    root.geometry("500x450")
    root.resizable(False, False)
    root.mainloop()
