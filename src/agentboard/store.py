"""Where the board's lines are kept. The board (board.py) only appends lines and reads them back; a Store does that.

FileStore, the plain file, is the only store: `<stream>.jsonl` in the board folder, one JSON object per line
(README.md, "The board file"). Another store (a server, an issue tracker) is a class with the same three methods,
given to config.configure(store=...); nothing else in agentboard changes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Protocol


class Store(Protocol):
    def append(self, stream: str, line: dict) -> None:
        """Add one line to `stream`. Never raises: a failed write warns on stderr."""

    def lines(self, stream: str) -> list[dict]:
        """Every line of `stream`, oldest first; [] when there is none. Lines that aren't JSON objects are skipped."""

    def changed(self, stream: str) -> float:
        """When `stream` last changed (any number that grows; 0 when there is none): `agents wait` re-reads only then."""


class FileStore:
    """`<stream>.jsonl` files in one folder."""

    def __init__(self, folder: Path):
        self.folder = folder

    def path(self, stream: str) -> Path:
        return self.folder / f"{stream}.jsonl"

    def append(self, stream: str, line: dict) -> None:
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            with self.path(stream).open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, separators=(",", ":"), sort_keys=True, default=str) + "\n")
        except OSError as exc:
            print(f"WARNING: could not write the board {self.path(stream)}: {exc}", file=sys.stderr)

    def lines(self, stream: str) -> list[dict]:
        path = self.path(stream)
        if not path.is_file():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def changed(self, stream: str) -> float:
        try:
            return self.path(stream).stat().st_mtime
        except OSError:
            return 0.0
