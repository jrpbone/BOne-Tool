"""Image to ASCII processing and self-contained workspace controller."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
import os
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps, ImageTk, UnidentifiedImageError
from tkinterdnd2 import DND_FILES

if TYPE_CHECKING:
    from main import BOneTool


ASCII_CHARS = "@%#*+=-:. "


ASCII_SETS = {
    "Classic": ASCII_CHARS,
    "Detailed": "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/|()1{}[]?-_+~<>i!lI;:,\"^`'. ",
    "Blocks": "#*=:. ",
}


def image_to_ascii(
    path: str | Path,
    max_width: int = 100,
    brightness: float = 1.0,
    contrast: float = 1.0,
    invert: bool = False,
    characters: str = ASCII_CHARS,
) -> str:
    if max_width < 1 or not characters:
        raise ValueError("Width and character set must not be empty.")
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGBA")
        background = Image.new("RGBA", image.size, "white")
        background.alpha_composite(image)
        image = background.convert("L")
        image = ImageEnhance.Brightness(image).enhance(brightness)
        image = ImageEnhance.Contrast(image).enhance(contrast)
        if invert:
            image = ImageOps.invert(image)
        width = min(max_width, image.width)
        height = max(1, round(image.height * width / image.width * 0.5))
        image = image.resize((width, height), Image.Resampling.LANCZOS)
        pixels = image.load()
        return "\n".join(
            "".join(characters[pixels[x, y] * (len(characters) - 1) // 255] for x in range(width))
            for y in range(height)
        )


def ascii_to_image(
    text: str,
    font_size: int = 14,
    foreground: str = "#f6b94a",
    background: str = "#0b1020",
    font_path: str | None = None,
) -> Image.Image:
    if not text or font_size < 1:
        raise ValueError("Create ASCII art first.")
    try:
        font = ImageFont.truetype(font_path or Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "consola.ttf", font_size)
    except OSError:
        if font_path:
            raise
        font = ImageFont.load_default(size=font_size)
    box = font.getbbox("M")
    char_width, line_height = box[2] - box[0], box[3] - box[1] + 2
    lines = text.splitlines() or [""]
    image = Image.new("RGB", (max(map(len, lines)) * char_width, len(lines) * line_height), background)
    ImageDraw.Draw(image).multiline_text((0, 0), text, fill=foreground, font=font, spacing=2)
    return image


class AsciiFeature:
    page_id = "ascii"
    title = "Image to ASCII"

    def __init__(self, app: "BOneTool") -> None:
        self.app = app
        self.current_image: Path | None = None
        self.preview_image = None
        self.preview_photo = None
        self.ascii_font_path: str | None = None
        self.ascii_status = tk.StringVar(master=app, value="Import an image to begin")
        self.ascii_width = tk.IntVar(master=app, value=100)
        self.ascii_brightness = tk.DoubleVar(master=app, value=2.0)
        self.ascii_contrast = tk.DoubleVar(master=app, value=2.0)
        self.ascii_invert = tk.BooleanVar(master=app, value=True)
        self.ascii_charset = tk.StringVar(master=app, value="Classic")
        self.ascii_font_size = tk.IntVar(master=app, value=14)
        self.ascii_foreground = tk.StringVar(master=app, value=self.app.ACCENT)
        self.ascii_background = tk.StringVar(master=app, value=self.app.BG)

    def build(self, parent: tk.Widget) -> tk.Frame:
        page = tk.Frame(parent, bg=self.app.BG)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        controls = tk.Frame(page, bg=self.app.PANEL, padx=16, pady=12)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        tk.Label(controls, text="WIDTH", bg=self.app.PANEL, fg=self.app.MUTED, font=("Segoe UI Semibold", 8)).grid(row=0, column=0)
        tk.Spinbox(
            controls, from_=20, to=300, textvariable=self.ascii_width, width=5,
            bg=self.app.FIELD, fg=self.app.TEXT, buttonbackground=self.app.FIELD, relief="flat",
        ).grid(row=0, column=1, padx=(6, 14), ipady=4)
        tk.Label(controls, text="BRIGHTNESS", bg=self.app.PANEL, fg=self.app.MUTED, font=("Segoe UI Semibold", 8)).grid(row=0, column=2)
        tk.Scale(
            controls, from_=0.25, to=2.0, resolution=0.05, variable=self.ascii_brightness,
            orient="horizontal", showvalue=True, digits=3, length=110, bg=self.app.PANEL, fg=self.app.TEXT,
            troughcolor=self.app.FIELD, highlightthickness=0,
        ).grid(row=0, column=3, padx=(4, 10))
        tk.Label(controls, text="CONTRAST", bg=self.app.PANEL, fg=self.app.MUTED, font=("Segoe UI Semibold", 8)).grid(row=0, column=4)
        tk.Scale(
            controls, from_=0.25, to=2.0, resolution=0.05, variable=self.ascii_contrast,
            orient="horizontal", showvalue=True, digits=3, length=110, bg=self.app.PANEL, fg=self.app.TEXT,
            troughcolor=self.app.FIELD, highlightthickness=0,
        ).grid(row=0, column=5, padx=(4, 10))
        ttk.Combobox(
            controls, textvariable=self.ascii_charset, values=list(ASCII_SETS), state="readonly",
            style="Cipher.TCombobox", width=10,
        ).grid(row=0, column=6, padx=(0, 8))
        tk.Checkbutton(
            controls, text="Invert", variable=self.ascii_invert, bg=self.app.PANEL, fg=self.app.TEXT,
            selectcolor=self.app.FIELD, activebackground=self.app.PANEL, activeforeground=self.app.TEXT,
        ).grid(row=0, column=7)
        self.app._button(controls, "Apply", self.render_ascii).grid(row=0, column=8, padx=(8, 0))
        tk.Label(controls, text="IMAGE FONT SIZE", bg=self.app.PANEL, fg=self.app.MUTED, font=("Segoe UI Semibold", 8)).grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))
        tk.Spinbox(
            controls, from_=8, to=48, textvariable=self.ascii_font_size, width=5,
            bg=self.app.FIELD, fg=self.app.TEXT, buttonbackground=self.app.FIELD, relief="flat",
        ).grid(row=1, column=2, sticky="w", pady=(10, 0), ipady=4)
        self.app._button(controls, "Text color", lambda: self.choose_ascii_color(True), secondary=True).grid(row=1, column=3, pady=(10, 0))
        self.app._button(controls, "Background", lambda: self.choose_ascii_color(False), secondary=True).grid(row=1, column=4, columnspan=2, pady=(10, 0))
        self.app._button(controls, "Choose font", self.choose_ascii_font, secondary=True).grid(row=1, column=6, columnspan=2, pady=(10, 0))

        workspace = tk.Frame(page, bg=self.app.BG)
        workspace.grid(row=1, column=0, sticky="nsew")
        workspace.grid_columnconfigure(0, weight=1, uniform="ascii")
        workspace.grid_columnconfigure(1, weight=1, uniform="ascii")
        workspace.grid_rowconfigure(0, weight=1)
        preview_card = self.app._card(workspace, "IMAGE PREVIEW")
        preview_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        preview_card.grid_rowconfigure(1, weight=1)
        self.image_preview = tk.Label(
            preview_card, text="Drop or import an image", bg=self.app.FIELD, fg=self.app.MUTED,
            width=1, font=("Segoe UI", 10),
        )
        self.image_preview.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 16))
        self.image_preview.bind("<Configure>", self.resize_image_preview)

        card = self.app._card(workspace, "ASCII ART", self.ascii_status)
        card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        card.grid_rowconfigure(1, weight=1)
        self.ascii_output = self.app._text_box(card, readonly=True, accent=True)
        self.ascii_output.configure(wrap="none")
        self.ascii_output.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 14))
        actions = tk.Frame(card, bg=self.app.PANEL)
        actions.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 16))
        actions.grid_columnconfigure(1, weight=1)
        self.app._button(actions, "Import image", self.import_image).grid(row=0, column=0)
        self.app._button(actions, "Save text", self.save_ascii_text, secondary=True).grid(row=0, column=2)
        self.app._button(actions, "Save image", self.save_ascii_image, secondary=True).grid(row=0, column=3, padx=(8, 0))
        self.app._button(
            actions, "Clear", lambda: self.clear_ascii(), secondary=True
        ).grid(row=0, column=4, padx=(8, 0))
        self.app._button(
            actions, "Copy ASCII", lambda: self.app.copy_text(self.ascii_output, self.ascii_status)
        ).grid(row=0, column=5, padx=(8, 0))
        for widget in (page, self.image_preview, self.ascii_output):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self.app.drop_files)
        return page

    def import_image(self) -> None:
        filename = filedialog.askopenfilename(
            parent=self.app,
            title="Import an image into BOne Tool",
            filetypes=(
                ("Image files", "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff"),
                ("All files", "*.*"),
            ),
        )
        if not filename:
            return
        self.load_image(filename)

    def load_image(self, filename: str) -> None:
        try:
            with Image.open(filename) as source:
                preview = ImageOps.exif_transpose(source).convert("RGBA")
                background = Image.new("RGBA", preview.size, "white")
                background.alpha_composite(preview)
                preview = background.convert("RGB")
                preview.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
            self.app._set(self.ascii_output, "")
            self.ascii_status.set("Could not read image")
            messagebox.showerror("Image import failed", str(error), parent=self.app)
            return
        self.current_image = Path(filename)
        self.preview_image = preview
        self.resize_image_preview()
        self.app.remember_file(filename)
        self.render_ascii()

    def render_ascii(self) -> None:
        if not self.current_image:
            self.ascii_status.set("Import an image first")
            return
        try:
            result = image_to_ascii(
                self.current_image,
                self.ascii_width.get(),
                self.ascii_brightness.get(),
                self.ascii_contrast.get(),
                self.ascii_invert.get(),
                ASCII_SETS[self.ascii_charset.get()],
            )
        except (OSError, ValueError, tk.TclError) as error:
            self.ascii_status.set(str(error))
            return
        self.app._set(self.ascii_output, result)
        self.ascii_status.set(f"{self.current_image.name} / {len(result.splitlines())} lines")

    def resize_image_preview(self, _event=None) -> None:
        if self.preview_image is None:
            return
        preview = self.preview_image.copy()
        preview.thumbnail(
            (max(1, self.image_preview.winfo_width() - 12), max(1, self.image_preview.winfo_height() - 12)),
            Image.Resampling.LANCZOS,
        )
        self.preview_photo = ImageTk.PhotoImage(preview)
        self.image_preview.configure(image=self.preview_photo, text="")

    def save_ascii_text(self) -> None:
        self.app.save_text(self.app._get(self.ascii_output), "Save ASCII art", self.ascii_status)

    def save_ascii_image(self) -> None:
        value = self.app._get(self.ascii_output)
        try:
            image = ascii_to_image(
                value, self.ascii_font_size.get(), self.ascii_foreground.get(),
                self.ascii_background.get(), self.ascii_font_path,
            )
        except (OSError, ValueError, tk.TclError) as error:
            messagebox.showerror("ASCII export failed", str(error), parent=self.app)
            return
        filename = filedialog.asksaveasfilename(
            parent=self.app, title="Save ASCII image", defaultextension=".png",
            filetypes=(("PNG image", "*.png"), ("JPEG image", "*.jpg;*.jpeg")),
        )
        try:
            if filename:
                suffix = Path(filename).suffix.lower()
                if suffix not in {".png", ".jpg", ".jpeg"}:
                    raise ValueError("Use a .png, .jpg, or .jpeg filename.")
                if suffix in {".jpg", ".jpeg"}:
                    image.save(filename, format="JPEG", quality=95, subsampling=0)
                else:
                    image.save(filename, format="PNG")
                self.ascii_status.set(f"Saved {Path(filename).name}")
                self.app.remember_file(filename)
        except (OSError, ValueError) as error:
            messagebox.showerror("ASCII export failed", str(error), parent=self.app)
        finally:
            image.close()

    def choose_ascii_color(self, foreground: bool) -> None:
        variable = self.ascii_foreground if foreground else self.ascii_background
        color = colorchooser.askcolor(variable.get(), parent=self.app, title="Choose ASCII color")[1]
        if color:
            variable.set(color)

    def choose_ascii_font(self) -> None:
        filename = filedialog.askopenfilename(
            parent=self.app, title="Choose ASCII font",
            filetypes=(("Font files", "*.ttf *.otf"), ("All files", "*.*")),
        )
        if filename:
            self.ascii_font_path = filename
            self.ascii_status.set(f"Image font: {Path(filename).name}")

    def clear_ascii(self) -> None:
        self.app._set(self.ascii_output, "")
        self.current_image = None
        self.preview_image = None
        self.preview_photo = None
        self.image_preview.configure(image="", text="Drop or import an image")
        self.ascii_status.set("Import an image to begin")

    def focus(self) -> None:
        self.ascii_output.focus_set()
