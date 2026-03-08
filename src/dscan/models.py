from datetime import datetime
import os

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class FileEntry:
    name: str
    extension: str | None
    path: str
    dir_path: str
    size: int
    created_at: datetime
    modified_at: datetime

    @classmethod
    def from_dir_entry(cls, entry: os.DirEntry) -> "FileEntry":
        stat = entry.stat(follow_symlinks=False)
        name, ext = os.path.splitext(entry.name)
        return cls(
            name=name,
            extension=ext[1:].lower() if ext else None,
            path=entry.path,
            dir_path=os.path.dirname(entry.path),
            size=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_ctime),
            modified_at=datetime.fromtimestamp(stat.st_mtime),
        )


@dataclass(slots=True, frozen=True)
class DirectoryEntry:
    name: str
    path: str
    parent_path: str
    created_at: datetime
    modified_at: datetime

    @classmethod
    def from_dir_entry(cls, entry: os.DirEntry) -> "DirectoryEntry":
        stat = entry.stat(follow_symlinks=False)
        return cls(
            name=entry.name,
            path=entry.path,
            parent_path=os.path.dirname(entry.path),
            created_at=datetime.fromtimestamp(stat.st_ctime),
            modified_at=datetime.fromtimestamp(stat.st_mtime),
        )
