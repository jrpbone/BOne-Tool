"""Encrypt / Decrypt processing and self-contained workspace controller."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
import tkinter as tk
from tkinter import filedialog, messagebox
import base64
import binascii
import os
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from PIL import Image, ImageTk
import qrcode
from tkinterdnd2 import DND_FILES

if TYPE_CHECKING:
    from main import BOneTool


MAGIC = b"OC1"
SALT_BYTES = 16
NONCE_BYTES = 12


def password_strength(password: str) -> str:
    if not password:
        return "No password"
    score = min(len(password) // 4, 3) + sum(
        any(test(character) for character in password)
        for test in (str.islower, str.isupper, str.isdigit, lambda value: not value.isalnum())
    )
    return ("Weak", "Weak", "Fair", "Fair", "Good", "Good", "Strong", "Strong")[min(score, 7)]


def _derive_key(password: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode("utf-8"))


def encrypt_text(text: str, password: str) -> str:
    if len(password) < 8:
        raise ValueError("Use a password with at least 8 characters.")
    salt, nonce = os.urandom(SALT_BYTES), os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(_derive_key(password, salt)).encrypt(nonce, text.encode("utf-8"), MAGIC)
    payload = base64.urlsafe_b64encode(salt + nonce + ciphertext).decode("ascii").rstrip("=")
    return f"{MAGIC.decode()}.{payload}"


def decrypt_text(token: str, password: str) -> str:
    if not password:
        raise ValueError("Enter the password used to encrypt this message.")
    if not token.startswith("OC1."):
        raise ValueError("This is not a BOne Tool OC1 message.")
    encoded = token[4:].strip()
    try:
        padding = "=" * (-len(encoded) % 4)
        payload = base64.b64decode(encoded + padding, altchars=b"-_", validate=True)
        if len(payload) < SALT_BYTES + NONCE_BYTES + 16:
            raise ValueError
        salt = payload[:SALT_BYTES]
        nonce = payload[SALT_BYTES : SALT_BYTES + NONCE_BYTES]
        ciphertext = payload[SALT_BYTES + NONCE_BYTES :]
        plaintext = AESGCM(_derive_key(password, salt)).decrypt(nonce, ciphertext, MAGIC)
        return plaintext.decode("utf-8")
    except (ValueError, UnicodeDecodeError, binascii.Error, InvalidTag) as error:
        raise ValueError("Could not decrypt. Check the password and message.") from error


class CryptoFeature:
    page_id = "encrypt"
    title = "Encrypt / Decrypt"

    def __init__(self, app: "BOneTool") -> None:
        self.app = app
        self.password = tk.StringVar(master=app)
        self.password_status = tk.StringVar(master=app, value="No password")
        self.crypto_status = tk.StringVar(master=app, value="AES-256-GCM / Scrypt / OC1")

    def build(self, parent: tk.Widget) -> tk.Frame:
        page = tk.Frame(parent, bg=self.app.BG)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        password_card = tk.Frame(page, bg=self.app.PANEL, padx=20, pady=14)
        password_card.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        password_card.grid_columnconfigure(1, weight=1)
        tk.Label(
            password_card, text="PASSWORD", bg=self.app.PANEL, fg=self.app.MUTED,
            font=("Segoe UI Semibold", 9),
        ).grid(row=0, column=0, sticky="w", padx=(0, 18))
        self.password_entry = tk.Entry(
            password_card, textvariable=self.password, show="*", bg=self.app.FIELD, fg=self.app.TEXT,
            insertbackground=self.app.ACCENT, relief="flat", font=("Cascadia Mono", 10),
        )
        self.password_entry.grid(row=0, column=1, sticky="ew", ipady=10)
        self.password.trace_add("write", lambda *_args: self.password_status.set(password_strength(self.password.get())))
        tk.Label(
            password_card, textvariable=self.password_status, bg=self.app.PANEL, fg=self.app.MUTED,
            font=("Segoe UI", 9), width=10,
        ).grid(row=0, column=2, padx=(10, 0))
        self.show_password_button = self.app._button(password_card, "Show", self.toggle_password, secondary=True)
        self.show_password_button.grid(row=0, column=3, padx=(10, 0))

        workspace = tk.Frame(page, bg=self.app.BG)
        workspace.grid(row=1, column=0, sticky="nsew")
        workspace.grid_columnconfigure(0, weight=1, uniform="crypto")
        workspace.grid_columnconfigure(1, weight=1, uniform="crypto")
        workspace.grid_rowconfigure(0, weight=1)

        source_card = self.app._card(workspace, "MESSAGE OR OC1 TOKEN")
        source_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        source_card.grid_rowconfigure(1, weight=1)
        source_card.grid_rowconfigure(2, minsize=106)
        self.crypto_input = self.app._text_box(source_card)
        self.crypto_input.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 14))
        for widget in (page, self.crypto_input):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self.app.drop_files)
        source_actions = tk.Frame(source_card, bg=self.app.PANEL)
        source_actions.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 16))
        source_actions.grid_columnconfigure(2, weight=1)
        self.app._button(source_actions, "Encrypt", self.encrypt).grid(row=0, column=0)
        self.app._button(source_actions, "Decrypt", self.decrypt, secondary=True).grid(row=0, column=1, padx=(8, 0))
        self.app._button(source_actions, "Import text", self.import_text_file, secondary=True).grid(row=0, column=3)
        self.app._button(source_actions, "Clear", self.clear_crypto, secondary=True).grid(row=0, column=4, padx=(8, 0))

        result_card = self.app._card(workspace, "RESULT", self.crypto_status)
        result_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        result_card.grid_rowconfigure(1, weight=1)
        result_card.grid_rowconfigure(2, minsize=106)
        self.crypto_output = self.app._text_box(result_card, readonly=True, accent=True)
        self.crypto_output.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 14))
        result_actions = tk.Frame(result_card, bg=self.app.PANEL)
        result_actions.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 16))
        result_actions.grid_columnconfigure(0, weight=1)
        self.app._button(result_actions, "Use as input", self.use_crypto_output, secondary=True).grid(
            row=0, column=0, sticky="w"
        )
        self.app._button(result_actions, "Save", self.save_crypto_output, secondary=True).grid(row=0, column=1)
        self.app._button(result_actions, "QR", self.show_qr, secondary=True).grid(row=0, column=2, padx=(8, 0))
        self.app._button(result_actions, "Copy", self.copy_crypto_output).grid(row=0, column=3, padx=(8, 0))
        return page

    def encrypt(self) -> None:
        text = self.app._get(self.crypto_input)
        if not text:
            self.crypto_status.set("Enter a message first")
            return
        try:
            self.app._set(self.crypto_output, encrypt_text(text, self.password.get()))
            self.crypto_status.set("Encrypted / OC1")
        except ValueError as error:
            self.crypto_status.set(str(error))

    def import_text_file(self, filename: str | None = None) -> None:
        filename = filename or filedialog.askopenfilename(
            parent=self.app, title="Import text", filetypes=(("Text files", "*.txt *.oc1"), ("All files", "*.*"))
        )
        if not filename:
            return
        try:
            text = Path(filename).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            messagebox.showerror("Text import failed", str(error), parent=self.app)
            return
        self.crypto_input.delete("1.0", "end")
        self.crypto_input.insert("1.0", text)
        self.crypto_status.set(f"Imported {Path(filename).name}")
        self.app.remember_file(filename)

    def save_crypto_output(self) -> None:
        self.app.save_text(self.app._get(self.crypto_output), "Save result", self.crypto_status)

    def show_qr(self) -> None:
        value = self.app._get(self.crypto_output)
        if not value:
            self.crypto_status.set("Create a result first")
            return
        try:
            image = qrcode.make(value).convert("RGB")
        except (ValueError, qrcode.exceptions.DataOverflowError) as error:
            messagebox.showerror("QR generation failed", str(error), parent=self.app)
            return
        window = tk.Toplevel(self.app)
        window.title("BOne Tool QR")
        window.configure(bg=self.app.BG, padx=16, pady=16)
        preview = image.copy()
        preview.thumbnail((520, 520), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(preview)
        label = tk.Label(window, image=photo, bg="white")
        label.image = photo
        label.pack()

        def save() -> None:
            filename = filedialog.asksaveasfilename(
                parent=window, title="Save QR code", defaultextension=".png",
                filetypes=(("PNG image", "*.png"),),
            )
            if filename:
                try:
                    image.save(filename)
                except OSError as error:
                    messagebox.showerror("QR save failed", str(error), parent=window)

        self.app._button(window, "Save PNG", save).pack(pady=(12, 0))

    def decrypt(self) -> None:
        token = self.app._get(self.crypto_input).strip()
        try:
            self.app._set(self.crypto_output, decrypt_text(token, self.password.get()))
            self.crypto_status.set("Decrypted and authenticated")
        except ValueError as error:
            self.app._set(self.crypto_output, "")
            self.crypto_status.set(str(error))

    def toggle_password(self) -> None:
        hidden = self.password_entry.cget("show") == "*"
        self.password_entry.configure(show="" if hidden else "*")
        self.show_password_button.configure(text="Hide" if hidden else "Show")

    def use_crypto_output(self) -> None:
        value = self.app._get(self.crypto_output)
        if value:
            self.crypto_input.delete("1.0", "end")
            self.crypto_input.insert("1.0", value)
            self.crypto_status.set("Result moved to input")

    def copy_crypto_output(self) -> None:
        self.app.copy_text(self.crypto_output, self.crypto_status)

    def clear_crypto(self) -> None:
        self.crypto_input.delete("1.0", "end")
        self.app._set(self.crypto_output, "")
        self.password.set("")
        self.crypto_status.set("AES-256-GCM / Scrypt / OC1")
        self.crypto_input.focus_set()

    def focus(self) -> None:
        self.crypto_input.focus_set()
