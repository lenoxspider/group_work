"""
Local filesystem implementation of VaultStorage.

What it does:
- Validates and sanitizes file names.
- Computes SHA-256 hash of file contents.
- Persists file deliverables into versioned disk files.

What it does NOT do:
- Does NOT execute SQL statements.
- Does NOT communicate with Discord.
"""

import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

from src.domain.errors import StorageError
from src.domain.interfaces.vault_storage import VaultStorage

class LocalFileVault(VaultStorage):
    """Stores files on the local filesystem with cryptographic verification."""

    def __init__(self, target_dir: str):
        self.target_dir = target_dir
        os.makedirs(self.target_dir, exist_ok=True)

    def _sanitize(self, filename: str) -> str:
        """Removes dangerous or non-alphanumeric characters."""
        return re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)

    async def store_file(self, filename: str, content: bytes) -> Tuple[str, str, int]:
        """
        Calculates SHA-256 and writes bytes to destination file.

        Args:
            filename: Input file name.
            content: Raw file bytes.

        Returns:
            Tuple[str, str, int]: (stored_filename, sha256_hash, file_size)

        Raises:
            StorageError: If disk write fails.
        """
        try:
            file_hash = hashlib.sha256(content).hexdigest()
            short_hash = file_hash[:8]
            date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

            clean_name = self._sanitize(filename)
            stem = Path(clean_name).stem
            ext = Path(clean_name).suffix or ".bin"
            stored_name = f"{stem}_{date_str}_{short_hash}{ext}"

            dest_path = os.path.join(self.target_dir, stored_name)
            with open(dest_path, "wb") as f:
                f.write(content)

            return stored_name, file_hash, len(content)
        except Exception as e:
            raise StorageError(f"Failed to persist file {filename}: {e}") from e
