# BOne Tool

> A private, local-first desktop toolbox for authenticated encryption, hashing, custom alphabets, image-to-ASCII conversion, and text encoding.

![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Desktop application](https://img.shields.io/badge/App-Desktop-5C2D91)
![AES-256-GCM](https://img.shields.io/badge/Encryption-AES--256--GCM-0A7B83)
![Local first](https://img.shields.io/badge/Privacy-Local--first-2E8B57)

BOne Tool brings several everyday privacy and conversion utilities into one focused `tkinter` application. Encrypt a message, verify a download, preview text in a custom alphabet, turn an image into ASCII art, or transform an encoding without sending the source data to an online service.

All operations run inside the local Python process. No account, server, or network connection is required.

## Highlights

| Workspace | What it offers |
| --- | --- |
| **Encrypt / Decrypt** | Password-based AES-256-GCM encryption, authenticated `OC1` tokens, QR generation, and text import/export. |
| **Hash** | Live text digests, multi-file hashing, and checksum verification across eight algorithms. |
| **Alphabet** | Side-by-side plain and custom-font editors with live synchronization and local font importing. |
| **Image to ASCII** | Image preview, adjustable ASCII conversion, clipboard support, and text or styled PNG export. |
| **Encoding** | Two-way Base64, hexadecimal, and URL percent-encoding transformations. |
| **Settings** | Light and dark themes, editor sizing, and optional recent-file history. |

## Why BOne Tool?

- **Local by default** — messages, passwords, encryption keys, hashes, and images are processed on the device.
- **Authenticated encryption** — AES-256-GCM protects both confidentiality and integrity; modified data is rejected before plaintext is shown.
- **Portable output** — encrypted content is stored as a copyable, URL-safe `OC1.` token.
- **Practical workflows** — copy, save, reuse, import, export, verify, or generate a QR code without leaving the application.
- **No custom cipher** — the encryption format combines established primitives from the `cryptography` package.

## Quick Start

### Requirements

- Python 3.10 or newer
- Tk support, normally included with Windows and standard Python installers
- The packages declared in `requirements.txt`

### Install and run

From the project directory:

```bash
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# macOS or Linux
source .venv/bin/activate
```

Install the dependencies and launch the application:

```bash
python -m pip install -r requirements.txt
python main.py
```

## Feature Tour

### Authenticated text encryption

- Encrypts UTF-8 text with **AES-256-GCM**.
- Derives the key from the password with **Scrypt**.
- Generates a new random 16-byte salt and 12-byte nonce for every encryption.
- Produces a portable, versioned token beginning with `OC1.`.
- Rejects an incorrect password, corrupted token, or modified ciphertext.
- Requires at least eight password characters and displays a simple strength indicator.
- Imports `.txt` and `.oc1` files and saves results as text.
- Copies results, moves them back to the input, or renders them as a savable QR code.

> [!IMPORTANT]
> The password is never stored in an `OC1` token. If it is lost, BOne Tool cannot recover the plaintext.

### Hashing and verification

BOne Tool updates text hashes as you type and reports both character and UTF-8 byte counts.

| Algorithm | Role |
| --- | --- |
| SHA-256 | Default general-purpose integrity digest |
| SHA-512 | SHA-2 with a larger digest |
| SHA3-256 / SHA3-512 | SHA-3 family digests |
| BLAKE2b / BLAKE2s | Fast modern cryptographic hashes |
| SHA-1 / MD5 | Legacy checksum compatibility only |

Files are read in 1 MiB chunks, allowing large files to be hashed without loading them completely into memory. Text and file verification use `hmac.compare_digest` for constant-time digest comparison.

> [!WARNING]
> SHA-1 and MD5 are vulnerable to collision attacks. Keep them for legacy checksum matching, not new security-sensitive designs.

### Custom alphabet workspace

- Keeps the **Plain English** and **Custom Alphabet** editors synchronized in both directions.
- Includes decorative fonts under `fonts/` and switches between them at runtime.
- Imports TTF, OTF, TTC, WOFF, and WOFF2 files.
- Converts compatible WOFF/WOFF2 fonts to a desktop TTF or OTF format.
- Discovers compatible fonts placed beside `main.py` or directly inside `fonts/`.
- Loads stored fonts privately into the application process on Windows rather than installing them system-wide.

The selected font changes how characters look, not the characters themselves. For example, a custom-looking `A` remains Unicode `U+0041`; pasting it into software without the font displays an ordinary `A`.

### Image to ASCII

- Accepts PNG, JPEG, WebP, BMP, GIF, and TIFF images.
- Corrects stored EXIF orientation and composites transparent pixels over white.
- Adjusts output width, brightness, contrast, inversion, and character set.
- Provides Classic, Detailed, and Blocks character ramps.
- Copies or saves the generated art as UTF-8 text.
- Exports a styled PNG with a chosen TTF/OTF font, font size, text color, and background color.
- Uses the first frame when an animated image is imported.

The source image is only read; conversion does not modify it.

### Encoding tools

| Method | Encode | Decode |
| --- | --- | --- |
| Base64 | UTF-8 text to Base64 | Valid Base64 to UTF-8 text |
| Hexadecimal | UTF-8 bytes to hexadecimal | Valid hexadecimal bytes to UTF-8 text |
| URL | Text to percent-encoded form | Percent-encoded text to its decoded form |

Encoding changes representation only. It does **not** provide encryption or secrecy.

### Desktop conveniences

- Drag an image into the application to open it in **Image to ASCII**.
- Drag `.txt` or `.oc1` content to **Encrypt / Decrypt**.
- Drag other files to **Hash**, including multiple files at once.
- Switch between light and dark themes.
- Set the shared editor font size from 8 to 24 points.
- Optionally remember up to ten recent file paths and reopen them with a double-click.

## Common Workflows

### Encrypt a message

1. Open **Encrypt / Decrypt**.
2. Enter a long, unique password or passphrase.
3. Enter the message in the left panel.
4. Select **Encrypt**.
5. Copy or save the complete value beginning with `OC1.`.

Encrypting identical text twice creates different tokens because every operation uses a fresh salt and nonce.

### Decrypt a message

1. Paste the complete `OC1.` token into the left panel.
2. Enter the original password.
3. Select **Decrypt**.

Plaintext is displayed only after AES-GCM authenticates the encrypted data.

### Verify a downloaded file

1. Open **Hash** and select the algorithm used by the publisher.
2. Paste the expected digest into the verification field.
3. Select **Verify file** and choose the downloaded file.
4. Read the match result in the digest panel.

### Create ASCII art

1. Open **Image to ASCII** and import or drop an image.
2. Adjust the conversion controls and select **Apply**.
3. Copy the output, save it as text, or style and export it as a PNG.

## The `OC1` Format

`OC1` is a small, versioned container around established cryptographic primitives. It is not a newly designed encryption algorithm.

```text
OC1.<URL-safe Base64 payload without padding>
```

The decoded payload contains:

```text
+----------------+-----------------+--------------------------+
| Salt: 16 bytes | Nonce: 12 bytes | Ciphertext + GCM tag     |
+----------------+-----------------+--------------------------+
```

| Component | Configuration |
| --- | --- |
| Key derivation | Scrypt, 32-byte output, `N=32768`, `r=8`, `p=1` |
| Encryption | AES-GCM with a 256-bit key |
| Authentication tag | 16 bytes, appended by AES-GCM |
| Associated data | The bytes `OC1` |

<details>
<summary><strong>Encryption and decryption flow</strong></summary>

Encryption generates a random salt, derives a key with Scrypt, generates a random nonce, and encrypts the UTF-8 message with AES-GCM. The salt, nonce, ciphertext, and authentication tag are encoded with URL-safe Base64 and prefixed with `OC1.`.

Decryption validates the prefix, decodes the payload, derives the same key from the supplied password and stored salt, and asks AES-GCM to authenticate and decrypt the ciphertext. Any change to the password, nonce, ciphertext, tag, associated data, or derived key causes authentication to fail.

</details>

## Security and Privacy

BOne Tool can protect message confidentiality and integrity when the password is strong, the computer is trusted, and the recipient receives the password through an appropriately secure channel.

It does not protect against:

- Weak, reused, shared, or exposed passwords
- Keyloggers, clipboard monitors, screen capture, or other malware
- Someone reading plaintext while it is displayed
- Replacement of the application or Python environment
- Offline password guessing against a captured token
- Accidental loss of the password

BOne Tool is not a password manager, secure messenger, file-encryption utility, or audited replacement for established high-risk security products.

### Data stored on disk

Preferences are stored in `~/.bonecipher.json`. This file can contain:

- The selected theme
- The editor font size
- Whether recent-file history is enabled
- Up to ten absolute file paths, only when history is enabled

It does not store message contents, passwords, tokens, hashes, or encryption keys. User-generated output is written only after an explicit save action. Imported fonts are stored in `fonts/`, and compatible font files placed beside `main.py` are copied there when discovered.

## Project Structure

```text
.
|-- fonts/              Bundled fonts and imported-font storage
|-- main.py             Desktop interface and core application logic
|-- test_main.py        Utility and image-conversion tests
|-- requirements.txt    Runtime dependencies
`-- README.md           Project documentation
```

Core functions in `main.py` include:

- `encrypt_text(text, password)` — creates an authenticated `OC1` token.
- `decrypt_text(token, password)` — authenticates and decrypts a token.
- `_derive_key(password, salt)` — derives a 256-bit AES key with Scrypt.
- `hash_text(text, algorithm)` and `hash_file(path, algorithm)` — create hexadecimal digests.
- `image_to_ascii(...)` and `ascii_to_image(...)` — convert between images and ASCII art.
- `transform_text(text, method, decode)` — handles Base64, hex, and URL transformations.
- `BOneTool` — builds and controls the desktop application.

## Development

Compile the module without opening the interface:

```bash
python -m py_compile main.py
```

Run the automated tests:

```bash
python -m unittest -v
```

Run a minimal encryption round trip:

```bash
python -c "from main import encrypt_text, decrypt_text; token = encrypt_text('hello', 'a strong password'); assert decrypt_text(token, 'a strong password') == 'hello'"
```

Check the installed dependency set:

```bash
python -m pip check
```

## Built With

- [`cryptography`](https://cryptography.io/) — Scrypt and AES-GCM
- [`fonttools`](https://fonttools.readthedocs.io/) — font validation, metadata, and web-font conversion
- [Pillow](https://python-pillow.org/) — image processing and ASCII PNG rendering
- [`qrcode`](https://pypi.org/project/qrcode/) — QR code generation
- [`tkinterdnd2`](https://pypi.org/project/tkinterdnd2/) — desktop drag and drop
- Python's standard library — interface widgets, hashing, encodings, random bytes, settings, and file handling

---

Built for useful local workflows where source data should stay on the machine.
