# PSells

[![Tests](https://github.com/pierremakhlouta/psells/actions/workflows/tests.yml/badge.svg)](https://github.com/pierremakhlouta/psells/actions/workflows/tests.yml)
[![Security](https://github.com/pierremakhlouta/psells/actions/workflows/security.yml/badge.svg)](https://github.com/pierremakhlouta/psells/actions/workflows/security.yml)

A command-line inventory and profit tracker for my reselling business.

PSells replaces the spreadsheet that used to run the business. It tracks the
products held, the sales made, stock returned to the supplying partner, and the
payouts made to that partner, and computes a live dashboard from all four.

## What it does

- Full inventory management: view, search, add, edit, delete
- Records sales, returns to the partner, and partner payouts
- Works out each item's partner cut from a rule set per item
- Computes stock levels, revenue, profit, and the balance owing to the partner

Every figure that can be derived is computed on demand rather than stored, so no
total can drift out of sync with the records it came from. See
[DATA_MODEL.md](DATA_MODEL.md) for the structure and [DECISIONS.md](DECISIONS.md)
for why it is built this way.

## Requirements

Python 3. The application itself uses only the standard library, so there is
nothing to install in order to run it.

`openpyxl` is needed only by `import_excel.py`, the one-time script that migrated
the original spreadsheet, and `pytest` only to run the test suite:

    pip install -r requirements.txt

## Running it

    python3 psells.py

Run it from the project root, since the data files are read from `data/`
relative to the working directory.

    0: Quit
    1: View Dashboard
    2: View Inventory
    3: Search
    4: Add
    5: Edit
    6: Delete
    7: Record Sale
    8: Record Return
    9: Record Payment

## Trying it with sample data

The real data files are not in this repository. Everything under `data/` is
gitignored, because this tracks a real business and its prices, margins and
commercial terms do not belong in a public repository.

To see the application working, copy the fake sample records into place first:

    mkdir -p data
    cp sample_data/*.json data/
    python3 psells.py

That copies the sample configuration across as well, which the application needs
in order to start. It will say so plainly if the configuration is missing rather
than failing partway through. The percentage in `sample_data/config.json` is a
placeholder, not the real figure.

The sample set is small and invented, but it covers the cases worth seeing: all
three partner-share modes, a discontinued item, an item that has sold out, a
return, and two partner payments.

## Running the tests

    pip install -r requirements.txt
    pytest

The suite covers the logic with no input or output: partner-share calculation in
all three modes, id assignment, product search, and the dashboard totals. It runs
on every push through GitHub Actions, along with a dependency vulnerability audit.

The tests need no data files. They build their own fixtures, so they run against
a fresh clone with an empty `data/` folder.

## Where this is going

PSells is built one layer at a time as a long-running project rather than a
finished product. The terminal application is the working core, covered by an
automated test suite that runs on every push. Planned on top of it are a move
from JSON files to a real database, a web API, containers, and cloud deployment,
carrying the same data model and business rules through each step.