import asyncio
import hashlib
from pathlib import Path
from typing import BinaryIO, Final
from uuid import UUID

CHUNK_SIZE_BYTES: Final[int] = 1024 * 1024


class FileTooLargeError(Exception):
    pass


class FileStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def path_for(self, document_id: UUID) -> Path:
        return self._root / f"{document_id}.pdf"

    async def save(self, document_id: UUID, source: BinaryIO, max_bytes: int) -> str:
        return await asyncio.to_thread(self._save, document_id, source, max_bytes)

    async def delete(self, document_id: UUID) -> None:
        await asyncio.to_thread(self.path_for(document_id).unlink, missing_ok=True)

    def _save(self, document_id: UUID, source: BinaryIO, max_bytes: int) -> str:
        self._root.mkdir(parents=True, exist_ok=True)
        destination = self.path_for(document_id)
        digest = hashlib.sha256()
        size = 0
        try:
            with destination.open("wb") as target:
                while chunk := source.read(CHUNK_SIZE_BYTES):
                    size += len(chunk)
                    if size > max_bytes:
                        raise FileTooLargeError(f"File exceeds {max_bytes} bytes")
                    digest.update(chunk)
                    target.write(chunk)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        return digest.hexdigest()
