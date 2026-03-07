import logging
import os
from pathlib import Path
from queue import Queue, Empty
from threading import Lock, Event
from concurrent.futures import ThreadPoolExecutor
from typing import Iterator, Literal
from dscan.filter import FilterMode

logger = logging.getLogger(__name__)


class _ScanState:
    """Thread-safe pending work counter for coordinating concurrent directory scanning.

    Tracks the number of directories that are either queued or actively being
    processed by a worker. Signals completion once all work is exhausted,
    allowing the main thread to stop draining results.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._pending = 0
        self._done = Event()

    def add(self, count: int) -> None:
        """Register new units of work.

        Must be called before putting new directories into the queue to avoid
        a race condition where workers falsely signal completion.

        Args:
            count: Number of new directories to register as pending.
        """
        with self._lock:
            self._pending += count

    def complete(self) -> None:
        """Mark one unit of work as finished.

        Decrements the pending counter. If no work remains, sets the done
        event so the main thread and all workers can exit cleanly.
        """
        with self._lock:
            self._pending -= 1
            if self._pending == 0:
                logger.debug("All pending work exhausted — signalling done")
                self._done.set()

    @property
    def is_done(self) -> bool:
        """Returns True if all pending work has been completed."""
        return self._done.is_set()


class TreeCrawler:
    """Crawls a directory tree concurrently using a shared work-stealing queue.

    Workers pull directories from a shared queue. Newly discovered subdirectories
    are pushed back into the queue for any idle worker to pick up, keeping all
    threads busy regardless of tree depth or structure.

    Example:
        # Ignore specific directories (default mode):
        crawler = TreeCrawler(dirs={".git", "node_modules"}, max_depth=3)

        # Only descend into specific directories:
        crawler = TreeCrawler(dirs={"src", "lib"}, filter_mode=FilterMode.INCLUDE)

        for entry in crawler.scan(Path("/home/user")):
            print(entry.path)

    Attributes:
        _dirs: Set of directory names used for filtering during traversal.
        _filter_mode: Whether _dirs is treated as a block list or include list.
        _max_workers: Number of worker threads used during scanning.
        _max_depth: Maximum directory depth to scan. None means unlimited.
    """

    def __init__(
        self,
        dirs: list[str] | None = None,
        filter_mode: FilterMode = FilterMode.IGNORE,
        max_workers: int | None = None,
        max_depth: int | None = None,
    ) -> None:
        """Initialises the TreeCrawler.

        Args:
            dirs: Directory names to filter during traversal. Behaviour depends
                on filter_mode. Defaults to {".git", ".idea", ".venv",
                "__pycache__"} when mode is FilterMode.IGNORE, or an empty set otherwise.
            filter_mode: Controls how dirs is applied during descent:
                - filter_mode.IGNORE  — skip directories whose name is in dirs.
                - filter_mode.INCLUDE — only descend into directories whose name is in dirs.
                Entries are still yielded regardless of this filter; it only
                controls whether a directory is recursed into.
            max_workers: Number of worker threads. Defaults to min(32, cpu_count * 2).
            max_depth: Maximum depth to descend relative to root_path. Depth 0
                scans only the root itself, depth 1 includes its immediate children,
                and so on. None (default) means unlimited depth.
        """
        self._filter_mode = filter_mode
        self._dirs = (
            set(dirs)
            if dirs is not None
            else (
                {".git", ".idea", ".venv", "__pycache__"}
                if filter_mode == FilterMode.IGNORE
                else set()
            )
        )
        self._max_workers = max_workers or min(32, max(1, (os.cpu_count() or 4) * 2))
        self._max_depth = max_depth
        logger.debug(
            f"TreeCrawler initialised — "
            f"filter_mode={self._filter_mode!r}, "
            f"dirs={self._dirs}, "
            f"max_workers={self._max_workers}, "
            f"max_depth={self._max_depth!r}"
        )

    def scan(self, root_path: Path) -> Iterator[os.DirEntry]:
        """Scan a directory tree and yield all entries in completion order.

        Spawns worker threads that pull directories from a shared queue.
        Results are yielded as they become available. Once all workers finish,
        any remaining buffered results are drained and yielded.

        Args:
            root_path: Root directory to begin scanning from.

        Yields:
            os.DirEntry: Every entry found in the tree that was not pruned
                by dirs or max_depth. Entries are yielded in worker
                completion order, not filesystem order.
        """
        # Queue holds (path, depth) tuples. Root starts at depth 0.
        dir_queue: Queue[tuple[Path, int]] = Queue()
        result_queue: Queue[os.DirEntry] = Queue()
        state = _ScanState()

        state.add(1)
        dir_queue.put((root_path, 0))

        logger.info(
            f"Starting scan: {root_path} "
            f"({self._max_workers} workers, max_depth={self._max_depth!r})"
        )

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            for _ in range(self._max_workers):
                executor.submit(self._worker, dir_queue, result_queue, state)

            while not state.is_done:
                try:
                    yield result_queue.get(timeout=0.05)
                except Empty:
                    continue

        # Executor has joined — all workers are done. Drain any remaining results.
        drained = 0
        while not result_queue.empty():
            try:
                yield result_queue.get_nowait()
                drained += 1
            except Empty:
                break

        if drained:
            logger.debug(f"Drained {drained} remaining entries after workers finished")

        logger.info(f"Scan complete: {root_path}")

    def _worker(
        self,
        dir_queue: Queue,
        result_queue: Queue,
        state: _ScanState,
    ) -> None:
        """Worker loop that pulls directories from the queue and scans them.

        Runs until the scan state signals completion. For each directory
        dequeued, scans its contents and re-enqueues any discovered
        subdirectories for other workers to pick up, unless the depth limit
        has been reached.

        New subdirectories are registered with state before being enqueued
        to prevent a race condition where all workers complete before new
        work is visible to the state counter.

        Args:
            dir_queue: Shared queue of (directory, depth) tuples to scan.
            result_queue: Shared queue to put discovered entries into.
            state: Shared scan state used to track pending work.
        """
        while not state.is_done:
            try:
                current_dir, depth = dir_queue.get(timeout=0.05)
            except Empty:
                continue

            logger.debug(f"Worker picked up: {current_dir} (depth={depth})")
            new_dirs = self._scan_dir(current_dir, depth, result_queue)

            # Register new work BEFORE completing current — prevents false done signal.
            state.add(len(new_dirs))
            for d, child_depth in new_dirs:
                dir_queue.put((d, child_depth))
            state.complete()

    def _scan_dir(
        self, dir_path: Path, depth: int, result_queue: Queue
    ) -> list[tuple[Path, int]]:
        """Scan a single directory and collect results and subdirectories.

        All entries are placed into result_queue. Subdirectories that are not
        filtered by dirs are returned for re-enqueueing, unless max_depth has
        been reached.

        Args:
            dir_path: Path to the directory to scan.
            depth: Depth of dir_path relative to the scan root (root = 0).
            result_queue: Queue to put discovered DirEntry objects into.

        Returns:
            List of (subdirectory path, child depth) tuples to enqueue for
            further scanning. Empty when at or beyond max_depth.
        """
        new_dirs: list[tuple[Path, int]] = []
        at_depth_limit = self._max_depth is not None and depth >= self._max_depth
        logger.debug(f"Scanning: {dir_path} (depth={depth}, limit={self._max_depth!r})")

        try:
            with os.scandir(dir_path) as it:
                for entry in it:
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                    except OSError as e:
                        logger.warning(f"Skipping entry {entry.path}: {e}")
                        continue

                    result_queue.put(entry)

                    if is_dir:
                        if (
                            self._filter_mode == FilterMode.IGNORE
                            and entry.name in self._dirs
                        ):
                            logger.debug(f"Skipping ignored directory: {entry.path}")
                        elif (
                            self._filter_mode == FilterMode.INCLUDE
                            and entry.name not in self._dirs
                        ):
                            logger.debug(
                                f"Skipping directory not in include list: {entry.path}"
                            )
                        elif at_depth_limit:
                            logger.debug(
                                f"Depth limit reached ({depth}/{self._max_depth}), "
                                f"not descending into: {entry.path}"
                            )
                        else:
                            logger.debug(f"Queuing subdirectory: {entry.path}")
                            new_dirs.append((Path(entry.path), depth + 1))

        except PermissionError:
            logger.warning(f"Permission denied: {dir_path}")
        except OSError as e:
            logger.warning(f"Cannot scan {dir_path}: {e}")

        logger.debug(
            f"Finished scanning: {dir_path} — found {len(new_dirs)} subdirectories"
        )
        return new_dirs
