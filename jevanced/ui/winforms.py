"""The jevanced window (Windows Forms, via IronPython).

This file only draws what ``JevancedApp.view()`` returns and forwards
button presses to the app, so the behaviour behind it is unit-tested
without Windows. The window was checked in Razor Enhanced 1.0.0.14.

The window runs on its own STA thread; Razor Enhanced's script thread
stays free to run the game loop.
"""

import threading

import clr

clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")

from System.Drawing import Color, Font, FontStyle, Point, Size  # noqa: E402
from System.Threading import ApartmentState, Thread, ThreadStart  # noqa: E402
from System.Windows.Forms import (  # noqa: E402
    AnchorStyles,
    Application,
    Button,
    CheckBox,
    FlatStyle,
    Form,
    FormStartPosition,
    Label,
    MethodInvoker,
    NumericUpDown,
    ScrollBars,
    TextBox,
    Timer,
)

REFRESH_MS = 300
WIDTH = 480

RED = Color.FromArgb(200, 30, 30)
DARK_RED = Color.FromArgb(120, 40, 40)
GREEN = Color.FromArgb(30, 130, 60)
AMBER = Color.FromArgb(170, 110, 0)
GREY = Color.FromArgb(90, 90, 90)


def _label(parent, text, x, y, w, h=20, bold=False, size=9.0):
    label = Label()
    label.Text = text
    label.Location = Point(x, y)
    label.Size = Size(w, h)
    label.Font = Font("Segoe UI", size, FontStyle.Bold if bold else FontStyle.Regular)
    parent.Controls.Add(label)
    return label


def _button(parent, text, x, y, w, h, handler):
    button = Button()
    button.Text = text
    button.Location = Point(x, y)
    button.Size = Size(w, h)
    button.Click += handler
    parent.Controls.Add(button)
    return button


class JevancedForm(Form):
    def __init__(self, app):
        self.app = app
        # Setting up the checkboxes fires their change events; ignore those
        # until every control exists.
        self._syncing = True
        self._last_log = None

        self.Text = "jevanced"
        self.ClientSize = Size(WIDTH, 640)
        self.MinimumSize = Size(WIDTH + 16, 520)
        self.StartPosition = FormStartPosition.CenterScreen
        self.TopMost = True  # keep the kill switch visible over the client

        pad = 12
        inner = WIDTH - 2 * pad

        # Kill switch: always at the top, always clickable.
        self.stop_button = _button(self, "STOP", pad, pad, inner, 64, self._on_stop)
        self.stop_button.Font = Font("Segoe UI", 20.0, FontStyle.Bold)
        self.stop_button.ForeColor = Color.White
        self.stop_button.FlatStyle = FlatStyle.Flat
        self.stop_button.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right

        y = pad + 72
        self.start_button = _button(self, "Start", pad, y, 110, 32, self._on_start)
        self.status_label = _label(self, "Idle", pad + 120, y, inner - 120, 18, bold=True, size=10.0)
        self.detail_label = _label(self, "", pad + 120, y + 18, inner - 120, 34, size=8.5)
        self.detail_label.ForeColor = GREY

        y += 58
        _label(self, "Jev API key", pad, y, inner, 18, bold=True)
        y += 20
        self.key_box = TextBox()
        self.key_box.Location = Point(pad, y)
        self.key_box.Size = Size(inner - 170, 24)
        self.key_box.UseSystemPasswordChar = True
        self.Controls.Add(self.key_box)
        self.save_key_button = _button(self, "Save key", pad + inner - 164, y - 1, 80, 26, self._on_save_key)
        self.clear_key_button = _button(self, "Remove", pad + inner - 80, y - 1, 80, 26, self._on_clear_key)
        y += 28
        self.key_display = _label(self, "", pad, y, inner, 18)
        self.key_message = _label(self, "", pad, y + 18, inner, 34, size=8.5)
        self.key_message.ForeColor = GREY

        y += 58
        _label(self, "Options", pad, y, inner, 18, bold=True)
        y += 20
        self.dry_run_box = self._checkbox("Dry run: log what Jev chooses, don't do it", pad, y, inner)
        y += 22
        self.speech_box = self._checkbox("Allow Jev to speak in game chat", pad, y, inner)
        y += 22
        self.top_box = self._checkbox("Keep this window on top", pad, y, inner)
        self.top_box.Checked = True
        y += 26
        _label(self, "Pause between decisions (ms)", pad, y + 2, 200)
        self.tick_box = NumericUpDown()
        self.tick_box.Location = Point(pad + 205, y)
        self.tick_box.Size = Size(90, 24)
        self.tick_box.Minimum = 250
        self.tick_box.Maximum = 60000
        self.tick_box.Increment = 250
        self.tick_box.ValueChanged += self._on_options
        self.Controls.Add(self.tick_box)

        y += 34
        self.stats_label = _label(self, "", pad, y, inner, 36, size=8.5)
        y += 40
        self.log_box = TextBox()
        self.log_box.Multiline = True
        self.log_box.ReadOnly = True
        self.log_box.ScrollBars = ScrollBars.Vertical
        self.log_box.Font = Font("Consolas", 8.5)
        self.log_box.Location = Point(pad, y)
        self.log_box.Size = Size(inner, 640 - y - pad)
        self.log_box.Anchor = (AnchorStyles.Top | AnchorStyles.Bottom
                               | AnchorStyles.Left | AnchorStyles.Right)
        self.Controls.Add(self.log_box)

        self.FormClosing += self._on_closing
        self.timer = Timer()
        self.timer.Interval = REFRESH_MS
        self.timer.Tick += self._on_tick
        self._syncing = False
        self.refresh_view()
        self.timer.Start()

    def _checkbox(self, text, x, y, w):
        box = CheckBox()
        box.Text = text
        box.Location = Point(x, y)
        box.Size = Size(w, 20)
        box.CheckedChanged += self._on_options
        self.Controls.Add(box)
        return box

    # ---- events ----------------------------------------------------------

    def _on_stop(self, sender, args):
        self.app.stop("Kill switch pressed")
        self.refresh_view()

    def _on_start(self, sender, args):
        self.app.request_start()
        self.refresh_view()

    def _on_save_key(self, sender, args):
        self.app.save_key(self.key_box.Text)
        # Never keep the key in the window once it's been handed over.
        self.key_box.Text = ""
        self.refresh_view()

    def _on_clear_key(self, sender, args):
        self.app.clear_key()
        self.refresh_view()

    def _on_options(self, sender, args):
        if self._syncing:
            return
        self.TopMost = self.top_box.Checked
        self.app.update_settings(
            dry_run=self.dry_run_box.Checked,
            allow_speech=self.speech_box.Checked,
            tick_interval_ms=int(self.tick_box.Value),
        )

    def _on_tick(self, sender, args):
        try:
            self.refresh_view()
        except Exception:
            pass

    def _on_closing(self, sender, args):
        self.timer.Stop()
        self.app.request_shutdown()

    # ---- drawing ---------------------------------------------------------

    def refresh_view(self):
        view = self.app.view()
        running = view["running"]

        self.stop_button.BackColor = RED if view["can_stop"] else DARK_RED
        self.start_button.Enabled = view["can_start"]
        self.status_label.Text = view["status_text"]
        if running:
            self.status_label.ForeColor = AMBER if view["dry_run"] else GREEN
        elif view["status"] == "error":
            self.status_label.ForeColor = RED
        else:
            self.status_label.ForeColor = GREY
        self.detail_label.Text = view["detail"]

        self.key_display.Text = "Saved key: " + view["key_display"]
        self.key_message.ForeColor = RED if view["key_error"] else GREY
        self.key_message.Text = view["key_message"]

        self._syncing = True
        try:
            if self.dry_run_box.Checked != view["dry_run"]:
                self.dry_run_box.Checked = view["dry_run"]
            if self.speech_box.Checked != view["allow_speech"]:
                self.speech_box.Checked = view["allow_speech"]
            if int(self.tick_box.Value) != view["tick_interval_ms"]:
                self.tick_box.Value = view["tick_interval_ms"]
        finally:
            self._syncing = False

        self.stats_label.Text = "Decided by: {0}\nDecisions: {1}   Last: {2}".format(
            view["backend"] or "-", view["ticks"], view["last_action"] or "-")

        lines = view["log"]
        marker = (len(lines), lines[-1] if lines else "")
        if marker != self._last_log:
            self._last_log = marker
            self.log_box.Text = "\r\n".join(lines)
            self.log_box.SelectionStart = len(self.log_box.Text)
            self.log_box.ScrollToCaret()


class WindowHandle(object):
    def __init__(self, form, thread):
        self.form = form
        self.thread = thread

    def close(self):
        form = self.form
        if form is None or form.IsDisposed or not form.IsHandleCreated:
            return
        try:
            form.BeginInvoke(MethodInvoker(form.Close))
        except Exception:
            pass


def start_window(app, timeout_s=10.0):
    """Open the window on its own STA thread and return a handle to it."""
    holder = {}
    ready = threading.Event()

    def run():
        try:
            try:
                Application.EnableVisualStyles()
            except Exception:
                pass
            form = JevancedForm(app)
            holder["form"] = form
        except Exception as exc:
            holder["error"] = exc
            ready.set()
            return
        ready.set()
        Application.Run(form)

    thread = Thread(ThreadStart(run))
    thread.SetApartmentState(ApartmentState.STA)
    thread.IsBackground = True
    thread.Start()
    ready.wait(timeout_s)
    if "error" in holder:
        raise holder["error"]
    if "form" not in holder:
        raise RuntimeError("The jevanced window didn't open.")
    return WindowHandle(holder.get("form"), thread)
