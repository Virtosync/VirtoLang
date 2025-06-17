# VirtoLang v2.4 – Release Notes (June 2025)

## Major New Features & Improvements

- **Tkinter GUI Support**: Added built-in functions for creating GUIs with Tkinter, including `tk_root`, `tk_label`, `tk_button`, `tk_messagebox`, `tk_set_title`, and `tk_mainloop`. You can now build simple windows and dialogues directly from VirtoLang code.
- **Colorama Terminal Styling**: Added built-ins for terminal color and style control: `colorama_fore`, `colorama_back`, and `colorama_style`.
- **Improved Built-in Error Reporting**: Argument and type errors in built-in functions now raise a clear `ArgumentError` with user-friendly messages and file context, instead of Python tracebacks or generic runtime errors.
- **Consistent Error Handling**: All runtime and argument errors now include the filename for better debugging.
- **Expanded HTTP Built-ins**: More HTTP helpers (`http_put`, `http_delete`, `http_head`, `http_options`, `http_patch`, `http_status`, `http_json`, `http_text`, `http_headers`, `http_url`, `http_ok`, `http_raise_for_status`) for advanced web scripting.
- **Documentation Updates**: The user guide and built-in function list have been updated to reflect all new features and usage patterns.

## Example: Tkinter GUI in VirtoLang
```vlang
root = tk_root()
tk_set_title(root, "Hello Window!")
label = tk_label(root, "Welcome to VirtoLang 2.4!")
label.pack()
tk_mainloop(root)
```

## Example: Colorama Styling
```vlang
print(colorama_fore("red") + "This is red text!" + colorama_style("reset_all"))
```

## Example: HTTP POST with Error Handling
```vlang
try {
    print(http_post("https://example.com"))
} except ArgumentError as e {
    print(e)
}
```

---

For a full list of built-ins and usage, see the updated documentation in `README.md`.
