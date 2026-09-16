"""Key-gated conversation UI for the encryption workspace."""

import tkinter as tk
from tkinter import ttk

from .key_dialog import ask_key

from .chat_store import ChatStore, default_chat_directory, run_command


HELP = "-e selects Encrypt; -d selects Decrypt. The mode stays active for following messages.\n-help shows commands; -lock locks this session. Enter sends; Shift+Enter adds a line."
VARIANTS = {"As-is (session only)": "as_is", "Portable OC1": "oc1"}


class CryptoChat:
    def __init__(self, app):
        self.app = app
        self.store = ChatStore(default_chat_directory())
        self.session = None
        self.key = None
        self.messages = []
        self.ids = []
        self.status = tk.StringVar(master=app, value="Create or open a conversation")
        self.variant = tk.StringVar(master=app, value="As-is (session only)")
        self.operation = "encrypt"
        self.mode_label = tk.StringVar(master=app, value="Encrypt mode")

    def build(self, parent):
        page = tk.Frame(parent, bg=self.app.BG)
        page.grid_columnconfigure(1, weight=1)
        page.grid_rowconfigure(0, weight=1)
        sidebar = tk.Frame(page, bg=self.app.PANEL, padx=12, pady=12)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.app._button(sidebar, "New conversation", self.new).pack(fill="x")
        self.sessions = tk.Listbox(sidebar, width=23, bg=self.app.FIELD, fg=self.app.TEXT,
                                   selectbackground=self.app.ACCENT, exportselection=False)
        self.sessions.pack(fill="both", expand=True, pady=12)
        self.sessions.bind("<<ListboxSelect>>", self.open_selected)
        self.app._button(sidebar, "Open / unlock", self.open_selected, secondary=True).pack(fill="x")
        self.app._button(sidebar, "Lock", self.lock, secondary=True).pack(fill="x", pady=(8, 0))
        body = tk.Frame(page, bg=self.app.PANEL, padx=16, pady=12)
        body.grid(row=0, column=1, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)
        tk.Label(body, textvariable=self.status, bg=self.app.PANEL, fg=self.app.MUTED,
                 anchor="w", wraplength=480).grid(row=0, column=0, sticky="ew", pady=(0, 10))
        transcript = tk.Frame(body, bg=self.app.PANEL)
        transcript.grid(row=1, column=0, sticky="nsew")
        self.history = tk.Canvas(transcript, bg=self.app.PANEL, highlightthickness=0)
        self.bubbles = tk.Frame(self.history, bg=self.app.PANEL)
        self.bubble_window = self.history.create_window(0, 0, window=self.bubbles, anchor="nw")
        self.bubble_widgets = []
        self.history.bind("<Configure>", self.resize_bubbles)
        self.bubbles.bind("<Configure>", lambda _event: self.history.configure(scrollregion=self.history.bbox("all")))
        self.history.bind("<MouseWheel>", self.scroll_history)
        self.history.pack(side="left", fill="both", expand=True)
        scroll = tk.Scrollbar(transcript, command=self.history.yview)
        scroll.pack(side="right", fill="y")
        self.history.configure(yscrollcommand=scroll.set)
        controls = tk.Frame(body, bg=self.app.PANEL)
        controls.grid(row=2, column=0, sticky="ew", pady=10)
        selector = ttk.Combobox(controls, textvariable=self.variant, values=tuple(VARIANTS),
                                state="readonly", style="Cipher.TCombobox", width=24)
        selector.pack(side="left")
        tk.Label(controls, textvariable=self.mode_label, bg=self.app.PANEL,
                 fg=self.app.MUTED).pack(side="right")
        self.composer = self.app._text_box(body)
        self.composer.configure(height=3, undo=False)
        self.composer.grid(row=3, column=0, sticky="ew")
        self.composer.bind("<Return>", self._return)
        actions = tk.Frame(body, bg=self.app.PANEL)
        actions.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self.app._button(actions, "Send", self.send).pack(side="right")
        self.app._button(actions, "Copy latest", self.copy_latest, secondary=True).pack(side="right", padx=8)
        self.lock()
        self.refresh()
        return page

    def refresh(self):
        try:
            self.ids = self.store.sessions()
        except OSError as error:
            self.status.set(f"Cannot read conversations: {error}")
            return
        self.sessions.delete(0, "end")
        for identifier in self.ids:
            self.sessions.insert("end", f"Conversation {identifier[:8]}")
        if self.session in self.ids:
            index = self.ids.index(self.session)
            self.sessions.selection_set(index)
            self.sessions.see(index)

    def enter(self):
        if not self.ids:
            self.new()

    def new(self):
        self.lock()
        key = ask_key(self.app, "New conversation", "Choose a key with at least 8 characters to protect this conversation.")
        if key is None:
            return
        if len(key) < 8:
            self.status.set("Use a key with at least 8 characters")
            return
        confirmation = ask_key(self.app, "Confirm your key", "Type your key again to make sure it matches.", "Create conversation")
        if confirmation is None:
            return
        if confirmation != key:
            self.status.set("Keys do not match. Create the conversation again.")
            return
        try:
            session = self.store.create(key)
        except (OSError, ValueError) as error:
            self.status.set(f"Could not create conversation: {error}")
            return
        self.activate(session, key, [])
        self.refresh()

    def open_selected(self, _event=None):
        selection = self.sessions.curselection()
        if not selection:
            return
        session = self.ids[selection[0]]
        if session == self.session and self.key is not None:
            return
        self.lock()
        key = ask_key(self.app, "Unlock conversation", "Enter your key to open this private conversation.", "Unlock")
        if key is None:
            return
        try:
            messages = self.store.open(session, key)
        except (OSError, ValueError) as error:
            self.status.set(f"Could not unlock: {error}")
            return
        self.activate(session, key, messages)

    def activate(self, session, key, messages):
        self.session, self.key, self.messages = session, key, messages
        self.set_mode("encrypt")
        self.composer.configure(state="normal")
        self.status.set(f"Conversation {session[:8]} / unlocked")
        self.render()
        self.focus()

    def lock(self):
        self.session = None
        self.key = None
        self.messages = []
        self.set_mode("encrypt")
        self.clear_bubbles()
        self.composer.configure(state="normal")
        self.composer.delete("1.0", "end")
        self.composer.edit_reset()
        self.composer.configure(state="disabled")
        self.status.set("Locked / select a conversation to unlock, or create a new one")

    def clear_bubbles(self):
        for child in self.bubbles.winfo_children():
            child.destroy()
        self.bubble_widgets = []
        self.history.configure(scrollregion=(0, 0, 0, 0))

    def render(self):
        self.clear_bubbles()
        for item in self.messages:
            row = tk.Frame(self.bubbles, bg=self.app.PANEL)
            row.pack(fill="x", pady=6, padx=12)
            bubble = tk.Label(row, text=item["text"], bg=self.app.FIELD, fg=self.app.TEXT,
                              justify="left", anchor="w", padx=14, pady=10,
                              font=("Cascadia Mono", self.app.editor_font_size.get()),
                              cursor="hand2")
            bubble.pack(side="left" if item["operation"] == "decrypt" else "right")
            bubble.bind("<Button-1>", lambda _event, text=item["text"]: self.copy_message(text))
            bubble.bind("<MouseWheel>", self.scroll_history)
            row.bind("<MouseWheel>", self.scroll_history)
            self.bubble_widgets.append(bubble)
        self.resize_bubbles()
        self.history.update_idletasks()
        self.history.configure(scrollregion=self.history.bbox("all"))
        self.history.yview_moveto(1.0)

    def resize_bubbles(self, _event=None):
        width = max(1, self.history.winfo_width())
        self.history.itemconfigure(self.bubble_window, width=width)
        for bubble in self.bubble_widgets:
            bubble.configure(wraplength=max(80, int(width * 0.75) - 52))

    def scroll_history(self, event):
        self.history.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def copy_message(self, text):
        self.app.clipboard_clear()
        self.app.clipboard_append(text)
        self.status.set("Message copied")

    def set_mode(self, operation):
        self.operation = operation
        self.mode_label.set(f"{operation.capitalize()} mode")

    def send(self):
        if self.key is None:
            self.status.set("Unlock or create a conversation first")
            return
        command = self.app._get(self.composer)
        if command.strip() in {"-e", "-d"}:
            self.set_mode("encrypt" if command.strip() == "-e" else "decrypt")
            self.status.set(self.mode_label.get())
            self.composer.delete("1.0", "end")
            self.composer.edit_reset()
            return
        if command.strip() == "-lock":
            self.lock()
            return
        if command.strip() == "-help":
            self.status.set(HELP)
            self.composer.delete("1.0", "end")
            return
        parts = command.rstrip().rsplit(maxsplit=1)
        if len(parts) == 2 and parts[1] in {"-e", "-d"}:
            self.set_mode("encrypt" if parts[1] == "-e" else "decrypt")
        try:
            message = run_command(command, self.key, VARIANTS[self.variant.get()], self.messages,
                                  mode=self.operation)
            messages = [*self.messages, message]
            self.store.save(self.session, self.key, messages)
        except (OSError, ValueError) as error:
            self.status.set(str(error))
            return
        self.messages = messages
        self.composer.delete("1.0", "end")
        self.composer.edit_reset()
        self.render()
        if message["operation"] == "encrypt" and message.get("variant") == "as_is":
            self.status.set(f"Saved / {len(message['text'])} characters / this conversation only")
        else:
            self.status.set("Encrypted and saved" if message["operation"] == "encrypt" else "Decrypted / history saved encrypted")

    def _return(self, event):
        if event.state & 0x1:
            return None
        self.send()
        return "break"

    def copy_latest(self):
        if self.messages:
            self.copy_message(self.messages[-1]["text"])

    def focus(self):
        (self.composer if self.key is not None else self.sessions).focus_set()
