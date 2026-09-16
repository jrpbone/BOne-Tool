import ctypes
import json
import os
import shutil
import sys
import webbrowser
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from fontTools.ttLib import TTCollection, TTFont, TTLibError
from modules.alphabet_print import build_print_pdf
from tkinterdnd2 import TkinterDnD
from modules.registry import FEATURE_TYPES
# Compatibility exports for existing scripts; new code imports feature modules directly.
from modules.crypto import MAGIC, SALT_BYTES, NONCE_BYTES, password_strength, _derive_key, encrypt_text, decrypt_text
from modules.hashing import ALGORITHMS, hash_text, hash_file
from modules.image_ascii import ASCII_CHARS, ASCII_SETS, image_to_ascii, ascii_to_image
from modules.encoding import transform_text


BUNDLE_DIR = Path(__file__).resolve().parent
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else BUNDLE_DIR
FONT_DIR = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "BOneTool" / "fonts"
    if getattr(sys, "frozen", False) else APP_DIR / "fonts"
)
FONT_EXTENSIONS = {".ttf", ".otf", ".ttc", ".woff", ".woff2"}
DESKTOP_FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}
THEMES = {
    "Dark": {"BG": "#0b1020", "PANEL": "#121a2d", "FIELD": "#182238", "TEXT": "#eef2ff", "MUTED": "#8d9ab5", "ACCENT": "#f6b94a"},
    "Light": {"BG": "#eef1f6", "PANEL": "#ffffff", "FIELD": "#dfe5ee", "TEXT": "#182238", "MUTED": "#61708a", "ACCENT": "#c87a00"},
}
SETTINGS_PATH = Path.home() / ".bonecipher.json"


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
        self.current_page = "encrypt"
        self.recent_files = recent_files

        self.font_choice = tk.StringVar()
        self.alphabet_status = tk.StringVar(value="Loading fonts...")
        self.theme_choice = tk.StringVar(value=theme)
        self.editor_font_size = tk.IntVar(value=editor_size)
        self.history_enabled = tk.BooleanVar(value=self.settings.get("history_enabled") is True)
        self.features = {feature.page_id: feature(self) for feature in FEATURE_TYPES}
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
        workspaces = [(feature.page_id, feature.title, feature.build) for feature in self.features.values()]
        workspaces.insert(2, ("alphabet", "Alphabet", self._build_alphabet_page))
        workspaces.append(("settings", "Settings", self._build_settings_page))
        self.nav_buttons = {
            key: self._button(nav, title, lambda key=key: self.show_page(key), secondary=key != "encrypt")
            for key, title, _build in workspaces
        }
        for column, button in enumerate(self.nav_buttons.values()):
            button.grid(row=0, column=column, padx=(8 if column else 0, 0))

        pages = tk.Frame(shell, bg=self.BG)
        pages.grid(row=1, column=0, sticky="nsew")
        pages.grid_columnconfigure(0, weight=1)
        pages.grid_rowconfigure(0, weight=1)
        self.pages = {key: build(pages) for key, _title, build in workspaces}
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")


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
        self._button(custom_actions, "Print", self.print_alphabet).grid(row=1, column=1, pady=(8, 0))
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
        if name in self.features:
            self.features[name].focus()
        else:
            {"alphabet": self.alphabet_plain, "settings": self.recent_list}[name].focus_set()

    def selected_font_family(self) -> str:
        return self.font_choices.get(self.font_choice.get(), "Segoe UI")

    def _store_font(self, source: Path, force: bool = False) -> Path:
        suffix = source.suffix.lower()
        if suffix not in FONT_EXTENSIONS:
            raise ValueError(f"Unsupported font type: {suffix or 'no extension'}")
        font_families(source)
        FONT_DIR.mkdir(parents=True, exist_ok=True)

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
        FONT_DIR.mkdir(parents=True, exist_ok=True)
        if getattr(sys, "frozen", False):
            for bundled in (BUNDLE_DIR / "fonts").iterdir():
                destination = FONT_DIR / bundled.name
                if bundled.is_file() and not destination.exists():
                    shutil.copy2(bundled, destination)
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


    def sync_alphabet(self, source: tk.Text) -> None:
        target = self.alphabet_custom if source is self.alphabet_plain else self.alphabet_plain
        value = self._get(source)
        target.delete("1.0", "end")
        target.insert("1.0", value)
        self.alphabet_status.set(f"{self.selected_font_family()} / {len(value):,} characters")

    def print_alphabet(self) -> None:
        try:
            if self.font_choice.get() not in self.font_choices:
                raise ValueError("Select or import a custom font first.")
            value = self._get(self.alphabet_custom)
            if not value.strip():
                raise ValueError("Enter some text in the Alphabet workspace first.")
            filename = filedialog.asksaveasfilename(
                parent=self, title="Save alphabet PDF before printing", defaultextension=".pdf",
                initialfile="alphabet-print.pdf", filetypes=[("PDF document", "*.pdf")],
            )
            if not filename:
                return
            path = Path(filename)
            document = build_print_pdf(value, FONT_DIR / self.font_choice.get(), self.selected_font_family())
            path.write_bytes(document)
            self.alphabet_status.set("PDF saved / open it and choose Print (Ctrl+P)")
            try:
                if os.name == "nt":
                    os.startfile(str(path.resolve()))
                elif not webbrowser.open(path.resolve().as_uri()):
                    raise OSError("No PDF viewer could be opened.")
            except (OSError, webbrowser.Error):
                messagebox.showinfo("PDF saved", f"Saved to {path}. Open it in a PDF viewer and choose Print.", parent=self)
        except (KeyError, OSError, TTLibError, ValueError, webbrowser.Error) as error:
            messagebox.showerror("Printing failed", str(error), parent=self)

    def clear_alphabet(self) -> None:
        self.alphabet_plain.delete("1.0", "end")
        self.alphabet_custom.delete("1.0", "end")
        self.alphabet_status.set(f"{self.selected_font_family()} / ready")
        self.alphabet_plain.focus_set()


    def drop_files(self, event) -> None:
        filenames = self.tk.splitlist(event.data)
        if not filenames:
            return
        image_extensions = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
        first = filenames[0]
        suffix = Path(first).suffix.lower()
        if suffix in image_extensions:
            self.show_page("ascii")
            self.features["ascii"].load_image(first)
        elif suffix in {".txt", ".oc1"}:
            self.show_page("encrypt")
            self.features["encrypt"].import_text_file(first)
        else:
            self.show_page("hash")
            self.features["hash"].display_file_hashes(filenames)

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
            self.features["ascii"].load_image(filename)
        elif suffix in {".txt", ".oc1"}:
            self.show_page("encrypt")
            self.features["encrypt"].import_text_file(filename)
        else:
            self.show_page("hash")
            self.features["hash"].display_file_hashes((filename,))

    def destroy(self) -> None:
        if os.name == "nt":
            for path in self.loaded_font_paths:
                ctypes.windll.gdi32.RemoveFontResourceExW(str(path), 0x10, 0)
        super().destroy()


if __name__ == "__main__":
    BOneTool().mainloop()
