"""Hash processing and self-contained workspace controller."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import hashlib
import hmac
from tkinterdnd2 import DND_FILES

if TYPE_CHECKING:
    from main import BOneTool


ALGORITHMS = ("sha256", "sha512", "sha3_256", "sha3_512", "blake2b", "blake2s", "sha1", "md5")


def hash_text(text: str, algorithm: str) -> str:
    return hashlib.new(algorithm, text.encode("utf-8")).hexdigest()


def hash_file(path: str | Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class HashFeature:
    page_id = "hash"
    title = "Hash"

    def __init__(self, app: "BOneTool") -> None:
        self.app = app
        self.algorithm = tk.StringVar(master=app, value="sha256")
        self.hash_count = tk.StringVar(master=app, value="0 characters / 0 bytes")
        self.hash_status = tk.StringVar(master=app, value="Ready")
        self.verify_value = tk.StringVar(master=app)

    def build(self, parent: tk.Widget) -> tk.Frame:
        page = tk.Frame(parent, bg=self.app.BG)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        algorithm_card = tk.Frame(page, bg=self.app.PANEL, padx=20, pady=14)
        algorithm_card.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        tk.Label(
            algorithm_card, text="ALGORITHM", bg=self.app.PANEL, fg=self.app.MUTED,
            font=("Segoe UI Semibold", 9),
        ).grid(row=0, column=0, sticky="w", padx=(0, 18))
        algorithm = ttk.Combobox(
            algorithm_card, textvariable=self.algorithm, values=ALGORITHMS, state="readonly",
            style="Cipher.TCombobox", font=("Cascadia Mono", 10), width=15,
        )
        algorithm.grid(row=0, column=1, sticky="w")
        algorithm.bind("<<ComboboxSelected>>", lambda _event: self.generate_hash())
        self.app._button(algorithm_card, "Hash files", self.hash_files, secondary=True).grid(row=0, column=2, padx=(12, 0))
        self.app._button(algorithm_card, "Verify file", self.verify_file, secondary=True).grid(row=0, column=3, padx=(8, 0))

        workspace = tk.Frame(page, bg=self.app.BG)
        workspace.grid(row=1, column=0, sticky="nsew")
        workspace.grid_columnconfigure(0, weight=1, uniform="hash")
        workspace.grid_columnconfigure(1, weight=1, uniform="hash")
        workspace.grid_rowconfigure(0, weight=1)

        input_card = self.app._card(workspace, "PLAIN TEXT", self.hash_count)
        input_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        input_card.grid_rowconfigure(1, weight=1)
        input_card.grid_rowconfigure(2, minsize=104)
        self.hash_input = self.app._text_box(input_card)
        self.hash_input.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 16))
        self.hash_input.bind("<KeyRelease>", self._on_hash_input)

        output_card = self.app._card(workspace, "DIGEST", self.hash_status)
        output_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        output_card.grid_rowconfigure(1, weight=1)
        self.hash_output = self.app._text_box(output_card, readonly=True, accent=True)
        self.hash_output.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 12))
        verify = tk.Entry(
            output_card, textvariable=self.verify_value, bg=self.app.FIELD, fg=self.app.TEXT,
            insertbackground=self.app.ACCENT, relief="flat", font=("Cascadia Mono", 9),
        )
        verify.grid(row=2, column=0, sticky="ew", padx=18, ipady=10)
        verify.bind("<Return>", lambda _event: self.verify_hash())
        actions = tk.Frame(output_card, bg=self.app.PANEL)
        actions.grid(row=3, column=0, sticky="ew", padx=18, pady=14)
        actions.grid_columnconfigure(0, weight=1)
        self.app._button(actions, "Verify", self.verify_hash, secondary=True).grid(row=0, column=0, sticky="w")
        self.app._button(actions, "Copy digest", lambda: self.app.copy_text(self.hash_output, self.hash_status)).grid(
            row=0, column=1, padx=(8, 0)
        )
        self.app._button(actions, "Clear", self.clear_hash, secondary=True).grid(row=0, column=2, padx=(8, 0))
        return page

    def _on_hash_input(self, _event=None) -> None:
        text = self.app._get(self.hash_input)
        self.hash_count.set(f"{len(text):,} characters / {len(text.encode('utf-8')):,} bytes")
        self.generate_hash()

    def generate_hash(self) -> None:
        text = self.app._get(self.hash_input)
        digest = hash_text(text, self.algorithm.get()) if text else ""
        self.app._set(self.hash_output, digest)
        self.hash_status.set("Ready" if not text else f"{self.algorithm.get().upper()} / {len(digest)} chars")

    def hash_files(self) -> None:
        filenames = filedialog.askopenfilenames(parent=self.app, title="Hash files")
        if filenames:
            self.display_file_hashes(filenames)

    def display_file_hashes(self, filenames) -> None:
        results = []
        try:
            for filename in filenames:
                digest = hash_file(filename, self.algorithm.get())
                results.append(digest if len(filenames) == 1 else f"{digest}  {filename}")
                self.app.remember_file(filename)
        except OSError as error:
            messagebox.showerror("File hashing failed", str(error), parent=self.app)
            return
        self.app._set(self.hash_output, "\n".join(results))
        self.hash_status.set(f"{len(results)} file{'s' if len(results) != 1 else ''} / {self.algorithm.get().upper()}")

    def verify_file(self) -> None:
        expected = self.verify_value.get().strip().lower()
        if not expected:
            self.hash_status.set("Enter the expected digest first")
            return
        filename = filedialog.askopenfilename(parent=self.app, title="Verify file")
        if not filename:
            return
        try:
            actual = hash_file(filename, self.algorithm.get())
        except OSError as error:
            messagebox.showerror("File verification failed", str(error), parent=self.app)
            return
        self.app._set(self.hash_output, actual)
        self.hash_status.set("File digest matches" if hmac.compare_digest(actual, expected) else "File digest does not match")
        self.app.remember_file(filename)

    def verify_hash(self) -> None:
        digest = self.app._get(self.hash_output)
        expected = self.verify_value.get().strip().lower()
        if not digest or not expected:
            self.hash_status.set("Enter text and a digest first")
            return
        self.hash_status.set("Digest matches" if hmac.compare_digest(digest, expected) else "Digest does not match")

    def clear_hash(self) -> None:
        self.hash_input.delete("1.0", "end")
        self.verify_value.set("")
        self.app._set(self.hash_output, "")
        self.hash_count.set("0 characters / 0 bytes")
        self.hash_status.set("Ready")
        self.hash_input.focus_set()

    def focus(self) -> None:
        self.hash_input.focus_set()
