import logging
import os
from collections.abc import Callable, Iterator
from pathlib import Path
from dscan.models import FileEntry, DirectoryEntry
from dscan.crawler import TreeCrawler
from dscan.filter import FilterMode, ScanFilter

logger = logging.getLogger(__name__)


def scan_entries(
    path: str | Path,
    *,
    # ── What to yield ────────────────────────────────────────────────────────
    files_only: bool = False,
    dirs_only: bool = False,
    # ── Extension filtering (mutually exclusive) ──────────────────────────────
    extensions: set[str] | list[str] | None = None,
    ignore_extensions: set[str] | list[str] | None = None,
    # ── Name-pattern filtering (mutually exclusive) ───────────────────────────
    match: str | None = None,
    ignore_pattern: str | None = None,
    # ── Traversal ────────────────────────────────────────────────────────────
    ignore_dirs: list[str] | None = None,
    only_dirs: list[str] | None = None,
    max_depth: int | None = None,
    max_workers: int | None = None,
    # ── Escape hatch ─────────────────────────────────────────────────────────
    custom_filter: Callable[[os.DirEntry], bool] | None = None,
) -> Iterator[os.DirEntry]:
    """Scan a directory tree and yield matching entries.

    Combines traversal and filtering into a single call. All keyword
    arguments are optional — calling ``scan_entries(path)`` alone yields every
    entry in the tree with sensible defaults.

    Args:
        path: Root directory to scan. Strings are accepted and resolved
            automatically; non-existent or non-directory paths raise
            ``ValueError``.

        files_only: Yield only files (no directories).
        dirs_only:  Yield only directories (no files).
            ``files_only`` and ``dirs_only`` are mutually exclusive.

        extensions: Allowlist of file extensions to yield, e.g.
            ``{".py", ".md"}``. Leading dots are optional and matching
            is case-insensitive. Has no effect on directory entries.
        ignore_extensions: Denylist of extensions to suppress.
            Mutually exclusive with ``extensions``.

        match: Glob pattern — only yield entries whose name matches,
            e.g. ``"test_*"``.
        ignore_pattern: Glob pattern — suppress entries whose name
            matches, e.g. ``".*"``.
            Mutually exclusive with ``match``.

        ignore_dirs: Directory names to skip when descending, e.g.
            ``["node_modules", "dist"]``. Merged with the built-in
            defaults (``.git``, ``.idea``, ``.venv``, ``__pycache__``).
            Pass an empty list to disable all default ignores.
        only_dirs: When provided, descend *only* into directories whose
            name appears in this list. Mutually exclusive with
            ``ignore_dirs``.
        max_depth: How many levels deep to descend. ``0`` scans only the
            root itself; ``None`` (default) is unlimited.
        max_workers: Worker thread count. Defaults to
            ``min(32, cpu_count * 2)``.

        custom_filter: Optional callable ``(DirEntry) -> bool``. Return
            ``False`` to drop an entry. Applied after all other filters.

    Yields:
        ``os.DirEntry`` for every entry that passes all active filters.

    Raises:
        ValueError: If ``path`` does not exist or is not a directory, or
            if any pair of mutually-exclusive arguments are both supplied.

    Examples:
        Yield all Python files up to 3 levels deep::

            for entry in scan_entries("~/projects", extensions={".py"}, max_depth=3):
                print(entry.path)

        Yield everything, skipping hidden files and ``dist`` folders::

            for entry in scan_entries(
                "/srv/app",
                ignore_pattern=".*",
                ignore_dirs=["dist"],
            ):
                print(entry.path)

        Only descend into ``src`` and ``tests`` directories::

            for entry in scan_entries(".", only_dirs=["src", "tests"], files_only=True):
                print(entry.path)
    """
    # ── Validate mutually exclusive pairs ────────────────────────────────────
    if files_only and dirs_only:
        raise ValueError("files_only and dirs_only are mutually exclusive")
    if extensions and ignore_extensions:
        raise ValueError("extensions and ignore_extensions are mutually exclusive")
    if match and ignore_pattern:
        raise ValueError("match and ignore_pattern are mutually exclusive")
    if ignore_dirs is not None and only_dirs is not None:
        raise ValueError("ignore_dirs and only_dirs are mutually exclusive")

    # ── Resolve path ─────────────────────────────────────────────────────────
    root = _resolve_path(path)

    # ── Build TreeCrawler ─────────────────────────────────────────────────────
    if only_dirs is not None:
        crawler = TreeCrawler(
            dirs=only_dirs,
            filter_mode=FilterMode.INCLUDE,
            max_workers=max_workers,
            max_depth=max_depth,
        )
    else:
        # Merge caller-supplied ignores with the built-in defaults.
        default_ignores = {".git", ".idea", ".venv", "__pycache__"}
        extra = set(ignore_dirs) if ignore_dirs is not None else set()
        merged = (default_ignores | extra) if ignore_dirs is None else extra
        crawler = TreeCrawler(
            dirs=list(merged),
            filter_mode=FilterMode.IGNORE,
            max_workers=max_workers,
            max_depth=max_depth,
        )

    # ── Build ScanFilter ──────────────────────────────────────────────────────
    scan_filter = ScanFilter(
        only_files=files_only,
        only_dirs=dirs_only,
        extensions=_normalise_exts(extensions)
        if extensions
        else (_normalise_exts(ignore_extensions) if ignore_extensions else None),
        extensions_mode=(
            FilterMode.IGNORE if ignore_extensions else FilterMode.INCLUDE
        ),
        name_pattern=match or ignore_pattern,
        name_pattern_mode=(FilterMode.IGNORE if ignore_pattern else FilterMode.INCLUDE),
        custom=custom_filter,
    )

    return scan_filter.apply(crawler.scan(root))


def scan(
    path: str | Path,
    *,
    # ── What to yield ────────────────────────────────────────────────────────
    files_only: bool = False,
    dirs_only: bool = False,
    # ── Extension filtering (mutually exclusive) ──────────────────────────────
    extensions: set[str] | list[str] | None = None,
    ignore_extensions: set[str] | list[str] | None = None,
    # ── Name-pattern filtering (mutually exclusive) ───────────────────────────
    match: str | None = None,
    ignore_pattern: str | None = None,
    # ── Traversal ────────────────────────────────────────────────────────────
    ignore_dirs: list[str] | None = None,
    only_dirs: list[str] | None = None,
    max_depth: int | None = None,
    max_workers: int | None = None,
    # ── Escape hatch ─────────────────────────────────────────────────────────
    custom_filter: Callable[[os.DirEntry], bool] | None = None,
) -> Iterator[FileEntry | DirectoryEntry]:
    """Like ``scan_entries``, but yields rich metadata models instead of raw
    ``DirEntry`` objects.

    See ``scan_entries`` for argument details and examples.

    Yields:
        FileEntry or DirectoryEntry, depending on the type of each entry.
    """
    for entry in scan_entries(
        path,
        files_only=files_only,
        dirs_only=dirs_only,
        extensions=extensions,
        ignore_extensions=ignore_extensions,
        match=match,
        ignore_pattern=ignore_pattern,
        ignore_dirs=ignore_dirs,
        only_dirs=only_dirs,
        max_depth=max_depth,
        max_workers=max_workers,
        custom_filter=custom_filter,
    ):
        if entry.is_file(follow_symlinks=False):
            yield FileEntry.from_dir_entry(entry)
        elif entry.is_dir(follow_symlinks=False):
            yield DirectoryEntry.from_dir_entry(entry)


# ── Internal helpers ──────────────────────────────────────────────────────────


def _resolve_path(path: str | Path) -> Path:
    """Resolve *path* to an absolute ``Path``, raising ``ValueError`` on failure."""
    try:
        p = Path(path).expanduser().resolve()
    except Exception as e:
        raise ValueError(f"Invalid path {path!r}: {e}") from e

    if not p.exists():
        raise ValueError(f"Path does not exist: {p}")
    if not p.is_dir():
        raise ValueError(f"Path is not a directory: {p}")

    return p


# ── Normalise extensions (ensure leading dot) ─────────────────────────────
def _normalise_exts(exts: set[str] | list[str]) -> set[str]:
    return {e if e.startswith(".") else f".{e}" for e in exts}
