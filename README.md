# dscan

`dscan` is a fast, concurrent directory tree scanner for Python 3.12+. It provides a high-level API for traversing large file systems with advanced filtering capabilities, yielding either raw `os.DirEntry` objects or rich Pydantic-based metadata models.

## Key Features

- **🚀 Concurrent Scanning:** Uses a thread pool and a work-stealing queue for efficient traversal, especially on high-latency file systems.
- **✨ Rich Metadata Models:** Optionally yields `FileEntry` and `DirectoryEntry` objects with pre-calculated sizes, extensions, and timestamps.
- **🛡️ Flexible Filtering:** Built-in support for extension allowlists/denylists, glob pattern matching, and custom filter callables.
- **📐 Traversal Control:** Limit scan depth, ignore specific directories (with sensible defaults like `.git` and `.venv`), or only descend into specific subtrees.
- **🧵 Thread-Safe:** Designed for concurrent execution with a managed internal state.

---

## Installation

```bash
pip install dscan
```

*(Note: Requires Python 3.12+ and `pydantic`)*

---

## Quick Start

### Basic Scanning
The `scan` function is the primary entry point, yielding rich metadata models.

```python
from dscan import scan

# Yield every file and directory under the current path
for entry in scan("."):
    print(f"{entry.name} - {entry.path}")
```

### High-Performance Raw Scanning
If you only need raw `os.DirEntry` objects (for maximum performance or minimal overhead), use `scan_entries`.

```python
from dscan import scan_entries

for entry in scan_entries("~/Documents", max_depth=2):
    if entry.is_file():
        print(f"File: {entry.name}")
```

---

## Powerful Filtering

`dscan` provides a comprehensive set of filters directly in the `scan` and `scan_entries` functions.

### Extension Filtering
Include or exclude specific file types.

```python
# Only Python and Markdown files
for file in scan(".", extensions={".py", ".md"}):
    print(file.path)

# Skip large binary files
for file in scan(".", ignore_extensions={".bin", ".exe"}):
    print(file.path)
```

### Pattern Matching
Match or ignore files and directories using glob patterns.

```python
# Find all "test" related files
for entry in scan(".", match="test_*"):
    print(entry.name)

# Ignore all hidden files/folders
for entry in scan(".", ignore_pattern=".*"):
    print(entry.name)
```

### Traversal Limits
Control how deep and where the scanner goes.

```python
# Scan only immediate children (depth 0)
for entry in scan(".", max_depth=0):
    print(entry.name)

# Only descend into 'src' and 'lib' folders
for entry in scan(".", only_dirs=["src", "lib"]):
    print(entry.path)

# Skip specific heavy directories
for entry in scan(".", ignore_dirs=["node_modules", "target"]):
    print(entry.path)
```

### Custom Filters
Provide your own logic for ultimate control.

```python
def is_large_file(entry):
    return entry.is_file() and entry.stat().st_size > 1_000_000

for entry in scan(".", custom_filter=is_large_file):
    print(f"Found large file: {entry.name}")
```

---

## Data Models

When using `scan()`, you receive either a `FileEntry` or a `DirectoryEntry`.

### `FileEntry`
- `name`: Filename without extension.
- `extension`: Lowercase extension without the dot (e.g., `py`).
- `path`: Full path to the file.
- `dir_path`: Path to the containing directory.
- `size`: File size in bytes.
- `created_at`: `datetime` object.
- `modified_at`: `datetime` object.

### `DirectoryEntry`
- `name`: Directory name.
- `path`: Full path to the directory.
- `parent_path`: Path to the parent directory.
- `created_at`: `datetime` object.
- `modified_at`: `datetime` object.

---

## Comparison

| Feature | `os.walk` | `pathlib.rglob` | `dscan` |
| :--- | :---: | :---: | :---: |
| **Concurrency** | ❌ | ❌ | ✅ |
| **Built-in Models** | ❌ | ❌ | ✅ |
| **Depth Control** | Manual | ❌ | ✅ |
| **Exclusion Rules** | Manual | ❌ | ✅ |
| **Performance** | Good | Moderate | **High** |

---

## License

MIT
