# tasknote

tasknote is a small local notebook for project notes, decisions, and next steps.
Add an entry from the terminal, give it a project name, and look it up later.
Entries are stored in a SQLite file on your computer.

It's for keeping track of personal projects without opening another app or
setting up an account. It uses Python 3.10 or newer and the standard library.
There are no runtime dependencies or network calls.

## Install

```sh
git clone https://github.com/Jbutler23-ai/tasknote.git
cd tasknote
python -m pip install .
tasknote --help
```

You can also run `python tasknote.py` directly. For development, use
`python -m pip install --editable .`.

## Add and find entries

```sh
tasknote add "Try the parser on a small fixture" --project parser --kind todo
tasknote add "Keep the input format as plain text" --project parser --kind decision
tasknote list --project parser
tasknote show 1
```

The three entry kinds are `note`, `decision`, and `todo`. The default kind is
`note`, and the default project name is `default`. Project names are labels;
they do not have to match a folder. Entries get an ID and a UTC creation time.

`list` returns the newest entries first, with a default limit of 20. Filter by
project, kind, or both:

```sh
tasknote list --project parser --kind todo --limit 10
```

Limits must be between 1 and 1,000. `show` retrieves an entry by its ID regardless
of project. A todo is currently an entry type, not a task with a completion state.

## Choose a notebook

By default, tasknote uses `.tasknote/notes.db` in the current working directory.
Changing directories changes that default notebook. To use one notebook across
several folders, supply the same path each time:

```sh
tasknote --db ./project-notes.sqlite3 add "Try the sample workflow" --project demo
tasknote --db ./project-notes.sqlite3 list
```

The first valid `add` creates the notebook and its parent directory if needed.
Listing a notebook that does not exist returns an empty result without creating
anything. An unrecognized database or unsupported schema version produces an
error; tasknote does not replace it.

Notes are stored as ordinary local data, without encryption. Keep private
notebooks and backups out of public repositories. This repository ignores the
default notebook directory and common SQLite filenames. The included examples
use made-up project notes.

## JSON output

Global options go before the command:

```sh
tasknote --format json list --project parser
tasknote --format json show 1
tasknote --db ./project-notes.sqlite3 --format json add "Check the fixture" --kind todo
```

`add` and `show` return one object with `id`, `project`, `kind`, `body`, and
`created_at`. `list` returns an array of those objects. JSON goes to stdout and
errors go to stderr.

Exit status is 0 for success, 1 when `show` cannot find an entry, and 2 for invalid
input or a database error.

## Current limits

This first version supports adding, listing, and showing entries. It does not
yet edit notes, search their contents, manage tags, mark todos complete, or
export and restore a notebook. There is no sync or shared-user mode. See
[ROADMAP.md](ROADMAP.md) for proposed next steps.

## Development

```sh
python -m unittest discover -s tests -v
python -m pip install build
python -m build
```

The test workflow covers Windows, Linux, and macOS with Python 3.10, 3.12, and
3.14, including installation checks. Tests use temporary notebooks.

## License

[MIT](LICENSE).
