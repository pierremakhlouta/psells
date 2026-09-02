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
