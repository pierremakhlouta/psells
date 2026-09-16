# PSells

[![Tests](https://github.com/pierremakhlouta/psells/actions/workflows/tests.yml/badge.svg)](https://github.com/pierremakhlouta/psells/actions/workflows/tests.yml)
[![Security](https://github.com/pierremakhlouta/psells/actions/workflows/security.yml/badge.svg)](https://github.com/pierremakhlouta/psells/actions/workflows/security.yml)

A command-line inventory and profit tracker for my reselling business.

PSells replaces the spreadsheet that used to run the business. It tracks the
products held, the sales made, stock returned to the supplying partner, and the
payouts made to that partner, and computes a live dashboard from all four.

## What it does

- Full inventory management: view, browse by category, search, add, edit, delete
- Records sales, returns to the partner, and partner payouts
- Works out each item's partner cut from a rule set per item
- Computes stock levels, revenue, profit, and the balance owing to the partner
- Refuses to delete a product that has sales or returns against it
- Backs itself up daily, on a schedule, and verifies each copy

Every figure that can be derived is computed on demand rather than stored, so no
total can drift out of sync with the records it came from. See
[DATA_MODEL.md](DATA_MODEL.md) for the structure and [DECISIONS.md](DECISIONS.md)
for why it is built this way.

## Requirements

Python 3, and the `sqlite3` command line tool, which ships with macOS and most
Linux distributions. The application itself uses only the standard library, so
there is nothing to install in order to run it.

`openpyxl` is needed only by `import_excel.py`, the one-time script that read the
original spreadsheet, and `pytest` only to run the test suite:

    pip install -r requirements.txt

## Running it

    python3 psells.py

Run it from the project root. The database and the configuration file are read
from `data/` relative to the working directory, and the application exits with an
explanation if either is missing.

    0: Quit
    1: View Dashboard
    2: View Inventory
    3: List Categories
    4: Search
    5: Add
    6: Edit
    7: Delete
    8: Record Sale
    9: Record Return
    10: Record Payment

Search matches a product name or a category, so typing a category returns
everything in it. Choosing a product to sell, edit or delete matches on the name
only, deliberately, so that an action is never offered against a whole category
at once.

## Trying it with sample data

The real data is not in this repository. Everything under `data/` is gitignored,
because this tracks a real business and its prices, margins and commercial terms
do not belong in a public repository.

To see the application working, build a database from the schema and load the
invented sample records into it:

    mkdir -p data
    cp sample_data/config.json data/
    sqlite3 data/psells.db < schema.sql
    sqlite3 data/psells.db < sample_data/seed.sql
    python3 psells.py

The configuration file has to be copied across as well, because the application
needs it in order to start and will say so plainly rather than failing partway
through a task. The percentage in `sample_data/config.json` is a placeholder, not
the real figure.

The sample set is small and invented, but it covers the cases worth seeing: all
three partner-share modes, a product discontinued at retail, one that has sold
out, a return, and two partner payments.

## Backups

`backup.sh` takes a verified copy of the database into `~/PSells-Backups/daily/`,
logs the result to `~/PSells-Backups/backup.log`, and removes copies older than
thirty days. It uses SQLite's own backup command rather than `cp`, because a
plain file copy of a live database can miss changes that are still sitting in a
journal beside it.

It verifies each copy before it deletes anything: the new file has to pass an
integrity check and contain at least one product. A backup that is valid and
empty is worse than no backup, because it looks fine in a listing.

Run it by hand:

    ./backup.sh

Or daily, through cron:

    0 9 * * * "$HOME/path/to/psells/backup.sh"

Note that cron does not run jobs it missed. On a laptop that sleeps, a time when
the machine is reliably awake matters more than the exact hour.

## Running the tests

    pip install -r requirements.txt
    pytest

The suite covers the logic that has no input or output: partner-share
calculation in all three modes including its rounding, product and category
search, the dashboard totals, the derived stock quantities, and the rule that a
product with history cannot be deleted.

The tests need no data files. They build databases in memory from `schema.sql`
itself, so a constraint added to the schema is exercised by the existing tests
automatically. They run on every push through GitHub Actions, along with a
dependency vulnerability audit.

## Known limitations

Worth stating plainly rather than leaving to be discovered.

- **The features are not automatically tested.** Every function that prompts,
  prints or writes is covered by manual testing only. A green badge here means
  the calculations are right, not that the application works.
- **Two rules live in the application rather than the database.** Available stock
  never going negative, and an intake quantity never being edited below what has
  already sold and returned, both span more than one table. SQLite does not allow
  a subquery inside a `CHECK` constraint, so neither can be expressed as one.
- **Notes cannot be cleared once set.** In edit mode a blank answer means keep
  the current value, so there is no way to blank a note that already has text.
- **One prompt in edit does not accept a blank answer.** Every field takes Enter
  to keep the current value, except the question asking whether to change the
  partner share, which requires an explicit yes or no.
- **A partner share of zero is accepted.** Deliberate, because at least one real
  item is owned outright.
- **Corrupt input files are only partly handled.** A missing or malformed
  configuration file exits cleanly with a message. A corrupt database does not.
- **`migrate_to_sqlite.py` no longer runs.** It is the one-time script that moved
  the data out of JSON files, kept as the record of how that was done. It was
  written against the code as it stood before the move and is not maintained.

## Where this is going

PSells is built one layer at a time as a long-running project rather than a
finished product. The terminal application is the working core, storing its data
in SQLite behind a schema that enforces the business rules, covered by an
automated test suite that runs on every push, and backed up on a schedule.
Planned on top of it are a web API, a small web interface, containers, and cloud
deployment, carrying the same data model and business rules through each step.
