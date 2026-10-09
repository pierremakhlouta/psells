"""Tests for the documents that describe PSells as a whole: ARCHITECTURE.md
now, and the runbook beside it.

They hold the documents to the repository, so a file renamed or removed
cannot leave a document pointing at nothing: every file a document names
must exist, and every diagram must be one Mermaid draws.
"""

import os
import re
import subprocess

import psells


ROOT = psells.PROJECT_DIR
ARCHITECTURE = os.path.join(ROOT, "ARCHITECTURE.md")
DIAGRAM_KINDS = ("flowchart", "sequenceDiagram")


def read(path):
    with open(path) as file:
        return file.read()


def tracked_files():
    """Every path git holds, and every folder above one."""
    listed = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                            text=True, check=True).stdout.split()
    paths = set(listed)
    for path in listed:
        parts = path.split("/")
        for depth in range(1, len(parts)):
            paths.add("/".join(parts[:depth]) + "/")
    return paths


def named_files(text):
    """The repository files a document names in backticks: a path with a
    slash, or a file name with an extension. Not what never reaches the
    repository: data/, .env, or anything under ~."""
    names = set()
    for token in re.findall(r"`([^`\s]+)`", text):
        if token.startswith(("~", "data/", ".env", "/", "http")):
            continue
        if "/" in token or re.fullmatch(r"[\w.-]+\.(py|sh|sql|yaml|yml|md|conf|txt|json|plist|service|timer)", token) \
                or token in ("Dockerfile",):
            names.add(token)
    return names


def test_every_file_the_architecture_names_is_in_the_repository():
    tracked = tracked_files()
    basenames = {path.rstrip("/").split("/")[-1] for path in tracked}
    names = named_files(read(ARCHITECTURE))

    assert len(names) >= 20
    missing = sorted(name for name in names
                     if name not in tracked and name.rstrip("/") + "/" not in tracked
                     and name not in basenames)
    assert missing == []


def test_every_diagram_is_one_mermaid_draws():
    blocks = re.findall(r"```mermaid\n(.*?)```", read(ARCHITECTURE), re.S)

    assert len(blocks) >= 8
    for block in blocks:
        assert block.split()[0] in DIAGRAM_KINDS, block.split("\n")[0]


def test_readme_leads_to_the_architecture():
    assert "[ARCHITECTURE.md](ARCHITECTURE.md)" in read(os.path.join(ROOT, "README.md"))
