# dscan

[![PyPI](https://img.shields.io/pypi/v/dscanpy)](https://pypi.org/project/dscanpy/)
[![Python](https://img.shields.io/pypi/pyversions/dscanpy)](https://pypi.org/project/dscanpy/)
[![License](https://img.shields.io/pypi/l/dscanpy)](LICENSE)


`dscan` is a concurrent directory scanner for Python 3.12+. It wraps `os.scandir` in a thread pool with a work-stealing queue, exposing a filtering API that covers most of what you'd otherwise implement by hand on top of `os.walk`.

Two modes: `scan_entries` yields raw `os.DirEntry` objects with minimal overhead; `scan` yields dataclass models with pre-computed metadata.

---

## Why concurrent scanning?

On a local SSD, directory traversal is fast enough that threading adds more overhead than it saves. `scan_entries` still matches or edges out `os.walk`, but the real case for concurrency is **network-attached storage**.

On SMB shares, NFS mounts, or any high-latency filesystem, each `scandir` call blocks waiting for a server response. `os.walk` does this serially — one directory at a time. dscan keeps multiple directories in-flight simultaneously, so workers aren't sitting idle while the network responds. On deep trees with many subdirectories, this compounds significantly.

---

## Benchmarks

### Local SSD (~4M entries, MacBook)

| | entries | time |
|---|---|---|
| `os.walk` (no stat) | 4,046,505 | 33.30s |
| `os.walk` (+ stat) | 4,039,313 | 85.24s |
| `dscan.scan_entries` | 4,046,502 | **31.90s** |
| `dscan.scan` (models) | 4,014,758 | 140.15s |

`scan_entries` is on par with bare `os.walk`. `scan` is slower because stat calls happen on the main thread serially — the workers parallelise `scandir`, not `stat`. Use `scan` when you want the structured output; use `scan_entries` when throughput matters.

### Simulated network latency (5ms per directory)

```python
# rough simulation
import time, os
_real = os.scandir
os.scandir = lambda p: (time.sleep(0.005), _real(p))[1]
```

| | time |
|---|---|
| `os.walk` | ~linear with directory count |
| `dscan.scan_entries` | scales with `max_workers` |

At 5ms latency per directory, a tree with 10,000 directories takes ~50s serially. With 16 workers dscan brings that to ~4s. The deeper and wider the tree, the bigger the difference.

---

## Installation

```bash
pip install dscan
```

Requires Python 3.12+. No other dependencies.

---

## Usage

### Basic scan

```python
from dscan import scan

for entry in scan("."):
    print(f"{entry.name} - {entry.path}")
```

### Raw entries (lower overhead)

```python
from dscan import scan_entries

for entry in scan_entries("~/Documents", max_depth=2):
    if entry.is_file():
        print(entry.name)
```

---

## Filtering

### Extensions

```python
# Only Python and Markdown files
for file in scan(".", extensions={".py", ".md"}):
    print(file.path)

# Skip compiled files
for file in scan(".", ignore_extensions={".bin", ".exe"}):
    print(file.path)
```

### Glob patterns

```python
# Only test files
for entry in scan(".", match="test_*"):
    print(entry.name)

# Skip hidden files and directories
for entry in scan(".", ignore_pattern=".*"):
    print(entry.name)
```

### Directory traversal

```python
# Immediate children only
for entry in scan(".", max_depth=0):
    print(entry.name)

# Only descend into src/ and lib/
for entry in scan(".", only_dirs=["src", "lib"]):
    print(entry.path)

# Skip specific directories
# .git, .idea, .venv, __pycache__ are skipped by default
for entry in scan(".", ignore_dirs=["node_modules", "dist"]):
    print(entry.path)

# Disable all default ignores
for entry in scan(".", ignore_dirs=[]):
    print(entry.path)
```

### Custom filter

```python
def is_large_file(entry):
    return entry.is_file() and entry.stat().st_size > 1_000_000

for entry in scan(".", custom_filter=is_large_file):
    print(entry.name)
```

### Tuning workers

```python
# default is min(32, cpu_count * 2)
# increase on high-latency mounts
for entry in scan_entries("/mnt/nas", max_workers=32):
    print(entry.path)
```

---

## Data Models

`scan()` returns `FileEntry` or `DirectoryEntry` dataclasses.

### `FileEntry`

| field | description |
|---|---|
| `name` | filename without extension |
| `extension` | lowercase extension, no leading dot |
| `path` | full path |
| `dir_path` | containing directory |
| `size` | bytes |
| `created_at` | `datetime` |
| `modified_at` | `datetime` |

### `DirectoryEntry`

| field | description |
|---|---|
| `name` | directory name |
| `path` | full path |
| `parent_path` | parent directory |
| `created_at` | `datetime` |
| `modified_at` | `datetime` |

---

## vs the stdlib

| | `os.walk` | `pathlib.rglob` | `dscan` |
|---|:---:|:---:|:---:|
| Concurrent traversal | No | No | Yes |
| Built-in models | No | No | Yes |
| Depth limit | Manual | No | Yes |
| Directory exclusions | Manual | No | Yes |

---

## License

MIT