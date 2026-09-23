"""Tests for what the container image is built from.

The project folder holds the real database and the real partner percentage in
data/, so the image must be built from named files and never from the whole
folder. These read the Dockerfile and .dockerignore as text and hold that in
place. They also check the other direction: a module the server imports but
the Dockerfile forgets would build fine and fail only when the container
starts.

compose.yaml is read as data too, for the rules that keep the stack private:
the web port published on 127.0.0.1 only, no port at all for the database, no
password written into the file, and .env kept out of git and out of images.
"""

import ast
import os

import yaml

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


def ignored(filename):
    """The entries of an ignore file, without comments or trailing slashes."""
    with open(os.path.join(PROJECT_DIR, filename)) as ignore:
        return {line.strip().rstrip("/") for line in ignore
                if line.strip() and not line.startswith("#")}


def test_the_build_context_leaves_out_the_data_folder():
    assert "data" in ignored(".dockerignore")


def test_the_env_file_stays_out_of_git_and_out_of_images():
    assert ".env" in ignored(".gitignore")
    assert ".env" in ignored(".dockerignore")


def test_every_module_the_server_imports_is_copied():
    needed = {name + ".py" for name in local_imports("api")}
    sources = {source.rstrip("/") for source in copied_sources()}

    assert needed <= sources, needed - sources
    assert "templates" in sources


# compose.yaml ----------------------------------------------------------------

def compose():
    with open(os.path.join(PROJECT_DIR, "compose.yaml")) as compose_file:
        return yaml.safe_load(compose_file)


def published_ports(service):
    """Every port mapping of a service, in the short "host:container" form.

    The long form, a mapping with published and host_ip keys, is refused
    outright, so a port cannot slip past these checks by being written another
    way.
    """
    ports = service.get("ports", [])
    for port in ports:
        assert isinstance(port, str), f"write ports as strings: {port!r}"
    return ports


def test_every_published_port_is_bound_to_this_machine_only():
    services = compose()["services"]
    ports = [port for service in services.values()
             for port in published_ports(service)]

    assert ports, "the web server publishes no port at all"
    for port in ports:
        assert port.startswith("127.0.0.1:"), port


def test_the_database_publishes_no_port():
    assert "ports" not in compose()["services"]["db"]


def test_the_database_password_is_read_from_the_environment():
    password = compose()["services"]["db"]["environment"]["POSTGRES_PASSWORD"]

    assert password.startswith("${POSTGRES_PASSWORD:?"), password


def test_the_database_lives_on_a_named_volume():
    document = compose()
    mounts = document["services"]["db"]["volumes"]

    named = [mount.split(":")[0] for mount in mounts]
    assert named == ["pgdata"]
    assert "pgdata" in document["volumes"]


def test_the_app_is_never_given_a_default_data_folder():
    # A default would be ./data, which is the real SQLite file.
    for mount in compose()["services"]["app"].get("volumes", []):
        source = mount.split(":/")[0]
        assert not source.startswith(("./", "data", "/")), mount
        if source.startswith("${"):
            assert ":?" in source and ":-" not in source, mount
