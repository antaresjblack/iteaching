from abc import ABC, abstractmethod
from typing import BinaryIO


class StorageInterface(ABC):
    @abstractmethod
    async def save(self, source: BinaryIO, destination: str) -> str:
        """Persist a file and return its storage path or object key."""

    @abstractmethod
    async def delete(self, path: str) -> None:
        """Delete a stored file by path or object key."""
