import contextlib
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import tasknote


class TasknoteTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.database = self.root / "notes.db"

    def run_cli(self, *args, database=None, output_format="json"):
        stdout = io.StringIO()
        stderr = io.StringIO()
        database = self.database if database is None else database
        argv = ["--db", str(database), "--format", output_format, *args]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = tasknote.main(argv)
            except SystemExit as error:
                code = error.code
        return code, stdout.getvalue(), stderr.getvalue()

    def add(self, body, *args):
        code, stdout, stderr = self.run_cli("add", body, *args)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stderr, "")
        return json.loads(stdout)

    def test_add_and_show_persist_a_note_with_utc_timestamp(self):
        before = datetime.now(timezone.utc)
        note = self.add("Check the parser before release.")
        code, stdout, stderr = self.run_cli("show", str(note["id"]))
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(json.loads(stdout), note)
        self.assertEqual(set(note), {"id", "project", "kind", "body", "created_at"})
        self.assertEqual(note["project"], "default")
        self.assertEqual(note["kind"], "note")
        self.assertEqual(note["body"], "Check the parser before release.")
        self.assertIsInstance(note["id"], int)
        timestamp = datetime.fromisoformat(note["created_at"].replace("Z", "+00:00"))
        self.assertEqual(timestamp.utcoffset().total_seconds(), 0)
        self.assertLessEqual(abs((timestamp - before).total_seconds()), 5)
        with contextlib.closing(sqlite3.connect(self.database)) as connection, connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 1)

    def test_list_filters_before_applying_newest_first_limit(self):
        first = self.add("First todo", "--project", "parser", "--kind", "todo")
        second = self.add("Second todo", "--project", "parser", "--kind", "todo")
        self.add("Decision", "--project", "parser", "--kind", "decision")
        self.add("Other project", "--project", "viewer", "--kind", "todo")
        newest = self.add("Newest todo", "--project", "parser", "--kind", "todo")
        code, stdout, stderr = self.run_cli("list", "--project", "parser", "--kind", "todo", "--limit", "2")
        self.assertEqual((code, stderr), (0, ""))
        notes = json.loads(stdout)
        self.assertEqual([note["id"] for note in notes], [newest["id"], second["id"]])
        self.assertNotIn(first["id"], [note["id"] for note in notes])
        _, stdout, _ = self.run_cli("list", "--project", "does-not-exist")
        self.assertEqual(json.loads(stdout), [])

    def test_default_list_limit_is_twenty(self):
        identifiers = [self.add(f"Item {number}")["id"] for number in range(22)]
        code, stdout, stderr = self.run_cli("list")
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual([note["id"] for note in json.loads(stdout)], list(reversed(identifiers))[:20])

    def test_reads_of_missing_database_create_nothing(self):
        database = self.root / "not-created" / "notes.db"
        code, stdout, stderr = self.run_cli("list", database=database)
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(json.loads(stdout), [])
        self.assertFalse(database.parent.exists())
        code, stdout, stderr = self.run_cli("show", "1", database=database)
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertTrue(stderr.strip())
        self.assertFalse(database.parent.exists())

    def test_missing_note_is_distinct_from_database_error(self):
        self.add("An existing note")
        code, stdout, stderr = self.run_cli("show", "999")
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertTrue(stderr.strip())
        self.assertNotIn("Traceback", stderr)

    def test_note_id_beyond_sqlite_integer_range_reports_input_error(self):
        self.add("An existing note")
        code, stdout, stderr = self.run_cli("show", "9223372036854775808")
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertTrue(stderr.strip())
        self.assertNotIn("Traceback", stderr)

    def test_empty_body_and_project_are_rejected_before_database_creation(self):
        cases = [
            ("add", ""),
            ("add", " \t\r\n "),
            ("add", "A note", "--project", ""),
            ("add", "A note", "--project", " \t "),
        ]
        for args in cases:
            with self.subTest(args=args):
                code, stdout, stderr = self.run_cli(*args)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertTrue(stderr.strip())
                self.assertFalse(self.database.exists())

    def test_invalid_limit_kind_and_id_are_rejected(self):
        cases = [
            ("list", "--limit", "0"),
            ("list", "--limit", "-1"),
            ("list", "--limit", "1001"),
            ("show", "0"),
            ("show", "-1"),
            ("show", "abc"),
            ("add", "A note", "--kind", "unknown"),
        ]
        for args in cases:
            with self.subTest(args=args):
                code, stdout, stderr = self.run_cli(*args)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertTrue(stderr.strip())
                self.assertNotIn("Traceback", stderr)
                self.assertFalse(self.database.exists())

    def test_sql_text_is_stored_as_data(self):
        body = "'); DROP TABLE notes; --"
        project = "demo' OR 1=1 --"
        note = self.add(body, "--project", project)
        self.add("Ordinary note", "--project", "other")
        code, stdout, stderr = self.run_cli("list", "--project", project)
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(json.loads(stdout), [note])
        self.assertEqual(note["body"], body)
        self.assertEqual(note["project"], project)
        with contextlib.closing(sqlite3.connect(self.database)) as connection, connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM notes").fetchone()[0], 2)

    def test_multiline_body_survives_round_trip(self):
        body = "Use the small fixture.\n\n- Check empty input\n- Keep the existing output\n"
        note = self.add(body, "--kind", "decision")
        code, stdout, stderr = self.run_cli("show", str(note["id"]))
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(json.loads(stdout)["body"], body.strip())

    def test_failed_write_rolls_back_and_preserves_existing_notes(self):
        original = self.add("Keep this note")
        original_connect = sqlite3.connect

        class FailingConnection(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                cursor = super().execute(sql, parameters)
                if sql.lstrip().upper().startswith("INSERT INTO NOTES"):
                    raise sqlite3.OperationalError("simulated write failure")
                return cursor

        def connect(*args, **kwargs):
            kwargs["factory"] = FailingConnection
            return original_connect(*args, **kwargs)

        with mock.patch.object(tasknote.sqlite3, "connect", side_effect=connect):
            code, stdout, stderr = self.run_cli("add", "This write fails")
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertTrue(stderr.strip())
        code, stdout, stderr = self.run_cli("list")
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(json.loads(stdout), [original])
        next_note = self.add("This write succeeds")
        self.assertEqual(next_note["id"], original["id"] + 1)

    def test_foreign_database_is_rejected_without_modification(self):
        with contextlib.closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("CREATE TABLE samples (value TEXT)")
            connection.execute("INSERT INTO samples VALUES ('example')")
        for version in (0, 1):
            with contextlib.closing(sqlite3.connect(self.database)) as connection, connection:
                connection.execute(f"PRAGMA user_version = {version}")
            original = self.database.read_bytes()
            for args in (("add", "A note"), ("list",), ("show", "1")):
                with self.subTest(version=version, args=args):
                    code, stdout, stderr = self.run_cli(*args)
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertTrue(stderr.strip())
                    self.assertEqual(self.database.read_bytes(), original)
        with contextlib.closing(sqlite3.connect(self.database)) as connection, connection:
            self.assertEqual(connection.execute("SELECT value FROM samples").fetchall(), [("example",)])

    def test_newer_database_version_is_rejected_without_modification(self):
        self.add("Keep this note")
        with contextlib.closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("PRAGMA user_version = 99")
        original = self.database.read_bytes()
        for args in (("add", "New note"), ("list",), ("show", "1")):
            with self.subTest(args=args):
                code, stdout, stderr = self.run_cli(*args)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertTrue(stderr.strip())
                self.assertEqual(self.database.read_bytes(), original)

    def test_invalid_database_errors_do_not_print_tracebacks(self):
        malformed = self.root / "malformed.db"
        malformed.write_bytes(b"This is not a SQLite database.\n")
        original = malformed.read_bytes()
        for database in (malformed, self.root):
            for args in (("add", "A note"), ("list",), ("show", "1")):
                with self.subTest(database=database, args=args):
                    code, stdout, stderr = self.run_cli(*args, database=database)
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertTrue(stderr.strip())
                    self.assertNotIn("Traceback", stderr)
        self.assertEqual(malformed.read_bytes(), original)

    def test_reads_support_uri_special_characters_and_leave_database_unchanged(self):
        folder = "space # percent %" if sys.platform == "win32" else "space # question ? percent %"
        database = self.root / folder / "notes #1.db"
        code, stdout, stderr = self.run_cli("add", "URI path example", database=database)
        self.assertEqual((code, stderr), (0, ""))
        note = json.loads(stdout)
        original = database.read_bytes()
        original_files = sorted(path.name for path in database.parent.iterdir())
        for args in (("list",), ("show", str(note["id"]))):
            with self.subTest(args=args):
                code, stdout, stderr = self.run_cli(*args, database=database)
                self.assertEqual((code, stderr), (0, ""))
                value = json.loads(stdout)
                self.assertEqual(value, [note] if args[0] == "list" else note)
                self.assertEqual(database.read_bytes(), original)
                self.assertEqual(sorted(path.name for path in database.parent.iterdir()), original_files)

    def test_unicode_notes_work_with_legacy_console_encoding(self):
        note = self.add("Review \u65e5\u672c\u8a9e labels", "--project", "demo-\u03bb")
        for output_format in ("plain", "json"):
            with self.subTest(output_format=output_format):
                buffer = io.BytesIO()
                output = io.TextIOWrapper(buffer, encoding="cp1252")
                errors = io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    code = tasknote.main(["--db", str(self.database), "--format", output_format, "show", str(note["id"])])
                output.flush()
                text = buffer.getvalue().decode("cp1252")
                output.detach()
                self.assertEqual((code, errors.getvalue()), (0, ""))
                self.assertTrue(text)
                if output_format == "json":
                    self.assertEqual(json.loads(text), note)

    def test_default_database_stays_in_the_current_directory(self):
        script = Path(tasknote.__file__).resolve()
        list_result = subprocess.run(
            [sys.executable, str(script), "--format", "json", "list"],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=20,
        )
        self.assertEqual(list_result.returncode, 0, list_result.stderr)
        self.assertEqual(json.loads(list_result.stdout), [])
        self.assertFalse((self.root / ".tasknote").exists())
        add_result = subprocess.run(
            [sys.executable, str(script), "--format", "json", "add", "Local fixture"],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=20,
        )
        self.assertEqual(add_result.returncode, 0, add_result.stderr)
        self.assertEqual(json.loads(add_result.stdout)["body"], "Local fixture")
        self.assertTrue((self.root / ".tasknote" / "notes.db").is_file())
        self.assertFalse(self.database.exists())


if __name__ == "__main__":
    unittest.main()
