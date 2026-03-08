import os
import time
from pathlib import Path
from dscan import scan_entries, scan


def bench_os_walk(root):
    start = time.perf_counter()
    count = 0
    for root_dir, dirs, files in os.walk(root):
        count += len(dirs) + len(files)
    end = time.perf_counter()
    return count, end - start


def bench_os_walk_stat(root):
    start = time.perf_counter()
    count = 0
    for root_dir, dirs, files in os.walk(root):
        for name in dirs + files:
            try:
                os.stat(os.path.join(root_dir, name))
                count += 1
            except OSError:
                continue
    end = time.perf_counter()
    return count, end - start


def bench_pathlib_rglob(root):
    start = time.perf_counter()
    count = 0
    for _ in Path(root).rglob("*"):
        count += 1
    end = time.perf_counter()
    return count, end - start


def bench_dscan_entries(root):
    start = time.perf_counter()
    count = 0
    for _ in scan_entries(root, ignore_dirs=[]):
        count += 1
    end = time.perf_counter()
    return count, end - start


def bench_dscan_models(root):
    start = time.perf_counter()
    count = 0
    for _ in scan(root, ignore_dirs=[]):
        count += 1
    end = time.perf_counter()
    return count, end - start


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "."
    print(f"Benchmarking on {path}...")

    count, duration = bench_os_walk(path)
    print(f"os.walk (no stat): {count} entries, {duration:.4f}s")

    count, duration = bench_os_walk_stat(path)
    print(f"os.walk (+ stat): {count} entries, {duration:.4f}s")

    count, duration = bench_pathlib_rglob(path)
    print(f"pathlib.rglob: {count} entries, {duration:.4f}s")

    count, duration = bench_dscan_entries(path)
    print(f"dscan.scan_entries: {count} entries, {duration:.4f}s")

    count, duration = bench_dscan_models(path)
    print(f"dscan.scan (models/stat): {count} entries, {duration:.4f}s")
