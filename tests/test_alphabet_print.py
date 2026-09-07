from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from fontTools.ttLib import TTCollection, TTFont

from modules.alphabet_print import build_print_pdf


FONT_DIR = Path(__file__).resolve().parents[1] / "fonts"


def font_family(path):
    with TTFont(path) as font:
        return font["name"].getDebugName(1)


class AlphabetPrintTest(unittest.TestCase):
    def test_bundled_fonts_generate_pdf(self):
        for path in FONT_DIR.iterdir():
            if path.suffix.lower() not in {".ttf", ".otf"}:
                continue
            with self.subTest(font=path.name):
                pdf = build_print_pdf("Hello <world> &\n  ABC", path, font_family(path))
                self.assertTrue(pdf.startswith(b"%PDF-"))
                self.assertIn(b"/Count 1", pdf)
                self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))

    def test_long_text_paginates(self):
        path = next(FONT_DIR.glob("*.ttf"))
        pdf = build_print_pdf("Hello\n" * 30, path, font_family(path))
        self.assertRegex(pdf, rb"/Count [2-9]\b")

    def test_collection_selects_requested_face(self):
        paths = list(FONT_DIR.glob("*.ttf"))
        collection = TTCollection()
        collection.fonts = [TTFont(path) for path in paths]
        try:
            buffer = BytesIO()
            collection.save(buffer)
            buffer.seek(0)
            with patch("modules.alphabet_print.TTCollection", return_value=TTCollection(buffer)):
                pdf = build_print_pdf("Hello", Path("faces.ttc"), font_family(paths[-1]))
                self.assertTrue(pdf.startswith(b"%PDF-"))
        finally:
            collection.close()

    def test_empty_text_and_missing_family(self):
        path = next(FONT_DIR.glob("*.ttf"))
        with self.assertRaisesRegex(ValueError, "Enter some text"):
            build_print_pdf(" \n", path, "anything")
        with self.assertRaisesRegex(ValueError, "no longer available"):
            build_print_pdf("Hello", path, "missing family")
