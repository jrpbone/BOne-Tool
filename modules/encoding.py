"""Encoding processing and self-contained workspace controller."""

from __future__ import annotations

from typing import TYPE_CHECKING
import tkinter as tk
from tkinter import ttk
import base64
import binascii
from urllib.parse import quote, unquote

if TYPE_CHECKING:
    from main import BOneTool


def transform_text(text: str, method: str, decode: bool = False) -> str:
    if method == "Base64":
        if decode:
            return base64.b64decode(text, validate=True).decode("utf-8")
        return base64.b64encode(text.encode("utf-8")).decode("ascii")
    if method == "Hex":
        return bytes.fromhex(text).decode("utf-8") if decode else text.encode("utf-8").hex()
    return unquote(text) if decode else quote(text)


class EncodingFeature:
    page_id = "encoding"
    title = "Encoding"

    def __init__(self, app: "BOneTool") -> None:
        self.app = app
        self.encoding_method = tk.StringVar(master=app, value="Base64")
        self.encoding_direction = tk.StringVar(master=app, value="Encode")
        self.encoding_status = tk.StringVar(master=app, value="Ready")

    def build(self, parent: tk.Widget) -> tk.Frame:
        page = tk.Frame(parent, bg=self.app.BG)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        controls = tk.Frame(page, bg=self.app.PANEL, padx=20, pady=14)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        ttk.Combobox(
            controls, textvariable=self.encoding_method, values=("Base64", "Hex", "URL"),
            state="readonly", style="Cipher.TCombobox", width=12,
        ).grid(row=0, column=0)
        ttk.Combobox(
            controls, textvariable=self.encoding_direction, values=("Encode", "Decode"),
            state="readonly", style="Cipher.TCombobox", width=10,
        ).grid(row=0, column=1, padx=(8, 0))
        self.app._button(controls, "Transform", self.run_encoding).grid(row=0, column=2, padx=(8, 0))

        workspace = tk.Frame(page, bg=self.app.BG)
        workspace.grid(row=1, column=0, sticky="nsew")
        workspace.grid_columnconfigure(0, weight=1, uniform="encoding")
        workspace.grid_columnconfigure(1, weight=1, uniform="encoding")
        workspace.grid_rowconfigure(0, weight=1)
        input_card = self.app._card(workspace, "INPUT")
        input_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        input_card.grid_rowconfigure(1, weight=1)
        self.encoding_input = self.app._text_box(input_card)
        self.encoding_input.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 16))
        output_card = self.app._card(workspace, "OUTPUT", self.encoding_status)
        output_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        output_card.grid_rowconfigure(1, weight=1)
        self.encoding_output = self.app._text_box(output_card, readonly=True, accent=True)
        self.encoding_output.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 12))
        actions = tk.Frame(output_card, bg=self.app.PANEL)
        actions.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 16))
        actions.grid_columnconfigure(0, weight=1)
        self.app._button(actions, "Copy", lambda: self.app.copy_text(self.encoding_output, self.encoding_status)).grid(row=0, column=1)
        return page

    def run_encoding(self) -> None:
        try:
            result = transform_text(
                self.app._get(self.encoding_input), self.encoding_method.get(),
                self.encoding_direction.get() == "Decode",
            )
        except (ValueError, UnicodeError, binascii.Error) as error:
            self.app._set(self.encoding_output, "")
            self.encoding_status.set(f"Invalid input: {error}")
            return
        self.app._set(self.encoding_output, result)
        self.encoding_status.set(f"{self.encoding_method.get()} {self.encoding_direction.get().lower()}d")

    def focus(self) -> None:
        self.encoding_input.focus_set()
