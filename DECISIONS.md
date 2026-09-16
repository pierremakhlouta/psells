# Decisions

PSells is an application for tracking a reselling business: the products held,
the sales made, items returned to suppliers, and payouts to a partner. This file
records the notable design choices and why; see the README for what the project
is and DATA_MODEL for how the data is structured. Kept short, the interesting
calls only, not every detail, and no specific business figures.

- **JSON, then SQLite.** Started with JSON storage because it maps directly onto
  Python's lists and dicts, preserves value types, and keeps the early model
  simple while the data structure is being worked out. The move to SQLite
  happened once querying and relationships became the point: items, sales,
  returns and payments needed reliable links, real queries, and a storage layer
  able to refuse bad data rather than one trusting the application to be careful
  every time.

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
  tell real records from fake ones. Invented sample data lives in its own folder
  and is copied into place by anyone who wants to run the app.

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

- **Money is stored as whole cents.** Floating-point arithmetic cannot represent
  most decimal fractions exactly, so the same formula returns an exact result for
  one price and a value trailing a string of nines for another, with nothing
  about a case to say in advance which it will be. Real sale records were already
  carrying that damage. SQLite offers no decimal or money type, and its floating
  type reproduces the problem inside the database, so monetary values are stored
  as integers counting cents. They then sum and compare exactly, which is what
  makes a storage migration verifiable as an exact match rather than a match
  within a tolerance. The cost is that cents and dollars look alike in code, so
  the conversion happens in two helpers and nowhere else. Rounding is applied at
  one point only, where a partner cut is computed from a percentage, and it
  rounds to the nearest cent rather than truncating, because truncation loses a
  cent on exactly the values that carry the floating-point damage.

- **Money is compared with a tolerance only where it is still a fraction.** Test
  assertions against stored money are exact, because stored money is an integer
  number of cents. The tolerance remains only for a figure computed from a
  percentage before it has been rounded to a cent. Quantities, being whole
  numbers, are compared exactly and always were.

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

- **Nothing derived is stored, including how many units have sold.** The rule
  above had one exception: units sold was a stored number that recording a sale
  incremented, and units received was reduced whenever stock went back to the
  partner. Both are now computed from the sales and returns tables, and the
  stored intake figure means what its name says. Recording a sale or a return
  became a single insert with no second value to keep in step, and the original
  intake quantity, which the old behaviour overwrote and lost, is now kept. This
  reverses an earlier decision to document the old meaning of that field rather
  than change it. The reversal was taken because the storage layer was being
  rebuilt anyway and because no return had ever been recorded, so there was
  nothing to reconstruct; the same change made later would mean recovering intake
  figures from partial history.

- **The retail-discontinued flag says what it means.** The field was renamed to make
  clear that it describes the retail market and not this business. It records
  that a product is no longer sold at major retailers, so no retail price exists
  to take a percentage of. It does not mean the product was dropped here: this is
  a reselling business, and such a product is still held, still listed, still
  sold, and still counted in stock. The old name carried a strong conventional
  meaning that contradicted the actual one, which is a different problem from a
  field whose name is merely imprecise, and a column name is read by every future
  query rather than only by the person who wrote it.

- **The partner-share value became two columns.** One column held a percentage
  for one mode and a cash amount for another, with a second column deciding which
  it was. That cannot be range-checked, since a percentage stops at one hundred
  and an amount does not, and once money counts cents the column would hold two
  different units with nothing to tell them apart. Splitting it lets the database
  state the rule directly: each mode allows exactly one shape, and the mode is
  still stored rather than inferred from which column is filled, for the same
  reason the retail flag is explicit.

- **Deleting a product with history is refused.** Deleting a product used to
  leave its sales pointing at nothing. Cascading the delete was rejected because
  it would remove those sales along with the product, silently changing revenue,
  profit and the balance owed to a real person, with no error and no way back
  except a backup; that also contradicts the rule that history stays fixed, which
  is the reason each sale freezes its own figures. Marking products deleted
  rather than removing them was considered and deferred, because hiding a product
  from a list is a different question from what a delete should do to history,
  and it can be added later. Refusing is the option that loses nothing and can
  still be changed; the other two are harder to walk back.

- **The schema carries the rules it can carry, and says which it cannot.** A
  declared column type in SQLite is close to advisory, so enforcement lives in
  constraints rather than in the type names: required fields, bounded
  percentages, valid modes, the shape each mode allows, real calendar dates, and
  foreign keys that refuse to create an orphan. Foreign keys are off by default
  in SQLite and are switched on per connection, which means a schema can look
  protected while enforcing nothing. Two rules cannot be expressed this way at
  all, because they span more than one row and constraints may not contain
  subqueries: that available stock never goes negative, and that an intake figure
  is never edited below what has already sold and returned. Those stay in the
  application, and saying so plainly is better than assuming the database is
  covering them.

- **Browsing matches widely, choosing a product does not.** Search covers a
  product's name and its category, because forgetting the exact name of one of
  several hundred items is normal while the category is usually easy to
  remember. Selecting a product to sell, edit or delete still matches on the
  name alone. The two look like the same operation and are not: one shows a
  list, the other leads straight into an action on whichever id is typed, and a
  category match there would offer an entire category at once. The asymmetry is
  deliberate and has a test holding it in place, so widening it later has to be
  a decision rather than a slip.

- **The sample data is a SQL seed file, not JSON.** The invented records used to
  be copied into place as files the application read directly. They are now
  statements applied to a database built from the real schema, so anyone trying
  the project exercises the same constraints the real data does, and a sample
  record that would break a rule cannot be shipped by accident.
