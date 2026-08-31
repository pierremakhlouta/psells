# PSells Data Model

The structure the application is built on. This document describes shape and
behavior: what each dataset holds, how the datasets relate, and what is stored
versus computed. It deliberately does not include real business figures (partner
percentages, prices, financial totals); those live outside the repository.

## Overview

PSells tracks a small reselling business as four datasets, each stored as a JSON
file containing a list of records:

| Dataset   | File             | One record represents      |
|-----------|------------------|----------------------------|
| Inventory | `inventory.json` | a product held for sale    |
| Sales     | `sales.json`     | a single sale of an item   |
| Returns   | `returns.json`   | items sent back to partner |
| Payments  | `payments.json`  | a payout made to partner   |

A dashboard presents figures rolled up from all four. Every dashboard figure is
computed on demand; none of it is stored.

## Core principles

- **Raw facts are stored; everything else is computed.** Records hold only what
  the user actually decides (what an item is, that a sale happened, that a
  payment was made). Derived figures such as available stock, revenue, profit,
  partner-share totals, and balances are calculated when needed, never saved.
- **Humans use names; the program uses IDs.** Each inventory item carries an
  auto-assigned id. Sales and returns reference an item by that id internally,
  while every user-facing interaction is by item name.

## Inventory (`inventory.json`)

One record per product.

| Field                 | Meaning                                                     |
|-----------------------|-------------------------------------------------------------|
| `id`                  | auto-assigned internal identifier                           |
| `category`            | product category                                            |
| `name`                | product name (how the user refers to it)                    |
| `quantity_received`   | units held from the original intake; reduced when unsold units are returned |
| `quantity_sold`       | how many have sold                                          |
| `retail_price`        | the item's price at major retailers                         |
| `listed_price`        | the price PSells lists it at                                |
| `partner_share_mode`  | how the partner's cut is set: `default`, `custom_percent`, or `custom_amount` |
| `partner_share_value` | the custom setting's number (a percentage or a fixed per-unit amount); not used for `default` |
| `condition`           | item condition                                              |
| `notes`               | free-text notes                                             |

**Computed, not stored:**
- **Quantity available** = quantity_received minus quantity_sold.
- **Partner share per unit** (a dollar amount) is computed from the mode:
  a default portion of the retail price for `default`, the custom percentage of
  the retail price for `custom_percent`, or the fixed amount for `custom_amount`.
  This dollar figure is shown when viewing or searching inventory; it is computed
  on demand, never stored, so it always reflects the current retail price.

Editing an item's partner-share setting changes only future sales.

## Sales (`sales.json`)

One record per sale.

| Field           | Meaning                                                   |
|-----------------|-----------------------------------------------------------|
| `id`            | auto-assigned identifier                                  |
| `date`          | date of sale                                              |
| `item_id`       | the inventory item sold (linked by id)                    |
| `quantity`      | units sold in this sale                                   |
| `sale_price`    | actual price per unit for this sale                       |
| `partner_share` | partner's cut per unit, frozen at the time of sale        |

Recording a sale: find the item by name, increment its `quantity_sold`, copy the
item's current partner-share-per-unit amount onto the sale, then store the sale.

**Computed, not stored:**
- **Revenue** = quantity times sale_price.
- **Profit** = revenue minus (partner_share times quantity).

Because partner_share is frozen onto each sale, later changes to the item never
alter the profit of sales already recorded.

## Returns (`returns.json`)

One record per return. Returns are for unsold inventory sent back to the partner;
a unit that has already sold cannot be returned.

| Field      | Meaning                                   |
|------------|-------------------------------------------|
| `id`       | auto-assigned identifier                  |
| `date`     | date of return                            |
| `item_id`  | the inventory item returned (linked by id)|
| `quantity` | units returned                            |
| `notes`    | free-text notes                           |

Recording a return reduces the linked item's `quantity_received` by the returned
quantity. Since returns are unsold units, the computed available quantity
decreases accordingly.

## Payments (`payments.json`)

One record per payout made to the partner.

| Field     | Meaning                    |
|-----------|----------------------------|
| `id`      | auto-assigned identifier   |
| `date`    | date of payment            |
| `amount`  | amount paid                |
| `notes`   | free-text notes            |

## Dashboard (fully computed)

Rolled up from the four datasets; nothing here is stored:

- total received, total sold, total available, total returned
- total revenue, total profit
- total partner share earned (all time)
- total paid to partner
- partner balance owing = total partner share earned minus total paid to partner