"""Tests for charts.py, the analytics page's chart geometry, and for
warehouse.py, which reads the warehouse's views for it.

The geometry is checked as geometry: bars in proportion, the zero line where
zero is, nothing outside the chart, round ticks that cover every value. The
readers are checked against the views themselves, read through a warehouse
the ETL builds in the test's own transaction.
"""

import os
from datetime import datetime, timezone

import pytest

import charts
import warehouse
from analytics import etl
from helpers import add_product, add_sale


# The geometry -------------------------------------------------------------------

def test_ticks_are_round_include_zero_and_cover_every_value():
    for low, high in ((0, 78600), (-1500, 42000), (0, 3), (0, 1), (250, 999)):
        ticks = charts.value_ticks(low, high)
        assert 0 in ticks
        assert ticks[0] <= min(low, 0) and ticks[-1] >= high
        steps = {b - a for a, b in zip(ticks, ticks[1:])}
        assert len(steps) == 1
        (step,) = steps
        assert step >= 1 and int(str(step)[0]) in (1, 2, 5) and set(str(step)[1:]) <= {"0"}


def test_an_all_zero_series_still_has_a_scale():
    assert charts.value_ticks(0, 0) == [0, 1]
    chart = charts.bar_chart(["July"], [[0], [0]])
    assert all(bar["height"] == 0 for bar in chart["bars"])


def test_bars_are_in_proportion_and_stand_on_the_zero_line():
    chart = charts.bar_chart(["May", "June"], [[15000, 30000], [10000, 0]])
    bars = {(b["label"], b["series"]): b for b in chart["bars"]}

    assert len(chart["bars"]) == 4
    # Twice the value, twice the height; every bar's foot on the zero line.
    assert bars["June", 0]["height"] == pytest.approx(2 * bars["May", 0]["height"], abs=0.2)
    for bar in chart["bars"]:
        assert bar["y"] + bar["height"] == pytest.approx(chart["zero_y"], abs=0.1)
    assert bars["June", 1]["height"] == 0


def test_a_negative_bar_hangs_below_the_zero_line():
    chart = charts.bar_chart(["May"], [[15000], [-1500]])
    gain = [b for b in chart["bars"] if b["value"] > 0][0]
    loss = [b for b in chart["bars"] if b["value"] < 0][0]

    # Zero is above the chart's bottom here, and both bars meet it.
    assert chart["zero_y"] < chart["height"] - charts.BOTTOM
    assert gain["y"] + gain["height"] == pytest.approx(chart["zero_y"], abs=0.1)
    assert loss["y"] == chart["zero_y"]
    # Ten times the value, ten times the height, on either side of zero.
    assert gain["height"] == pytest.approx(10 * loss["height"], abs=0.5)


def test_every_bar_label_and_tick_lies_inside_the_chart():
    chart = charts.bar_chart([f"M{n}" for n in range(12)],
                             [[n * 1000 for n in range(12)], [500] * 12])
    for bar in chart["bars"]:
        assert chart["left"] <= bar["x"] and bar["x"] + bar["width"] <= chart["right"] + 0.1
        assert 0 <= bar["y"] and bar["y"] + bar["height"] <= chart["height"]
    for tick in chart["ticks"]:
        assert 0 <= tick["y"] <= chart["height"]
    # Bars of one group never overlap the next group's.
    xs = sorted((b["x"], b["x"] + b["width"]) for b in chart["bars"])
    assert all(a_end <= b_start + 0.1 for (_, a_end), (b_start, _) in zip(xs, xs[1:]))


def test_the_line_passes_through_every_value_left_to_right():
    chart = charts.line_chart(["May", "June", "July"], [15000, 57000, 59800])
    xs = [dot["x"] for dot in chart["dots"]]
    ys = [dot["y"] for dot in chart["dots"]]

    assert xs == sorted(xs)
    # A larger value is higher, a smaller y.
    assert ys[0] > ys[1] > ys[2]
    assert chart["points"] == " ".join(f"{x},{y}" for x, y in zip(xs, ys))
    assert [dot["value"] for dot in chart["dots"]] == [15000, 57000, 59800]


def test_horizontal_bars_scale_to_the_largest_and_draw_nothing_for_none():
    chart = charts.horizontal_bars(["Watches", "Hats", "Bags"], [57000, 7600, 0])
    widths = [bar["width"] for bar in chart["bars"]]

    assert widths[0] == chart["width"] - 160 - charts.RIGHT
    assert widths[1] == pytest.approx(widths[0] * 7600 / 57000, abs=0.1)
    assert widths[2] == 0
    assert chart["height"] == 3 * 26


def test_no_labels_make_an_empty_chart():
    assert charts.bar_chart([], [[]])["bars"] == []
    assert charts.line_chart([], [])["points"] == ""
    assert charts.horizontal_bars([], [])["bars"] == []


# Reading the warehouse ----------------------------------------------------------

@pytest.fixture
def built(db):
    add_product(db, 1, 4)
    add_product(db, 2, 4, category="Bags")
    add_product(db, 3, 10, category="Bags")
    add_product(db, 4, 8, category="Hats")
    add_sale(db, 1, 1, 3, sale_price_cents=9000, partner_share_cents=3600,
             date="2026-07-10")
    add_sale(db, 2, 2, 1, sale_price_cents=30000, partner_share_cents=5000,
             date="2026-08-20")
    add_sale(db, 3, 4, 2, sale_price_cents=4000, partner_share_cents=1000,
             date="2026-08-21")
    data = etl.extract(db)
    etl.load(db, etl.transform(data), data["totals"],
             datetime(2026, 10, 8, tzinfo=timezone.utc))
    return db


def test_the_readers_return_the_views_rows_in_their_order(built):
    assert warehouse.kpis(built) == built.execute("SELECT * FROM kpis").fetchone()
    months = warehouse.sales_by_month(built)
    assert [m["month"].month for m in months] == [7, 8]
    categories = warehouse.category_performance(built)
    # Bags 30000, Shoes 27000, Hats 8000.
    assert [c["category"] for c in categories] == ["Bags", "Shoes", "Hats"]


def test_top_by_profit_follows_the_views_rank_and_stops_at_the_limit(built):
    top = warehouse.top_by_profit(built, limit=2)

    # Profit: product 2 25000, product 1 16200, product 4 6000. By units the
    # order would be 1 (3 units) first, so the two orders differ here.
    assert [p["product_id"] for p in top] == [2, 1]
    assert [p["rank_by_profit"] for p in top] == [1, 2]


def test_lowest_sell_through_puts_the_most_waiting_stock_first_among_equals(built):
    lowest = warehouse.lowest_sell_through(built, limit=3)

    # Product 3 sold none of 10; products 2 (1 of 4) and 4 (2 of 8) tie at a
    # quarter, and 4 has more stock waiting.
    assert [p["product_id"] for p in lowest] == [3, 4, 2]
    assert lowest[0]["sell_through"] == 0


def test_no_warehouse_set_up_is_a_sentence_not_an_error(monkeypatch):
    monkeypatch.delenv("PSELLS_WAREHOUSE_URL", raising=False)

    with pytest.raises(warehouse.WarehouseUnavailable) as raised:
        warehouse.connect()
    assert "No analytics warehouse is set up here" in str(raised.value)


def test_a_warehouse_that_does_not_answer_says_so_without_its_address(monkeypatch):
    monkeypatch.setenv("PSELLS_WAREHOUSE_URL",
                       "postgresql://psells_reader:invented@127.0.0.1:1/nowhere")

    with pytest.raises(warehouse.WarehouseUnavailable) as raised:
        warehouse.connect()
    message = str(raised.value)
    assert message == "The analytics warehouse did not answer. Try again in a moment."
    assert "127.0.0.1" not in message and "invented" not in message


def test_the_readers_only_read_and_work_nothing_out():
    with open(os.path.join(os.path.dirname(charts.__file__), "warehouse.py")) as file:
        source = file.read().upper()

    # No write, and no figure of its own: sums, counts, rounding and ratios
    # are the views'.
    for word in ("INSERT ", "UPDATE ", "DELETE ", "CREATE ", "DROP ", "TRUNCATE ",
                 "SUM(", "COUNT(", "AVG(", "ROUND(", "NULLIF("):
        assert word not in source, word
    assert source.count("SELECT * FROM ") == 5
