"""Tests for what the container image is built from.

The project folder holds the real database and the real partner percentage in
data/, so the image must be built from named files and never from the whole
folder. These read the Dockerfile and .dockerignore as text and hold that in
place. They also check the other direction: a module the server imports but
the Dockerfile forgets would build fine and fail only when the container
starts.
"""

import ast
import os

import psells


PROJECT_DIR = psells.PROJECT_DIR


def instructions():
    """The Dockerfile as (INSTRUCTION, [arguments]) pairs.

    Comments are dropped and a line ending in a backslash is joined to the next,
    which is how Docker itself reads the file.
    """
    with open(os.path.join(PROJECT_DIR, "Dockerfile")) as dockerfile:
        text = dockerfile.read()

    lines = [line for line in text.splitlines()
             if not line.lstrip().startswith("#")]
    joined = "\n".join(lines).replace("\\\n", " ")

    result = []
    for line in joined.splitlines():
        words = line.split()
        if words:
            result.append((words[0].upper(), words[1:]))
    return result


def copied_sources():
    """Every source path named by a COPY, without the destination."""
    sources = []
    for instruction, arguments in instructions():
        if instruction == "COPY":
            paths = [a for a in arguments if not a.startswith("--")]
            sources.extend(paths[:-1])
    return sources


def local_imports(module_name, seen=None):
    """The project's own modules that module_name needs, itself included."""
    seen = set() if seen is None else seen
    path = os.path.join(PROJECT_DIR, module_name + ".py")
    if module_name in seen or not os.path.exists(path):
        return seen
    seen.add(module_name)

    with open(path) as source:
        tree = ast.parse(source.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        else:
            continue
        for name in names:
            local_imports(name.split(".")[0], seen)
    return seen


def test_the_image_never_copies_the_whole_folder_or_the_data():
    for source in copied_sources():
        # normpath turns ./data/x into data/x, which a plain strip would miss.
        name = os.path.normpath(source).lstrip("/")
        assert name not in ("", ".", "*"), source
        assert "*" not in name, source
        assert name.split("/")[0] != "data", source


def test_the_image_is_built_with_copy_not_add():
    # ADD also downloads URLs and unpacks archives, which a build that names
    # its files one by one has no use for.
    assert "ADD" not in [instruction for instruction, _ in instructions()]


def test_the_build_context_leaves_out_the_data_folder():
    with open(os.path.join(PROJECT_DIR, ".dockerignore")) as ignore:
        entries = {line.strip().rstrip("/") for line in ignore
                   if line.strip() and not line.startswith("#")}

    assert "data" in entries


def test_every_module_the_server_imports_is_copied():
    needed = {name + ".py" for name in local_imports("api")}
    sources = {source.rstrip("/") for source in copied_sources()}

    assert needed <= sources, needed - sources
    assert "templates" in sources
