import fnmatch
import logging
import os
from collections.abc import Callable, Iterator
from typing import Literal

from enum import Enum


class FilterMode(Enum):
    IGNORE = "ignore"
    INCLUDE = "include"


logger = logging.getLogger(__name__)


class ScanFilter:
    """Post-scan filter that wraps a DriveScanner iterator.

    Operates on yielded entries only — traversal behaviour (depth,
    which dirs to recurse into) is controlled by DriveScanner itself.

    Example:
        scanner = DriveScanner(max_depth=3)

        # Only yield .pdf and .pptx files:
        f = ScanFilter(extensions={".pdf", ".pptx"})

        # Yield everything except .pdf:
        f = ScanFilter(extensions={".pdf"}, extensions_mode="ignore")

        # Yield entries whose name does NOT match a pattern:
        f = ScanFilter(name_pattern=".*", name_pattern_mode="ignore")

        for entry in f.apply(scanner.scan(root)):
            print(entry.path)
    """

    def __init__(
        self,
        only_files: bool = False,
        only_dirs: bool = False,
        extensions: set[str] | None = None,
        extensions_mode: FilterMode = FilterMode.INCLUDE,
        name_pattern: str | None = None,
        name_pattern_mode: FilterMode = FilterMode.INCLUDE,
        custom: Callable[[os.DirEntry], bool] | None = None,
    ) -> None:
        """Initialises the ScanFilter.

        Args:
            only_files: If True, only yield file entries.
            only_dirs: If True, only yield directory entries.
                Mutually exclusive with only_files.
            extensions: Set of file extensions to filter on (e.g. {".pdf", ".py"}).
                Has no effect on directory entries. Case-insensitive.
            extensions_mode: Controls how extensions is applied:
                - FilterMode.INCLUDE — only yield files whose extension is in extensions.
                - FilterMode.IGNORE  — skip files whose extension is in extensions.
            name_pattern: A glob pattern matched against entry.name (e.g. ".*", "*.min.*").
            name_pattern_mode: Controls how name_pattern is applied:
                - FilterMode.INCLUDE — only yield entries whose name matches the pattern.
                - FilterMode.IGNORE  — skip entries whose name matches the pattern.
            custom: Optional callable that receives a DirEntry and returns True to
                keep the entry, False to drop it. Applied last, after all other filters.
        """
        if only_files and only_dirs:
            raise ValueError("only_files and only_dirs are mutually exclusive")

        self._only_files = only_files
        self._only_dirs = only_dirs
        self._extensions = {ext.lower() for ext in extensions} if extensions else None
        self._extensions_mode = extensions_mode
        self._name_pattern = name_pattern
        self._name_pattern_mode = name_pattern_mode
        self._custom = custom

        logger.debug(
            f"ScanFilter initialised — "
            f"only_files={self._only_files}, "
            f"only_dirs={self._only_dirs}, "
            f"extensions={self._extensions}, "
            f"extensions_mode={self._extensions_mode!r}, "
            f"name_pattern={self._name_pattern!r}, "
            f"name_pattern_mode={self._name_pattern_mode!r}, "
            f"custom={'provided' if custom else 'None'}"
        )

    def apply(self, entries: Iterator[os.DirEntry]) -> Iterator[os.DirEntry]:
        """Apply all configured filters to an entry iterator.

        Args:
            entries: Iterator of DirEntry objects, typically from DriveScanner.scan().

        Yields:
            os.DirEntry: Entries that pass all active filters.
        """
        for entry in entries:
            if self._only_files and not entry.is_file(follow_symlinks=False):
                logger.debug(f"ScanFilter: skipping non-file: {entry.path}")
                continue
            if self._only_dirs and not entry.is_dir(follow_symlinks=False):
                logger.debug(f"ScanFilter: skipping non-directory: {entry.path}")
                continue

            if self._extensions and not entry.is_dir(follow_symlinks=False):
                ext = os.path.splitext(entry.name)[1].lower()
                match = ext in self._extensions
                if self._extensions_mode == FilterMode.INCLUDE and not match:
                    logger.debug(
                        f"ScanFilter: extension {ext!r} not in include list: {entry.path}"
                    )
                    continue
                if self._extensions_mode == FilterMode.IGNORE and match:
                    logger.debug(
                        f"ScanFilter: extension {ext!r} in ignore list: {entry.path}"
                    )
                    continue

            if self._name_pattern:
                match = fnmatch.fnmatch(entry.name, self._name_pattern)
                if self._name_pattern_mode == FilterMode.INCLUDE and not match:
                    logger.debug(
                        f"ScanFilter: name {entry.name!r} doesn't match include "
                        f"pattern {self._name_pattern!r}: {entry.path}"
                    )
                    continue
                if self._name_pattern_mode == FilterMode.IGNORE and match:
                    logger.debug(
                        f"ScanFilter: name {entry.name!r} matches ignore "
                        f"pattern {self._name_pattern!r}: {entry.path}"
                    )
                    continue

            if self._custom and not self._custom(entry):
                logger.debug(f"ScanFilter: rejected by custom filter: {entry.path}")
                continue

            yield entry
