"""Keep project notes, decisions, and next steps in a local SQLite notebook."""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
from typing import TextIO


SCHEMA_VERSION = 1
KINDS = ("note", "decision", "todo")
_FIELDS = "id, project, kind, body, created_at"
_COLUMNS = [
    ("id", "INTEGER", 0, 1),
    ("project", "TEXT", 1, 0),
    ("kind", "TEXT", 1, 0),
    ("body", "TEXT", 1, 0),
    ("created_at", "TEXT", 1, 0),
]


class TasknoteError(ValueError):
    """An input or database cannot be used."""


class NoteNotFound(TasknoteError):
    """The requested note is not in this notebook."""


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TasknoteError(f"{label} must not be empty")
    return value.strip()


def _kind(value: str) -> str:
    if value not in KINDS:
        raise TasknoteError("Kind must be note, decision, or todo")
    return value


def _database_path(database: Path) -> Path:
    return Path(os.path.abspath(Path(database).expanduser()))


def _file_info(path: Path) -> os.stat_result | None:
    try:
        metadata = path.stat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(metadata.st_mode):
        raise TasknoteError("The database path must point to a file")
    return metadata


def _connect(path: Path, mode: str) -> sqlite3.Connection:
    # as_uri escapes characters such as # and ? before SQLite parses the URI.
    connection = sqlite3.connect(path.as_uri() + f"?mode={mode}", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _check_schema(connection: sqlite3.Connection, allow_empty: bool = False) -> bool:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    objects = [
        (row[0], row[1])
        for row in connection.execute(
            "SELECT type, name FROM sqlite_master "
            "WHERE name NOT GLOB 'sqlite_*' ORDER BY type, name"
        )
    ]
    if version == 0 and not objects and allow_empty:
        return False
    if version != SCHEMA_VERSION:
        raise TasknoteError(
            f"Unsupported database schema version {version}; expected {SCHEMA_VERSION}"
        )
    if objects != [("table", "notes")]:
        raise TasknoteError("This database does not have the tasknote schema")
    columns = [
        (row[1], row[2].upper(), row[3], row[5])
        for row in connection.execute("PRAGMA table_info(notes)")
    ]
    if columns != _COLUMNS:
        raise TasknoteError("This database does not have the tasknote schema")
    return True


def _initialize(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE notes ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "project TEXT NOT NULL, "
        "kind TEXT NOT NULL CHECK (kind IN ('note', 'decision', 'todo')), "
        "body TEXT NOT NULL, "
        "created_at TEXT NOT NULL)"
    )
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def add_note(
    database: Path, body: str, project: str = "default", kind: str = "note"
) -> dict:
    """Save one note, creating a notebook only after the inputs are valid."""
    body = _text(body, "Note text")
    project = _text(project, "Project")
    kind = _kind(kind)
    path = _database_path(database)
    try:
        metadata = _file_info(path)
        allow_empty = metadata is None or metadata.st_size == 0
        if metadata is not None:
            # Check existing files without opening them for writing first.
            with closing(_connect(path, "ro")) as connection:
                _check_schema(connection, allow_empty=allow_empty)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)

        with closing(_connect(path, "rw" if metadata is not None else "rwc")) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                if not _check_schema(connection, allow_empty=allow_empty):
                    _initialize(connection)
                created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                cursor = connection.execute(
                    "INSERT INTO notes (project, kind, body, created_at) VALUES (?, ?, ?, ?)",
                    (project, kind, body, created_at),
                )
                row = connection.execute(
                    f"SELECT {_FIELDS} FROM notes WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()
                note = dict(row)
            return note
    except (OSError, sqlite3.Error) as error:
        raise TasknoteError(f"Could not save the note: {error}") from error


def list_notes(
    database: Path,
    project: str | None = None,
    kind: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Read newest notes first; a missing notebook is an empty notebook."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise TasknoteError("Limit must be between 1 and 1000")
    if project is not None:
        project = _text(project, "Project")
    if kind is not None:
        kind = _kind(kind)
    path = _database_path(database)
    try:
        if _file_info(path) is None:
            return []
        with closing(_connect(path, "ro")) as connection:
            _check_schema(connection)
            conditions = []
            parameters = []
            if project is not None:
                conditions.append("project = ?")
                parameters.append(project)
            if kind is not None:
                conditions.append("kind = ?")
                parameters.append(kind)
            query = f"SELECT {_FIELDS} FROM notes"
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY id DESC LIMIT ?"
            parameters.append(limit)
            return [dict(row) for row in connection.execute(query, parameters)]
    except (OSError, sqlite3.Error) as error:
        raise TasknoteError(f"Could not read the notebook: {error}") from error


def show_note(database: Path, note_id: int) -> dict:
    """Read one note by its positive integer ID."""
    if (
        isinstance(note_id, bool)
        or not isinstance(note_id, int)
        or not 1 <= note_id <= 2**63 - 1
    ):
        raise TasknoteError("Note ID must be between 1 and 9223372036854775807")
    path = _database_path(database)
    try:
        if _file_info(path) is None:
            raise NoteNotFound(f"Note {note_id} was not found")
        with closing(_connect(path, "ro")) as connection:
            _check_schema(connection)
            row = connection.execute(
                f"SELECT {_FIELDS} FROM notes WHERE id = ?", (note_id,)
            ).fetchone()
            if row is None:
                raise NoteNotFound(f"Note {note_id} was not found")
            return dict(row)
    except (OSError, sqlite3.Error) as error:
        raise TasknoteError(f"Could not read the notebook: {error}") from error


def _plain_note(note: dict) -> str:
    project = json.dumps(note["project"], ensure_ascii=False)
    header = f"#{note['id']} [{note['kind']}] {project} - {note['created_at']}"
    return header + "\n" + note["body"]


def _write(stream: TextIO, text: str) -> None:
    encoding = getattr(stream, "encoding", None)
    if encoding:
        text = text.encode(encoding, errors="backslashreplace").decode(encoding)
    stream.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", type=Path, default=Path(".tasknote/notes.db"), help="notebook database path"
    )
    parser.add_argument("--format", choices=("plain", "json"), default="plain")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="save a note, decision, or next step")
    add.add_argument("text", help="note text; quote it when it contains spaces")
    add.add_argument("--project", default="default")
    add.add_argument("--kind", choices=KINDS, default="note")
    listing = commands.add_parser("list", help="list the newest notes first")
    listing.add_argument("--project")
    listing.add_argument("--kind", choices=KINDS)
    listing.add_argument("--limit", type=int, default=20)
    showing = commands.add_parser("show", help="show a note by ID")
    showing.add_argument("id", type=int)
    args = parser.parse_args(argv)

    try:
        if args.command == "add":
            result = add_note(args.db, args.text, args.project, args.kind)
        elif args.command == "list":
            result = list_notes(args.db, args.project, args.kind, args.limit)
        else:
            result = show_note(args.db, args.id)
    except NoteNotFound as error:
        _write(sys.stderr, f"tasknote: {error}\n")
        return 1
    except (TasknoteError, OSError, ValueError, RuntimeError) as error:
        _write(sys.stderr, f"tasknote: {error}\n")
        return 2

    if args.format == "json":
        output = json.dumps(result, indent=2, ensure_ascii=True)
    elif isinstance(result, list):
        output = "\n\n".join(_plain_note(note) for note in result) or "No notes found."
    else:
        output = _plain_note(result)
    _write(sys.stdout, output + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
