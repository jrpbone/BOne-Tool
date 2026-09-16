"""Same-length references to OC1 ciphertext kept in an encrypted conversation.

References are lookup identifiers, not standalone ciphertext or secret keys.
Length is measured in Unicode code points, matching Python's len(message).
"""

import secrets
import string

from .crypto import decrypt_text, encrypt_text


REFERENCE_ALPHABET = string.ascii_letters + string.digits


def create_reference(text: str, key: str, messages: list[dict]) -> dict:
    length = len(text)
    if not length:
        raise ValueError("Enter a message first.")
    used = {
        item["text"] for item in messages
        if item.get("variant") == "as_is" and item.get("operation") == "encrypt"
        and len(item["text"]) == length
    }
    # Very short inputs have a finite reference space. Choose from the remaining
    # one-character values directly to avoid random retry failure near capacity.
    if length == 1:
        available = [char for char in REFERENCE_ALPHABET if char not in used]
        if not available:
            raise ValueError("All one-character references are used. Start a new conversation or select Portable OC1.")
        reference = secrets.choice(available)
    else:
        for _ in range(256):
            reference = "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(length))
            if reference not in used:
                break
        else:
            raise ValueError("Could not allocate a unique reference. Start a new conversation or select Portable OC1.")
    return {
        "operation": "encrypt", "variant": "as_is", "text": reference,
        "ciphertext": encrypt_text(text, key),
    }


def decrypt_reference(reference: str, key: str, messages: list[dict]) -> str:
    for item in messages:
        if item.get("variant") == "as_is" and item.get("operation") == "encrypt" and item["text"] == reference:
            return decrypt_text(item["ciphertext"], key)
    raise ValueError("Reference not found in this conversation. Open the original conversation or use a portable OC1 token.")
