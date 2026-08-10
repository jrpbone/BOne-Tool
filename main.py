import base64
import binascii
import ctypes
import hashlib
import hmac
import json
import os
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from urllib.parse import quote, unquote

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from fontTools.ttLib import TTCollection, TTFont, TTLibError
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps, ImageTk, UnidentifiedImageError
import qrcode
from tkinterdnd2 import DND_FILES, TkinterDnD


ALGORITHMS = ("sha256", "sha512", "sha3_256", "sha3_512", "blake2b", "blake2s", "sha1", "md5")
MAGIC = b"OC1"
SALT_BYTES = 16
NONCE_BYTES = 12
APP_DIR = Path(__file__).parent
FONT_DIR = APP_DIR / "fonts"
FONT_EXTENSIONS = {".ttf", ".otf", ".ttc", ".woff", ".woff2"}
DESKTOP_FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}
ASCII_CHARS = "@%#*+=-:. "
ASCII_SETS = {
    "Classic": ASCII_CHARS,
    "Detailed": "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/|()1{}[]?-_+~<>i!lI;:,\"^`'. ",
    "Blocks": "#*=:. ",
}
THEMES = {
    "Dark": {"BG": "#0b1020", "PANEL": "#121a2d", "FIELD": "#182238", "TEXT": "#eef2ff", "MUTED": "#8d9ab5", "ACCENT": "#f6b94a"},
    "Light": {"BG": "#eef1f6", "PANEL": "#ffffff", "FIELD": "#dfe5ee", "TEXT": "#182238", "MUTED": "#61708a", "ACCENT": "#c87a00"},
}
SETTINGS_PATH = Path.home() / ".bonecipher.json"


def hash_text(text: str, algorithm: str) -> str:
    return hashlib.new(algorithm, text.encode("utf-8")).hexdigest()


def hash_file(path: str | Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def transform_text(text: str, method: str, decode: bool = False) -> str:
    if method == "Base64":
        if decode:
            return base64.b64decode(text, validate=True).decode("utf-8")
        return base64.b64encode(text.encode("utf-8")).decode("ascii")
    if method == "Hex":
        return bytes.fromhex(text).decode("utf-8") if decode else text.encode("utf-8").hex()
    return unquote(text) if decode else quote(text)


def password_strength(password: str) -> str:
    if not password:
        return "No password"
    score = min(len(password) // 4, 3) + sum(
        any(test(character) for character in password)
        for test in (str.islower, str.isupper, str.isdigit, lambda value: not value.isalnum())
    )
    return ("Weak", "Weak", "Fair", "Fair", "Good", "Good", "Strong", "Strong")[min(score, 7)]


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


def font_families(path: Path) -> list[str]:
    fonts = TTCollection(path, lazy=True).fonts if path.suffix.lower() == ".ttc" else [TTFont(path, lazy=True)]
    try:
        families = {
            name.toUnicode().strip()
            for font in fonts
            for name_id in (16, 1)
            for name in font["name"].names
            if name.nameID == name_id and name.toUnicode().strip()
        }
        if not families:
            raise ValueError("Font does not contain a family name.")
        return sorted(families)
    finally:
        for font in fonts:
            font.close()


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


class BOneTool(TkinterDnD.Tk):
    BG = "#0b1020"
    PANEL = "#121a2d"
    FIELD = "#182238"
    TEXT = "#eef2ff"
    MUTED = "#8d9ab5"
    ACCENT = "#f6b94a"
    SUCCESS = "#5ee0a0"
    ERROR = "#ff7b84"

    def __init__(self) -> None:
        super().__init__()
        try:
            self.settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.settings = {}
        if not isinstance(self.settings, dict):
            self.settings = {}
        theme = self.settings.get("theme") if self.settings.get("theme") in THEMES else "Dark"
        editor_size = self.settings.get("editor_font_size", 10)
        editor_size = editor_size if isinstance(editor_size, int) and 8 <= editor_size <= 24 else 10
        recent_files = self.settings.get("recent_files", [])
        recent_files = recent_files if isinstance(recent_files, list) and all(isinstance(path, str) for path in recent_files) else []
        for name, value in THEMES[theme].items():
            setattr(self, name, value)
        self.title("BOne Tool")
        self.geometry("1040x760")
        self.minsize(760, 640)
        self.configure(bg=self.BG)
        self.loaded_font_paths: set[Path] = set()
        self.font_choices: dict[str, str] = {}
        self.current_image: Path | None = None
        self.preview_image = None
        self.preview_photo = None
        self.ascii_font_path: str | None = None
        self.current_page = "encrypt"
        self.recent_files = recent_files

        self.algorithm = tk.StringVar(value="sha256")
        self.hash_count = tk.StringVar(value="0 characters / 0 bytes")
        self.hash_status = tk.StringVar(value="Ready")
        self.verify_value = tk.StringVar()
        self.password = tk.StringVar()
        self.password_status = tk.StringVar(value="No password")
        self.crypto_status = tk.StringVar(value="AES-256-GCM / Scrypt / OC1")
        self.font_choice = tk.StringVar()
        self.alphabet_status = tk.StringVar(value="Loading fonts...")
        self.ascii_status = tk.StringVar(value="Import an image to begin")
        self.ascii_width = tk.IntVar(value=100)
        self.ascii_brightness = tk.DoubleVar(value=2.0)
        self.ascii_contrast = tk.DoubleVar(value=2.0)
        self.ascii_invert = tk.BooleanVar(value=True)
        self.ascii_charset = tk.StringVar(value="Classic")
        self.ascii_font_size = tk.IntVar(value=14)
        self.ascii_foreground = tk.StringVar(value=self.ACCENT)
        self.ascii_background = tk.StringVar(value=self.BG)
        self.encoding_method = tk.StringVar(value="Base64")
        self.encoding_direction = tk.StringVar(value="Encode")
        self.encoding_status = tk.StringVar(value="Ready")
        self.theme_choice = tk.StringVar(value=theme)
        self.editor_font_size = tk.IntVar(value=editor_size)
        self.history_enabled = tk.BooleanVar(value=self.settings.get("history_enabled") is True)
        self.refresh_fonts()

        self._style_widgets()
        self._build_ui()
        self.show_page("encrypt")

    def _style_widgets(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Cipher.TCombobox",
            fieldbackground=self.FIELD,
            background=self.FIELD,
            foreground=self.TEXT,
            arrowcolor=self.ACCENT,
            bordercolor=self.FIELD,
            lightcolor=self.FIELD,
            darkcolor=self.FIELD,
            padding=10,
        )
        style.map(
            "Cipher.TCombobox",
            fieldbackground=[("readonly", self.FIELD)],
            foreground=[("readonly", self.TEXT)],
            selectbackground=[("readonly", self.FIELD)],
            selectforeground=[("readonly", self.TEXT)],
        )

    def _build_ui(self) -> None:
        shell = tk.Frame(self, bg=self.BG, padx=42, pady=30)
        shell.pack(fill="both", expand=True)
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(1, weight=1)

        nav = tk.Frame(shell, bg=self.BG)
        nav.grid(row=0, column=0, sticky="w", pady=(0, 16))
        self.nav_buttons = {
            "encrypt": self._button(nav, "Encrypt / Decrypt", lambda: self.show_page("encrypt")),
            "hash": self._button(nav, "Hash", lambda: self.show_page("hash"), secondary=True),
            "alphabet": self._button(nav, "Alphabet", lambda: self.show_page("alphabet"), secondary=True),
            "ascii": self._button(nav, "Image to ASCII", lambda: self.show_page("ascii"), secondary=True),
            "encoding": self._button(nav, "Encoding", lambda: self.show_page("encoding"), secondary=True),
            "settings": self._button(nav, "Settings", lambda: self.show_page("settings"), secondary=True),
        }
        for column, button in enumerate(self.nav_buttons.values()):
            button.grid(row=0, column=column, padx=(8 if column else 0, 0))

        pages = tk.Frame(shell, bg=self.BG)
        pages.grid(row=1, column=0, sticky="nsew")
        pages.grid_columnconfigure(0, weight=1)
        pages.grid_rowconfigure(0, weight=1)
        self.pages = {
            "encrypt": self._build_crypto_page(pages),
            "hash": self._build_hash_page(pages),
            "alphabet": self._build_alphabet_page(pages),
            "ascii": self._build_ascii_page(pages),
            "encoding": self._build_encoding_page(pages),
            "settings": self._build_settings_page(pages),
        }
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

    def _build_crypto_page(self, parent: tk.Widget) -> tk.Frame:
        page = tk.Frame(parent, bg=self.BG)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        password_card = tk.Frame(page, bg=self.PANEL, padx=20, pady=14)
        password_card.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        password_card.grid_columnconfigure(1, weight=1)
        tk.Label(
            password_card, text="PASSWORD", bg=self.PANEL, fg=self.MUTED,
            font=("Segoe UI Semibold", 9),
        ).grid(row=0, column=0, sticky="w", padx=(0, 18))
        self.password_entry = tk.Entry(
            password_card, textvariable=self.password, show="*", bg=self.FIELD, fg=self.TEXT,
            insertbackground=self.ACCENT, relief="flat", font=("Cascadia Mono", 10),
        )
        self.password_entry.grid(row=0, column=1, sticky="ew", ipady=10)
        self.password.trace_add("write", lambda *_args: self.password_status.set(password_strength(self.password.get())))
        tk.Label(
            password_card, textvariable=self.password_status, bg=self.PANEL, fg=self.MUTED,
            font=("Segoe UI", 9), width=10,
        ).grid(row=0, column=2, padx=(10, 0))
        self.show_password_button = self._button(password_card, "Show", self.toggle_password, secondary=True)
        self.show_password_button.grid(row=0, column=3, padx=(10, 0))

        workspace = tk.Frame(page, bg=self.BG)
        workspace.grid(row=1, column=0, sticky="nsew")
        workspace.grid_columnconfigure(0, weight=1, uniform="crypto")
        workspace.grid_columnconfigure(1, weight=1, uniform="crypto")
        workspace.grid_rowconfigure(0, weight=1)

        source_card = self._card(workspace, "MESSAGE OR OC1 TOKEN")
        source_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        source_card.grid_rowconfigure(1, weight=1)
        source_card.grid_rowconfigure(2, minsize=106)
        self.crypto_input = self._text_box(source_card)
        self.crypto_input.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 14))
        for widget in (page, self.crypto_input):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self.drop_files)
        source_actions = tk.Frame(source_card, bg=self.PANEL)
        source_actions.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 16))
        source_actions.grid_columnconfigure(2, weight=1)
        self._button(source_actions, "Encrypt", self.encrypt).grid(row=0, column=0)
        self._button(source_actions, "Decrypt", self.decrypt, secondary=True).grid(row=0, column=1, padx=(8, 0))
        self._button(source_actions, "Import text", self.import_text_file, secondary=True).grid(row=0, column=3)
        self._button(source_actions, "Clear", self.clear_crypto, secondary=True).grid(row=0, column=4, padx=(8, 0))

        result_card = self._card(workspace, "RESULT", self.crypto_status)
        result_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        result_card.grid_rowconfigure(1, weight=1)
        result_card.grid_rowconfigure(2, minsize=106)
        self.crypto_output = self._text_box(result_card, readonly=True, accent=True)
        self.crypto_output.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 14))
        result_actions = tk.Frame(result_card, bg=self.PANEL)
        result_actions.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 16))
        result_actions.grid_columnconfigure(0, weight=1)
        self._button(result_actions, "Use as input", self.use_crypto_output, secondary=True).grid(
            row=0, column=0, sticky="w"
        )
        self._button(result_actions, "Save", self.save_crypto_output, secondary=True).grid(row=0, column=1)
        self._button(result_actions, "QR", self.show_qr, secondary=True).grid(row=0, column=2, padx=(8, 0))
        self._button(result_actions, "Copy", self.copy_crypto_output).grid(row=0, column=3, padx=(8, 0))
        return page

    def _build_hash_page(self, parent: tk.Widget) -> tk.Frame:
        page = tk.Frame(parent, bg=self.BG)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        algorithm_card = tk.Frame(page, bg=self.PANEL, padx=20, pady=14)
        algorithm_card.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        tk.Label(
            algorithm_card, text="ALGORITHM", bg=self.PANEL, fg=self.MUTED,
            font=("Segoe UI Semibold", 9),
        ).grid(row=0, column=0, sticky="w", padx=(0, 18))
        algorithm = ttk.Combobox(
            algorithm_card, textvariable=self.algorithm, values=ALGORITHMS, state="readonly",
            style="Cipher.TCombobox", font=("Cascadia Mono", 10), width=15,
        )
        algorithm.grid(row=0, column=1, sticky="w")
        algorithm.bind("<<ComboboxSelected>>", lambda _event: self.generate_hash())
        self._button(algorithm_card, "Hash files", self.hash_files, secondary=True).grid(row=0, column=2, padx=(12, 0))
        self._button(algorithm_card, "Verify file", self.verify_file, secondary=True).grid(row=0, column=3, padx=(8, 0))

        workspace = tk.Frame(page, bg=self.BG)
        workspace.grid(row=1, column=0, sticky="nsew")
        workspace.grid_columnconfigure(0, weight=1, uniform="hash")
        workspace.grid_columnconfigure(1, weight=1, uniform="hash")
        workspace.grid_rowconfigure(0, weight=1)

        input_card = self._card(workspace, "PLAIN TEXT", self.hash_count)
        input_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        input_card.grid_rowconfigure(1, weight=1)
        input_card.grid_rowconfigure(2, minsize=104)
        self.hash_input = self._text_box(input_card)
        self.hash_input.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 16))
        self.hash_input.bind("<KeyRelease>", self._on_hash_input)

        output_card = self._card(workspace, "DIGEST", self.hash_status)
        output_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        output_card.grid_rowconfigure(1, weight=1)
        self.hash_output = self._text_box(output_card, readonly=True, accent=True)
        self.hash_output.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 12))
        verify = tk.Entry(
            output_card, textvariable=self.verify_value, bg=self.FIELD, fg=self.TEXT,
            insertbackground=self.ACCENT, relief="flat", font=("Cascadia Mono", 9),
        )
        verify.grid(row=2, column=0, sticky="ew", padx=18, ipady=10)
        verify.bind("<Return>", lambda _event: self.verify_hash())
        actions = tk.Frame(output_card, bg=self.PANEL)
        actions.grid(row=3, column=0, sticky="ew", padx=18, pady=14)
        actions.grid_columnconfigure(0, weight=1)
        self._button(actions, "Verify", self.verify_hash, secondary=True).grid(row=0, column=0, sticky="w")
        self._button(actions, "Copy digest", lambda: self.copy_text(self.hash_output, self.hash_status)).grid(
            row=0, column=1, padx=(8, 0)
        )
        self._button(actions, "Clear", self.clear_hash, secondary=True).grid(row=0, column=2, padx=(8, 0))
        return page

    def _build_alphabet_page(self, parent: tk.Widget) -> tk.Frame:
        page = tk.Frame(parent, bg=self.BG)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        font_card = tk.Frame(page, bg=self.PANEL, padx=20, pady=14)
        font_card.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        font_card.grid_columnconfigure(1, weight=1)
        tk.Label(
            font_card, text="ACTIVE FONT", bg=self.PANEL, fg=self.MUTED,
            font=("Segoe UI Semibold", 9),
        ).grid(row=0, column=0, sticky="w", padx=(0, 18))
        self.font_selector = ttk.Combobox(
            font_card, textvariable=self.font_choice, values=list(self.font_choices), state="readonly",
            style="Cipher.TCombobox", font=("Segoe UI", 10),
        )
        self.font_selector.grid(row=0, column=1, sticky="ew")
        self.font_selector.bind("<<ComboboxSelected>>", self.select_font)
        self.font_selector.bind("<Button-1>", lambda _event: self.refresh_fonts())
        self._button(font_card, "Import fonts", self.import_fonts, secondary=True).grid(
            row=0, column=2, padx=(10, 0)
        )

        workspace = tk.Frame(page, bg=self.BG)
        workspace.grid(row=1, column=0, sticky="nsew")
        workspace.grid_columnconfigure(0, weight=1, uniform="alphabet")
        workspace.grid_columnconfigure(1, weight=1, uniform="alphabet")
        workspace.grid_rowconfigure(0, weight=1)

        plain_card = self._card(workspace, "PLAIN ENGLISH")
        plain_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        plain_card.grid_rowconfigure(1, weight=1)
        plain_card.grid_rowconfigure(2, minsize=106)
        self.alphabet_plain = self._text_box(plain_card)
        self.alphabet_plain.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 14))
        self.alphabet_plain.bind("<KeyRelease>", lambda _event: self.sync_alphabet(self.alphabet_plain))
        plain_actions = tk.Frame(plain_card, bg=self.PANEL)
        plain_actions.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 16))
        plain_actions.grid_columnconfigure(0, weight=1)
        self._button(
            plain_actions, "Copy English", lambda: self.copy_text(self.alphabet_plain, self.alphabet_status)
        ).grid(row=0, column=1)

        custom_card = self._card(workspace, "CUSTOM ALPHABET", self.alphabet_status)
        custom_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        custom_card.grid_rowconfigure(1, weight=1)
        custom_card.grid_rowconfigure(2, minsize=106)
        self.alphabet_custom = tk.Text(
            custom_card, wrap="word", undo=True, bg=self.FIELD, fg=self.ACCENT,
            insertbackground=self.ACCENT, selectbackground="#4b3b22", relief="flat",
            padx=16, pady=14, width=1, height=1, font=(self.selected_font_family(), 30),
        )
        self.alphabet_custom.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 14))
        self.alphabet_custom.bind("<KeyRelease>", lambda _event: self.sync_alphabet(self.alphabet_custom))
        custom_actions = tk.Frame(custom_card, bg=self.PANEL)
        custom_actions.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 16))
        custom_actions.grid_columnconfigure(0, weight=1)
        self._button(custom_actions, "Clear", self.clear_alphabet, secondary=True).grid(row=0, column=0, sticky="w")
        self._button(
            custom_actions, "Copy letters", lambda: self.copy_text(self.alphabet_custom, self.alphabet_status)
        ).grid(row=0, column=1)
        return page

    def _build_ascii_page(self, parent: tk.Widget) -> tk.Frame:
        page = tk.Frame(parent, bg=self.BG)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        controls = tk.Frame(page, bg=self.PANEL, padx=16, pady=12)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        tk.Label(controls, text="WIDTH", bg=self.PANEL, fg=self.MUTED, font=("Segoe UI Semibold", 8)).grid(row=0, column=0)
        tk.Spinbox(
            controls, from_=20, to=300, textvariable=self.ascii_width, width=5,
            bg=self.FIELD, fg=self.TEXT, buttonbackground=self.FIELD, relief="flat",
        ).grid(row=0, column=1, padx=(6, 14), ipady=4)
        tk.Label(controls, text="BRIGHTNESS", bg=self.PANEL, fg=self.MUTED, font=("Segoe UI Semibold", 8)).grid(row=0, column=2)
        tk.Scale(
            controls, from_=0.25, to=2.0, resolution=0.05, variable=self.ascii_brightness,
            orient="horizontal", showvalue=True, digits=3, length=110, bg=self.PANEL, fg=self.TEXT,
            troughcolor=self.FIELD, highlightthickness=0,
        ).grid(row=0, column=3, padx=(4, 10))
        tk.Label(controls, text="CONTRAST", bg=self.PANEL, fg=self.MUTED, font=("Segoe UI Semibold", 8)).grid(row=0, column=4)
        tk.Scale(
            controls, from_=0.25, to=2.0, resolution=0.05, variable=self.ascii_contrast,
            orient="horizontal", showvalue=True, digits=3, length=110, bg=self.PANEL, fg=self.TEXT,
            troughcolor=self.FIELD, highlightthickness=0,
        ).grid(row=0, column=5, padx=(4, 10))
        ttk.Combobox(
            controls, textvariable=self.ascii_charset, values=list(ASCII_SETS), state="readonly",
            style="Cipher.TCombobox", width=10,
        ).grid(row=0, column=6, padx=(0, 8))
        tk.Checkbutton(
            controls, text="Invert", variable=self.ascii_invert, bg=self.PANEL, fg=self.TEXT,
            selectcolor=self.FIELD, activebackground=self.PANEL, activeforeground=self.TEXT,
        ).grid(row=0, column=7)
        self._button(controls, "Apply", self.render_ascii).grid(row=0, column=8, padx=(8, 0))
        tk.Label(controls, text="PNG FONT SIZE", bg=self.PANEL, fg=self.MUTED, font=("Segoe UI Semibold", 8)).grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))
        tk.Spinbox(
            controls, from_=8, to=48, textvariable=self.ascii_font_size, width=5,
            bg=self.FIELD, fg=self.TEXT, buttonbackground=self.FIELD, relief="flat",
        ).grid(row=1, column=2, sticky="w", pady=(10, 0), ipady=4)
        self._button(controls, "Text color", lambda: self.choose_ascii_color(True), secondary=True).grid(row=1, column=3, pady=(10, 0))
        self._button(controls, "Background", lambda: self.choose_ascii_color(False), secondary=True).grid(row=1, column=4, columnspan=2, pady=(10, 0))
        self._button(controls, "Choose font", self.choose_ascii_font, secondary=True).grid(row=1, column=6, columnspan=2, pady=(10, 0))

        workspace = tk.Frame(page, bg=self.BG)
        workspace.grid(row=1, column=0, sticky="nsew")
        workspace.grid_columnconfigure(0, weight=1, uniform="ascii")
        workspace.grid_columnconfigure(1, weight=1, uniform="ascii")
        workspace.grid_rowconfigure(0, weight=1)
        preview_card = self._card(workspace, "IMAGE PREVIEW")
        preview_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        preview_card.grid_rowconfigure(1, weight=1)
        self.image_preview = tk.Label(
            preview_card, text="Drop or import an image", bg=self.FIELD, fg=self.MUTED,
            width=1, font=("Segoe UI", 10),
        )
        self.image_preview.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 16))
        self.image_preview.bind("<Configure>", self.resize_image_preview)

        card = self._card(workspace, "ASCII ART", self.ascii_status)
        card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        card.grid_rowconfigure(1, weight=1)
        self.ascii_output = self._text_box(card, readonly=True, accent=True)
        self.ascii_output.configure(wrap="none")
        self.ascii_output.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 14))
        actions = tk.Frame(card, bg=self.PANEL)
        actions.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 16))
        actions.grid_columnconfigure(1, weight=1)
        self._button(actions, "Import image", self.import_image).grid(row=0, column=0)
        self._button(actions, "Save text", self.save_ascii_text, secondary=True).grid(row=0, column=2)
        self._button(actions, "Save PNG", self.save_ascii_png, secondary=True).grid(row=0, column=3, padx=(8, 0))
        self._button(
            actions, "Clear", lambda: self.clear_ascii(), secondary=True
        ).grid(row=0, column=4, padx=(8, 0))
        self._button(
            actions, "Copy ASCII", lambda: self.copy_text(self.ascii_output, self.ascii_status)
        ).grid(row=0, column=5, padx=(8, 0))
        for widget in (page, self.image_preview, self.ascii_output):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self.drop_files)
        return page

    def _build_encoding_page(self, parent: tk.Widget) -> tk.Frame:
        page = tk.Frame(parent, bg=self.BG)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        controls = tk.Frame(page, bg=self.PANEL, padx=20, pady=14)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        ttk.Combobox(
            controls, textvariable=self.encoding_method, values=("Base64", "Hex", "URL"),
            state="readonly", style="Cipher.TCombobox", width=12,
        ).grid(row=0, column=0)
        ttk.Combobox(
            controls, textvariable=self.encoding_direction, values=("Encode", "Decode"),
            state="readonly", style="Cipher.TCombobox", width=10,
        ).grid(row=0, column=1, padx=(8, 0))
        self._button(controls, "Transform", self.run_encoding).grid(row=0, column=2, padx=(8, 0))

        workspace = tk.Frame(page, bg=self.BG)
        workspace.grid(row=1, column=0, sticky="nsew")
        workspace.grid_columnconfigure(0, weight=1, uniform="encoding")
        workspace.grid_columnconfigure(1, weight=1, uniform="encoding")
        workspace.grid_rowconfigure(0, weight=1)
        input_card = self._card(workspace, "INPUT")
        input_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        input_card.grid_rowconfigure(1, weight=1)
        self.encoding_input = self._text_box(input_card)
        self.encoding_input.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 16))
        output_card = self._card(workspace, "OUTPUT", self.encoding_status)
        output_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        output_card.grid_rowconfigure(1, weight=1)
        self.encoding_output = self._text_box(output_card, readonly=True, accent=True)
        self.encoding_output.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 12))
        actions = tk.Frame(output_card, bg=self.PANEL)
        actions.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 16))
        actions.grid_columnconfigure(0, weight=1)
        self._button(actions, "Copy", lambda: self.copy_text(self.encoding_output, self.encoding_status)).grid(row=0, column=1)
        return page

    def _build_settings_page(self, parent: tk.Widget) -> tk.Frame:
        page = tk.Frame(parent, bg=self.BG)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        controls = tk.Frame(page, bg=self.PANEL, padx=20, pady=16)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        tk.Label(controls, text="THEME", bg=self.PANEL, fg=self.MUTED, font=("Segoe UI Semibold", 9)).grid(row=0, column=0)
        ttk.Combobox(
            controls, textvariable=self.theme_choice, values=list(THEMES), state="readonly",
            style="Cipher.TCombobox", width=10,
        ).grid(row=0, column=1, padx=(8, 18))
        tk.Label(controls, text="EDITOR SIZE", bg=self.PANEL, fg=self.MUTED, font=("Segoe UI Semibold", 9)).grid(row=0, column=2)
        tk.Spinbox(
            controls, from_=8, to=24, textvariable=self.editor_font_size, width=4,
            bg=self.FIELD, fg=self.TEXT, buttonbackground=self.FIELD, relief="flat",
        ).grid(row=0, column=3, padx=(8, 18), ipady=4)
        self._button(controls, "Apply", self.apply_settings).grid(row=0, column=4)

        history = self._card(page, "RECENT FILE PATHS")
        history.grid(row=1, column=0, sticky="nsew")
        history.grid_rowconfigure(1, weight=1)
        self.recent_list = tk.Listbox(
            history, bg=self.FIELD, fg=self.TEXT, selectbackground=self.ACCENT,
            relief="flat", font=("Cascadia Mono", 10),
        )
        self.recent_list.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 12))
        self.recent_list.bind("<Double-Button-1>", self.open_recent)
        actions = tk.Frame(history, bg=self.PANEL)
        actions.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 16))
        tk.Checkbutton(
            actions, text="Remember file paths", variable=self.history_enabled, command=self.toggle_history,
            bg=self.PANEL, fg=self.TEXT, selectcolor=self.FIELD,
            activebackground=self.PANEL, activeforeground=self.TEXT,
        ).grid(row=0, column=0)
        self._button(actions, "Clear history", self.clear_history, secondary=True).grid(row=0, column=1, padx=(12, 0))
        self.update_recent_list()
        return page

    def _card(self, parent: tk.Widget, title: str, detail: tk.StringVar | None = None) -> tk.Frame:
        card = tk.Frame(parent, bg=self.PANEL)
        card.grid_columnconfigure(0, weight=1)
        top = tk.Frame(card, bg=self.PANEL)
        top.grid(row=0, column=0, sticky="ew", padx=18, pady=16)
        top.grid_columnconfigure(0, weight=1)
        tk.Label(top, text=title, bg=self.PANEL, fg=self.TEXT, font=("Segoe UI Semibold", 10)).grid(
            row=0, column=0, sticky="w"
        )
        if detail:
            tk.Label(top, textvariable=detail, bg=self.PANEL, fg=self.MUTED, font=("Segoe UI", 8)).grid(
                row=0, column=1, sticky="e"
            )
        return card

    def _text_box(self, parent: tk.Widget, readonly: bool = False, accent: bool = False) -> tk.Text:
        return tk.Text(
            parent, wrap="word", undo=not readonly, bg=self.FIELD,
            fg=self.ACCENT if accent else self.TEXT, insertbackground=self.ACCENT,
            selectbackground="#344466", relief="flat", padx=16, pady=14, width=1, height=1,
            font=("Cascadia Mono", self.editor_font_size.get()), state="disabled" if readonly else "normal",
        )

    def _button(self, parent: tk.Widget, text: str, command, secondary: bool = False) -> tk.Button:
        return tk.Button(
            parent, text=text, command=command, bg=self.FIELD if secondary else self.ACCENT,
            fg=self.TEXT if secondary else self.BG,
            activebackground="#25324d" if secondary else "#ffd078",
            activeforeground=self.TEXT if secondary else self.BG, relief="flat", cursor="hand2",
            padx=14, pady=8, font=("Segoe UI Semibold", 9),
        )

    def show_page(self, name: str) -> None:
        self.current_page = name
        self.pages[name].tkraise()
        for page_name, button in self.nav_buttons.items():
            active = page_name == name
            button.configure(bg=self.ACCENT if active else self.FIELD, fg=self.BG if active else self.TEXT)
        {
            "encrypt": self.crypto_input,
            "hash": self.hash_input,
            "alphabet": self.alphabet_plain,
            "ascii": self.ascii_output,
            "encoding": self.encoding_input,
            "settings": self.recent_list,
        }[name].focus_set()

    def selected_font_family(self) -> str:
        return self.font_choices.get(self.font_choice.get(), "Segoe UI")

    def _store_font(self, source: Path, force: bool = False) -> Path:
        suffix = source.suffix.lower()
        if suffix not in FONT_EXTENSIONS:
            raise ValueError(f"Unsupported font type: {suffix or 'no extension'}")
        font_families(source)
        FONT_DIR.mkdir(exist_ok=True)

        if suffix in {".woff", ".woff2"}:
            font = TTFont(source)
            try:
                extension = ".otf" if font.sfntVersion == "OTTO" else ".ttf"
                destination = FONT_DIR / f"{source.stem}{extension}"
                if force or not destination.exists() or destination.stat().st_mtime < source.stat().st_mtime:
                    font.flavor = None
                    font.save(destination)
                return destination
            finally:
                font.close()

        destination = FONT_DIR / source.name
        if source.resolve() == destination.resolve():
            return source
        if force or not destination.exists() or destination.stat().st_mtime < source.stat().st_mtime:
            shutil.copy2(source, destination)
        return destination

    def refresh_fonts(self) -> None:
        FONT_DIR.mkdir(exist_ok=True)
        for source in list(APP_DIR.iterdir()) + list(FONT_DIR.glob("*.woff*")):
            if source.is_file() and source.suffix.lower() in FONT_EXTENSIONS:
                try:
                    self._store_font(source)
                except (KeyError, OSError, TTLibError, ValueError):
                    pass

        choices: dict[str, str] = {}
        for path in sorted(FONT_DIR.iterdir(), key=lambda item: item.name.lower()):
            if not path.is_file() or path.suffix.lower() not in DESKTOP_FONT_EXTENSIONS:
                continue
            try:
                families = font_families(path)
            except (KeyError, OSError, TTLibError, ValueError):
                continue
            resolved = path.resolve()
            if os.name == "nt" and resolved not in self.loaded_font_paths:
                if ctypes.windll.gdi32.AddFontResourceExW(str(resolved), 0x10, 0):
                    self.loaded_font_paths.add(resolved)
            choices[path.name] = families[0]

        current = self.font_choice.get()
        self.font_choices = choices
        if current not in choices:
            preferred = next((label for label, family in choices.items() if family == "Libre Barcode 39"), "")
            self.font_choice.set(preferred or next(iter(choices), ""))
        if hasattr(self, "font_selector"):
            self.font_selector.configure(values=list(choices))
            self.select_font()
        elif choices:
            self.alphabet_status.set(f"{self.selected_font_family()} / ready")
        else:
            self.alphabet_status.set("No compatible fonts found")

    def import_fonts(self) -> None:
        selected = filedialog.askopenfilenames(
            parent=self,
            title="Import fonts into BOne Tool",
            filetypes=(
                ("Font files", "*.ttf *.otf *.ttc *.woff *.woff2"),
                ("TrueType fonts", "*.ttf *.ttc"),
                ("OpenType fonts", "*.otf"),
                ("Web fonts", "*.woff *.woff2"),
                ("All files", "*.*"),
            ),
        )
        if not selected:
            return
        imported, errors = 0, []
        for filename in selected:
            try:
                self._store_font(Path(filename), force=True)
                imported += 1
            except (KeyError, OSError, TTLibError, ValueError) as error:
                errors.append(f"{Path(filename).name}: {error}")
        self.refresh_fonts()
        self.alphabet_status.set(f"Imported {imported} font file{'s' if imported != 1 else ''}")
        if errors:
            messagebox.showwarning("Some fonts were not imported", "\n".join(errors), parent=self)

    def select_font(self, _event=None) -> None:
        family = self.selected_font_family()
        if hasattr(self, "alphabet_custom"):
            self.alphabet_custom.configure(font=(family, 30))
            self.alphabet_status.set(f"{family} / {len(self._get(self.alphabet_custom)):,} characters")

    @staticmethod
    def _get(widget: tk.Text) -> str:
        return widget.get("1.0", "end-1c")

    @staticmethod
    def _set(widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def encrypt(self) -> None:
        text = self._get(self.crypto_input)
        if not text:
            self.crypto_status.set("Enter a message first")
            return
        try:
            self._set(self.crypto_output, encrypt_text(text, self.password.get()))
            self.crypto_status.set("Encrypted / OC1")
        except ValueError as error:
            self.crypto_status.set(str(error))

    def import_text_file(self, filename: str | None = None) -> None:
        filename = filename or filedialog.askopenfilename(
            parent=self, title="Import text", filetypes=(("Text files", "*.txt *.oc1"), ("All files", "*.*"))
        )
        if not filename:
            return
        try:
            text = Path(filename).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            messagebox.showerror("Text import failed", str(error), parent=self)
            return
        self.crypto_input.delete("1.0", "end")
        self.crypto_input.insert("1.0", text)
        self.crypto_status.set(f"Imported {Path(filename).name}")
        self.remember_file(filename)

    def save_crypto_output(self) -> None:
        self.save_text(self._get(self.crypto_output), "Save result", self.crypto_status)

    def show_qr(self) -> None:
        value = self._get(self.crypto_output)
        if not value:
            self.crypto_status.set("Create a result first")
            return
        try:
            image = qrcode.make(value).convert("RGB")
        except (ValueError, qrcode.exceptions.DataOverflowError) as error:
            messagebox.showerror("QR generation failed", str(error), parent=self)
            return
        window = tk.Toplevel(self)
        window.title("BOne Tool QR")
        window.configure(bg=self.BG, padx=16, pady=16)
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

        self._button(window, "Save PNG", save).pack(pady=(12, 0))

    def decrypt(self) -> None:
        token = self._get(self.crypto_input).strip()
        try:
            self._set(self.crypto_output, decrypt_text(token, self.password.get()))
            self.crypto_status.set("Decrypted and authenticated")
        except ValueError as error:
            self._set(self.crypto_output, "")
            self.crypto_status.set(str(error))

    def toggle_password(self) -> None:
        hidden = self.password_entry.cget("show") == "*"
        self.password_entry.configure(show="" if hidden else "*")
        self.show_password_button.configure(text="Hide" if hidden else "Show")

    def use_crypto_output(self) -> None:
        value = self._get(self.crypto_output)
        if value:
            self.crypto_input.delete("1.0", "end")
            self.crypto_input.insert("1.0", value)
            self.crypto_status.set("Result moved to input")

    def copy_crypto_output(self) -> None:
        self.copy_text(self.crypto_output, self.crypto_status)

    def copy_text(self, widget: tk.Text, status: tk.StringVar) -> None:
        value = self._get(widget)
        if value:
            self.clipboard_clear()
            self.clipboard_append(value)
            status.set("Copied to clipboard")

    def save_text(self, value: str, title: str, status: tk.StringVar) -> None:
        if not value:
            status.set("Nothing to save")
            return
        filename = filedialog.asksaveasfilename(
            parent=self, title=title, defaultextension=".txt",
            filetypes=(("Text files", "*.txt"), ("All files", "*.*")),
        )
        if not filename:
            return
        try:
            Path(filename).write_text(value, encoding="utf-8")
        except OSError as error:
            messagebox.showerror("Save failed", str(error), parent=self)
            return
        status.set(f"Saved {Path(filename).name}")
        self.remember_file(filename)

    def clear_crypto(self) -> None:
        self.crypto_input.delete("1.0", "end")
        self._set(self.crypto_output, "")
        self.password.set("")
        self.crypto_status.set("AES-256-GCM / Scrypt / OC1")
        self.crypto_input.focus_set()

    def _on_hash_input(self, _event=None) -> None:
        text = self._get(self.hash_input)
        self.hash_count.set(f"{len(text):,} characters / {len(text.encode('utf-8')):,} bytes")
        self.generate_hash()

    def generate_hash(self) -> None:
        text = self._get(self.hash_input)
        digest = hash_text(text, self.algorithm.get()) if text else ""
        self._set(self.hash_output, digest)
        self.hash_status.set("Ready" if not text else f"{self.algorithm.get().upper()} / {len(digest)} chars")

    def hash_files(self) -> None:
        filenames = filedialog.askopenfilenames(parent=self, title="Hash files")
        if filenames:
            self.display_file_hashes(filenames)

    def display_file_hashes(self, filenames) -> None:
        results = []
        try:
            for filename in filenames:
                digest = hash_file(filename, self.algorithm.get())
                results.append(digest if len(filenames) == 1 else f"{digest}  {filename}")
                self.remember_file(filename)
        except OSError as error:
            messagebox.showerror("File hashing failed", str(error), parent=self)
            return
        self._set(self.hash_output, "\n".join(results))
        self.hash_status.set(f"{len(results)} file{'s' if len(results) != 1 else ''} / {self.algorithm.get().upper()}")

    def verify_file(self) -> None:
        expected = self.verify_value.get().strip().lower()
        if not expected:
            self.hash_status.set("Enter the expected digest first")
            return
        filename = filedialog.askopenfilename(parent=self, title="Verify file")
        if not filename:
            return
        try:
            actual = hash_file(filename, self.algorithm.get())
        except OSError as error:
            messagebox.showerror("File verification failed", str(error), parent=self)
            return
        self._set(self.hash_output, actual)
        self.hash_status.set("File digest matches" if hmac.compare_digest(actual, expected) else "File digest does not match")
        self.remember_file(filename)

    def verify_hash(self) -> None:
        digest = self._get(self.hash_output)
        expected = self.verify_value.get().strip().lower()
        if not digest or not expected:
            self.hash_status.set("Enter text and a digest first")
            return
        self.hash_status.set("Digest matches" if hmac.compare_digest(digest, expected) else "Digest does not match")

    def clear_hash(self) -> None:
        self.hash_input.delete("1.0", "end")
        self.verify_value.set("")
        self._set(self.hash_output, "")
        self.hash_count.set("0 characters / 0 bytes")
        self.hash_status.set("Ready")
        self.hash_input.focus_set()

    def sync_alphabet(self, source: tk.Text) -> None:
        target = self.alphabet_custom if source is self.alphabet_plain else self.alphabet_plain
        value = self._get(source)
        target.delete("1.0", "end")
        target.insert("1.0", value)
        self.alphabet_status.set(f"{self.selected_font_family()} / {len(value):,} characters")

    def clear_alphabet(self) -> None:
        self.alphabet_plain.delete("1.0", "end")
        self.alphabet_custom.delete("1.0", "end")
        self.alphabet_status.set(f"{self.selected_font_family()} / ready")
        self.alphabet_plain.focus_set()

    def import_image(self) -> None:
        filename = filedialog.askopenfilename(
            parent=self,
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
            self._set(self.ascii_output, "")
            self.ascii_status.set("Could not read image")
            messagebox.showerror("Image import failed", str(error), parent=self)
            return
        self.current_image = Path(filename)
        self.preview_image = preview
        self.resize_image_preview()
        self.remember_file(filename)
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
        self._set(self.ascii_output, result)
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
        self.save_text(self._get(self.ascii_output), "Save ASCII art", self.ascii_status)

    def save_ascii_png(self) -> None:
        value = self._get(self.ascii_output)
        try:
            image = ascii_to_image(
                value, self.ascii_font_size.get(), self.ascii_foreground.get(),
                self.ascii_background.get(), self.ascii_font_path,
            )
        except (OSError, ValueError, tk.TclError) as error:
            messagebox.showerror("ASCII export failed", str(error), parent=self)
            return
        filename = filedialog.asksaveasfilename(
            parent=self, title="Save ASCII image", defaultextension=".png",
            filetypes=(("PNG image", "*.png"),),
        )
        if filename:
            try:
                image.save(filename)
            except OSError as error:
                messagebox.showerror("ASCII export failed", str(error), parent=self)
                return
            self.ascii_status.set(f"Saved {Path(filename).name}")
            self.remember_file(filename)

    def choose_ascii_color(self, foreground: bool) -> None:
        variable = self.ascii_foreground if foreground else self.ascii_background
        color = colorchooser.askcolor(variable.get(), parent=self, title="Choose ASCII color")[1]
        if color:
            variable.set(color)

    def choose_ascii_font(self) -> None:
        filename = filedialog.askopenfilename(
            parent=self, title="Choose ASCII font",
            filetypes=(("Font files", "*.ttf *.otf"), ("All files", "*.*")),
        )
        if filename:
            self.ascii_font_path = filename
            self.ascii_status.set(f"PNG font: {Path(filename).name}")

    def clear_ascii(self) -> None:
        self._set(self.ascii_output, "")
        self.current_image = None
        self.preview_image = None
        self.preview_photo = None
        self.image_preview.configure(image="", text="Drop or import an image")
        self.ascii_status.set("Import an image to begin")

    def run_encoding(self) -> None:
        try:
            result = transform_text(
                self._get(self.encoding_input), self.encoding_method.get(),
                self.encoding_direction.get() == "Decode",
            )
        except (ValueError, UnicodeError, binascii.Error) as error:
            self._set(self.encoding_output, "")
            self.encoding_status.set(f"Invalid input: {error}")
            return
        self._set(self.encoding_output, result)
        self.encoding_status.set(f"{self.encoding_method.get()} {self.encoding_direction.get().lower()}d")

    def drop_files(self, event) -> None:
        filenames = self.tk.splitlist(event.data)
        if not filenames:
            return
        image_extensions = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
        first = filenames[0]
        suffix = Path(first).suffix.lower()
        if suffix in image_extensions:
            self.show_page("ascii")
            self.load_image(first)
        elif suffix in {".txt", ".oc1"}:
            self.show_page("encrypt")
            self.import_text_file(first)
        else:
            self.show_page("hash")
            self.display_file_hashes(filenames)

    def apply_settings(self) -> None:
        try:
            editor_size = self.editor_font_size.get()
        except tk.TclError:
            messagebox.showerror("Invalid setting", "Editor size must be a number from 8 to 24.", parent=self)
            return
        if not 8 <= editor_size <= 24:
            messagebox.showerror("Invalid setting", "Editor size must be from 8 to 24.", parent=self)
            return
        old_colors = {name: getattr(self, name) for name in THEMES["Dark"]}
        new_colors = THEMES[self.theme_choice.get()]
        replacements = {old_colors[name]: new_colors[name] for name in old_colors}
        for name, value in new_colors.items():
            setattr(self, name, value)
        self._recolor_widget(self, replacements)
        for widget in self._all_widgets(self):
            if isinstance(widget, tk.Text) and widget is not self.alphabet_custom:
                widget.configure(font=("Cascadia Mono", editor_size))
        self._style_widgets()
        self.show_page(self.current_page)
        self.save_settings()

    def _recolor_widget(self, widget: tk.Widget, replacements: dict[str, str]) -> None:
        for option in ("background", "foreground", "insertbackground", "selectbackground", "activebackground", "activeforeground", "troughcolor"):
            if option in widget.keys():
                current = str(widget.cget(option))
                if current in replacements:
                    widget.configure(**{option: replacements[current]})
        for child in widget.winfo_children():
            self._recolor_widget(child, replacements)

    @staticmethod
    def _all_widgets(parent: tk.Widget):
        for child in parent.winfo_children():
            yield child
            yield from BOneTool._all_widgets(child)

    def save_settings(self) -> None:
        settings = {
            "theme": self.theme_choice.get(),
            "editor_font_size": self.editor_font_size.get(),
            "history_enabled": self.history_enabled.get(),
        }
        if self.history_enabled.get():
            settings["recent_files"] = self.recent_files
        try:
            SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        except OSError as error:
            messagebox.showerror("Settings could not be saved", str(error), parent=self)

    def remember_file(self, filename: str | Path) -> None:
        if not self.history_enabled.get():
            return
        path = str(Path(filename).resolve())
        self.recent_files = [path, *(item for item in self.recent_files if item != path)][:10]
        self.update_recent_list()
        self.save_settings()

    def update_recent_list(self) -> None:
        if not hasattr(self, "recent_list"):
            return
        self.recent_list.delete(0, "end")
        for filename in self.recent_files:
            self.recent_list.insert("end", filename)

    def toggle_history(self) -> None:
        if not self.history_enabled.get():
            self.recent_files.clear()
            self.update_recent_list()
        self.save_settings()

    def clear_history(self) -> None:
        self.recent_files.clear()
        self.update_recent_list()
        self.save_settings()

    def open_recent(self, _event=None) -> None:
        selected = self.recent_list.curselection()
        if not selected:
            return
        filename = self.recent_list.get(selected[0])
        if not Path(filename).is_file():
            messagebox.showerror("File not found", filename, parent=self)
            return
        suffix = Path(filename).suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}:
            self.show_page("ascii")
            self.load_image(filename)
        elif suffix in {".txt", ".oc1"}:
            self.show_page("encrypt")
            self.import_text_file(filename)
        else:
            self.show_page("hash")
            self.display_file_hashes((filename,))

    def destroy(self) -> None:
        if os.name == "nt":
            for path in self.loaded_font_paths:
                ctypes.windll.gdi32.RemoveFontResourceExW(str(path), 0x10, 0)
        super().destroy()


if __name__ == "__main__":
    BOneTool().mainloop()
