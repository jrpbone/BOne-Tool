import json
import unittest
from pathlib import Path
from unittest.mock import patch

from main import BOneTool, THEMES
from modules.key_dialog import KeyDialog
from tests.temp_directory import temporary_directory


class ThemeDialogTest(unittest.TestCase):
    def test_theme_toggle_dialog_actions_and_saved_preference(self):
        with temporary_directory() as directory, patch("main.SETTINGS_PATH", Path(directory) / "settings.json"), \
                patch("modules.crypto_chat.default_chat_directory", return_value=Path(directory) / "chats"), \
                patch.object(BOneTool, "refresh_fonts"):
            app = BOneTool()
            app.withdraw()
            try:
                chat = app.features["encrypt"].chat
                chat.messages = [{"operation": "decrypt", "text": "Example"}]
                chat.render()
                dialog = KeyDialog(app, "Unlock conversation", "Enter your key.", "Unlock")
                for theme in ("Light", "Dark", "Light"):
                    app.toggle_theme()
                    self.assertEqual(app.BG, THEMES[theme]["BG"])
                    self.assertEqual(dialog.cget("bg"), app.BG)
                    self.assertEqual(dialog.entry.cget("bg"), app.FIELD)
                    self.assertEqual(dialog.entry.cget("selectbackground"), app.SELECTION)
                    self.assertEqual(chat.bubble_widgets[0].cget("bg"), app.FIELD)
                    self.assertEqual(app.features["encrypt"].crypto_input.cget("fg"), app.TEXT)
                    self.assertEqual(json.loads((Path(directory) / "settings.json").read_text())["theme"], theme)
                dialog.submit()
                self.assertTrue(dialog.winfo_exists())
                self.assertTrue(dialog.error.get())
                dialog.entry.insert(0, "test-key")
                self.assertEqual(dialog.entry.cget("show"), "*")
                dialog.toggle_visibility()
                self.assertEqual(dialog.entry.cget("show"), "")
                dialog.toggle_visibility()
                self.assertEqual(dialog.entry.cget("show"), "*")
                dialog.submit()
                self.assertEqual(dialog.result, "test-key")
                confirmation = KeyDialog(app, "Confirm your key", "Type your key again.")
                self.assertEqual(confirmation.entry.cget("bg"), THEMES["Light"]["FIELD"])
                confirmation.entry.insert(0, "cancelled-key")
                confirmation.cancel()
                self.assertIsNone(confirmation.result)
            finally:
                app.destroy()
            restored = BOneTool()
            restored.withdraw()
            try:
                self.assertEqual(restored.theme_choice.get(), "Light")
                self.assertEqual(restored.cget("bg"), THEMES["Light"]["BG"])
            finally:
                restored.destroy()
