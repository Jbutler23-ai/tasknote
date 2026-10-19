# Try a sample notebook

Run these commands from a folder where you want to keep the sample database.
They use made-up notes and create only `sample.sqlite3`.

```sh
tasknote --db sample.sqlite3 add "Try the small sample input" --project parser --kind todo
tasknote --db sample.sqlite3 add "Use UTF-8 for the sample files" --project parser --kind decision
tasknote --db sample.sqlite3 list --project parser
tasknote --db sample.sqlite3 --format json list --kind todo
```

Use an ID shown in the output with `tasknote --db sample.sqlite3 show ID`.
Running the example again adds new entries; it does not replace existing notes.
