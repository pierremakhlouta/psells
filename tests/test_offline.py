"""Tests for PSells' service worker and its offline page, read as files.

static/sw.js keeps a page to show without a connection, and the icons, and
never a page of PSells, since every page is live figures. These hold the
pieces to each other: the offline page to base.html's style, which the
security policy allows by its hash; the worker's files to the ones nginx
serves; the registration to the whole site. tests/browser/ runs the worker
in real browsers.
"""

import os
import re

import psells


STATIC = os.path.join(psells.PROJECT_DIR, "static")


def read(*parts):
    with open(os.path.join(*parts)) as file:
        return file.read()


def style_block(text):
    (block,) = re.findall(r"<style>(.*?)</style>", text, re.S)
    return block


def worker_shell():
    text = read(STATIC, "sw.js")
    (listed,) = re.findall(r"const SHELL = \[(.*?)\];", text, re.S)
    return re.findall(r'"([^"]+)"', listed), text


def test_the_offline_page_has_base_htmls_style_exactly():
    # Copied, so the one hash in the policy covers both. Change base.html's
    # block and copy it here, or the offline page loses its styles.
    assert style_block(read(STATIC, "offline.html")) == style_block(
        read(psells.PROJECT_DIR, "templates", "base.html"))


def test_the_offline_page_holds_no_figure_and_runs_no_script():
    page = read(STATIC, "offline.html")

    assert "<script" not in page
    assert "$" not in page.split("<style>")[0] + page.split("</style>")[1]
    assert "<h1>You're offline</h1>" in page


def test_the_worker_keeps_only_files_nginx_serves_and_never_a_page():
    shell, text = worker_shell()
    served = re.search(r"\^/static/\((.+)\)\$",
                       read(psells.PROJECT_DIR, "nginx", "snippets", "static.conf"))
    names = {name.replace("\\.", ".") for name in served.group(1).split("|")}

    assert "/static/offline.html" in shell
    for path in shell:
        assert path.startswith("/static/") and path.removeprefix("/static/") in names, path
    # A page goes to the network and is never stored: the one put, by any
    # name, is for the shell's files, after the navigation branch has
    # returned. A text check only; tests/browser/ looks in the real cache.
    assert len(re.findall(r"\.put\(", text)) == 1
    navigate = text[text.index('request.mode === "navigate"'):text.index("SHELL.includes(")]
    assert ".put(" not in navigate and "fetch(request)" in navigate
    # Only GETs to PSells itself are looked at at all.
    assert 'request.method !== "GET" || url.origin !== self.location.origin' in text


def test_a_new_worker_replaces_the_old_and_deletes_its_cache():
    _, text = worker_shell()

    assert re.search(r'const VERSION = "\d+";', text)
    assert 'const CACHE = "psells-shell-v" + VERSION;' in text
    assert "names.filter((name) => name !== CACHE).map((name) => caches.delete(name))" in text


def test_every_page_registers_the_worker_for_the_whole_site():
    text = read(STATIC, "register.js")

    assert 'navigator.serviceWorker.register("/sw.js", { scope: "/" })' in text
    assert '"serviceWorker" in navigator' in text
