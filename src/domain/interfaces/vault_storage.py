"""
Vault storage interface.

What it does:
- Defines the contract for securely storing and hashing file deliverables.

What it does NOT do:
- Does NOT perform direct OS file writes or disk calls.
"""

from typing import Protocol, Tuple

class VaultStorage(Protocol):
    """Abstract interface for file deliverable storage and verification."""

    async def store_file(self, filename: str, content: bytes) -> Tuple[str, str, int]:
        """
        Stores file content and calculates cryptographic hash.

        Args:
            filename: Original file name.
            content: Raw file bytes.

        Returns:
            Tuple[str, str, int]: (stored_filename, sha256_hash, byte_size)
        """
        ...
