"""
Deliverable vault management service.

What it does:
- Orchestrates cryptographic verification and storage of uploaded deliverables.
- Updates member submission metrics in repository.

What it does NOT do:
- Does NOT access raw filesystem functions directly.
- Does NOT send Discord messages or embeds.
"""

from dataclasses import dataclass
from typing import Optional
from src.domain.interfaces.vault_storage import VaultStorage
from src.domain.interfaces.activity_repository import ActivityRepository

@dataclass(frozen=True)
class VaultSubmissionResultDTO:
    """Output payload for a verified file submission."""
    user_id: str
    original_filename: str
    stored_filename: str
    file_hash: str
    file_size: int
    notes: Optional[str] = None

class VaultService:
    """Orchestrates deliverable file verification and activity recording."""

    def __init__(self, vault_storage: VaultStorage, activity_repo: ActivityRepository):
        self._storage = vault_storage
        self._activity_repo = activity_repo

    async def store_deliverable(
        self,
        guild_id: Optional[str],
        user_id: str,
        filename: str,
        content: bytes,
        notes: Optional[str] = None
    ) -> VaultSubmissionResultDTO:
        """
        Stores deliverable file and credits user's contribution record.

        Args:
            guild_id: Optional guild context ID.
            user_id: Discord user ID of submitter.
            filename: Original file name.
            content: Raw file bytes.
            notes: Optional submission notes/description.

        Returns:
            VaultSubmissionResultDTO: Verification details including SHA-256 hash.
        """
        stored_name, file_hash, file_size = await self._storage.store_file(filename, content)
        await self._activity_repo.record_file_submission(guild_id, user_id)

        return VaultSubmissionResultDTO(
            user_id=user_id,
            original_filename=filename,
            stored_filename=stored_name,
            file_hash=file_hash,
            file_size=file_size,
            notes=notes
        )
