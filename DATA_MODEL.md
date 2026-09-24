# PSells Data Model

The structure the application is built on. This document describes shape and
behavior: what each table holds, how they relate, and what is stored versus
computed. It deliberately does not include real business figures (partner
percentages, prices, financial totals); those live outside the repository.

## Overview

PSells tracks a small reselling business as four related tables:

| Table     | One row represents         |
|-----------|----------------------------|
| products  | a product held for sale    |
| sales     | a single sale of a product |
| returns   | units sent back to partner |
| payments  | a payout made to partner   |

A dashboard presents figures rolled up from all four. Every dashboard figure is
computed on demand; none of it is stored.

## Core principles

- **Raw facts are stored; everything else is computed.** Rows hold only what the
  user actually decides: what a product is, that a sale happened, that a payment
  was made. Quantity sold, quantity returned, available stock, the partner cut in
  dollars, revenue, profit, partner-share totals and balances are all calculated
  when needed and never saved. There are no exceptions to this rule.
- **Humans use names; the program uses IDs.** Each product carries an
  auto-assigned id. Sales and returns reference a product by that id internally,
  while every user-facing interaction is by product name.
- **Facts recorded at the time are facts, not derived values.** A sale stores the
  partner cut that applied at the moment it happened. That figure is derivable
  when the sale is made and not afterwards, so it is recorded rather than
  recomputed.

## Money

**Monetary values are represented as integer cents everywhere inside the
application.** A column named `..._cents` holds 2670 to mean $26.70. Values are
converted to dollars only for display, and back to cents only when a figure is
entered; those two conversions live in dedicated helpers and nowhere else.

A binary floating point number cannot represent most decimal fractions exactly,
so sums and comparisons of money stored that way are unreliable. Integer cents
are exact, sum exactly, and compare exactly. This was decided under SQLite,
which has no decimal type, and kept under PostgreSQL, which does: its `numeric`
would be exact too, but Python reads it back as `Decimal`, and every figure
would stop being the plain integer the rest of the application works in.

Money columns are `integer`, not `bigint`, for the same reason. In PostgreSQL a
`SUM` over `integer` returns `bigint`, which Python reads as an integer; a `SUM`
over `bigint` returns `numeric`, which it reads as `Decimal`. A single value
tops out at $21,474,836.47, and one beyond that is refused, not wrapped.

A percentage is not a monetary value, so this rule does not apply to it. See
Partner share below.

**Rounding.** Every figure entered by the user is already a whole number of cents,
so nothing is rounded on the way in. The only value that can land on a fraction of
a cent is a partner cut computed as a percentage of a price. That result is
rounded to the nearest cent, half away from zero, at the moment it is computed,
and exactly once.

## Quantities

Four quantities describe a product's stock. Only the first is stored.

| Quantity   | Source                                            |
|------------|---------------------------------------------------|
| received   | stored on the product: the original intake        |
| sold       | computed: sum of that product's sale quantities   |
| returned   | computed: sum of that product's return quantities |
| available  | computed: received minus sold minus returned      |

Application code reads products through a view called `products_view`, which
carries those three computed quantities alongside the stored columns. A row
arrives with `quantity_available` already on it, so nothing in the application
works stock out for itself. The view aggregates sales and returns separately
before joining them to products, because joining both at once multiplies them
together and both totals come out wrong.

`quantity_received` is the number of units originally taken in. It is never
changed by recording a sale or a return. It can be changed by editing the
product, because a mistyped intake figure needs correcting, and that edit is
refused if it would set the figure below units already sold plus units already
returned.

A sale does not update anything on the product. Recording a sale is a single
insert into `sales`. Recording a return is a single insert into `returns`. There
is no second copy of any quantity that can fall out of step.

Returns are unsold units sent back to the partner. A unit that has already sold
cannot be returned. Both selling and returning are refused when available stock
is zero or less.

## products

One row per product.

| Column                      | Type    | Notes                                    |
|-----------------------------|---------|------------------------------------------|
| `id`                        | integer | primary key, `GENERATED ALWAYS AS IDENTITY` |
| `category`                  | text    | required, non-blank                      |
| `name`                      | text    | required, non-blank, not unique          |
| `quantity_received`         | integer | original intake; never altered by a transaction |
| `retail_price_cents`        | integer | the price at major retailers; 0 only when retail-discontinued |
| `listed_price_cents`        | integer | the price PSells lists it at             |
| `retail_discontinued`       | integer | 0 or 1                                   |
| `partner_share_mode`        | text    | `default`, `custom_percent`, or `custom_amount` |
| `partner_share_percent`     | double precision | set only when the mode is `custom_percent` |
| `partner_share_amount_cents`| integer | set only when the mode is `custom_amount`  |
| `condition`                 | text    | required                                 |
| `notes`                     | text    | may be empty                             |

**ID allocation.** Every table's id comes from a sequence, which never hands out
the same value twice, so an id freed by deleting a product is never given to
the next one. Under SQLite it was: ids were the highest existing id plus one, so
deleting the newest product freed its id, and a browser tab left open on that
product's form would have posted to whichever product was added next. That case
is gone.

`GENERATED ALWAYS` means an insert cannot choose its own id; the database
refuses one unless the insert says `OVERRIDING SYSTEM VALUE`. Only loading
existing records does that (the move from SQLite, the sample data, the test
helpers), and each then moves the sequence past the highest id. Ids can have
gaps: an insert that is refused or rolled back still uses up its number, and
nothing depends on ids being consecutive.

`retail_discontinued` stays an integer holding 0 or 1, as it was under SQLite,
rather than becoming PostgreSQL's `boolean`. The API already presents it as a
boolean; changing the column is its own change, with its own tests, if it is
ever wanted.

### retail_discontinued

**This describes the retail market, not PSells inventory.** A product marked
`retail_discontinued` is no longer sold at major retailers, so there is no longer
a retail price to take a percentage of. That is the entire meaning.

PSells is a reselling business, so such a product is still ordinary stock: still
held, still listed, still sellable, still counted in available stock, still
included in the dashboard. The flag has no effect on availability, listing,
sales eligibility, or any total.

Because there is no retail price to work from, `retail_price_cents` stores 0 and
the product must use `custom_amount`, a fixed per-unit figure agreed with the
partner. The application enforces this in both directions: marking a product
retail-discontinued forces that mode, and clearing the flag requires entering a
real retail price before the other modes become available again.

A zero retail price means exactly this situation and nothing else. A product that
is not retail-discontinued always has a positive retail price.

The field is an explicit flag rather than an inference from a zero price, so that
zero is not made to carry two meanings.

### Partner share

The partner's cut per unit is computed from the mode:

| Mode             | Per-unit cut                                            |
|------------------|---------------------------------------------------------|
| `default`        | the configured default percentage of `retail_price_cents` |
| `custom_percent` | `partner_share_percent` of `retail_price_cents`         |
| `custom_amount`  | `partner_share_amount_cents`                            |

The percentage base is always the retail price, never the listed price and never
the price a sale actually went through at.

The default percentage is read from a configuration file outside the repository,
because it is a real commercial term.

The percentage and the fixed amount are separate columns rather than one column
whose unit depends on the mode. A single column would hold a percentage in one
row and an amount in the next with nothing to distinguish them, which cannot be
range-checked, cannot be named honestly once money is in cents, and cannot be
read without consulting another column first.

`partner_share_percent` is a floating point number rather than an integer. A
percentage is not money: it is never summed or compared for equality, it is an
input to one multiplication whose result is immediately rounded to the nearest
cent, so floating point representation cannot accumulate. Storing it as integer
basis points would make the model entirely integer but would make the stored
values harder to read. This is a decision rather than an oversight.

It is `double precision`, the same eight-byte number SQLite's `REAL` was, so a
stored percentage reads back exactly as it was written. PostgreSQL's own `real`
is four bytes and keeps about seven significant digits.

`partner_share_mode` remains stored even though it could be inferred from which
column is populated, for the same reason `retail_discontinued` is a flag: the
meaning belongs in the data, not in an inference.

This dollar figure is shown when viewing or searching products. It is computed on
demand, never stored, so it always reflects the current retail price. Editing a
product's partner-share setting changes only future sales.

## sales

One row per sale.

| Column                | Type    | Notes                                     |
|-----------------------|---------|-------------------------------------------|
| `id`                  | integer | primary key, from a sequence              |
| `date`                | date    | the day of the sale                       |
| `item_id`             | integer | references `products(id)`                 |
| `quantity`            | integer | units sold in this sale                   |
| `sale_price_cents`    | integer | actual price per unit for this sale       |
| `partner_share_cents` | integer | partner's cut per unit, frozen at sale time |

Recording a sale: find the product by name, compute its current partner cut per
unit, and insert one row. Nothing on the product changes.

**Computed, not stored:** revenue is quantity times sale price; profit is revenue
minus partner share times quantity.

Because the partner cut is frozen onto each sale, later changes to a product
never alter the profit of sales already recorded.

## returns

One row per return. Returns are unsold stock sent back to the partner.

| Column     | Type    | Notes                     |
|------------|---------|---------------------------|
| `id`       | integer | primary key, from a sequence |
| `date`     | date    | the day of the return     |
| `item_id`  | integer | references `products(id)` |
| `quantity` | integer | units returned            |
| `notes`    | text    | may be empty              |

Recording a return inserts one row and changes nothing on the product. The
product's computed available quantity falls accordingly.

## payments

One row per payout made to the partner.

| Column         | Type    | Notes                     |
|----------------|---------|---------------------------|
| `id`           | integer | primary key, from a sequence |
| `date`         | date    | the day it was paid       |
| `amount_cents` | integer | amount paid               |
| `notes`        | text    | may be empty              |

Payments do not reference a product. They are payouts against the running balance
owed to the partner as a whole, not against any particular sale.

## Relationships and deletion

`sales.item_id` and `returns.item_id` are foreign keys referencing
`products(id)`. Payments reference nothing.

**Foreign keys are enforced,** by PostgreSQL, always, on every connection. Under
SQLite they had to be switched on per connection, and a schema could look
protected while enforcing nothing.

**Deleting a product that has sales or returns is refused.** The foreign keys are
`ON DELETE RESTRICT`, and the application reports which records prevent the
deletion rather than failing silently. A product with no transactions deletes
normally.

This preserves the rule that history stays fixed. Cascading the delete was
rejected: it would remove the sales along with the product, silently changing
revenue, profit and the balance owed to the partner, with no way back except a
backup. Marking products deleted instead of removing them was considered and
deferred; it solves hiding a product from the list, which is a separate question
from what a delete should do to history, and it can be added later without
disturbing anything decided here.

## Constraints and invariants

These are the rules the database itself enforces. PostgreSQL enforces every
declared type, so an integer column refuses text, and a date column refuses a
day that does not exist. The constraints below carry the rules a type cannot
express. They were written first for SQLite, where a declared type was close to
advisory, and carried over unchanged in meaning.

### products

| Rule | Reason |
|---|---|
| `id` is the primary key | identity |
| `category`, `name`, `condition` are NOT NULL and non-blank | required fields |
| `notes` is NOT NULL and may be an empty string | optional text, never missing |
| `quantity_received >= 1` | a product with no units is not a product |
| `retail_price_cents >= 0` | prices are never negative |
| `listed_price_cents >= 0` | zero is permitted; the prompt allows it |
| `retail_discontinued` is 0 or 1 | boolean |
| `partner_share_mode` is one of the three modes | no fourth mode can exist |
| `partner_share_percent` is NULL or between 0 and 100 | a percentage is bounded |
| `partner_share_amount_cents` is NULL or `>= 0` | zero is a real arrangement |

**The partner-share matrix.** Exactly one shape is valid per mode:

| Mode | `partner_share_percent` | `partner_share_amount_cents` |
|---|---|---|
| `default` | NULL | NULL |
| `custom_percent` | 0 to 100 | NULL |
| `custom_amount` | NULL | 0 or more |

**The retail-discontinued relationship.** These two hold together:

| `retail_discontinued` | `retail_price_cents` | `partner_share_mode` |
|---|---|---|
| 0 | greater than 0 | any of the three |
| 1 | exactly 0 | `custom_amount` |

Note the consequence for input: because a zero retail price is reserved for
retail-discontinued products, `add` and `edit` must require a positive retail
price whenever the flag is off. The prompt previously allowed zero.

### sales and returns

| Rule | Reason |
|---|---|
| `item_id` references an existing product | no orphans |
| `quantity >= 1` | a transaction of nothing is not a transaction |
| `sale_price_cents >= 0`, `partner_share_cents >= 0` | never negative |
| `date` is a real calendar date | the `date` type rejects `2026-13-45` and `2026-02-30` |

### payments

| Rule | Reason |
|---|---|
| `amount_cents >= 0` | never negative |
| `date` is a real calendar date | as above |

### What the database cannot enforce

Two invariants span more than one row, and a `CHECK` constraint can only look at
the row it is checking, in PostgreSQL as in SQLite, so neither can be expressed
as one:

- available stock never goes negative
- `quantity_received` is never edited below units already sold plus returned

Both remain enforced in application code, exactly as they are today. This is
worth stating plainly so the schema is not mistaken for more protection than it
provides. They could become triggers later if that protection is wanted at the
storage layer.

## Dashboard

Rolled up from the four tables; nothing here is stored:

- total received, total sold, total available, total returned
- total revenue, total profit
- total partner share earned (all time)
- total paid to partner
- partner balance owing = total partner share earned minus total paid to partner

Total available is total received minus total sold minus total returned. Returns
no longer reduce a stored intake figure, so they are subtracted here explicitly.
