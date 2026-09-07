"""Create printable PDFs with custom lettering using the selected font face."""

from io import BytesIO
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont
from PIL import Image, ImageDraw, ImageFont


def build_print_pdf(text: str, font_path: Path, family: str) -> bytes:
    """Render A4 pages at 300 DPI, preserving fonts without system installation."""
    if not text.strip():
        raise ValueError("Enter some text in the Alphabet workspace first.")
    fonts = (TTCollection(font_path).fonts if font_path.suffix.lower() == ".ttc"
             else [TTFont(font_path)])
    try:
        selected = next((font for font in fonts if any(
            name.nameID in (1, 16) and name.toUnicode().strip() == family
            for name in font["name"].names
        )), None)
        if selected is None:
            raise ValueError("The selected font family is no longer available.")
        selected.flavor = None
        buffer = BytesIO()
        selected.save(buffer)
        buffer.seek(0)
        font = ImageFont.truetype(buffer, 125)  # 30 points at 300 DPI
    finally:
        for item in fonts:
            item.close()

    width, height, margin = 2480, 3508, 236
    ascent, descent = font.getmetrics()
    line_height = max(188, ascent + descent)
    pages = []
    page = Image.new("RGB", (width, height), "white")
    pages.append(page)
    draw = ImageDraw.Draw(page)
    y = margin

    def draw_line(line):
        nonlocal page, draw, y
        left, top, right, bottom = font.getbbox(line or " ", anchor="ls")
        occupied = max(line_height, bottom - top)
        if occupied > height - 2 * margin:
            raise ValueError("The selected font is too tall to fit on a page.")
        if y + occupied > height - margin:
            page = Image.new("RGB", (width, height), "white")
            pages.append(page)
            draw = ImageDraw.Draw(page)
            y = margin
        draw.text((margin - min(0, left), y - top), line, font=font, fill="black", anchor="ls")
        y += occupied

    try:
        for paragraph in text.replace("\r\n", "\n").replace("\r", "\n").expandtabs(4).split("\n"):
            line = ""
            for character in paragraph:
                candidate = line + character
                left, _, right, _ = font.getbbox(candidate)
                if right - min(0, left) > width - 2 * margin:
                    if not line:
                        raise ValueError("A character in the selected font is too wide for the page.")
                    draw_line(line)
                    line = character
                    char_left, _, char_right, _ = font.getbbox(character)
                    if char_right - min(0, char_left) > width - 2 * margin:
                        raise ValueError("A character in the selected font is too wide for the page.")
                else:
                    line = candidate
            draw_line(line)
        output = BytesIO()
        pages[0].save(output, format="PDF", resolution=300, save_all=True,
                      append_images=pages[1:], title="Custom Alphabet")
        return output.getvalue()
    finally:
        for page in pages:
            page.close()
