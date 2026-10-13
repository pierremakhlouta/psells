"""PSells as a phone sees it: the files that add it to a home screen, and the
service worker that shows a page when it is offline.

The login page is the one page a phone opens with no session, and it carries
everything the others do, so each test starts there.
"""

import json
import struct
from urllib.parse import urlsplit

from conftest import screenshot


WORKER_CACHE = "psells-shell-v1"


def open_login(context, base_url):
    page = context.new_page()
    response = page.goto(base_url + "/login")
    assert response.status == 200
    return page


def wait_for_worker(page):
    """Until the service worker controls the page, as it does from the
    second load on."""
    ready = page.evaluate("""() => Promise.race([
        navigator.serviceWorker.ready.then(() => true),
        new Promise((resolve) => setTimeout(() => resolve(false), 15000)),
    ])""")
    assert ready, "no service worker became ready within 15 seconds"
    page.reload()
    assert page.evaluate("navigator.serviceWorker.controller !== null")


def fetch(page, path):
    """What the browser itself gets for a path: status, type and the first
    bytes, fetched from inside the page, so through its own trust and cache."""
    return page.evaluate("""async (path) => {
        const response = await fetch(path);
        const bytes = new Uint8Array(await response.arrayBuffer());
        return {status: response.status, type: response.headers.get("content-type"),
                text: new TextDecoder().decode(bytes), head: Array.from(bytes.slice(0, 24))};
    }""", path)


def test_the_manifest_and_every_icon_load(phone, base_url):
    context, name = phone
    page = open_login(context, base_url)

    href = page.get_attribute('link[rel="manifest"]', "href")
    response = fetch(page, href)
    assert response["status"] == 200
    assert response["type"] == "application/manifest+json"
    manifest = json.loads(response["text"])
    assert manifest["name"] == "PSells" and manifest["display"] == "standalone"

    icons = [icon["src"] for icon in manifest["icons"]]
    icons.append(page.get_attribute('link[rel="apple-touch-icon"]', "href"))
    for src in icons:
        icon = fetch(page, src)
        assert icon["status"] == 200, src
        assert icon["type"] == "image/png", src
        head = bytes(icon["head"])
        assert head[:8] == b"\x89PNG\r\n\x1a\n", src
        width, height = struct.unpack(">II", head[16:24])
        assert width == height and width in (180, 192, 512), src
    screenshot(page, name + "-login")


def test_it_opens_offline_after_the_first_visit(phone, base_url, relay):
    context, name = phone
    page = open_login(context, base_url)
    wait_for_worker(page)

    # The connection gone, as a phone's signal goes; see relay.py for why
    # not Playwright's own offline switch.
    relay.cut()
    for path in ["/", "/login", "/analytics"]:
        page.goto(base_url + path)
        assert page.locator("h1").inner_text() == "You're offline", path
    screenshot(page, name + "-offline")

    # Back online, the real page again, from the network.
    relay.restore()
    page.goto(base_url + "/login")
    assert page.locator("h1").inner_text() == "Log in"


def test_a_page_says_so_when_the_connection_goes(phone, base_url):
    context, name = phone
    page = open_login(context, base_url)
    notice = page.locator("#offline-notice")
    assert notice.is_hidden()

    context.set_offline(True)
    notice.wait_for(state="visible")
    screenshot(page, name + "-connection-lost")
    context.set_offline(False)
    notice.wait_for(state="hidden")


def test_the_cache_holds_only_psells_own_app_files(phone, base_url):
    context, _ = phone
    page = open_login(context, base_url)
    wait_for_worker(page)
    # Pages visited, which must not be kept.
    page.goto(base_url + "/login")
    page.goto(base_url + "/")

    caches = page.evaluate("""async () => {
        const result = {};
        for (const name of await caches.keys()) {
            const cache = await caches.open(name);
            result[name] = (await cache.keys()).map((request) => request.url);
        }
        return result;
    }""")

    assert list(caches) == [WORKER_CACHE]
    origin = urlsplit(base_url)
    paths = set()
    for url in caches[WORKER_CACHE]:
        parts = urlsplit(url)
        assert (parts.scheme, parts.netloc) == (origin.scheme, origin.netloc), url
        paths.add(parts.path)
    assert paths == {"/static/offline.html", "/static/icon-192.png",
                     "/static/icon-512.png", "/static/apple-touch-icon.png",
                     "/static/manifest.webmanifest"}
