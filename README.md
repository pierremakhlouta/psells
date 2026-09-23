# PSells

[![Tests](https://github.com/pierremakhlouta/psells/actions/workflows/tests.yml/badge.svg)](https://github.com/pierremakhlouta/psells/actions/workflows/tests.yml)
[![Security](https://github.com/pierremakhlouta/psells/actions/workflows/security.yml/badge.svg)](https://github.com/pierremakhlouta/psells/actions/workflows/security.yml)
[![Lint](https://github.com/pierremakhlouta/psells/actions/workflows/lint.yml/badge.svg)](https://github.com/pierremakhlouta/psells/actions/workflows/lint.yml)

An inventory and profit tracker for my reselling business, used from a browser
or from the terminal.

PSells replaces the spreadsheet that used to run the business. It tracks the
products held, the sales made, stock returned to the supplying partner, and the
payouts made to that partner, and computes a live dashboard from all four.

## What it does

- Full inventory management: view, browse by category, search, add, edit, delete
- Records sales, returns to the partner, and partner payouts
- Does all of it from a browser, in server-rendered pages, or from the terminal
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
Linux distributions. The terminal application uses only the standard library, so
there is nothing to install in order to run it.

The web pages and the HTTP API run in one process and need FastAPI, uvicorn,
Jinja2 for the templates, and python-multipart to read form posts. Development
also needs pytest, httpx2 for the test client, PyYAML so a test can read
`compose.yaml`, and openpyxl for `import_excel.py`, the one-time script that
read the original spreadsheet. psycopg, the PostgreSQL driver, is a runtime
requirement; the tests use it today and the application moves onto it next:

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

To see the application working, build a separate database from the schema, load
the invented sample records into it, and point the application at it and at the
sample configuration. From the project folder:

    sqlite3 /tmp/psells-sample.db < schema.sql
    sqlite3 /tmp/psells-sample.db < sample_data/seed.sql

    PSELLS_DB=/tmp/psells-sample.db PSELLS_CONFIG=sample_data/config.json python3 psells.py
    PSELLS_DB=/tmp/psells-sample.db PSELLS_CONFIG=sample_data/config.json uvicorn api:app

Both variables are set on the command itself rather than exported, so the next
command in the same terminal goes back to the real data. Do not copy the sample
files into `data/` on a machine that has real data there: the sample
configuration would replace the real partner percentage and the database would
be built where the real one lives. The percentage in `sample_data/config.json`
is a placeholder, not the real figure.

The sample set is small and invented, but it covers the cases worth seeing: all
three partner-share modes, a product discontinued at retail, one that has sold
out, a return, and two partner payments.

## The web interface

    uvicorn api:app --reload

Then open `http://127.0.0.1:8000/`. One process serves the pages and the API.

- **Inventory**, the home page: the nine dashboard figures above a table of
  every product with its stock, listed price, partner cut and retail status, and
  a search box that matches name or category.
- **Add** and **Edit** a product. The edit form opens filled in; a field emptied
  there is cleared, unlike the command line, where Enter keeps the current value.
- **Sell**, **Return** and **Edit** from each row with stock, **Record payment**
  from the navigation, and **Delete** from a product's edit page.

The pages are a view, not a second implementation, and three rules keep them
one. A page route calls the same `psells` functions the command line calls and
does no arithmetic on money, stock or partner share. Wherever a page shows a
figure the API also serves, a test asserts the two agree. And templates format
and never compute, which a test enforces by parsing every template and failing
on any arithmetic or any filter other than the one that formats money.

Every form answers a successful save with a 303 redirect, so refreshing the page
afterwards cannot repeat it. A refusal shows the form again with a sentence
beside each field that is wrong and everything already typed kept: 422 when what
was typed is wrong in itself, 409 when it was fine and the stock disagrees.

Any write that a browser labels as coming from another site is refused with a
403 before any route runs, including one sent from another server on the same
machine. See [DECISIONS.md](DECISIONS.md) for why this checks the browser's
labels rather than using a token.

## The HTTP API

`api.py` serves the same data over HTTP. It is another way in, not another
application: every figure it returns comes from the functions the command line
uses, and it works nothing out for itself. It is served by the same uvicorn
process as the pages; open `http://127.0.0.1:8000/docs`, which is generated from
the code and lists every endpoint with its fields and types.

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

## Running it in a container

The `Dockerfile` builds an image holding the code and nothing else. The
database and the configuration file are mounted into it at `/data` when it
starts, so an image never carries a record. It names every file it copies
rather than copying the folder, and `.dockerignore` keeps `data/` out of the
build altogether; `tests/test_container.py` fails if either stops being true.

To run it against the sample data, build a sample folder first, then the image:

    rm -rf /tmp/psells-sample && mkdir /tmp/psells-sample
    sqlite3 /tmp/psells-sample/psells.db < schema.sql
    sqlite3 /tmp/psells-sample/psells.db < sample_data/seed.sql
    cp sample_data/config.json /tmp/psells-sample/

    docker build -t psells .
    docker run --rm -p 127.0.0.1:8000:8000 -v /tmp/psells-sample:/data psells

Then open `http://127.0.0.1:8000/`. Inside the container the server listens on
`0.0.0.0`, because Docker forwards a published port to the container's network
interface and a server on the container's own `127.0.0.1` would never receive
it. `-p 127.0.0.1:8000:8000` is what keeps it to this machine. Leaving out the
`127.0.0.1:` publishes it to the whole network, which with no authentication
means anyone on the same Wi-Fi can change the records.

Do not mount the real `data/` folder into the container. SQLite's file locks
are not guaranteed to hold across Docker Desktop's file sharing, so the
container and the command line on the Mac could write at the same moment, and
the real data moves to PostgreSQL in this phase anyway.

### With Compose and PostgreSQL

`compose.yaml` runs the web server beside a PostgreSQL 18 database. The
application does not use the database yet; it still reads the SQLite file in
the mounted folder, and moves to PostgreSQL later in this phase.

Its settings, including the database password, live in `.env` beside
`compose.yaml`, which is gitignored and kept out of every image. Start from the
template and set a real password:

    cp .env.example .env
    openssl rand -hex 24      # paste the result as POSTGRES_PASSWORD in .env

With the sample folder built as above:

    docker compose up --build -d --wait
    docker compose ps
    docker compose exec db psql -U psells psells
    docker compose down

`--wait` returns once both services report healthy: the database when it
accepts connections, the web server when uvicorn does. Without it, a request
made straight after `up` can get an empty reply, because Docker accepts a
connection on the published port before the server inside is listening.

The web server is published on `127.0.0.1:8000` only. The database publishes no
port at all: only the web server reaches it, over the private network Compose
creates, and `docker compose exec db psql` is the way to a SQL prompt. Its
files live in a Docker volume named `psells_pgdata`, not in this folder.
`docker compose down` keeps that volume; `docker compose down -v` deletes it,
and with it the database. `tests/test_container.py` holds the port, password
and volume rules in place.

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

The suite needs a PostgreSQL to run against: `db-test` in `compose.yaml`, a
throwaway database that holds invented rows in memory, shares nothing with the
real one, and is published on `127.0.0.1:5433`. Start it once, then run pytest
as often as you like:

    pip install -r requirements-dev.txt
    docker compose --profile test up -d --wait db-test
    pytest
    docker compose --profile test stop db-test

Without it, pytest stops at once with one line saying how to start it, rather
than skipping the database tests and reporting a pass. The suite wipes the
database it is pointed at, so it refuses any whose name does not end in
`_test`. `PSELLS_TEST_DATABASE_URL` points it somewhere else.

Every warning is an error (`pytest.ini`), apart from one known deprecation in
Starlette's test client on Python 3.14, matched on its exact message.

Seven files, and the split is deliberate, so a red run says what kind of thing
broke before you read a line of it.

`test_domain.py` covers everything in `psells.py` that has no input or output:
partner-share in all three modes including its rounding, search, the dashboard
totals, the derived stock quantities, money formatting, and every write with its
rules (`create_product`, `update_product`, `create_sale`, `create_return`,
`create_payment`, `delete_product`) and the readers that turn a form's text into
their values.

`test_features.py` covers the ten menu functions end to end. They prompt and
print, so input is faked with pytest's `monkeypatch` and output is read back
with `capsys`. Each test queues one answer per question, which makes the length
of that queue a claim about how many questions the function asks: if it ever
asks one more, the queue runs dry and the test fails rather than hanging.

`test_api.py` drives the HTTP endpoints through FastAPI's test client, with the
connection dependency pointed at the same in-memory database.

`test_web.py` drives the pages the same way, reading each page with small
parsers built on the standard library, so an assertion names a cell in a row
or a field in a form rather than finding a string somewhere on the page. Its
tests submit through the forms the pages actually serve, and compare what the
pages show with what the API serves.

`test_cross_site.py` covers the refusal of writes from another site.

`test_schema.py` runs `schema_postgres.sql` on the real engine: every rule
tried with a row that breaks exactly that rule and refused by that rule's own
constraint, ids never reused, the view's derived stock, and the Python types
each column comes back as. Each test runs in a transaction that is rolled back
at the end, so nothing has to be cleaned up.

`test_container.py` reads the `Dockerfile`, `.dockerignore` and `compose.yaml`
and fails if the image could ever be built from the whole folder or from
`data/`, if it leaves out a module the server imports, if any port is published
beyond this machine, if the database publishes a port at all, or if a password
is written into `compose.yaml`.

No test needs a data file. The SQLite tests build databases in memory from
`schema.sql`, and the PostgreSQL tests build theirs from `schema_postgres.sql`,
so a constraint added to either is exercised automatically. On GitHub Actions
the test database is a service container of the same image, on the same
port. Everything runs on every push through GitHub Actions, alongside a
dependency vulnerability audit and a shellcheck pass over the shell scripts.
Dependabot checks every pinned version weekly and opens a pull request when one
has a newer release.

## Known limitations

Worth stating plainly rather than leaving to be discovered.

- **There is no authentication.** Anyone who can reach the port can read every
  figure and change every record, through the pages or the API. The server
  listens on `127.0.0.1` only, which is the whole of the protection at the
  moment, so do not put it on `0.0.0.0`. In a container it has to listen on
  `0.0.0.0`, and the same protection comes from publishing the port as
  `127.0.0.1:8000:8000`.
- **The protection against cross-site writes relies on the browser's labels.**
  Every current browser sends them, and a page cannot change them, but a token
  in every form would not depend on them. That is the thing to add alongside
  authentication.
- **The API can read and sell, and nothing else.** Every other write is in the
  web pages and the command line. Write endpoints wait until authentication is
  decided, rather than adding unauthenticated ways to change the records that
  nothing yet calls.
- **An id can be reused.** Deleting the newest product frees its id for the next
  one added. Products with sales or returns cannot be deleted, so no history is
  ever misattributed, but a browser tab left open on the deleted product's edit
  or sell form would post to the new product that inherited its id. This goes
  away with the move to PostgreSQL, whose ids are never reused.
- **Two rules live in the application rather than the database.** Available stock
  never going negative, and an intake quantity never being edited below what has
  already sold and returned, both span more than one table. SQLite does not allow
  a subquery inside a `CHECK` constraint, so neither can be expressed as one.
- **Notes cannot be cleared from the command line.** In its edit, a blank answer
  means keep the current value, so a note that has text cannot be blanked there.
  The web edit page can clear it.
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
finished product. It stores its data in SQLite behind a schema that enforces the
business rules, is used through server-rendered web pages, a terminal
application and an HTTP API that all call the same functions, is covered by an
automated test suite that runs on every push, and is backed up on a schedule.
Planned next are containers and PostgreSQL, then cloud deployment, carrying the
same data model and business rules through each step.
