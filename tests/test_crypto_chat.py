import unittest
from pathlib import Path
from unittest.mock import patch

from main import BOneTool
from modules.chat_store import ChatStore, run_command
from modules.crypto import decrypt_text
from modules.session_reference import REFERENCE_ALPHABET
from tests.temp_directory import temporary_directory


class ChatStoreTest(unittest.TestCase):
    def test_as_is_matches_length_and_reopens(self):
        key = "conversation-key"
        with temporary_directory() as directory:
            store = ChatStore(Path(directory))
            session = store.create(key)
            messages = []
            for text in ("hello", "a", "hello world!", "line one\nline two", "\u03b2\U0001f600", "e\u0301"):
                result = run_command(text + " -e", key, "as_is", messages)
                self.assertEqual(len(result["text"]), len(text))
                self.assertNotIn("OC1.", result["text"])
                messages.append(result)
                self.assertEqual(run_command(result["text"] + " -d", key, messages=messages)["text"], text)
            store.save(session, key, messages)
            restored = ChatStore(Path(directory)).open(session, key)
            self.assertEqual(run_command(restored[0]["text"] + " -d", key, messages=restored)["text"], "hello")
            self.assertNotIn("hello", (Path(directory) / f"{session}.oc1").read_text())
            with self.assertRaises(ValueError):
                run_command(restored[0]["text"] + " -d", "wrong-key", messages=restored)
            with self.assertRaisesRegex(ValueError, "original conversation"):
                run_command(restored[0]["text"] + " -d", key, messages=[])
            with self.assertRaisesRegex(ValueError, "active conversation"):
                run_command("hello -e", key, "as_is")

    def test_as_is_collision_and_short_reference_exhaustion(self):
        used = [{"operation": "encrypt", "variant": "as_is", "text": char}
                for char in REFERENCE_ALPHABET[:-1]]
        result = run_command("x -e", "conversation-key", "as_is", used)
        self.assertEqual(result["text"], REFERENCE_ALPHABET[-1])
        with self.assertRaisesRegex(ValueError, "one-character references"):
            run_command("y -e", "conversation-key", "as_is", [*used, result])
        previous = [{"operation": "encrypt", "variant": "as_is", "text": "aa"}]
        with patch("modules.session_reference.secrets.choice", side_effect=list("aabb")):
            result = run_command("hi -e", "conversation-key", "as_is", previous)
        self.assertEqual(result["text"], "bb")

    def test_as_is_store_rejects_missing_ciphertext_and_duplicate_references(self):
        with temporary_directory() as directory:
            store = ChatStore(Path(directory))
            session = store.create("conversation-key")
            result = run_command("hello -e", "conversation-key", "as_is", [])
            for invalid in ([{**result, "ciphertext": None}], [result, result]):
                store.save(session, "conversation-key", invalid)
                with self.assertRaises(ValueError):
                    store.open(session, "conversation-key")

    def test_commands_preserve_message_and_reject_invalid_input(self):
        key = "conversation-key"
        for command in ("hello \u03b2\nworld -e", "hello \u03b2\nworld -e   "):
            result = run_command(command, key)
            self.assertEqual(decrypt_text(result["text"], key), "hello β\nworld")
            self.assertEqual(run_command(result["text"] + " -d", key)["text"], "hello β\nworld")
        for command in ("", "-e", "-d", "-e hello", "hello", "hello-e", "hello -x", "invalid -d"):
            with self.subTest(command=command), self.assertRaises(ValueError):
                run_command(command, key)

    def test_persistence_key_isolation_and_atomic_failure(self):
        with temporary_directory() as directory:
            store = ChatStore(Path(directory))
            session = store.create("first-key")
            other = store.create("second-key")
            messages = [{"operation": "decrypt", "text": "private sentence"}]
            store.save(session, "first-key", messages)
            self.assertEqual(ChatStore(Path(directory)).open(session, "first-key"), messages)
            self.assertEqual(store.open(other, "second-key"), [])
            raw = (Path(directory) / f"{session}.oc1").read_text()
            self.assertNotIn("private sentence", raw)
            self.assertNotIn("first-key", raw)
            with self.assertRaises(ValueError):
                store.open(session, "second-key")
            with patch("modules.chat_store.os.replace", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    store.save(session, "first-key", [])
            self.assertEqual(store.open(session, "first-key"), messages)
            self.assertEqual(len(list(Path(directory).iterdir())), 2)
            with self.assertRaises(ValueError):
                store.open("../escape", "first-key")
            path = Path(directory) / f"{session}.oc1"
            path.write_text(raw[:-5] + "AAAAA")
            with self.assertRaises(ValueError):
                store.open(session, "first-key")


class ChatIntegrationTest(unittest.TestCase):
    def test_persistent_modes_and_standalone_commands(self):
        with temporary_directory() as directory, patch("modules.crypto_chat.default_chat_directory", return_value=Path(directory)), \
                patch("main.SETTINGS_PATH", Path(directory) / "settings.json"), patch.object(BOneTool, "refresh_fonts"):
            app = BOneTool()
            app.withdraw()
            try:
                chat = app.features["encrypt"].chat
                session = chat.store.create("first-key")
                chat.activate(session, "first-key", [])

                def send(text):
                    chat.composer.delete("1.0", "end")
                    chat.composer.insert("1.0", text)
                    chat.send()

                with patch.object(chat.store, "save") as save:
                    send("-e")
                    save.assert_not_called()
                self.assertEqual(chat.messages, [])
                send("hello")
                first = chat.messages[-1]["text"]
                send("second")
                second = chat.messages[-1]["text"]
                self.assertEqual(len(chat.messages), 2)
                send("-d")
                self.assertEqual(len(chat.messages), 2)
                self.assertEqual(chat.operation, "decrypt")
                send(first)
                self.assertEqual(chat.messages[-1]["text"], "hello")
                send(second)
                self.assertEqual(chat.messages[-1]["text"], "second")
                send("invalid reference")
                self.assertEqual(len(chat.messages), 4)
                self.assertEqual(chat.operation, "decrypt")
                send("-help")
                self.assertEqual(chat.operation, "decrypt")
                send("-e")
                send("again")
                self.assertEqual(chat.messages[-1]["operation"], "encrypt")
                token = chat.messages[-1]["text"]
                send(token + " -d")
                self.assertEqual(chat.messages[-1]["text"], "again")
                self.assertEqual(chat.operation, "decrypt")
                send(token)
                self.assertEqual(chat.messages[-1]["text"], "again")
                chat.lock()
                chat.activate(session, "first-key", chat.store.open(session, "first-key"))
                self.assertEqual(chat.operation, "encrypt")
            finally:
                app.destroy()

    def test_key_prompts_send_lock_reopen_and_navigation(self):
        with temporary_directory() as directory, patch("modules.crypto_chat.default_chat_directory", return_value=Path(directory)), \
                patch("main.SETTINGS_PATH", Path(directory) / "settings.json"), patch.object(BOneTool, "refresh_fonts"):
            app = BOneTool()
            app.withdraw()
            try:
                feature = app.features["encrypt"]
                chat = feature.chat
                with patch("modules.crypto_chat.ask_key", side_effect=["first-key", "first-key"]):
                    feature.select_mode("chat")
                first = chat.session
                chat.composer.insert("1.0", "private sentence -e")
                chat.send()
                token = chat.messages[0]["text"]
                self.assertEqual(len(token), len("private sentence"))
                self.assertEqual(chat.messages[0]["variant"], "as_is")
                self.assertEqual(chat.bubble_widgets[0].cget("text"), token)
                self.assertEqual(chat.bubble_widgets[0].pack_info()["side"], "right")
                self.assertNotIn("private sentence", "\n".join(widget.cget("text") for widget in chat.bubble_widgets))
                self.assertEqual(app._get(chat.composer), "")
                chat.composer.insert("1.0", token + " -d")
                chat.send()
                self.assertIn("private sentence", "\n".join(widget.cget("text") for widget in chat.bubble_widgets))
                chat.composer.insert("1.0", "unsaved -e")
                with patch.object(chat.store, "save", side_effect=OSError("disk full")):
                    chat.send()
                self.assertEqual(len(chat.messages), 2)
                self.assertEqual(app._get(chat.composer), "unsaved -e")
                app.show_page("hash")
                self.assertIsNone(chat.key)
                self.assertEqual("\n".join(widget.cget("text") for widget in chat.bubble_widgets), "")
                self.assertEqual(app._get(chat.composer), "")
                app.show_page("encrypt")
                chat.sessions.selection_set(chat.ids.index(first))
                with patch("modules.crypto_chat.ask_key", return_value="wrong-key"):
                    chat.open_selected()
                self.assertIsNone(chat.key)
                with patch("modules.crypto_chat.ask_key", return_value="first-key"):
                    chat.open_selected()
                self.assertEqual(len(chat.messages), 2)
                chat.composer.insert("1.0", token + " -d")
                chat.send()
                self.assertEqual(chat.messages[-1]["text"], "private sentence")
                chat.variant.set("Portable OC1")
                chat.composer.insert("1.0", "portable -e")
                chat.send()
                self.assertTrue(chat.messages[-1]["text"].startswith("OC1."))
                self.assertEqual(decrypt_text(chat.messages[-1]["text"], "first-key"), "portable")
                with patch("modules.crypto_chat.ask_key", side_effect=["second-key", "second-key"]):
                    chat.new()
                self.assertEqual(chat.messages, [])
                self.assertEqual(len(chat.ids), 2)
                feature.select_mode("classic")
                self.assertIsNone(chat.key)
                with patch("modules.crypto_chat.ask_key", return_value=None):
                    chat.new()
                self.assertEqual(len(chat.store.sessions()), 2)
            finally:
                app.destroy()
