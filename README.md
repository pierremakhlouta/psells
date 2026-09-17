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

The HTTP API needs FastAPI and uvicorn. Development also needs pytest, httpx2
for the API tests, and openpyxl for `import_excel.py`, the one-time script that
read the original spreadsheet:

    pip install -r requirements.txt        # to run
    pip install -r requirements-dev.txt    # to work on it

## Running it

    python3 psells.py

The database and the configuration file are read from the `data/` folder beside
`psells.py`, not from the directory you happen to be standing in, so this works
from anywhere. The application exits with an explanation if either is missing.

Two environment variables override those paths:

    PSELLS_DB       the SQLite database file
    PSELLS_CONFIG   the JSON configuration file

Which is how to point the application at a copy rather than at the real records:

    sqlite3 data/psells.db ".backup 'copy.db'"
    PSELLS_DB=copy.db python3 psells.py

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

## The HTTP API

`api.py` serves the same data over HTTP. It is a second way in, not a second
application: every figure it returns comes from the functions the command line
uses, and it works nothing out for itself.

    uvicorn api:app --reload

Then open `http://127.0.0.1:8000/docs`, which is generated from the code and
lists every endpoint with its fields and types.

    GET  /products    every product, with stock and the partner cut per unit
    GET  /dashboard   the nine dashboard figures
    POST /sales       record one sale

All money is sent and received as a whole number of cents, never as dollars and
never as a formatted string. That matches how it is stored, keeps every value
exact, and leaves formatting to whatever is showing it to a person.

The server listens on `127.0.0.1` only, so nothing else on the network can reach
it. That matters, because there is no authentication of any kind yet.

To try it against a copy rather than the real records:

    sqlite3 data/psells.db ".backup 'copy.db'"
    PSELLS_DB=copy.db uvicorn api:app

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

    pip install -r requirements-dev.txt
    pytest

Three files, and the split is deliberate, so a red run says what kind of thing
broke before you read a line of it.

`test_domain.py` covers the calculations that have no input or output:
partner-share in all three modes including its rounding, search, the dashboard
totals, the derived stock quantities, the rule that a product with history
cannot be deleted, and `create_sale`.

`test_features.py` covers the ten menu functions end to end. They prompt and
print, so input is faked with pytest's `monkeypatch` and output is read back
with `capsys`. Each test queues one answer per question, which makes the length
of that queue a claim about how many questions the function asks: if it ever
asks one more, the queue runs dry and the test fails rather than hanging.

`test_api.py` drives the HTTP endpoints through FastAPI's test client, with the
connection dependency pointed at the same in-memory database.

No test needs a data file. They build databases in memory from `schema.sql`
itself, so a constraint added to the schema is exercised by the existing tests
automatically. Everything runs on every push through GitHub Actions, alongside a
dependency vulnerability audit and a shellcheck pass over the shell scripts.

## Known limitations

Worth stating plainly rather than leaving to be discovered.

- **The API has no authentication.** Anyone who can reach the port can read
  every figure and record a sale. It listens on `127.0.0.1` only, which is the
  whole of the protection at the moment, so do not put it on `0.0.0.0`.
- **The API can read and sell, and nothing else.** Adding, editing, deleting,
  returns and payments are still command line only.
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
