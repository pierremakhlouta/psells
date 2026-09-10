# Decisions

PSells is an application for tracking a reselling business: the products held,
the sales made, items returned to suppliers, and payouts to a partner. This file
records the notable design choices and why; see the README for what the project
is and DATA_MODEL for how the data is structured. Kept short, the interesting
calls only, not every detail, and no specific business figures.

- **JSON, then SQLite.** Started with JSON storage because it maps directly onto
  Python's lists and dicts, preserves value types, and keeps the early model
  simple while the data structure is being worked out. Moving to SQLite as
  querying and relationships become central, with items, sales, returns, and
  payments needing reliable links and real queries.

- **Store facts, compute the rest.** Only raw facts are saved (an item exists, a
  sale happened, a payment was made). The stored data is the source of truth, and
  everything derived (available stock, revenue, profit, partner totals, the
  dashboard) is calculated from it, never stored. Storing derived values just
  lets them drift out of sync with the facts.

- **People use names, the program uses IDs.** Each item gets an internal ID it
  never has to show, so existing physical stock needs no relabeling. Sales and
  returns link to items by ID under the hood while the user works by name; if
  multiple items share a name, the app asks the user to choose the correct one.

- **History stays fixed.** Each sale records its own figures at the moment it
  happens, so later changes to an item never rewrite the numbers on past sales.
  For example, changing an item's price later does not change the price recorded
  on an earlier sale.

- **Real data stays out of the repo.** Actual inventory and financials are never
  committed, preventing accidental exposure of business data. Everything under
  the data folder is ignored with no exceptions, so no rule has to be trusted to
  tell real records apart from fake ones. Invented sample data lives in its own
  folder and is copied into place by anyone who wants to run the app.

- **Discontinued items are marked, not inferred.** Some stock is no longer sold
  at retail and has no retail price to work from. Rather than letting a zero
  price quietly stand for that, items carry an explicit flag, so the meaning
  lives in the data instead of in the owner's head. A discontinued item takes a
  fixed per-unit partner amount and the application refuses the other modes,
  because a percentage of a price the item no longer has is not a number worth
  computing.

- **Commercial terms live outside the repository.** The default partner
  percentage is a real business term, so it is read from a configuration file
  under the ignored data folder rather than written into the source. The code
  ships with a placeholder sample instead. This keeps the figure private in a
  public repository, and it means renegotiating the rate is a one-line edit in
  one file rather than a code change.

- **The spreadsheet was cleaned before it was imported.** The original workbook
  carried the partner's terms in three different places, including free text
  inside a condition column and inside notes. Rather than write parsing logic
  against inconsistent prose, the source was given explicit columns first, so the
  one-time import became a straight mapping with nothing inferred. The importer
  builds every record in memory, validates the whole result, and writes both
  files or neither, because a half-finished import gives no way to tell which
  half is real.

- **The application became importable.** The menu loop used to run at the top
  level of the file, so merely importing it started the interactive menu. That is
  why the one-time import script could not reuse a single helper and had to
  duplicate its validation instead. The loop now sits behind an entry-point
  guard, so the file can be read as a library or run as a program. The same
  startup path checks the configuration file once and exits with a sentence if it
  is missing or unusable, rather than raising a stack trace later, the first time
  a product happens to be displayed. Failing immediately with an explanation
  beats failing halfway through a task.

- **Calculations were separated from printing.** The dashboard used to read four
  files, work out nine figures, and print them, all in one function, so there was
  no way to check the arithmetic except by reading terminal output. The figures
  now come from a function that takes the four datasets and returns them as a
  set of named values; the dashboard only fetches and displays. This was done to
  make the totals testable, but the same separation is what a future web
  interface needs, since that interface must call the same logic rather than work
  the totals out a second time for itself. The change was confirmed to alter
  nothing by comparing the dashboard output against real data before and after.

- **Tests fake the commercial terms rather than reading them.** Because the
  default partner percentage lives in an ignored configuration file, a test that
  exercised the default mode for real would depend on a private figure and would
  fail anywhere that file does not exist, which includes every automated run on a
  build server. Tests replace the function that reads the configuration with one
  returning an invented number. That keeps the real term out of a public
  repository and keeps the tests independent of the machine running them.

- **Money is compared with a tolerance, never exactly.** Floating-point
  arithmetic makes some of these figures land a fraction away from the value they
  should be. The same formula returns an exact result for one price and a value
  trailing a string of nines for another, and there is nothing about a case that
  says in advance which it will be. Every test assertion against a currency
  figure therefore allows a small tolerance. Quantities, being whole numbers, are
  still compared exactly.

- **Tests and the dependency audit are separate automated workflows.** Run as a
  single unit, a failing test would end the run before the audit executed, so a
  broken test would also hide whether the dependencies were safe. Kept apart,
  each reports its own result. The audit additionally runs on a weekly schedule,
  because vulnerabilities get discovered in dependencies that have not changed,
  and a check that only runs when code is pushed would never find them.

- **The test runner is pinned, the security scanner is not.** Pinning the test
  runner means every run uses the version the tests were written against, so a
  failure is a real failure rather than a change in the tool. The scanner is the
  opposite case: an older version simply knows about fewer vulnerabilities, so it
  is deliberately left to update itself.