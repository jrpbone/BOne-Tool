"""Reusable theme-aware modal for conversation keys."""

import tkinter as tk


class KeyDialog(tk.Toplevel):
    def __init__(self, app, title: str, prompt: str, action: str = "Continue"):
        super().__init__(app)
        self.withdraw()
        self.app = app
        self.result = None
        self.title(title)
        self.transient(app)
        self.resizable(False, False)
        self.configure(bg=app.BG)
        self.protocol("WM_DELETE_WINDOW", self.cancel)

        tk.Frame(self, bg=app.ACCENT, height=4).pack(fill="x")
        content = tk.Frame(self, bg=app.BG, padx=28, pady=24)
        content.pack(fill="both", expand=True)
        tk.Label(content, text="PRIVATE CONVERSATION", bg=app.BG, fg=app.ACCENT,
                 font=("Segoe UI Semibold", 9)).pack(anchor="w")
        tk.Label(content, text=title, bg=app.BG, fg=app.TEXT,
                 font=("Segoe UI Semibold", 21)).pack(anchor="w", pady=(8, 8))
        tk.Label(content, text=prompt, bg=app.BG, fg=app.MUTED,
                 font=("Segoe UI", 10), wraplength=380, justify="left").pack(anchor="w", pady=(0, 20))
        field = tk.Frame(content, bg=app.FIELD, padx=12, pady=10,
                         highlightthickness=1, highlightbackground=app.BORDER)
        field.pack(fill="x")
        self.entry = tk.Entry(field, show="*", bg=app.FIELD, fg=app.TEXT,
                              insertbackground=app.ACCENT, relief="flat", width=27,
                              selectbackground=app.SELECTION, selectforeground=app.TEXT,
                              font=("Cascadia Mono", 12))
        self.entry.pack(side="left", fill="x", expand=True)
        self.reveal = app._button(field, "Show", self.toggle_visibility, secondary=True)
        self.reveal.pack(side="right", padx=(8, 0))
        self.error = tk.StringVar(master=self)
        tk.Label(content, textvariable=self.error, bg=app.BG, fg=app.ERROR,
                 font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(8, 12))
        actions = tk.Frame(content, bg=app.BG)
        actions.pack(fill="x")
        app._button(actions, action, self.submit).pack(side="right")
        app._button(actions, "Cancel", self.cancel, secondary=True).pack(side="right", padx=8)
        self.bind("<Return>", lambda _event: self.submit())
        self.bind("<Escape>", lambda _event: self.cancel())

    def toggle_visibility(self):
        hidden = self.entry.cget("show") == "*"
        self.entry.configure(show="" if hidden else "*")
        self.reveal.configure(text="Hide" if hidden else "Show")

    def submit(self):
        value = self.entry.get()
        if not value:
            self.error.set("Enter your conversation key.")
            self.entry.focus_set()
            return
        self.result = value
        self.entry.delete(0, "end")
        self.destroy()

    def cancel(self):
        self.result = None
        self.entry.delete(0, "end")
        self.destroy()

    def show(self):
        self.update_idletasks()
        width, height = self.winfo_reqwidth(), self.winfo_reqheight()
        x = self.app.winfo_rootx() + (self.app.winfo_width() - width) // 2
        y = self.app.winfo_rooty() + (self.app.winfo_height() - height) // 2
        x = max(0, min(x, self.winfo_screenwidth() - width))
        y = max(0, min(y, self.winfo_screenheight() - height))
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.wait_visibility()
        self.grab_set()
        self.entry.focus_set()
        self.wait_window()
        return self.result


def ask_key(app, title: str, prompt: str, action: str = "Continue") -> str | None:
    return KeyDialog(app, title, prompt, action).show()
