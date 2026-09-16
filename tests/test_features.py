"""Integration checks for the modular workspaces using a withdrawn Tk window."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from main import BOneTool
from modules.crypto import decrypt_text, encrypt_text
from modules.registry import FEATURE_TYPES
from tests.temp_directory import temporary_directory


class CryptoTest(unittest.TestCase):
    def test_unicode_round_trip_and_wrong_password(self):
        token = encrypt_text("Hello \u03b2", "test-password")
        self.assertEqual(decrypt_text(token, "test-password"), "Hello \u03b2")
        with self.assertRaises(ValueError):
            decrypt_text(token, "wrong-password")


class FeatureIntegrationTest(unittest.TestCase):
    def setUp(self):
        # Avoid loading installed fonts or the user's persisted preferences.
        with patch("main.SETTINGS_PATH", Path("__unused_test_settings__")), patch.object(BOneTool, "refresh_fonts"):
            self.app = BOneTool()
        self.app.withdraw()
        self.addCleanup(self.app.destroy)

    def test_registered_pages_and_actions(self):
        app = self.app
        for feature_type in FEATURE_TYPES:
            key = feature_type.page_id
            self.assertIn(key, app.pages)
            app.nav_buttons[key].invoke()
            self.assertEqual(app.current_page, key)
        crypto = app.features["encrypt"]
        crypto.password.set("test-password")
        crypto.crypto_input.insert("1.0", "hello")
        crypto.encrypt()
        crypto.use_crypto_output()
        crypto.decrypt()
        self.assertEqual(app._get(crypto.crypto_output), "hello")
        hashing = app.features["hash"]
        hashing.hash_input.insert("1.0", "hello")
        hashing._on_hash_input()
        hashing.verify_value.set(app._get(hashing.hash_output))
        hashing.verify_hash()
        self.assertEqual(hashing.hash_status.get(), "Digest matches")
        encoding = app.features["encoding"]
        encoding.encoding_input.insert("1.0", "hello")
        encoding.run_encoding()
        self.assertEqual(app._get(encoding.encoding_output), "aGVsbG8=")
        app.theme_choice.set("Light")
        with patch.object(app, "save_settings"):
            app.apply_settings()
        self.assertEqual(crypto.crypto_input.cget("bg"), app.FIELD)
        crypto.clear_crypto()
        hashing.clear_hash()

    def test_file_drop_and_recent_file_routing(self):
        app = self.app
        with temporary_directory() as directory:
            root = Path(directory)
            image = root / "image.png"
            text = root / "message.txt"
            binary = root / "data.bin"
            Image.new("RGB", (8, 8), "black").save(image)
            text.write_text("hello", encoding="utf-8")
            binary.write_bytes(b"hello")
            for path, key in ((image, "ascii"), (text, "encrypt"), (binary, "hash")):
                app.drop_files(SimpleNamespace(data=app.tk.call("list", str(path))))
                self.assertEqual(app.current_page, key)
                app.recent_list.delete(0, "end")
                app.recent_list.insert(0, str(path))
                app.recent_list.selection_set(0)
                app.open_recent()
                self.assertEqual(app.current_page, key)
            self.assertTrue(app._get(app.features["ascii"].ascii_output))
            self.assertEqual(app._get(app.features["encrypt"].crypto_input), "hello")
            self.assertEqual(len(app._get(app.features["hash"].hash_output)), 64)
            app.features["ascii"].clear_ascii()
