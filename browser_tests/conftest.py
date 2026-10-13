"""Real browsers for browser_tests/, against a running PSells.

PSELLS_BROWSER_URL names the site: https://psells.localhost:9443 for the
cluster, as the Kubernetes check runs them, or the address run-local.sh
gives. Its certificate must be one the browsers trust. Each test runs twice,
as an iPhone in WebKit and as an Android phone in Chromium, each in a
context of its own so neither sees the other's service worker or cache.

Screenshots go to browser_tests/screenshots/, which git ignores, for a
person to look at.
"""

import os

import pytest
from playwright.sync_api import sync_playwright

from relay import Relay


BASE_URL = os.environ.get("PSELLS_BROWSER_URL", "").rstrip("/")
SCREENSHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")

PHONES = [("webkit", "iPhone 15"), ("chromium", "Pixel 7")]


@pytest.fixture(scope="session")
def base_url():
    if not BASE_URL:
        pytest.exit("Set PSELLS_BROWSER_URL to the site to test, such as "
                    "https://psells.localhost:9443", returncode=2)
    return BASE_URL


@pytest.fixture(scope="session")
def playwright():
    with sync_playwright() as driver:
        yield driver


@pytest.fixture
def relay():
    """The connection, which a test can cut; see relay.py."""
    connection = Relay()
    yield connection
    connection.close()


@pytest.fixture(params=PHONES, ids=["iphone-webkit", "android-chromium"])
def phone(request, playwright, base_url, relay):
    """A fresh browser context dressed as the phone, every request through
    the relay, and its name. Chromium sends even psells.localhost, a loopback
    name, through it only when told to."""
    engine, device = request.param
    arguments = ["--proxy-bypass-list=<-loopback>"] if engine == "chromium" else []
    browser = getattr(playwright, engine).launch(
        proxy={"server": relay.address}, args=arguments)
    context = browser.new_context(**playwright.devices[device])
    yield context, request.node.callspec.id
    context.close()
    browser.close()


def screenshot(page, name):
    os.makedirs(SCREENSHOTS, exist_ok=True)
    page.screenshot(path=os.path.join(SCREENSHOTS, name + ".png"))
