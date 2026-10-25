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
# Lists and collections
# ---------------------------------------------------------------------------


def first(items, default=None):
    """First item of a list/string/iterable, or ``default`` if it is empty."""
    for item in items:
        return item
    return default


def last(items, default=None):
    """Last item of a list/string, or ``default`` if it is empty."""
    items = items if hasattr(items, "__getitem__") else list(items)
    return items[-1] if len(items) else default


def take(items, count):
    """The first ``count`` items as a list."""
    import itertools

    return list(itertools.islice(items, count))


def drop(items, count):
    """Everything except the first ``count`` items, as a list."""
    return list(items)[count:]


def chunk(items, size):
    """Split into lists of ``size`` items: ``chunk([1,2,3,4,5], 2)`` -> ``[[1,2],[3,4],[5]]``."""
    items = list(items)
    if size < 1:
        raise ValueError("chunk size must be at least 1")
    return [items[i:i + size] for i in range(0, len(items), size)]


def flatten(items, depth=1):
    """Flatten nested lists ``depth`` levels (use ``depth=-1`` for all levels)."""
    result = []
    for item in items:
        if isinstance(item, (list, tuple)) and depth != 0:
            result.extend(flatten(item, depth - 1))
        else:
            result.append(item)
    return result


def flat_map(function, items):
    """Map ``function`` over ``items`` and join the resulting lists into one."""
    return [value for item in items for value in function(item)]


def unique(items, key=None):
    """Remove duplicates, keeping the first occurrence and the original order."""
    seen = set()
    result = []
    for item in items:
        marker = key(item) if key else item
        try:
            if marker in seen:
                continue
            seen.add(marker)
        except TypeError:
            if item in result:
                continue
        result.append(item)
    return result


def compact(items):
    """Drop falsy values (``none``, ``0``, empty strings/lists...)."""
    return [item for item in items if item]


def group_by(items, key):
    """Group items into ``{key(item): [items...]}``."""
    groups = {}
    for item in items:
        groups.setdefault(key(item), []).append(item)
    return groups


def count_by(items, key=None):
    """Count items (or ``key(item)`` values): ``count_by("hello")`` -> ``{"h":1,"e":1,"l":2,"o":1}``."""
    counts = {}
    for item in items:
        marker = key(item) if key else item
        counts[marker] = counts.get(marker, 0) + 1
    return counts


def partition(items, predicate):
    """Split into ``[matching, not_matching]`` lists."""
    yes, no = [], []
    for item in items:
        (yes if predicate(item) else no).append(item)
    return [yes, no]


def pluck(items, key):
    """Take one key/attribute from every item: ``pluck(users, "name")``."""
    result = []
    for item in items:
        result.append(item[key] if isinstance(item, (dict, list, tuple)) else getattr(item, key))
    return result


def sort_by(items, key, descending=False):
    """Return a sorted copy ordered by ``key(item)``."""
    return sorted(items, key=key, reverse=descending)


def min_by(items, key):
    """Item with the smallest ``key(item)``."""
    return min(items, key=key)


def max_by(items, key):
    """Item with the largest ``key(item)``."""
    return max(items, key=key)


def sum_by(items, key):
    """Sum of ``key(item)`` over all items."""
    return sum(key(item) for item in items)


def find(items, predicate, default=None):
    """First item for which ``predicate(item)`` is true, else ``default``."""
    for item in items:
        if predicate(item):
            return item
    return default


def find_index(items, predicate):
    """Index of the first matching item, or ``-1``."""
    for index, item in enumerate(items):
        if predicate(item):
            return index
    return -1


def every(items, predicate):
    """True if ``predicate`` is true for every item."""
    return all(predicate(item) for item in items)


def some(items, predicate):
    """True if ``predicate`` is true for at least one item."""
    return any(predicate(item) for item in items)


def count_if(items, predicate):
    """How many items satisfy ``predicate``."""
    return sum(1 for item in items if predicate(item))


def reduce(function, items, initial=None):
    """Fold a list into one value: ``reduce(fn(acc, x) {...}, items, start)``."""
    import functools

    if initial is None:
        return functools.reduce(function, items)
    return functools.reduce(function, items, initial)


def accumulate(items, function=None):
    """Running totals (or running ``function`` results) as a list."""
    import itertools

    return list(itertools.accumulate(items, function))


def product(items, start=1):
    """Multiply all numbers together."""
    import math

    return math.prod(items, start=start)


def zip_dict(keys, values):
    """Build a dict from two lists."""
    return dict(zip(keys, values))


def pairwise(items):
    """Neighbouring pairs: ``pairwise([1,2,3])`` -> ``[(1,2),(2,3)]``."""
    items = list(items)
    return list(zip(items, items[1:]))


def sliding_window(items, size):
    """Every run of ``size`` consecutive items."""
    items = list(items)
    return [items[i:i + size] for i in range(len(items) - size + 1)]


def rotate(items, steps=1):
    """Move items ``steps`` places to the left (negative = right)."""
    items = list(items)
    if not items:
        return items
    steps %= len(items)
    return items[steps:] + items[:steps]


def transpose(rows):
    """Swap rows and columns of a list of lists."""
    return [list(column) for column in zip(*rows)]


def repeat(value, times):
    """A list containing ``value`` ``times`` times."""
    return [value] * times


def index_of(items, value, default=-1):
    """Index of ``value`` in a list/string, or ``default`` if absent."""
    try:
        return items.index(value)
    except ValueError:
        return default


def union(*collections):
    """Unique items from all collections, in first-seen order."""
    return unique(item for collection in collections for item in collection)


def intersection(first_items, *others):
    """Items of the first collection that appear in all the others."""
    return [
        item for item in unique(first_items)
        if all(item in other for other in others)
    ]


def difference(first_items, *others):
    """Items of the first collection that appear in none of the others."""
    return [
        item for item in unique(first_items)
        if not any(item in other for other in others)
    ]


def counter(items):
    """Count occurrences, most common first: ``{"a": 3, "b": 1}``."""
    import collections

    return dict(collections.Counter(items).most_common())


def most_common(items, count=1):
    """The ``count`` most frequent items as ``[(item, times)]``."""
    import collections

    return collections.Counter(items).most_common(count)


def sample(items, count):
    """``count`` distinct random items."""
    return random.sample(list(items), count)


def merge(*dicts):
    """Combine dicts into a new one (later dicts win)."""
    result = {}
    for item in dicts:
        result.update(item)
    return result


def deep_merge(base, other):
    """Like ``merge`` but nested dicts are merged recursively."""
    result = dict(base)
    for key, value in other.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def pick(mapping, *keys):
    """A new dict with only the given keys."""
    return {key: mapping[key] for key in keys if key in mapping}


def omit(mapping, *keys):
    """A new dict without the given keys."""
    return {key: value for key, value in mapping.items() if key not in keys}


def invert(mapping):
    """Swap keys and values."""
    return {value: key for key, value in mapping.items()}


def map_values(mapping, function):
    """Apply ``function`` to every value of a dict."""
    return {key: function(value) for key, value in mapping.items()}


def map_keys(mapping, function):
    """Apply ``function`` to every key of a dict."""
    return {function(key): value for key, value in mapping.items()}


def filter_dict(mapping, predicate):
    """Keep entries where ``predicate(key, value)`` is true."""
    return {key: value for key, value in mapping.items() if predicate(key, value)}


def get_path(data, path, default=None):
    """Read nested data: ``get_path(cfg, "db.users.0.name")``."""
    current = data
    for part in str(path).split("."):
        try:
            if isinstance(current, (list, tuple)):
                current = current[int(part)]
            else:
                current = current[part]
        except (KeyError, IndexError, ValueError, TypeError):
            return default
    return current


def set_path(data, path, value):
    """Write nested data in place, creating dicts as needed; returns ``data``."""
    parts = str(path).split(".")
    current = data
    for part in parts[:-1]:
        if isinstance(current, list):
            current = current[int(part)]
        else:
            current = current.setdefault(part, {})
    if isinstance(current, list):
        current[int(parts[-1])] = value
    else:
        current[parts[-1]] = value
    return data


# ---------------------------------------------------------------------------
# Functional helpers
# ---------------------------------------------------------------------------


def compose(*functions):
    """``compose(f, g)(x)`` is ``f(g(x))``."""

    def composed(*args, **kwargs):
        result = functions[-1](*args, **kwargs)
        for function in reversed(functions[:-1]):
            result = function(result)
        return result

    return composed


def pipe(value, *functions):
    """Pass ``value`` through each function in turn: ``pipe(5, double, str)``."""
    for function in functions:
        value = function(value)
    return value


def partial(function, *fixed_args, **fixed_kwargs):
    """Pre-fill some arguments of a function."""
    import functools

    return functools.partial(function, *fixed_args, **fixed_kwargs)


def identity(value):
    """Return the value unchanged."""
    return value


def constant(value):
    """A function that always returns ``value``."""
    return lambda *args, **kwargs: value


def noop(*args, **kwargs):
    """Do nothing (handy as a default callback)."""
    return None


def tap(value, function):
    """Run ``function(value)`` for its side effect, then return ``value``."""
    function(value)
    return value


def once(function):
    """Wrap a function so it runs only the first time it is called."""
    state = []

    def wrapper(*args, **kwargs):
        if not state:
            state.append(function(*args, **kwargs))
        return state[0]

    return wrapper


def default(value, fallback):
    """``fallback`` if ``value`` is ``none``, else ``value``."""
    return fallback if value is None else value


def measure(function, *args, **kwargs):
    """Call a function and return ``[result, seconds_taken]``."""
    started = time.perf_counter()
    result = function(*args, **kwargs)
    return [result, time.perf_counter() - started]


def benchmark(function, runs=100):
    """Average seconds per call over ``runs`` calls."""
    started = time.perf_counter()
    for _ in range(runs):
        function()
    return (time.perf_counter() - started) / runs


def parallel_map(function, items, workers=8):
    """Like ``map`` but runs calls on a thread pool; returns a list in order."""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(function, items))


def run_in_thread(function, *args, **kwargs):
    """Start ``function`` on a background thread; returns the thread (``.join()`` it)."""
    import threading

    thread = threading.Thread(target=function, args=args, kwargs=kwargs, daemon=True)
    thread.start()
    return thread


def every_seconds(seconds, function, times=None):
    """Call ``function`` every ``seconds`` seconds (forever, or ``times`` times)."""
    count = 0
    while times is None or count < times:
        function()
        count += 1
        time.sleep(seconds)


# ---------------------------------------------------------------------------
# Type checks
# ---------------------------------------------------------------------------


def type_name(value):
    """The name of a value's type as a string."""
    return type(value).__name__


def is_number(value):
    """True for ints and floats (not booleans)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_string(value):
    return isinstance(value, str)


def is_list(value):
    return isinstance(value, list)


def is_dict(value):
    return isinstance(value, dict)


def is_none(value):
    return value is None


def is_empty(value):
    """True for ``none`` and empty strings/lists/dicts/sets."""
    return value is None or (hasattr(value, "__len__") and len(value) == 0)


def is_numeric_string(text):
    """True if the text can be read as a number: ``"3.5"`` -> true."""
    try:
        float(text)
        return True
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Strings and text
# ---------------------------------------------------------------------------


def _split_words(text):
    import re

    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(text))
    return [word for word in re.split(r"[^A-Za-z0-9]+", text) if word]


def snake_case(text):
    """``"Hello World"`` -> ``"hello_world"``."""
    return "_".join(word.lower() for word in _split_words(text))


def kebab_case(text):
    """``"Hello World"`` -> ``"hello-world"``."""
    return "-".join(word.lower() for word in _split_words(text))


def camel_case(text):
    """``"hello world"`` -> ``"helloWorld"``."""
    words = [word.lower() for word in _split_words(text)]
    return (words[0] + "".join(w.capitalize() for w in words[1:])) if words else ""


def pascal_case(text):
    """``"hello world"`` -> ``"HelloWorld"``."""
    return "".join(word.capitalize() for word in _split_words(text))


def title_case(text):
    """Capitalise every word."""
    return " ".join(word.capitalize() for word in str(text).split())


def slugify(text):
    """URL-friendly text: ``"Hello, World!"`` -> ``"hello-world"``."""
    import unicodedata

    plain = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return kebab_case(plain)


def truncate(text, length, suffix="..."):
    """Shorten text to ``length`` characters, adding ``suffix`` if cut."""
    text = str(text)
    if len(text) <= length:
        return text
    return text[: max(0, length - len(suffix))] + suffix


def pad_left(text, width, fill=" "):
    """Right-align text in ``width`` characters."""
    return str(text).rjust(width, fill)


def pad_right(text, width, fill=" "):
    """Left-align text in ``width`` characters."""
    return str(text).ljust(width, fill)


def center_text(text, width, fill=" "):
    """Centre text in ``width`` characters."""
    return str(text).center(width, fill)


def words(text):
    """Split text into words."""
    return str(text).split()


def lines(text):
    """Split text into lines."""
    return str(text).splitlines()


def is_blank(text):
    """True for ``none`` or text with only whitespace."""
    return text is None or not str(text).strip()


def reverse(items):
    """A reversed copy of a list or string."""
    return items[::-1] if hasattr(items, "__getitem__") else list(items)[::-1]


def is_palindrome(text):
    """True if the text reads the same both ways (ignoring case/punctuation)."""
    cleaned = [c.lower() for c in str(text) if c.isalnum()]
    return cleaned == cleaned[::-1]


def count_words(text):
    """Number of words in the text."""
    return len(str(text).split())


def remove_prefix(text, prefix):
    """Remove ``prefix`` from the start if present."""
    return str(text).removeprefix(prefix)


def remove_suffix(text, suffix):
    """Remove ``suffix`` from the end if present."""
    return str(text).removesuffix(suffix)


def wrap_text(text, width=70):
    """Word-wrap text to ``width`` columns; returns a string."""
    import textwrap

    return textwrap.fill(str(text), width)


def indent_text(text, prefix="    "):
    """Add ``prefix`` to the start of every line."""
    import textwrap

    return textwrap.indent(str(text), prefix)


def dedent_text(text):
    """Remove common leading whitespace from every line."""
    import textwrap

    return textwrap.dedent(str(text))


def strip_html(text):
    """Remove HTML tags from text."""
    import html
    import re

    return html.unescape(re.sub(r"<[^>]*>", "", str(text)))


def html_escape(text):
    """Escape ``& < > "`` for use in HTML."""
    import html

    return html.escape(str(text))


def html_unescape(text):
    """Turn ``&amp;`` style entities back into characters."""
    import html

    return html.unescape(str(text))


def levenshtein(a, b):
    """Edit distance between two strings (how many changes turn one into the other)."""
    a, b = str(a), str(b)
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, 1):
        current = [i]
        for j, char_b in enumerate(b, 1):
            current.append(min(
                previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (char_a != char_b)
            ))
        previous = current
    return previous[-1]


def similarity(a, b):
    """How alike two strings are, from 0.0 to 1.0."""
    import difflib

    return difflib.SequenceMatcher(None, str(a), str(b)).ratio()


def closest_match(word, options):
    """The option most similar to ``word`` (or ``none``)."""
    import difflib

    found = difflib.get_close_matches(str(word), [str(o) for o in options], 1, 0.0)
    return found[0] if found else None


def random_string(length=12, alphabet=None):
    """Random text (letters and digits by default)."""
    import secrets
    import string

    alphabet = alphabet or (string.ascii_letters + string.digits)
    return "".join(secrets.choice(alphabet) for _ in range(length))


def random_token(nbytes=16):
    """Secure random token as hex text."""
    import secrets

    return secrets.token_hex(nbytes)


def random_password(length=16):
    """A strong random password."""
    import secrets
    import string

    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def regex_find_all(pattern, text, flags=0):
    """Every match of a regular expression (groups if the pattern has them)."""
    import re

    return re.findall(pattern, str(text), flags)


def regex_replace(pattern, replacement, text, flags=0):
    """Replace every match of a regular expression."""
    import re

    return re.sub(pattern, replacement, str(text), flags=flags)


def regex_split(pattern, text, flags=0):
    """Split text on a regular expression."""
    import re

    return re.split(pattern, str(text), flags=flags)


def regex_test(pattern, text, flags=0):
    """True if the regular expression matches anywhere in the text."""
    import re

    return re.search(pattern, str(text), flags) is not None


def regex_groups(pattern, text, flags=0):
    """Groups of the first match as a list (empty if it does not match)."""
    import re

    match = re.search(pattern, str(text), flags)
    return list(match.groups()) if match else []


def extract_numbers(text):
    """All numbers found in text: ``"a 3 b 4.5"`` -> ``[3, 4.5]``."""
    import re

    found = re.findall(r"-?\d+(?:\.\d+)?", str(text))
    return [float(n) if "." in n else int(n) for n in found]


def extract_emails(text):
    """All email addresses found in text."""
    import re

    return re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", str(text))


def extract_urls(text):
    """All http(s) links found in text."""
    import re

    return re.findall(r"https?://[^\s<>\"')]+", str(text))


def is_email(text):
    """True if the text looks like an email address."""
    import re

    return re.fullmatch(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", str(text)) is not None


def is_url(text):
    """True if the text looks like an http(s) link."""
    import re

    return re.fullmatch(r"https?://[^\s]+", str(text)) is not None


def number_format(value, decimals=2):
    """``number_format(1234567.891)`` -> ``"1,234,567.89"``."""
    return f"{value:,.{decimals}f}"


def ordinal(number):
    """``1`` -> ``"1st"``, ``2`` -> ``"2nd"``."""
    number = int(number)
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def pluralize(count, singular, plural=None):
    """``pluralize(2, "file")`` -> ``"2 files"``."""
    word = singular if count == 1 else (plural or singular + "s")
    return f"{count} {word}"


def human_size(nbytes):
    """``human_size(1536)`` -> ``"1.5 KB"``."""
    size = float(nbytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024 or unit == "TB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def human_duration(seconds):
    """``human_duration(3725)`` -> ``"1h 2m 5s"``."""
    seconds = int(seconds)
    parts = []
    for label, size in (("d", 86400), ("h", 3600), ("m", 60)):
        amount, seconds = divmod(seconds, size)
        if amount:
            parts.append(f"{amount}{label}")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def roman(number):
    """``roman(1994)`` -> ``"MCMXCIV"``."""
    result = ""
    for value, symbol in (
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
        (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ):
        count, number = divmod(number, value)
        result += symbol * count
    return result


# ---------------------------------------------------------------------------
# Math and statistics
# ---------------------------------------------------------------------------


def _math():
    import math

    return math


def sqrt(x):
    return _math().sqrt(x)


def floor(x):
    return _math().floor(x)


def ceil(x):
    return _math().ceil(x)


def trunc(x):
    return _math().trunc(x)


def log(x, base=None):
    """Natural logarithm (or logarithm in ``base``)."""
    return _math().log(x) if base is None else _math().log(x, base)


def log2(x):
    return _math().log2(x)


def log10(x):
    return _math().log10(x)


def exp(x):
    return _math().exp(x)


def sin(x):
    return _math().sin(x)


def cos(x):
    return _math().cos(x)


def tan(x):
    return _math().tan(x)


def asin(x):
    return _math().asin(x)


def acos(x):
    return _math().acos(x)


def atan(x):
    return _math().atan(x)


def atan2(y, x):
    return _math().atan2(y, x)


def radians(degrees_value):
    return _math().radians(degrees_value)


def degrees(radians_value):
    return _math().degrees(radians_value)


def hypot(*values):
    """Length of a vector: ``hypot(3, 4)`` -> ``5.0``."""
    return _math().hypot(*values)


def distance(a, b):
    """Distance between two points given as lists/tuples."""
    return _math().dist(a, b)


def gcd(*values):
    """Greatest common divisor."""
    return _math().gcd(*values)


def lcm(*values):
    """Least common multiple."""
    return _math().lcm(*values)


def factorial(n):
    return _math().factorial(n)


def isqrt(n):
    """Integer square root."""
    return _math().isqrt(n)


def combinations_count(n, k):
    """How many ways to choose ``k`` of ``n`` items."""
    return _math().comb(n, k)


def permutations_count(n, k=None):
    return _math().perm(n, k)


def combinations(items, size):
    """All ways to pick ``size`` items (order ignored), as a list of lists."""
    import itertools

    return [list(c) for c in itertools.combinations(items, size)]


def permutations(items, size=None):
    """All orderings of the items, as a list of lists."""
    import itertools

    return [list(p) for p in itertools.permutations(items, size)]


def cartesian_product(*lists):
    """Every combination with one item from each list."""
    import itertools

    return [list(p) for p in itertools.product(*lists)]


def is_close(a, b, tolerance=1e-9):
    """True if two floats are equal within ``tolerance``."""
    return _math().isclose(a, b, rel_tol=tolerance, abs_tol=tolerance)


def is_prime(n):
    """True if ``n`` is a prime number."""
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    divisor = 3
    while divisor * divisor <= n:
        if n % divisor == 0:
            return False
        divisor += 2
    return True


def primes(limit):
    """All prime numbers up to and including ``limit``."""
    if limit < 2:
        return []
    sieve = bytearray([1]) * (limit + 1)
    sieve[0:2] = b"\x00\x00"
    for number in range(2, int(limit ** 0.5) + 1):
        if sieve[number]:
            sieve[number * number::number] = bytearray(len(sieve[number * number::number]))
    return [n for n, flag in enumerate(sieve) if flag]


def prime_factors(n):
    """Prime factors of ``n`` in order: ``prime_factors(12)`` -> ``[2, 2, 3]``."""
    factors = []
    divisor = 2
    while divisor * divisor <= n:
        while n % divisor == 0:
            factors.append(divisor)
            n //= divisor
        divisor += 1
    if n > 1:
        factors.append(n)
    return factors


def fibonacci(count):
    """The first ``count`` Fibonacci numbers."""
    result, a, b = [], 0, 1
    for _ in range(count):
        result.append(a)
        a, b = b, a + b
    return result


def sign(x):
    """``-1``, ``0`` or ``1``."""
    return (x > 0) - (x < 0)


def lerp(start, end, amount):
    """Blend between two numbers: ``lerp(0, 10, 0.5)`` -> ``5.0``."""
    return start + (end - start) * amount


def map_range(value, in_min, in_max, out_min, out_max):
    """Re-scale a number from one range to another."""
    return out_min + (value - in_min) * (out_max - out_min) / (in_max - in_min)


def percent(part, whole, decimals=1):
    """``percent(1, 4)`` -> ``25.0``."""
    return round(part / whole * 100, decimals) if whole else 0.0


def mean(values):
    import statistics

    return statistics.fmean(values)


def median(values):
    import statistics

    return statistics.median(values)


def mode(values):
    import statistics

    return statistics.mode(values)


def stdev(values):
    """Sample standard deviation."""
    import statistics

    return statistics.stdev(values)


def variance(values):
    """Sample variance."""
    import statistics

    return statistics.variance(values)


def percentile(values, p):
    """The ``p``-th percentile (0-100) with linear interpolation."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile() needs at least one value")
    position = (len(ordered) - 1) * p / 100
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def random_bool(probability=0.5):
    """``true`` with the given probability."""
    return random.random() < probability


def random_gauss(mu=0.0, sigma=1.0):
    """A normally distributed random number."""
    return random.gauss(mu, sigma)


def random_seed(value=None):
    """Make later random numbers repeatable."""
    random.seed(value)


def random_color():
    """A random colour like ``"#a3f29c"``."""
    return "#%06x" % random.randrange(0x1000000)


def roll(dice="1d6"):
    """Roll dice written like ``"2d6"`` and return the total."""
    count, _, sides = str(dice).lower().partition("d")
    return sum(random.randint(1, int(sides or 6)) for _ in range(int(count or 1)))


def to_bool(value):
    """Read ``"yes"``, ``"true"``, ``"1"``, ``"on"`` (any case) as true."""
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on", "t")
    return bool(value)


def to_base(number, base):
    """Write an integer in another base (2-36): ``to_base(255, 16)`` -> ``"ff"``."""
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if number == 0:
        return "0"
    sign_text = "-" if number < 0 else ""
    number = abs(number)
    result = ""
    while number:
        number, remainder = divmod(number, base)
        result = digits[remainder] + result
    return sign_text + result


# ---------------------------------------------------------------------------
# Dates and time
# ---------------------------------------------------------------------------


def parse_time(text, fmt=None):
    """Read a date/time from text (ISO by default, or a ``strftime`` ``fmt``)."""
    if fmt:
        return datetime.strptime(text, fmt)
    return datetime.fromisoformat(text)


def add_days(moment, days):
    """``moment`` plus ``days`` days (negative to go back)."""
    from datetime import timedelta

    return moment + timedelta(days=days)


def add_time(moment, days=0, hours=0, minutes=0, seconds=0):
    """``moment`` plus any mix of days/hours/minutes/seconds."""
    from datetime import timedelta

    return moment + timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


def diff_days(later, earlier):
    """Whole days between two dates/times."""
    return (later - earlier).days


def diff_seconds(later, earlier):
    """Seconds between two dates/times."""
    return (later - earlier).total_seconds()


def weekday_name(moment=None):
    """``"Monday"``... for a date (default today)."""
    return (moment or datetime.now()).strftime("%A")


def month_name(moment=None):
    """``"January"``... for a date (default today)."""
    return (moment or datetime.now()).strftime("%B")


def is_leap_year(year):
    import calendar

    return calendar.isleap(year)


def days_in_month(year, month):
    import calendar

    return calendar.monthrange(year, month)[1]


def utc_now():
    """The current time in UTC."""
    from datetime import timezone

    return datetime.now(timezone.utc)


def from_timestamp(seconds):
    """Turn a Unix timestamp into a date/time."""
    return datetime.fromtimestamp(seconds)


def calendar_text(year=None, month=None):
    """A printable calendar for a month (default: this month)."""
    import calendar

    today_value = datetime.now()
    return calendar.month(year or today_value.year, month or today_value.month)


def time_ago(moment):
    """``"5 minutes ago"`` style text for a past date/time."""
    seconds = int((datetime.now() - moment).total_seconds())
    if seconds < 0:
        return "in the future"
    for label, size in (("year", 31536000), ("month", 2592000), ("day", 86400),
                        ("hour", 3600), ("minute", 60)):
        if seconds >= size:
            amount = seconds // size
            return f"{amount} {label}{'s' if amount != 1 else ''} ago"
    return "just now"


class _Stopwatch:
    """Returned by ``stopwatch()``: ``.elapsed()`` seconds, ``.reset()``."""

    def __init__(self):
        self.start = time.perf_counter()

    def elapsed(self):
        return time.perf_counter() - self.start

    def reset(self):
        self.start = time.perf_counter()

    def __repr__(self):
        return f"<stopwatch {self.elapsed():.3f}s>"


def stopwatch():
    """Start a stopwatch object."""
    return _Stopwatch()


# ---------------------------------------------------------------------------
# Files and folders
# ---------------------------------------------------------------------------


def file_size(path):
    """Size of a file in bytes."""
    return os.path.getsize(path)


def file_name(path):
    """``"a/b/c.txt"`` -> ``"c.txt"``."""
    return os.path.basename(path)


def file_stem(path):
    """``"a/b/c.txt"`` -> ``"c"``."""
    return os.path.splitext(os.path.basename(path))[0]


def file_ext(path):
    """``"a/b/c.txt"`` -> ``".txt"``."""
    return os.path.splitext(path)[1]


def parent_dir(path):
    """The folder containing ``path``."""
    return os.path.dirname(os.path.abspath(path))


def abs_path(path):
    """Full path (``~`` is expanded)."""
    return os.path.abspath(os.path.expanduser(path))


def home_dir():
    """The user's home folder."""
    return os.path.expanduser("~")


def temp_dir():
    """The system temporary folder."""
    import tempfile

    return tempfile.gettempdir()


def temp_file(suffix="", content=None):
    """Create a temporary file and return its path (optionally with text in it)."""
    import tempfile

    handle, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        if content is not None:
            stream.write(content)
    return path


def modified_time(path):
    """When a file was last changed, as a date/time."""
    return datetime.fromtimestamp(os.path.getmtime(path))


def touch(path):
    """Create an empty file or update its modified time."""
    from pathlib import Path

    Path(path).touch()
    return path


def delete_dir(path):
    """Delete a folder and everything in it."""
    shutil.rmtree(path)


def copy_dir(source, target):
    """Copy a whole folder."""
    shutil.copytree(source, target, dirs_exist_ok=True)


def rename(path, new_name):
    """Rename a file or folder in place; returns the new path."""
    target = os.path.join(os.path.dirname(path), new_name)
    os.rename(path, target)
    return target


def glob_files(pattern, recursive=True):
    """Paths matching a pattern such as ``"src/**/*.py"``."""
    import glob

    return sorted(glob.glob(pattern, recursive=recursive))


def walk_dir(path="."):
    """Every file under a folder (recursively), as a list of paths."""
    found = []
    for folder, _, names in os.walk(path):
        found.extend(os.path.join(folder, name) for name in names)
    return sorted(found)


def count_lines(path):
    """Number of lines in a text file."""
    with open(path, encoding="utf-8", errors="replace") as stream:
        return sum(1 for _ in stream)


def file_hash(path, algorithm="sha256"):
    """Hash of a file's contents as hex text."""
    digest = hashlib.new(algorithm)
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def zip_folder(folder, archive_path=None):
    """Zip a folder; returns the ``.zip`` path."""
    base = archive_path[:-4] if archive_path and archive_path.endswith(".zip") else (archive_path or folder)
    return shutil.make_archive(base, "zip", folder)


def unzip(archive_path, target="."):
    """Extract a ``.zip`` file into ``target``."""
    shutil.unpack_archive(archive_path, target)
    return target


def disk_usage(path="."):
    """``{"total": .., "used": .., "free": ..}`` in bytes."""
    usage = shutil.disk_usage(path)
    return {"total": usage.total, "used": usage.used, "free": usage.free}


def read_toml(path):
    """Read a ``.toml`` file into a dict."""
    import tomllib

    with open(path, "rb") as stream:
        return tomllib.load(stream)


def toml_parse(text):
    """Read TOML text into a dict."""
    import tomllib

    return tomllib.loads(text)


def read_ini(path):
    """Read an ``.ini`` file into ``{section: {key: value}}``."""
    import configparser

    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    return {name: dict(parser[name]) for name in parser.sections()}


def csv_parse(text, delimiter=","):
    """Read CSV text into a list of dicts (first row = column names)."""
    import io

    return list(csv.DictReader(io.StringIO(text), delimiter=delimiter))


def csv_stringify(rows, delimiter=","):
    """Turn a list of dicts (or lists) into CSV text."""
    import io

    buffer = io.StringIO()
    rows = list(rows)
    if rows and isinstance(rows[0], dict):
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)
    else:
        csv.writer(buffer, delimiter=delimiter).writerows(rows)
    return buffer.getvalue()


def sqlite_query(path, sql, params=()):
    """Run an SQL query on a SQLite file; returns rows as a list of dicts."""
    import sqlite3

    connection = sqlite3.connect(path)
    try:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(sql, tuple(params)).fetchall()
        connection.commit()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def sqlite_exec(path, sql, params=()):
    """Run an SQL statement (INSERT/CREATE...); returns the number of rows changed."""
    import sqlite3

    connection = sqlite3.connect(path)
    try:
        cursor = connection.execute(sql, tuple(params))
        connection.commit()
        return cursor.rowcount
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Hashing, encoding and compression
# ---------------------------------------------------------------------------


def _bytes(value):
    return value if isinstance(value, (bytes, bytearray)) else str(value).encode("utf-8")


def sha1(text):
    return hashlib.sha1(_bytes(text)).hexdigest()


def sha512(text):
    return hashlib.sha512(_bytes(text)).hexdigest()


def hmac_sha256(key, message):
    """Keyed hash used to sign messages."""
    import hmac

    return hmac.new(_bytes(key), _bytes(message), hashlib.sha256).hexdigest()


def crc32(text):
    import zlib

    return zlib.crc32(_bytes(text))


def hex_encode(text):
    return _bytes(text).hex()


def hex_decode(text):
    return bytes.fromhex(text).decode("utf-8")


def base32_encode(text):
    return base64.b32encode(_bytes(text)).decode("ascii")


def base32_decode(text):
    return base64.b32decode(text).decode("utf-8")


def compress(text):
    """Compress text/bytes with zlib; returns bytes."""
    import zlib

    return zlib.compress(_bytes(text))


def decompress(data):
    """Reverse of ``compress``; returns text."""
    import zlib

    return zlib.decompress(data).decode("utf-8")


def rot13(text):
    import codecs

    return codecs.encode(str(text), "rot13")


def url_parse(url):
    """Split a URL into ``{"scheme", "host", "port", "path", "query", "fragment"}``."""
    from urllib.parse import parse_qs, urlparse

    parts = urlparse(url)
    return {
        "scheme": parts.scheme, "host": parts.hostname, "port": parts.port,
        "path": parts.path, "query": {k: v[0] if len(v) == 1 else v for k, v in parse_qs(parts.query).items()},
        "fragment": parts.fragment,
    }


def url_join(base, *parts):
    """Join URL pieces: ``url_join("https://a.com/x/", "y")``."""
    from urllib.parse import urljoin

    for part in parts:
        base = urljoin(base, part)
    return base


def query_string(params):
    """``{"a": 1, "b": "x y"}`` -> ``"a=1&b=x+y"``."""
    from urllib.parse import urlencode

    return urlencode(params)


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------


def http_json(url, **kwargs):
    """GET a URL and parse the reply as JSON."""
    return json.loads(http_get(url, **kwargs).text)


def dns_lookup(host):
    """IP address for a host name."""
    import socket

    return socket.gethostbyname(host)


def local_ip():
    """This computer's LAN address."""
    import socket

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def port_open(host, port, timeout=1.0):
    """True if something accepts connections on ``host:port``."""
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def is_online(timeout=2.0):
    """True if the internet looks reachable."""
    return port_open("1.1.1.1", 53, timeout)


# ---------------------------------------------------------------------------
# System, terminal and logging
# ---------------------------------------------------------------------------


def os_name():
    """``"windows"``, ``"linux"`` or ``"mac"``."""
    return {"win32": "windows", "darwin": "mac"}.get(sys.platform, "linux")


def hostname():
    import socket

    return socket.gethostname()


def username():
    import getpass

    return getpass.getuser()


def cpu_count():
    return os.cpu_count() or 1


def pid():
    return os.getpid()


def python_version():
    return sys.version.split()[0]


def env_set(name, value):
    """Set an environment variable for this program and its children."""
    os.environ[name] = str(value)
    return value


def env_all():
    """All environment variables as a dict."""
    return dict(os.environ)


def which(program):
    """Full path of a program on the PATH, or ``none``."""
    return shutil.which(program)


def clear_screen():
    """Clear the terminal."""
    os.system("cls" if os.name == "nt" else "clear")


def get_password(prompt="Password: "):
    """Read input without echoing it."""
    import getpass

    return getpass.getpass(prompt)


def read_int(prompt="", default=None):
    """Keep asking until the user types a whole number."""
    while True:
        text = input(prompt)
        if not text.strip() and default is not None:
            return default
        try:
            return int(text)
        except ValueError:
            print("Please enter a whole number.")


def read_float(prompt="", default=None):
    """Keep asking until the user types a number."""
    while True:
        text = input(prompt)
        if not text.strip() and default is not None:
            return default
        try:
            return float(text)
        except ValueError:
            print("Please enter a number.")


def confirm(prompt="Continue?", default=False):
    """Ask yes/no in the terminal."""
    hint = "Y/n" if default else "y/N"
    answer = input(f"{prompt} [{hint}] ").strip().lower()
    return default if not answer else answer in ("y", "yes")


def choose(prompt, options):
    """Show a numbered menu in the terminal and return the picked option."""
    options = list(options)
    for number, option in enumerate(options, 1):
        print(f"  {number}. {option}")
    while True:
        text = input(f"{prompt} ").strip()
        if text.isdigit() and 1 <= int(text) <= len(options):
            return options[int(text) - 1]
        print(f"Enter a number from 1 to {len(options)}.")


_COLORS = {
    "black": 30, "red": 31, "green": 32, "yellow": 33, "blue": 34,
    "magenta": 35, "cyan": 36, "white": 37, "gray": 90,
}


def colorize(text, color="green", bold=False):
    """Wrap text in terminal colour codes (``print`` the result)."""
    code = _COLORS.get(color)
    if code is None:
        raise ValueError(f"unknown colour {color!r}; use one of {', '.join(_COLORS)}")
    if os.name == "nt":
        os.system("")
    return f"\033[{'1;' if bold else ''}{code}m{text}\033[0m"


def progress_bar(done, total, width=30):
    """A text bar such as ``[#####-----] 50%``."""
    fraction = 0 if not total else min(max(done / total, 0), 1)
    filled = int(width * fraction)
    return f"[{'#' * filled}{'-' * (width - filled)}] {int(fraction * 100)}%"


def table(rows, headers=None):
    """Format rows (lists or dicts) as an aligned text table."""
    rows = list(rows)
    if rows and isinstance(rows[0], dict):
        headers = headers or list(rows[0])
        rows = [[row.get(h, "") for h in headers] for row in rows]
    body = [[str(cell) for cell in row] for row in rows]
    if headers:
        body.insert(0, [str(h) for h in headers])
    if not body:
        return ""
    widths = [max(len(row[i]) for row in body if i < len(row)) for i in range(max(map(len, body)))]
    lines_out = ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip() for row in body]
    if headers:
        lines_out.insert(1, "  ".join("-" * width for width in widths))
    return "\n".join(lines_out)


def print_table(rows, headers=None):
    """Print rows as an aligned text table."""
    print(table(rows, headers))


def _log(level, *messages):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} [{level}]", *messages)


def log_info(*messages):
    """Print a timestamped INFO line."""
    _log("INFO", *messages)


def log_warn(*messages):
    """Print a timestamped WARN line."""
    _log("WARN", *messages)


def log_error(*messages):
    """Print a timestamped ERROR line to the error stream."""
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} [ERROR]", *messages, file=sys.stderr)


def clipboard_get():
    """Text currently on the clipboard."""
    import tkinter

    root = tkinter.Tk()
    root.withdraw()
    try:
        return root.clipboard_get()
    except tkinter.TclError:
        return ""
    finally:
        root.destroy()


def clipboard_set(text):
    """Put text on the clipboard."""
    import tkinter

    root = tkinter.Tk()
    root.withdraw()
    root.clipboard_clear()
    root.clipboard_append(str(text))
    root.update()
    root.destroy()
    return text


def beep():
    """Make a short sound."""
    print("\a", end="", flush=True)


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

FUNCTIONS.update(
    {
        function.__name__: function
        for function in (
            # lists, dicts and collections
            first, last, take, drop, chunk, flatten, flat_map, unique, compact,
            group_by, count_by, partition, pluck, sort_by, min_by, max_by, sum_by,
            find, find_index, every, some, count_if, reduce, accumulate, product,
            zip_dict, pairwise, sliding_window, rotate, transpose, repeat,
            index_of, union, intersection, difference, counter, most_common,
            sample, merge, deep_merge, pick, omit, invert, map_values, map_keys,
            filter_dict, get_path, set_path,
            # functional helpers
            compose, pipe, partial, identity, constant, noop, tap, once, default,
            measure, benchmark, parallel_map, run_in_thread, every_seconds,
            # type checks
            type_name, is_number, is_string, is_list, is_dict, is_none, is_empty,
            is_numeric_string,
            # strings and text
            snake_case, kebab_case, camel_case, pascal_case, title_case, slugify,
            truncate, pad_left, pad_right, center_text, words, lines, is_blank,
            reverse, is_palindrome, count_words, remove_prefix, remove_suffix,
            wrap_text, indent_text, dedent_text, strip_html, html_escape,
            html_unescape, levenshtein, similarity, closest_match, random_string,
            random_token, random_password, regex_find_all, regex_replace,
            regex_split, regex_test, regex_groups, extract_numbers,
            extract_emails, extract_urls, is_email, is_url, number_format,
            ordinal, pluralize, human_size, human_duration, roman,
            # math and statistics
            sqrt, floor, ceil, trunc, log, log2, log10, exp, sin, cos, tan, asin,
            acos, atan, atan2, radians, degrees, hypot, distance, gcd, lcm,
            factorial, isqrt, combinations_count, permutations_count,
            combinations, permutations, cartesian_product, is_close, is_prime,
            primes, prime_factors, fibonacci, sign, lerp, map_range, percent,
            mean, median, mode, stdev, variance, percentile, random_bool,
            random_gauss, random_seed, random_color, roll, to_bool, to_base,
            # dates and time
            parse_time, add_days, add_time, diff_days, diff_seconds, weekday_name,
            month_name, is_leap_year, days_in_month, utc_now, from_timestamp,
            calendar_text, time_ago, stopwatch,
            # files, folders and data formats
            file_size, file_name, file_stem, file_ext, parent_dir, abs_path,
            home_dir, temp_dir, temp_file, modified_time, touch, delete_dir,
            copy_dir, rename, glob_files, walk_dir, count_lines, file_hash,
            zip_folder, unzip, disk_usage, read_toml, toml_parse, read_ini,
            csv_parse, csv_stringify, sqlite_query, sqlite_exec,
            # hashing, encoding, compression and URLs
            sha1, sha512, hmac_sha256, crc32, hex_encode, hex_decode,
            base32_encode, base32_decode, compress, decompress, rot13,
            url_parse, url_join, query_string,
            # network
            http_json, dns_lookup, local_ip, port_open, is_online,
            # system, terminal and logging
            os_name, hostname, username, cpu_count, pid, python_version,
            env_set, env_all, which, clear_screen, get_password, read_int,
            read_float, confirm, choose, colorize, progress_bar, table,
            print_table, log_info, log_warn, log_error, clipboard_get,
            clipboard_set, beep,
        )
    }
)

# Handy constants.
FUNCTIONS.update(
    {"pi": 3.141592653589793, "tau": 6.283185307179586, "inf": float("inf"),
     "nan": float("nan")}
)


def list_builtins():
    """Return the sorted names of all VirtoLang-specific built-in functions."""
    return sorted(FUNCTIONS)


FUNCTIONS["list_builtins"] = list_builtins
