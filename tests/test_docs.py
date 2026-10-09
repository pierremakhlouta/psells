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
        token = token.removeprefix("./")
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


# The runbook -------------------------------------------------------------------

RUNBOOK = os.path.join(ROOT, "RUNBOOK.md")


def code_blocks(text):
    return re.findall(r"```\n(.*?)```", text, re.S)


def test_every_file_the_runbook_names_is_in_the_repository():
    tracked = tracked_files()
    basenames = {path.rstrip("/").split("/")[-1] for path in tracked}
    names = named_files(read(RUNBOOK))

    assert len(names) >= 10
    assert sorted(name for name in names
                  if name not in tracked and name.rstrip("/") + "/" not in tracked
                  and name not in basenames) == []


def test_the_restore_never_empties_the_database_without_a_dump_to_put_in():
    (restore,) = [block for block in code_blocks(read(RUNBOOK))
                  if "DROP DATABASE" in block]

    # One chain, which stops at the first failure and starts with the dump.
    assert restore.count("\n") == 1
    assert restore.index('[ -s "$dump" ] &&') < restore.index("DROP DATABASE")
    assert " ; " not in restore and "||" not in restore
    # Into an empty database, without the dump's grants, all or nothing.
    assert ("pg_restore -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" --no-owner "
            "--no-privileges --single-transaction --exit-on-error") in restore
    assert restore.index("pg_restore") < restore.index("analytics/create-etl-role.sh")


def test_no_command_in_the_runbook_removes_the_real_volume():
    for block in code_blocks(read(RUNBOOK)):
        for line in block.splitlines():
            if "down -v" in line or "volume rm" in line or "prune" in line:
                assert " -p " in line and "psells-sample" in line, line


def test_readme_leads_to_the_runbook_and_no_longer_gives_the_old_restore():
    readme = read(os.path.join(ROOT, "README.md"))

    assert "[RUNBOOK.md](RUNBOOK.md)" in readme
    assert "--no-owner --exit-on-error' \\\n" not in readme
