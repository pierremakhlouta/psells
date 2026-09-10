import pytest

import psells


@pytest.fixture
def inventory():
    return [
        {"id": 1, "name": "Nike Air Max 90"},
        {"id": 2, "name": "Nike Air Force 1"},
        {"id": 3, "name": "Adidas Samba"}
    ]


def test_next_id_on_empty_list():
    assert psells.next_id([]) == 1


def test_next_id_on_sequential_records():
    records = [{"id": 1}, {"id": 2}, {"id": 3}]

    assert psells.next_id(records) == 4


def test_next_id_ignores_gaps_and_order():
    records = [{"id": 1}, {"id": 5}, {"id": 3}]

    assert psells.next_id(records) == 6


def test_find_items_by_name_exact_name(inventory):
    matches = psells.find_items_by_name(inventory, "Adidas Samba")

    assert [item["id"] for item in matches] == [3]


def test_find_items_by_name_is_case_insensitive(inventory):
    lower = psells.find_items_by_name(inventory, "adidas samba")
    upper = psells.find_items_by_name(inventory, "ADIDAS SAMBA")

    assert [item["id"] for item in lower] == [3]
    assert [item["id"] for item in upper] == [3]


def test_find_items_by_name_matches_a_substring(inventory):
    matches = psells.find_items_by_name(inventory, "force")

    assert [item["id"] for item in matches] == [2]


def test_find_items_by_name_returns_every_match(inventory):
    matches = psells.find_items_by_name(inventory, "nike")

    assert [item["id"] for item in matches] == [1, 2]


def test_find_items_by_name_returns_empty_list_when_nothing_matches(inventory):
    assert psells.find_items_by_name(inventory, "Puma") == []

def test_partner_share_default_mode(monkeypatch):
    monkeypatch.setattr(psells, "default_partner_share_percent", lambda: 40.0)

    item = {
        "partner_share_mode": "default",
        "retail_price": 500.0
    }

    assert psells.partner_share_for(item) == pytest.approx(200.0)


def test_partner_share_default_mode_on_an_awkward_price(monkeypatch):
    monkeypatch.setattr(psells, "default_partner_share_percent", lambda: 40.0)

    item = {
        "partner_share_mode": "default",
        "retail_price": 19.99
    }

    assert psells.partner_share_for(item) == pytest.approx(7.996)


def test_partner_share_custom_percent_mode():
    item = {
        "partner_share_mode": "custom_percent",
        "retail_price": 700.0,
        "partner_share_value": 40.0
    }

    assert psells.partner_share_for(item) == pytest.approx(280.0)


def test_partner_share_custom_amount_mode_ignores_retail_price():
    item = {
        "partner_share_mode": "custom_amount",
        "retail_price": 700.0,
        "partner_share_value": 30.0
    }

    assert psells.partner_share_for(item) == pytest.approx(30.0)


def test_partner_share_for_a_discontinued_item():
    item = {
        "partner_share_mode": "custom_amount",
        "retail_price": 0.0,
        "partner_share_value": 25.0
    }

    assert psells.partner_share_for(item) == pytest.approx(25.0)


def test_partner_share_unknown_mode_raises():
    item = {
        "partner_share_mode": "percentage",
        "retail_price": 100.0
    }

    with pytest.raises(ValueError, match="Invalid partner share mode"):
        psells.partner_share_for(item)