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
import glob
import os
import re

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


def test_every_copied_file_is_made_readable_before_the_server_user_takes_over():
    # COPY keeps the builder's file permissions and makes root the owner, so a
    # file saved readable only by its owner cannot be read by psells. The chmod
    # must come after the last COPY, which it has to cover, and before USER,
    # because psells is not allowed to change files root owns.
    names = [instruction for instruction, _ in instructions()]
    steps = [" ".join([instruction] + arguments)
             for instruction, arguments in instructions()]

    chmod = steps.index("RUN chmod -R a+rX /app")
    last_copy = max(i for i, name in enumerate(names) if name == "COPY")
    user = names.index("USER")

    assert last_copy < chmod < user


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

    assert "pgdata:/var/lib/postgresql" in mounts
    assert "pgdata" in document["volumes"]


def test_the_database_builds_its_tables_from_the_schema_read_only():
    mounts = compose()["services"]["db"]["volumes"]

    assert ("./schema.sql:/docker-entrypoint-initdb.d/schema.sql:ro"
            in mounts)


def test_the_app_mounts_only_the_config_file_read_only_and_never_a_default():
    mounts = compose()["services"]["app"]["volumes"]

    assert len(mounts) == 1
    source, target, mode = mounts[0].rsplit(":", 2)
    assert (target, mode) == ("/config/config.json", "ro")
    # Required from .env, never defaulted, so the rate in use is a choice.
    assert source.startswith("${PSELLS_CONFIG_FILE:?"), source
    assert ":-" not in source, source


def test_the_database_address_is_built_from_the_environment():
    environment = compose()["services"]["app"]["environment"]
    address = environment["PSELLS_DATABASE_URL"]

    # No password in the file, and the host is the database service itself.
    assert "${POSTGRES_PASSWORD:?" in address
    assert "@db:5432/" in address
    assert environment["PSELLS_CONFIG"] == "/config/config.json"


def test_the_test_database_starts_only_when_asked_for_and_keeps_nothing():
    test_db = compose()["services"]["db-test"]

    # Behind a profile, so "docker compose up" never starts it beside the real
    # database; in memory, so nothing it holds reaches a disk or a volume.
    assert test_db["profiles"] == ["test"]
    assert test_db["tmpfs"] == ["/var/lib/postgresql"]
    assert "volumes" not in test_db
    # The suite wipes whatever it is pointed at and refuses a name without
    # this ending; the service has to be called what the suite expects.
    assert test_db["environment"]["POSTGRES_DB"].endswith("_test")


# Pins -------------------------------------------------------------------------
#
# A tag can be moved to different code or different bytes after it is
# published; a commit hash or an image digest cannot. In March 2026 the tags of
# a widely used scanning action were moved to code that stole CI secrets, which
# is what these hold PSells against.

WORKFLOWS = sorted(glob.glob(
    os.path.join(PROJECT_DIR, ".github", "workflows", "*.yml")))

PINNED_ACTION = re.compile(r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$")
PINNED_IMAGE = re.compile(r"^[\w./-]+:\d+\.\d+(\.\d+)?[\w.-]*@sha256:[0-9a-f]{64}$")


def workflow(path):
    with open(path) as workflow_file:
        return yaml.safe_load(workflow_file)


def test_there_are_workflows_to_check():
    names = {os.path.basename(path) for path in WORKFLOWS}

    assert {"tests.yml", "lint.yml", "security.yml", "image.yml"} <= names


def test_every_action_is_pinned_to_a_commit():
    for path in WORKFLOWS:
        for job in workflow(path)["jobs"].values():
            for step in job["steps"]:
                if "uses" in step:
                    assert PINNED_ACTION.match(step["uses"]), (
                        os.path.basename(path), step["uses"])


def test_every_workflow_can_only_read_the_repository():
    for path in WORKFLOWS:
        assert workflow(path).get("permissions") == {"contents": "read"}, (
            os.path.basename(path))


def test_the_base_image_is_pinned_to_a_version_and_a_digest():
    froms = [arguments[0] for instruction, arguments in instructions()
             if instruction == "FROM"]

    assert len(froms) == 1
    assert PINNED_IMAGE.match(froms[0]), froms[0]


def test_every_postgres_is_the_same_pinned_image():
    # Dependabot updates the Dockerfile and compose.yaml but not a service
    # container in a workflow, so the three copies are held equal here.
    services = compose()["services"]
    ci = workflow(os.path.join(PROJECT_DIR, ".github", "workflows",
                               "tests.yml"))["jobs"]["test"]["services"]

    images = {services["db"]["image"], services["db-test"]["image"],
              ci["postgres"]["image"]}

    assert len(images) == 1, images
    assert PINNED_IMAGE.match(images.pop())


def test_dependabot_watches_every_kind_of_pin():
    with open(os.path.join(PROJECT_DIR, ".github", "dependabot.yml")) as config:
        ecosystems = {update["package-ecosystem"]
                      for update in yaml.safe_load(config)["updates"]}

    assert ecosystems == {"pip", "github-actions", "docker", "docker-compose"}
