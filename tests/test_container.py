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

nginx/nginx.conf is read the same way, with compose.yaml beside it: nginx is
the only way in, it passes on the headers the app relies on with the values
the app relies on, and the app believes forwarded headers from nginx alone.
"""

import ast
import glob
import ipaddress
import json
import os
import re
import stat

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


def test_only_nginx_publishes_the_web_port():
    services = compose()["services"]

    # The app is reached through nginx or not at all; a port of its own would
    # be a way round every rule in nginx.conf.
    assert "ports" not in services["app"]
    assert published_ports(services["proxy"]) == ["127.0.0.1:8000:8080"]


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


# nginx in front ----------------------------------------------------------------

NGINX_CONF = os.path.join(PROJECT_DIR, "nginx", "nginx.conf")

TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|[{};]|[^\s{};]+')


def nginx_directives():
    """nginx.conf as (enclosing blocks, words) pairs, one per directive.

    Enclosing blocks is a tuple with one entry per block the directive sits
    in, outermost first. Each entry is (n, opening words), where n numbers the
    blocks in the order they open, so two server blocks can be told apart. A
    proxy_set_header in the catch-all location of a server comes back as
    ((0, ("http",)), (2, ("server",)), (3, ("location", "/"))),
    ["proxy_set_header", ...]. Comments are dropped, and a block's own opening
    line is not a directive here.
    """
    with open(NGINX_CONF) as conf:
        text = "\n".join(line.split("#", 1)[0] for line in conf)

    result = []
    blocks = []
    words = []
    opened = 0
    for token in TOKEN.findall(text):
        if token == "{":
            blocks.append((opened, tuple(words)))
            opened += 1
            words = []
        elif token == "}":
            blocks.pop()
        elif token == ";":
            result.append((tuple(blocks), words))
            words = []
        else:
            words.append(token)
    assert not blocks and not words, "nginx.conf did not parse"
    return result


def servers():
    """Each server block's directives, keyed by the address it listens on.

    A directive's enclosing blocks are given from inside the server down, as
    plain opening words, so the catch-all location is (("location", "/"),).
    """
    by_number = {}
    for blocks, words in nginx_directives():
        names = [name for _, name in blocks]
        if names[:2] != [("http",), ("server",)]:
            continue
        inner = tuple(name for _, name in blocks[2:])
        by_number.setdefault(blocks[1][0], []).append((inner, words))

    by_listen = {}
    for directives in by_number.values():
        listens = [words[1] for inner, words in directives
                   if inner == () and words[0] == "listen"]
        assert len(listens) == 1, listens
        by_listen[listens[0]] = directives
    return by_listen


def proxied():
    """The directives of the location that passes requests to the app."""
    locations = [(blocks, words) for blocks, words in servers()["8080"]
                 if blocks == (("location", "/"),)]
    assert locations, "no catch-all location in the server on 8080"
    return [words for _, words in locations]


DEFAULT = re.compile(r"\$\{(\w+):-([^}]*)\}")


def with_defaults(value):
    """A compose value with each ${NAME:-default} replaced by its default."""
    return DEFAULT.sub(lambda match: match.group(2), value)


def test_nginx_listens_where_compose_forwards_and_nowhere_else():
    container_port = published_ports(compose()["services"]["proxy"])[0].rsplit(":", 1)[1]

    # One server for the world on the forwarded port, and one for the health
    # check on the container's own loopback, which a published port can never
    # reach.
    assert set(servers()) == {container_port, "127.0.0.1:8081"}


def test_the_health_check_asks_nginx_on_its_private_port():
    test = compose()["services"]["proxy"]["healthcheck"]["test"]

    assert test[-1] == "http://127.0.0.1:8081/health"


def test_nginx_passes_every_request_to_the_port_uvicorn_listens_on():
    command = json.loads(" ".join(
        [arguments for instruction, arguments in instructions()
         if instruction == "CMD"][0]))
    port = command[command.index("--port") + 1]

    assert ["proxy_pass", f"http://app:{port}"] in proxied()


def test_nginx_sends_the_host_with_its_port_and_sets_both_forwarded_headers():
    headers = {words[1]: words[2] for words in proxied()
               if words[0] == "proxy_set_header"}

    assert headers == {
        # The port stays on, or the cross-site check refuses genuine writes.
        "Host": "$http_host",
        # Set, so a client's own X-Forwarded-Proto is replaced.
        "X-Forwarded-Proto": "$scheme",
        # Set, not appended, so a client cannot choose the address recorded.
        "X-Forwarded-For": "$remote_addr",
    }


def test_the_app_believes_forwarded_headers_from_nginx_alone():
    document = compose()
    trusted = document["services"]["app"]["environment"]["FORWARDED_ALLOW_IPS"]
    address = document["services"]["proxy"]["networks"]["default"]["ipv4_address"]
    pool = document["networks"]["default"]["ipam"]["config"][0]

    # The same text, so the one variable that moves the range moves both.
    assert trusted == address

    # One address, not a list, a network or "*".
    nginx = ipaddress.ip_address(with_defaults(trusted))
    assert nginx in ipaddress.ip_network(with_defaults(pool["subnet"]))
    # Outside the range Docker hands out, so no other container can be given
    # the address the app trusts.
    assert nginx not in ipaddress.ip_network(with_defaults(pool["ip_range"]))


def test_nginx_runs_as_its_own_user_and_never_as_root():
    proxy = compose()["services"]["proxy"]
    directives = [words[0] for _, words in nginx_directives()]

    assert proxy["user"] == "101:101"
    # Written for a process that is not root: no user switch, and the process
    # id in a folder the nginx user can write.
    assert "user" not in directives
    assert ["pid", "/tmp/nginx.pid"] in [words for _, words in nginx_directives()]


def test_the_nginx_config_is_mounted_read_only_and_readable_by_nginx():
    mounts = compose()["services"]["proxy"]["volumes"]

    assert mounts == ["./nginx/nginx.conf:/etc/nginx/nginx.conf:ro"]
    # nginx reads it as user 101, not as the file's owner. A file readable by
    # its owner only is refused at startup on Linux, the trap of Phase 04 in
    # another form.
    assert os.stat(NGINX_CONF).st_mode & stat.S_IROTH


def test_nginx_starts_after_the_app_is_healthy_and_restarts_with_it():
    dependency = compose()["services"]["proxy"]["depends_on"]["app"]

    assert dependency == {"condition": "service_healthy", "restart": True}


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


def test_nginx_is_checked_in_ci_with_the_image_the_stack_runs():
    # Dependabot updates compose.yaml but not an image named in a workflow.
    stack = compose()["services"]["proxy"]["image"]
    ci = workflow(os.path.join(PROJECT_DIR, ".github", "workflows",
                               "lint.yml"))["jobs"]["nginx"]["env"]["NGINX_IMAGE"]

    assert stack == ci
    assert PINNED_IMAGE.match(stack), stack


def test_dependabot_watches_every_kind_of_pin():
    with open(os.path.join(PROJECT_DIR, ".github", "dependabot.yml")) as config:
        ecosystems = {update["package-ecosystem"]
                      for update in yaml.safe_load(config)["updates"]}

    assert ecosystems == {"pip", "github-actions", "docker", "docker-compose"}
