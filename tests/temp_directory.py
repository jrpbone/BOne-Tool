"""Temporary directories for non-sensitive test fixtures."""

from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4


@contextmanager
def temporary_directory():
    # Python 3.13's Windows mode-0700 directory ACL can exclude the identity
    # used for subsequent file access in a managed execution environment.
    # Inherit the temp parent's ACL instead; these fixtures contain no secrets.
    if os.name != "nt":
        with tempfile.TemporaryDirectory() as directory:
            yield Path(directory)
        return

    parent = Path(tempfile.gettempdir()).resolve()
    directory = parent / f"bone-test-{uuid4().hex}"
    directory.mkdir()  # Default permissions, exclusive creation.
    try:
        yield directory
    finally:
        if directory.resolve().parent != parent or directory.is_symlink():
            raise RuntimeError("Refusing to clean up a redirected test directory.")
        shutil.rmtree(directory)
