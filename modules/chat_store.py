"""Encrypted, atomic conversation storage; no keys or plaintext on disk."""

import json
import os
import tempfile
import uuid
from pathlib import Path

from .crypto import decrypt_text, encrypt_text
from .session_reference import create_reference, decrypt_reference, REFERENCE_ALPHABET


def default_chat_directory() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "BOneTool" / "conversations"


class ChatStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def sessions(self) -> list[str]:
        if not self.directory.exists():
            return []
        return sorted(path.stem for path in self.directory.glob("*.oc1") if len(path.stem) == 32)

    def _path(self, session: str) -> Path:
        if len(session) != 32 or any(char not in "0123456789abcdef" for char in session):
            raise ValueError("Invalid conversation identifier.")
        return self.directory / f"{session}.oc1"

    def create(self, key: str) -> str:
        session = uuid.uuid4().hex
        self.save(session, key, [])
        return session

    def save(self, session: str, key: str, messages: list[dict]) -> None:
        target = self._path(session)
        payload = json.dumps({"version": 1, "messages": messages}, ensure_ascii=False)
        encrypted = encrypt_text(payload, key)
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def open(self, session: str, key: str) -> list[dict]:
        try:
            payload = json.loads(decrypt_text(self._path(session).read_text(encoding="utf-8"), key))
            if not isinstance(payload, dict) or payload.get("version") != 1:
                raise ValueError("Unsupported conversation format.")
            messages = payload["messages"]
            if not isinstance(messages, list) or any(
                not isinstance(item, dict) or item.get("operation") not in {"encrypt", "decrypt"}
                or not isinstance(item.get("text"), str) for item in messages
            ):
                raise ValueError("Invalid conversation history.")
            references = set()
            for item in messages:
                if item.get("variant", "oc1") not in {"oc1", "as_is"}:
                    raise ValueError("Unsupported message variant.")
                if item.get("variant") == "as_is" and item["operation"] == "encrypt":
                    reference = item["text"]
                    if (not reference or any(char not in REFERENCE_ALPHABET for char in reference)
                            or reference in references or not isinstance(item.get("ciphertext"), str)
                            or not item["ciphertext"].startswith("OC1.")):
                        raise ValueError("Invalid conversation reference.")
                    references.add(reference)
            return messages
        except (KeyError, TypeError, UnicodeError) as error:
            raise ValueError("Invalid conversation history.") from error


def run_command(command: str, key: str, variant: str = "oc1", messages: list[dict] | None = None,
                mode: str | None = None) -> dict:
    """Use a trailing flag or the caller's active mode; never execute shell commands."""
    parts = command.rstrip().rsplit(maxsplit=1)
    if len(parts) == 2 and parts[1] in {"-e", "-d"}:
        text, flag = parts
        operation = "encrypt" if flag == "-e" else "decrypt"
    elif mode in {"encrypt", "decrypt"}:
        text, operation = command, mode
    else:
        raise ValueError("Use: message -e  or  output -d")
    if not text.strip():
        raise ValueError("Enter a message first.")
    if variant not in {"oc1", "as_is"}:
        raise ValueError("Select As-is or Portable OC1.")
    if operation == "encrypt" and variant == "as_is":
        if messages is None:
            raise ValueError("As-is output requires an active conversation.")
        return create_reference(text, key, messages)
    if operation == "decrypt" and not text.strip().startswith("OC1."):
        return {"operation": "decrypt", "variant": "as_is",
                "text": decrypt_reference(text.strip(), key, messages or [])}
    result = encrypt_text(text, key) if operation == "encrypt" else decrypt_text(text.strip(), key)
    return {"operation": operation, "text": result}
