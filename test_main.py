import tempfile
import unittest
from pathlib import Path

from PIL import Image

from main import ascii_to_image, hash_file, image_to_ascii, password_strength, transform_text


class ImageToAsciiTest(unittest.TestCase):
    def test_maps_dark_and_light_pixels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dark = Path(directory) / "dark.png"
            light = Path(directory) / "light.png"
            Image.new("L", (2, 1), 0).save(dark)
            Image.new("L", (2, 1), 255).save(light)

            self.assertEqual(image_to_ascii(dark), "@@")
            self.assertEqual(image_to_ascii(light), "  ")

    def test_image_controls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "pixel.png"
            Image.new("L", (1, 1), 0).save(image)
            self.assertEqual(image_to_ascii(image, invert=True), " ")
        self.assertGreater(ascii_to_image("@@\n@@").width, 0)


class UtilityTest(unittest.TestCase):
    def test_encoding_round_trips(self) -> None:
        for method in ("Base64", "Hex", "URL"):
            encoded = transform_text("hello world!", method)
            self.assertEqual(transform_text(encoded, method, decode=True), "hello world!")

    def test_file_hash_and_password_strength(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hello.txt"
            path.write_bytes(b"hello")
            self.assertEqual(hash_file(path, "sha256"), "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")
        self.assertEqual(password_strength(""), "No password")
        self.assertEqual(password_strength("Correct-Horse-42"), "Strong")


if __name__ == "__main__":
    unittest.main()
