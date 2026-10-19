# Next steps

The first version stores entries and retrieves them by project, kind, or ID.
The next work is about making a notebook useful as a project changes. These
estimates include tests and documentation and exclude the starter already built.

## Editing, search, and tags (6-8 hours)

- Edit an entry while retaining its creation time and recording the last edit.
- Search note text with predictable matching and ordering.
- Add tags and combined filters without changing project labels.
- Test Unicode searches, empty edits, and notes containing SQL punctuation.

Done when entries can be corrected and found by their contents without changing
unrelated notes.

## Export, backup, and restore (6-8 hours)

- Export a notebook to JSON and readable Markdown.
- Validate imported records before changing a notebook.
- Define how duplicate IDs and repeated imports are handled.
- Create backups through SQLite's backup interface and verify restored notebooks.
- Test interrupted imports and malformed backups.

Done when a notebook can be backed up and restored with its entries intact, and
invalid imports do not leave partially written data.

## Database upgrades and recovery (5-7 hours)

- Introduce versioned migrations for the editing and tag schema.
- Back up notebooks before a migration and apply each upgrade in a transaction.
- Add an inspection command for schema versions and basic integrity checks.
- Test upgrades from the original schema and interrupted migrations.

Done when an existing notebook can be upgraded without losing entries, and an
unsupported or damaged notebook gets a clear, recoverable error.

## Project management and defaults (4-6 hours)

- Add project descriptions and an archive state.
- Rename projects without changing entry IDs.
- Make the default notebook path configurable instead of relying only on the
  current directory.
- Define command-line overrides and test paths across platforms.

Done when users can keep one notebook across several folders and reorganize
project labels without copying entries by hand.

The remaining estimate is **21-29 hours**. These are proposed next steps for a new
project, not completed hours or a promised release date.
