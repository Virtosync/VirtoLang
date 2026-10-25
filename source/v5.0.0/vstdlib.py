"""VirtoLang standard built-ins.

Everything in the ``FUNCTIONS`` table at the bottom of this file is available
in every VirtoLang program (and in the REPL) without an ``import``.  They
cover jobs that are common but normally take a lot of code:

* files, folders and JSON / CSV            ``read_file``, ``write_json`` ...
* HTTP requests (client)                   ``http_get``, ``http_post`` ...
* a web server                             ``serve``
* desktop windows (GUI, via tkinter)       ``window``, ``message_box`` ...
* time, randomness, hashing, encoding      ``now``, ``random_int``, ``sha256`` ...
* system helpers                           ``run``, ``env``, ``open_url`` ...

Only the Python standard library is used.  Heavy modules (``tkinter``,
``http.server``...) are imported lazily, the first time they are needed, so
starting VirtoLang stays fast.

This module deliberately knows nothing about the interpreter: VirtoLang
functions are plain Python callables, so callbacks passed in by a program
(button handlers, web route handlers) are simply called like any function.
"""

import base64
import copy
import csv
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import time
import uuid as _uuid
from datetime import datetime

# ---------------------------------------------------------------------------
# Files and folders
# ---------------------------------------------------------------------------


def read_file(path, encoding="utf-8"):
    """Return the whole text of a file as a string."""
    with open(path, "r", encoding=encoding) as handle:
        return handle.read()


def read_lines(path, encoding="utf-8"):
    """Return the lines of a file as a list of strings (no trailing newlines)."""
    with open(path, "r", encoding=encoding) as handle:
        return handle.read().splitlines()


def write_file(path, text, encoding="utf-8"):
    """Write ``text`` to a file, replacing anything already there.

    Missing parent folders are created.  Returns the number of characters
    written.
    """
    _ensure_parent(path)
    with open(path, "w", encoding=encoding) as handle:
        return handle.write(str(text))


def append_file(path, text, encoding="utf-8"):
    """Add ``text`` to the end of a file, creating it if needed."""
    _ensure_parent(path)
    with open(path, "a", encoding=encoding) as handle:
        return handle.write(str(text))


def read_bytes(path):
    """Return the contents of a file as ``bytes``."""
    with open(path, "rb") as handle:
        return handle.read()


def write_bytes(path, data):
    """Write ``bytes`` to a file, replacing anything already there."""
    _ensure_parent(path)
    with open(path, "wb") as handle:
        return handle.write(data)


def file_exists(path):
    """True if ``path`` exists (file or folder)."""
    return os.path.exists(path)


def is_file(path):
    """True if ``path`` is an existing file."""
    return os.path.isfile(path)


def is_dir(path):
    """True if ``path`` is an existing folder."""
    return os.path.isdir(path)


def list_dir(path="."):
    """Return the sorted names of the entries in a folder."""
    return sorted(os.listdir(path))


def make_dir(path):
    """Create a folder (and any missing parents).  Does nothing if it exists."""
    os.makedirs(path, exist_ok=True)


def delete_file(path):
    """Delete a file, or a folder and everything in it."""
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


def copy_file(source, destination):
    """Copy a file to a new path and return the new path."""
    _ensure_parent(destination)
    return shutil.copy2(source, destination)


def move_file(source, destination):
    """Move or rename a file or folder."""
    _ensure_parent(destination)
    return shutil.move(source, destination)


def join_path(*parts):
    """Join path pieces with the right separator for this system."""
    return os.path.join(*parts)


def cwd():
    """Return the current working folder."""
    return os.getcwd()


def _ensure_parent(path):
    """Create the folder that will contain ``path`` if it does not exist."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)


# ---------------------------------------------------------------------------
# JSON and CSV
# ---------------------------------------------------------------------------


def json_parse(text):
    """Convert JSON text into dicts, lists, strings, numbers, True/False/None."""
    return json.loads(text)


def json_stringify(value, indent=None):
    """Convert a value into JSON text.  ``indent=2`` gives readable output."""
    return json.dumps(value, indent=indent, ensure_ascii=False, default=str)


def read_json(path):
    """Read a JSON file and return its contents as VirtoLang values."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, value, indent=2):
    """Write a value to a file as JSON (pretty-printed by default)."""
    write_file(path, json_stringify(value, indent=indent))


def read_csv(path):
    """Read a CSV file with a header row.

    Returns a list of dicts, one per row, keyed by the column names.
    """
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    """Write a list of dicts to a CSV file.

    The column names are taken from the keys of the rows (in first-seen order).
    """
    _ensure_parent(path)
    columns = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


class HttpResponse:
    """The result of an HTTP request.

    Attributes:
        status: Status code, e.g. ``200`` or ``404``.
        ok: True when the status is below 400.
        text: The body decoded as text.
        content: The raw body as ``bytes``.
        headers: Response headers as a dict (names in lower case).
        url: The final URL (after redirects).

    Use ``response.json()`` to parse a JSON body.
    """

    def __init__(self, status, headers, content, url):
        self.status = status
        self.ok = status < 400
        self.headers = {k.lower(): v for k, v in headers.items()}
        self.content = content
        self.url = url
        charset = "utf-8"
        content_type = self.headers.get("content-type", "")
        if "charset=" in content_type:
            charset = content_type.split("charset=")[-1].split(";")[0].strip()
        self.text = content.decode(charset, errors="replace")

    def json(self):
        """Parse the body as JSON."""
        return json.loads(self.text)

    def raise_for_status(self):
        """Raise an error if the status code is 400 or above."""
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status} for {self.url}")
        return self

    def __repr__(self):
        return f"<HttpResponse {self.status} {self.url}>"


def http_request(
    method, url, data=None, json=None, headers=None, params=None, timeout=30
):
    """Send an HTTP request and return an ``HttpResponse``.

    Args:
        method: ``"GET"``, ``"POST"``, ``"PUT"``, ``"DELETE"`` ...
        url: The address to call.
        data: Request body.  A dict is sent as a form
            (``application/x-www-form-urlencoded``); a string or bytes is sent
            as-is.
        json: A value to send as a JSON body (sets the content type for you).
        headers: Extra request headers as a dict.
        params: A dict added to the URL as a query string.
        timeout: Seconds to wait before giving up.

    HTTP error statuses (404, 500...) do **not** raise; check
    ``response.ok`` / ``response.status``.  Network failures (no connection,
    timeout) raise an error.
    """
    import urllib.error
    import urllib.parse
    import urllib.request

    json_module = sys.modules["json"]  # the ``json`` argument shadows the module
    headers = dict(headers or {})
    if params:
        separator = "&" if "?" in url else "?"
        url = url + separator + urllib.parse.urlencode(params, doseq=True)

    body = None
    if json is not None:
        body = json_module.dumps(json).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    elif isinstance(data, dict):
        body = urllib.parse.urlencode(data, doseq=True).encode("utf-8")
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif isinstance(data, str):
        body = data.encode("utf-8")
    elif data is not None:
        body = bytes(data)
    headers.setdefault("User-Agent", "VirtoLang")

    request = urllib.request.Request(
        url, data=body, headers=headers, method=str(method).upper()
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            return HttpResponse(reply.status, dict(reply.headers), reply.read(), reply.url)
    except urllib.error.HTTPError as error:
        return HttpResponse(error.code, dict(error.headers), error.read(), url)


def http_get(url, headers=None, params=None, timeout=30):
    """``GET`` a URL.  Example: ``http_get("https://example.com").text``."""
    return http_request("GET", url, headers=headers, params=params, timeout=timeout)


def http_post(url, data=None, json=None, headers=None, timeout=30):
    """``POST`` to a URL, sending ``data`` (form/text/bytes) or ``json``."""
    return http_request(
        "POST", url, data=data, json=json, headers=headers, timeout=timeout
    )


def http_put(url, data=None, json=None, headers=None, timeout=30):
    """``PUT`` to a URL, sending ``data`` (form/text/bytes) or ``json``."""
    return http_request(
        "PUT", url, data=data, json=json, headers=headers, timeout=timeout
    )


def http_delete(url, headers=None, timeout=30):
    """Send a ``DELETE`` request."""
    return http_request("DELETE", url, headers=headers, timeout=timeout)


def download(url, path, timeout=60):
    """Download a URL to a file and return the path.

    Raises an error if the server answers with a failure status.
    """
    response = http_get(url, timeout=timeout)
    response.raise_for_status()
    write_bytes(path, response.content)
    return path


def url_encode(value):
    """Percent-encode text (or a dict of fields) for use inside a URL."""
    import urllib.parse

    if isinstance(value, dict):
        return urllib.parse.urlencode(value, doseq=True)
    return urllib.parse.quote(str(value), safe="")


def url_decode(text):
    """Reverse ``url_encode`` for text."""
    import urllib.parse

    return urllib.parse.unquote(text)


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------


class Request:
    """What a web handler receives for each incoming HTTP request.

    Attributes:
        method: ``"GET"``, ``"POST"`` ...
        path: The path without the query string, e.g. ``"/users"``.
        query: Query-string values as a dict, e.g. ``{"page": "2"}``.
        headers: Request headers as a dict (names in lower case).
        body: The body decoded as text.
        content: The raw body as ``bytes``.
        client: The caller's IP address.

    ``request.json()`` parses a JSON body; ``request.form()`` parses a
    ``key=value&...`` form body into a dict.
    """

    def __init__(self, method, path, query, headers, content, client):
        self.method = method
        self.path = path
        self.query = query
        self.headers = headers
        self.content = content
        self.body = content.decode("utf-8", errors="replace")
        self.client = client

    def json(self):
        """Parse the body as JSON."""
        return json.loads(self.body)

    def form(self):
        """Parse a URL-encoded form body into a dict."""
        import urllib.parse

        return {k: v[0] for k, v in urllib.parse.parse_qs(self.body).items()}

    def __repr__(self):
        return f"<Request {self.method} {self.path}>"


def _build_reply(result):
    """Turn a handler's return value into ``(status, headers, body_bytes)``.

    Accepted return values:

    * ``str``   -> HTML if it starts with ``<``, otherwise plain text
    * ``dict`` / ``list`` -> JSON
    * ``bytes`` -> raw download
    * ``None``  -> empty ``200`` response
    * ``(body, status)`` or ``(body, status, headers_dict)`` -> as above with
      a custom status code and extra headers
    """
    status = 200
    extra_headers = {}
    if isinstance(result, tuple) and 2 <= len(result) <= 3:
        status = int(result[1])
        if len(result) == 3:
            extra_headers = dict(result[2])
        result = result[0]

    if result is None:
        body, content_type = b"", "text/plain; charset=utf-8"
    elif isinstance(result, (bytes, bytearray)):
        body, content_type = bytes(result), "application/octet-stream"
    elif isinstance(result, (dict, list)):
        body = json_stringify(result).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    else:
        text = str(result)
        body = text.encode("utf-8")
        is_html = text.lstrip().lower().startswith(("<!doctype", "<html", "<"))
        content_type = (
            "text/html; charset=utf-8" if is_html else "text/plain; charset=utf-8"
        )
    headers = {"Content-Type": content_type}
    headers.update(extra_headers)
    return status, headers, body


def serve(routes, port=8000, host="127.0.0.1"):
    """Start a web server and keep running until Ctrl-C.

    ``routes`` is either

    * a **function** that receives a ``Request`` and returns a reply
      (it handles every URL), or
    * a **dict** mapping a path to a reply or to a function.  A key can be a
      path (``"/about"``) or a method plus path (``"POST /submit"``).  The
      special key ``"*"`` is the fallback for unknown paths.

    A reply can be text, HTML, a dict/list (sent as JSON), bytes, or a tuple
    ``(body, status)`` / ``(body, status, headers)``.

    Example::

        def hello(request) {
            return {"hello": request.query.get("name", "world")}
        }
        serve({"/": "<h1>Welcome</h1>", "/hello": hello}, port=8080)

    The server handles one request at a time, which keeps VirtoLang programs
    free of threading surprises.  By default it only listens on this computer
    (``127.0.0.1``); pass ``host="0.0.0.0"`` to accept connections from other
    machines.
    """
    import urllib.parse
    from http.server import BaseHTTPRequestHandler, HTTPServer

    def find_reply(request):
        """Pick the route for a request and return its reply value."""
        if callable(routes):
            return routes(request)
        handler = routes.get(f"{request.method} {request.path}")
        if handler is None:
            handler = routes.get(request.path)
        if handler is None:
            handler = routes.get("*")
        if handler is None:
            return ("Not found", 404)
        return handler(request) if callable(handler) else handler

    class Handler(BaseHTTPRequestHandler):
        server_version = "VirtoLang"

        def _handle(self):
            parsed = urllib.parse.urlsplit(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            content = self.rfile.read(length) if length else b""
            query = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
            headers = {k.lower(): v for k, v in self.headers.items()}
            request = Request(
                self.command,
                urllib.parse.unquote(parsed.path),
                query,
                headers,
                content,
                self.client_address[0],
            )
            try:
                status, reply_headers, body = _build_reply(find_reply(request))
            except Exception as error:  # a bug in the user's handler
                print(f"VirtoLang server error: {error!r}", file=sys.stderr)
                status, reply_headers, body = _build_reply(("Server error", 500))
            self.send_response(status)
            for name, value in reply_headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            print(f"{self.command} {request.path} -> {status}")

        do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = _handle

        def log_message(self, *args):
            """Silence the default log; ``_handle`` prints a shorter line."""

    server = HTTPServer((host, int(port)), Handler)
    print(f"Serving on http://{host}:{port}  (press Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


# ---------------------------------------------------------------------------
# Desktop GUI (tkinter)
# ---------------------------------------------------------------------------


def _tk():
    """Import tkinter on first use, with a helpful error if it is missing."""
    try:
        import tkinter
        from tkinter import ttk
    except ImportError:
        raise RuntimeError(
            "GUI built-ins need tkinter, which is not available in this Python"
        ) from None
    return tkinter, ttk


class Widget:
    """A control inside a ``Window`` (label, button, entry, ...).

    ``get()`` returns the current value (typed text, checkbox state, slider
    position, selected item) and ``set(value)`` changes it.  ``disable()`` /
    ``enable()`` turn a control off and on.  ``widget`` is the raw tkinter
    object for advanced use.
    """

    def __init__(self, widget, variable=None, kind="label"):
        self.widget = widget
        self.variable = variable
        self.kind = kind

    def get(self):
        """Return the control's current value."""
        if self.kind == "textbox":
            return self.widget.get("1.0", "end-1c")
        if self.variable is not None:
            return self.variable.get()
        return self.widget.cget("text")

    def set(self, value):
        """Change the control's value (or a label/button's text)."""
        if self.kind == "textbox":
            self.widget.delete("1.0", "end")
            self.widget.insert("1.0", str(value))
        elif self.variable is not None:
            self.variable.set(value)
        else:
            self.widget.configure(text=str(value))

    def disable(self):
        """Grey the control out so it cannot be used."""
        self.widget.configure(state="disabled")

    def enable(self):
        """Make the control usable again."""
        self.widget.configure(state="normal")

    def __repr__(self):
        return f"<{self.kind} widget>"


class Window:
    """A desktop window.  Create one with ``window(title, width, height)``.

    Add controls from top to bottom with ``label``, ``button``, ``entry``,
    ``textbox``, ``checkbox``, ``dropdown`` and ``slider``; each returns a
    ``Widget``.  Call ``show()`` to display the window and wait until it is
    closed.

    Example::

        win = window("Greeter", 300, 160)
        name = win.entry()
        out = win.label("")
        def greet() { out.set("Hello, " + name.get()) }
        win.button("Greet", greet)
        win.show()
    """

    def __init__(self, title="VirtoLang", width=400, height=300):
        tkinter, ttk = _tk()
        self._tk, self._ttk = tkinter, ttk
        self.root = tkinter.Tk()
        self.root.title(str(title))
        self.root.geometry(f"{int(width)}x{int(height)}")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _place(self, widget):
        """Stack a new control below the previous ones."""
        widget.pack(padx=10, pady=4, fill="x")

    def label(self, text=""):
        """Add a line of text."""
        widget = self._ttk.Label(self.root, text=str(text))
        self._place(widget)
        return Widget(widget, kind="label")

    def button(self, text, command=None):
        """Add a button.  ``command`` is a function called with no arguments."""
        widget = self._ttk.Button(
            self.root, text=str(text), command=command or (lambda: None)
        )
        self._place(widget)
        return Widget(widget, kind="button")

    def entry(self, text=""):
        """Add a one-line text box."""
        variable = self._tk.StringVar(value=str(text))
        widget = self._ttk.Entry(self.root, textvariable=variable)
        self._place(widget)
        return Widget(widget, variable, kind="entry")

    def textbox(self, text="", height=8):
        """Add a multi-line text area."""
        widget = self._tk.Text(self.root, height=int(height))
        widget.insert("1.0", str(text))
        self._place(widget)
        return Widget(widget, kind="textbox")

    def checkbox(self, text, checked=False):
        """Add a tick box; ``get()`` returns True or False."""
        variable = self._tk.BooleanVar(value=bool(checked))
        widget = self._ttk.Checkbutton(self.root, text=str(text), variable=variable)
        self._place(widget)
        return Widget(widget, variable, kind="checkbox")

    def dropdown(self, options, selected=None):
        """Add a drop-down list; ``get()`` returns the chosen item."""
        options = [str(o) for o in options]
        variable = self._tk.StringVar(value=selected or (options[0] if options else ""))
        widget = self._ttk.Combobox(
            self.root, textvariable=variable, values=options, state="readonly"
        )
        self._place(widget)
        return Widget(widget, variable, kind="dropdown")

    def slider(self, low=0, high=100, value=None):
        """Add a slider; ``get()`` returns its number."""
        variable = self._tk.DoubleVar(value=low if value is None else value)
        widget = self._ttk.Scale(
            self.root, from_=low, to=high, variable=variable, orient="horizontal"
        )
        self._place(widget)
        return Widget(widget, variable, kind="slider")

    def after(self, milliseconds, command):
        """Call ``command`` once after a delay (use it for timers/animation)."""
        self.root.after(int(milliseconds), command)

    def title(self, text):
        """Change the window title."""
        self.root.title(str(text))

    def show(self):
        """Display the window and wait until the user closes it."""
        self.root.mainloop()

    def close(self):
        """Close the window."""
        self.root.destroy()

    def __repr__(self):
        return "<Window>"


def window(title="VirtoLang", width=400, height=300):
    """Create a desktop window.  See ``Window`` for what you can add to it."""
    return Window(title, width, height)


def _dialog_root():
    """A hidden, topmost root window so dialogs appear in front."""
    tkinter, _ = _tk()
    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    return root


def message_box(message, title="VirtoLang"):
    """Show a pop-up message with an OK button."""
    from tkinter import messagebox

    root = _dialog_root()
    try:
        messagebox.showinfo(str(title), str(message), parent=root)
    finally:
        root.destroy()


def ask_yes_no(question, title="VirtoLang"):
    """Show a Yes/No pop-up and return True or False."""
    from tkinter import messagebox

    root = _dialog_root()
    try:
        return messagebox.askyesno(str(title), str(question), parent=root)
    finally:
        root.destroy()


def ask_text(prompt, title="VirtoLang", default=""):
    """Pop up a box asking for text.  Returns the text, or None if cancelled."""
    from tkinter import simpledialog

    root = _dialog_root()
    try:
        return simpledialog.askstring(
            str(title), str(prompt), initialvalue=default, parent=root
        )
    finally:
        root.destroy()


def choose_file(title="Choose a file"):
    """Show an open-file dialog.  Returns the path, or None if cancelled."""
    from tkinter import filedialog

    root = _dialog_root()
    try:
        return filedialog.askopenfilename(title=title, parent=root) or None
    finally:
        root.destroy()


def choose_save_file(title="Save as"):
    """Show a save-file dialog.  Returns the path, or None if cancelled."""
    from tkinter import filedialog

    root = _dialog_root()
    try:
        return filedialog.asksaveasfilename(title=title, parent=root) or None
    finally:
        root.destroy()


def choose_folder(title="Choose a folder"):
    """Show a folder picker.  Returns the path, or None if cancelled."""
    from tkinter import filedialog

    root = _dialog_root()
    try:
        return filedialog.askdirectory(title=title, parent=root) or None
    finally:
        root.destroy()


# ---------------------------------------------------------------------------
# Time and dates
# ---------------------------------------------------------------------------


def sleep(seconds):
    """Pause the program for a number of seconds (decimals allowed)."""
    time.sleep(seconds)


def timestamp():
    """Seconds since 1 Jan 1970 (UTC) as a decimal number."""
    return time.time()


def now(fmt="%Y-%m-%d %H:%M:%S"):
    """The current local time as text.  ``fmt`` uses Python's strftime codes."""
    return datetime.now().strftime(fmt)


def today():
    """Today's date as ``YYYY-MM-DD``."""
    return datetime.now().strftime("%Y-%m-%d")


def format_time(seconds, fmt="%Y-%m-%d %H:%M:%S"):
    """Format a ``timestamp()`` value as local-time text."""
    return datetime.fromtimestamp(seconds).strftime(fmt)


# ---------------------------------------------------------------------------
# Randomness, hashing and encoding
# ---------------------------------------------------------------------------


def random_float():
    """A random decimal number from 0 up to (not including) 1."""
    return random.random()


def random_int(low, high):
    """A random whole number from ``low`` to ``high``, both included."""
    return random.randint(low, high)


def random_choice(items):
    """Pick one random item from a list, tuple or string."""
    return random.choice(items)


def shuffle(items):
    """Return a new list with the items in random order."""
    result = list(items)
    random.shuffle(result)
    return result


def uuid():
    """A new random unique ID as text."""
    return str(_uuid.uuid4())


def _to_bytes(value):
    """Accept text or bytes and return bytes."""
    return value if isinstance(value, (bytes, bytearray)) else str(value).encode("utf-8")


def sha256(value):
    """SHA-256 hash of text or bytes, as hex text."""
    return hashlib.sha256(_to_bytes(value)).hexdigest()


def md5(value):
    """MD5 hash of text or bytes, as hex text (not safe for passwords)."""
    return hashlib.md5(_to_bytes(value)).hexdigest()


def base64_encode(value):
    """Encode text or bytes as Base64 text."""
    return base64.b64encode(_to_bytes(value)).decode("ascii")


def base64_decode(text):
    """Decode Base64 text back into a string."""
    return base64.b64decode(text).decode("utf-8")


# ---------------------------------------------------------------------------
# System helpers and small utilities
# ---------------------------------------------------------------------------


class CommandResult:
    """The outcome of ``run(...)``: ``output``, ``error``, ``code`` and ``ok``."""

    def __init__(self, output, error, code):
        self.output = output
        self.error = error
        self.code = code
        self.ok = code == 0

    def __str__(self):
        return self.output

    def __repr__(self):
        return f"<CommandResult code={self.code}>"


def run(command, timeout=None):
    """Run a command (a string or a list) and return a ``CommandResult``.

    A string is run through the system shell, so pipes and redirects work.
    Output is captured instead of printed.
    """
    completed = subprocess.run(
        command,
        shell=isinstance(command, str),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return CommandResult(completed.stdout, completed.stderr, completed.returncode)


def env(name, default=None):
    """Read an environment variable, or ``default`` if it is not set."""
    return os.environ.get(name, default)


def args():
    """The command-line arguments passed to the interpreter, as a list."""
    return list(sys.argv[1:])


def open_url(url):
    """Open a web address (or file) in the default browser."""
    import webbrowser

    return webbrowser.open(url)


def clamp(value, low, high):
    """Limit ``value`` so it is never below ``low`` or above ``high``."""
    return max(low, min(high, value))


def to_int(value, default=0):
    """Convert to a whole number, returning ``default`` instead of failing."""
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def to_float(value, default=0.0):
    """Convert to a decimal number, returning ``default`` instead of failing."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def deep_copy(value):
    """A fully independent copy of a list/dict/object and everything inside."""
    return copy.deepcopy(value)


def pretty(value):
    """Return a readable, indented text form of dicts and lists."""
    return json_stringify(value, indent=2)


# ---------------------------------------------------------------------------
# Async helpers (used with ``async def`` / ``await``)
# ---------------------------------------------------------------------------


def async_run(awaitable):
    """Run an ``async def`` call to completion and return its result.

    Example: ``async_run(main())``.
    """
    import asyncio

    async def _wrapper():
        return await awaitable

    return asyncio.run(_wrapper())


async def async_sleep(seconds):
    """``await async_sleep(1)`` pauses this task without blocking the others."""
    import asyncio

    await asyncio.sleep(seconds)


async def gather(*awaitables):
    """``await gather(a(), b())`` runs them together; returns a list of results."""
    import asyncio

    return list(await asyncio.gather(*awaitables))


def create_task(awaitable):
    """Start an async call in the background (inside a running ``async def``)."""
    import asyncio

    return asyncio.ensure_future(awaitable)


# ---------------------------------------------------------------------------
# Ready-made decorators (use as ``@memoize`` above a ``def``)
# ---------------------------------------------------------------------------


def memoize(function):
    """Cache results so repeated calls with the same arguments are instant."""
    import functools

    return functools.wraps(function)(functools.lru_cache(maxsize=None)(function))


def timed(function):
    """Print how long each call to the function takes."""

    def wrapper(*args, **kwargs):
        started = time.perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - started
            print(f"{getattr(function, 'name', 'function')} took {elapsed:.4f}s")

    return wrapper


def retry(times=3, delay=0):
    """Decorator factory: ``@retry(3)`` calls again if the function raises."""

    def decorator(function):
        def wrapper(*args, **kwargs):
            for attempt in range(1, times + 1):
                try:
                    return function(*args, **kwargs)
                except Exception:
                    if attempt == times:
                        raise
                    if delay:
                        time.sleep(delay)

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

# Name -> function.  ``lexer`` merges this into the built-in table; the name
# on the left is what VirtoLang programs write.
FUNCTIONS = {
    function.__name__: function
    for function in (
        # files
        read_file, read_lines, write_file, append_file, read_bytes, write_bytes,
        file_exists, is_file, is_dir, list_dir, make_dir, delete_file,
        copy_file, move_file, join_path, cwd,
        # data formats
        json_parse, json_stringify, read_json, write_json, read_csv, write_csv,
        # http
        http_request, http_get, http_post, http_put, http_delete, download,
        url_encode, url_decode, serve,
        # gui
        window, message_box, ask_yes_no, ask_text, choose_file,
        choose_save_file, choose_folder,
        # time
        sleep, timestamp, now, today, format_time,
        # random / hashing / encoding
        random_float, random_int, random_choice, shuffle, uuid, sha256, md5,
        base64_encode, base64_decode,
        # system and utilities
        run, env, args, open_url, clamp, to_int, to_float, deep_copy, pretty,
                # async and decorators
                async_run, async_sleep, gather, create_task, memoize, timed, retry,
            )
}


def list_builtins():
    """Return the sorted names of all VirtoLang-specific built-in functions."""
    return sorted(FUNCTIONS)


FUNCTIONS["list_builtins"] = list_builtins
