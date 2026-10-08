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
import base64
import datetime
import glob
import hashlib
import ipaddress
import json
import os
import re
import stat
import subprocess
import sys

import pytest
import yaml

import psells
from helpers import TEST_DATABASE_URL


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
    # set_password.py is run inside the container too, so it and what it
    # imports have to be there.
    needed = {name + ".py"
              for name in local_imports("api") | local_imports("set_password")}
    sources = {source.rstrip("/") for source in copied_sources()}

    assert needed <= sources, needed - sources
    assert "templates" in sources


# compose.yaml ----------------------------------------------------------------

def compose():
    with open(os.path.join(PROJECT_DIR, "compose.yaml")) as compose_file:
        return yaml.safe_load(compose_file)


class ComposeLoader(yaml.SafeLoader):
    """A safe loader that also reads Compose's !override and !reset tags."""


ComposeLoader.add_constructor(
    "!override", lambda loader, node: Override(loader.construct_sequence(node)))
ComposeLoader.add_constructor("!reset", lambda loader, node: RESET)


class Override(list):
    """A list compose.aws.yaml marks !override: it replaces, not extends."""


# What compose.aws.yaml marks !reset: removed from the merged service.
RESET = object()


def compose_aws():
    with open(os.path.join(PROJECT_DIR, "compose.aws.yaml")) as compose_file:
        return yaml.load(compose_file, Loader=ComposeLoader)


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
    assert published_ports(services["proxy"]) == [
        "127.0.0.1:443:8443", "127.0.0.1:80:8080"]


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

    # No password in the file, and the host is the database service itself
    # unless POSTGRES_HOST names another, which only the AWS server's deploy
    # sets, for RDS.
    assert "${POSTGRES_PASSWORD:?" in address
    assert "@${POSTGRES_HOST:-db}:5432/" in address
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



def test_every_postgres_is_called_ready_only_once_it_answers_over_tcp():
    # On a new volume the image first runs a temporary server on its socket
    # alone while it loads the init files. A pg_isready over the socket passed
    # against that, and on 8 October 2026 CI's first request reached the app
    # while the database was restarting into the real server. Over TCP the
    # check passes only once that server is up.
    with open(os.path.join(PROJECT_DIR, ".github", "workflows",
                           "tests.yml")) as file:
        ci = yaml.safe_load(file)["jobs"]["test"]["services"]["postgres"]
    checks = {name: " ".join(compose()["services"][name]["healthcheck"]["test"])
              for name in ("db", "db-test")}
    checks["tests.yml"] = re.search(r'--health-cmd "([^"]+)"',
                                    ci["options"]).group(1)

    for name, check in checks.items():
        assert "pg_isready -h 127.0.0.1 " in check, name


# nginx in front ----------------------------------------------------------------

NGINX_CONF = os.path.join(PROJECT_DIR, "nginx", "nginx.conf")
NGINX_SITES = os.path.join(PROJECT_DIR, "nginx", "sites")
NGINX_SNIPPETS = os.path.join(PROJECT_DIR, "nginx", "snippets")
SITES = sorted(os.listdir(NGINX_SITES))
# Where compose.yaml mounts the chosen site's folder, and the snippets.
SITE_MOUNT = "/etc/nginx/site/"
SNIPPET_MOUNT = "/etc/nginx/snippets/"

# A token is a quoted string, single or double as nginx allows, a brace or a
# semicolon, or a bare word. Quotes come first, so a brace inside a quoted
# string, as in the JSON log format, is text and not a block.
TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|[{};]|[^\s{};]+')
INCLUDE = re.compile(r"^\s*include\s+(\S+);", re.M)


def without_comments(path):
    with open(path) as conf:
        return "\n".join(line.split("#", 1)[0] for line in conf)


def expand(text, site):
    """Each include in text replaced by the file, or files, it names, as
    nginx would read them with that site's folder mounted. A pattern that
    matches nothing, as a site with no servers of its own gives, adds nothing.
    """
    def included(match):
        path = match.group(1)
        if path.startswith(SNIPPET_MOUNT):
            files = [os.path.join(NGINX_SNIPPETS, path[len(SNIPPET_MOUNT):])]
        else:
            assert path.startswith(SITE_MOUNT), path
            files = sorted(glob.glob(os.path.join(NGINX_SITES, site,
                                                  path[len(SITE_MOUNT):])))
            if "*" not in path:
                assert files, path
        return "\n".join(expand(without_comments(name), site) for name in files)
    return INCLUDE.sub(included, text)


def nginx_text(site):
    """nginx.conf without comments, every include replaced by its files.

    With site None the includes are left as they are, which is how the tests
    see what nginx.conf itself says.
    """
    text = without_comments(NGINX_CONF)
    if site is None:
        return text
    return expand(text, site)


def nginx_directives(site="localhost"):
    """nginx.conf as (enclosing blocks, words) pairs, one per directive.

    Read as nginx reads it with that site's folder mounted: psells.localhost
    unless another is named.

    Enclosing blocks is a tuple with one entry per block the directive sits
    in, outermost first. Each entry is (n, opening words), where n numbers the
    blocks in the order they open, so two server blocks can be told apart. A
    proxy_set_header in the catch-all location of a server comes back as
    ((0, ("http",)), (2, ("server",)), (3, ("location", "/"))),
    ["proxy_set_header", ...]. Comments are dropped, and a block's own opening
    line is not a directive here.
    """
    text = nginx_text(site)

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


def servers(site="localhost"):
    """Each server block as (listen words, server names, directives).

    Listen words are the words after "listen", such as ["8443", "ssl",
    "default_server"]. A directive's enclosing blocks are given from inside the
    server down, as plain opening words, so the catch-all location is
    (("location", "/"),).
    """
    by_number = {}
    for blocks, words in nginx_directives(site):
        names = [name for _, name in blocks]
        if names[:2] != [("http",), ("server",)]:
            continue
        inner = tuple(name for _, name in blocks[2:])
        by_number.setdefault(blocks[1][0], []).append((inner, words))

    result = []
    for directives in by_number.values():
        top = [words for inner, words in directives if inner == ()]
        listens = [words[1:] for words in top if words[0] == "listen"]
        assert len(listens) == 1, listens
        server_names = [name for words in top if words[0] == "server_name"
                        for name in words[1:]]
        result.append((listens[0], server_names, directives))
    return result


def server(port, name=None, site="localhost"):
    """The one server listening on port with that server_name, or none."""
    found = [directives for listen, names, directives in servers(site)
             if listen[0] == port and (names == [name] if name else not names)]
    assert len(found) == 1, (port, name, len(found))
    return found[0]


def top_level(directives):
    return [words for inner, words in directives if inner == ()]


def proxied():
    """The directives of the location that passes requests to the app."""
    locations = [words for inner, words in server("8443", "psells.localhost")
                 if inner == (("location", "/"),)]
    assert locations, "no catch-all location in the psells.localhost server"
    return locations


DEFAULT = re.compile(r"\$\{(\w+):-([^}]*)\}")


def with_defaults(value):
    """A compose value with each ${NAME:-default} replaced by its default."""
    return DEFAULT.sub(lambda match: match.group(2), value)


def test_nginx_listens_where_compose_forwards_and_nowhere_else():
    forwarded = {port.rsplit(":", 1)[1]
                 for port in published_ports(compose()["services"]["proxy"])}
    listening = {listen[0] for listen, _, _ in servers()}

    # The two forwarded ports, and the health check on the container's own
    # loopback, which a published port can never reach.
    assert listening == forwarded | {"127.0.0.1:8081"}


def test_plain_http_only_redirects_to_the_one_https_address():
    directives = server("8080")

    assert top_level(directives) == [
        ["listen", "8080", "default_server"],
        ["return", "301", "https://psells.localhost$request_uri"],
    ]


def test_https_for_any_other_name_is_refused_and_never_served():
    # Refused in the handshake when asked for there, and answered 421 when
    # only the Host header names it, since nginx picks a server per request by
    # Host. A server with neither would serve nginx's own welcome page.
    assert top_level(server("8443")) == [
        ["listen", "8443", "ssl", "default_server"],
        ["ssl_reject_handshake", "on"],
        ["return", "421"],
    ]


def test_the_https_server_answers_psells_localhost_alone():
    top = top_level(server("8443", "psells.localhost"))

    assert ["listen", "8443", "ssl"] in top
    assert ["server_name", "psells.localhost"] in top


def test_https_is_tls_1_3_only_with_the_certificate_from_data_tls():
    http_level = [words for blocks, words in nginx_directives()
                  if [name for _, name in blocks] == [("http",)]]
    top = top_level(server("8443", "psells.localhost"))

    assert ["ssl_protocols", "TLSv1.3"] in http_level
    assert ["ssl_certificate", "/etc/nginx/tls/psells.localhost.crt"] in top
    assert ["ssl_certificate_key", "/etc/nginx/tls/psells.localhost.key"] in top
    assert ("./data/tls:/etc/nginx/tls:ro"
            in compose()["services"]["proxy"]["volumes"])


def test_the_health_check_asks_nginx_on_its_private_port():
    test = compose()["services"]["proxy"]["healthcheck"]["test"]

    assert test[-1] == "http://127.0.0.1:8081/health"


def test_nginx_passes_every_request_to_the_port_uvicorn_listens_on():
    command = json.loads(" ".join(
        [arguments for instruction, arguments in instructions()
         if instruction == "CMD"][0]))
    port = command[command.index("--port") + 1]

    assert ["proxy_pass", f"http://app:{port}"] in proxied()


def test_nginx_sends_the_host_as_sent_and_sets_both_forwarded_headers():
    headers = {words[1]: words[2] for words in proxied()
               if words[0] == "proxy_set_header"}

    assert headers == {
        # As the browser sent it, port and all, to match its Origin.
        "Host": "$http_host",
        # Set, so a client's own X-Forwarded-Proto is replaced, and written
        # out: every visitor used HTTPS, even when TLS ended at a load
        # balancer and nginx was reached over plain HTTP.
        "X-Forwarded-Proto": "https",
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


def http_level():
    return [words for blocks, words in nginx_directives()
            if [name for _, name in blocks] == [("http",)]]


def response_headers():
    """The add_header lines of the psells.localhost server, by name."""
    headers = {}
    for words in top_level(server("8443", "psells.localhost")):
        if words[0] == "add_header":
            name, value, *rest = words[1:]
            # On every response, errors included, not only successful ones.
            assert rest == ["always"], words
            headers[name] = value.strip('"')
    return headers


def test_nginx_hides_its_version_and_limits_request_bodies():
    assert ["server_tokens", "off"] in http_level()
    assert ["client_max_body_size", "64k"] in http_level()


def login_limit_map():
    """The map nginx keys the login limit on, as {match: value}."""
    found = [(blocks, words) for blocks, words in nginx_directives()
             if [name for _, name in blocks][-1:] == [
                 ("map", '"$request_method:$uri"', "$login_attempt")]]
    return {words[0].strip('"'): words[1].strip('"') for _, words in found}


def test_only_a_post_to_login_is_counted_by_address():
    # Every other request maps to an empty key, which limit_req never counts,
    # so pages, the API and showing the login page are never limited.
    assert login_limit_map() == {"default": "", "POST:/login":
                                 "$binary_remote_addr"}


def test_login_attempts_are_limited_to_five_a_minute_with_a_burst_of_five():
    assert ["limit_req_zone", "$login_attempt", "zone=login:1m",
            "rate=5r/m"] in http_level()
    assert ["limit_req_status", "429"] in http_level()
    assert ["limit_req", "zone=login", "burst=5", "nodelay"] in proxied()


def test_the_limit_sits_where_every_request_to_the_app_passes():
    # In the one location that proxies, so no path to the app avoids it, and
    # nowhere else, where a second limit_req would count some posts twice.
    everywhere = [(blocks, words) for blocks, words in nginx_directives()
                  if words[0] == "limit_req"]

    assert len(everywhere) == 1
    assert [name for _, name in everywhere[0][0]][-1] == ("location", "/")


def test_every_psells_response_carries_the_security_headers():
    headers = response_headers()

    assert headers["Strict-Transport-Security"] == "max-age=31536000"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "same-origin"
    assert set(headers) == {
        "Strict-Transport-Security", "Content-Security-Policy",
        "X-Content-Type-Options", "Referrer-Policy"}


def test_no_location_drops_the_server_headers():
    # nginx forgets a server's add_header lines inside any location that has
    # one of its own, silently.
    for inner, words in server("8443", "psells.localhost"):
        assert not (inner and words[0] == "add_header"), (inner, words)


def csp():
    return dict(
        (directive.split(" ", 1) + [""])[:2]
        for directive in (part.strip() for part in
                          response_headers()["Content-Security-Policy"].split(";"))
        if directive)


def test_the_content_security_policy_allows_nothing_it_does_not_name():
    policy = csp()

    assert policy["default-src"] == "'none'"
    assert policy["form-action"] == "'self'"
    assert policy["frame-ancestors"] == "'none'"
    assert policy["base-uri"] == "'none'"
    assert set(policy) == {"default-src", "style-src", "form-action",
                           "frame-ancestors", "base-uri"}
    # No script source of any kind, and no way to allow inline code wholesale.
    assert "unsafe" not in response_headers()["Content-Security-Policy"]


def test_the_style_hash_matches_the_style_block_pages_are_served_with(client):
    page = client.get("/").text
    blocks = re.findall(r"<style>(.*?)</style>", page, re.S)
    digest = base64.b64encode(
        hashlib.sha256(blocks[0].encode()).digest()).decode()

    # One block, so one hash covers every page; a second would need its own.
    assert len(blocks) == 1
    assert csp()["style-src"] == f"'sha256-{digest}'", (
        "templates/base.html changed its <style> block: put this hash in "
        f"nginx.conf: sha256-{digest}")
    # And nothing on any page that the policy would refuse.
    assert "<script" not in page
    assert " style=" not in page


LOG_FORMAT = re.compile(r"log_format\s+psells\s+escape=json\s+((?:'[^']*'\s*)+);")

# What a visitor could be identified or tracked by, none of which the access
# log may carry, because on the server it leaves for Grafana Cloud.
PERSONAL_VARIABLES = {"$remote_addr", "$binary_remote_addr",
                      "$http_x_forwarded_for", "$proxy_add_x_forwarded_for",
                      "$realip_remote_addr", "$request", "$request_uri",
                      "$args", "$query_string", "$is_args", "$http_user_agent",
                      "$http_referer", "$http_cookie", "$remote_user"}


def access_log_format():
    """The psells log format's template, its quoted pieces joined."""
    (pieces,) = LOG_FORMAT.findall(nginx_text(None))
    return "".join(re.findall(r"'([^']*)'", pieces))


def test_every_request_is_logged_as_json_in_the_one_format():
    directives = [(blocks, words) for site in SITES
                  for blocks, words in nginx_directives(site)
                  if words[0] in ("access_log", "log_format")]

    for blocks, words in directives:
        if words[0] == "access_log":
            # Logged in the psells format, or not at all (the health checks).
            assert words[1:] in (["/dev/stdout", "psells"], ["off"]), words
    assert ["access_log", "/dev/stdout", "psells"] in [
        words for blocks, words in directives
        if [b[1] for b in blocks] == [("http",)]]


def test_the_log_line_is_json_with_what_the_slos_need():
    template = access_log_format()
    # Each variable stands in as a value nginx could give it.
    sample = {"$time_iso8601": "2026-10-04T12:00:00+00:00",
              "$host": "psells.localhost", "$request_method": "GET",
              "$uri": '/a"b\\c', "$status": "200", "$body_bytes_sent": "512",
              "$request_time": "0.012", "$upstream_response_time": "-"}
    line = template
    for name in sorted(sample, key=len, reverse=True):
        # escape=json escapes inside strings; this does the same here.
        value = sample[name]
        if name == "$uri":
            value = json.dumps(value)[1:-1]
        line = line.replace(name, value)

    entry = json.loads(line)

    assert set(entry) == {"time", "host", "method", "path", "status", "bytes",
                          "request_time", "upstream_time"}
    assert entry["path"] == '/a"b\\c'
    assert isinstance(entry["status"], int)
    assert isinstance(entry["request_time"], float)


def test_the_log_line_carries_nothing_that_identifies_a_visitor():
    used = set(re.findall(r"\$[a-z_]+", access_log_format()))

    assert used
    assert not used & PERSONAL_VARIABLES, used & PERSONAL_VARIABLES


def test_nginx_loads_no_modules_because_the_slim_image_has_none():
    # compose.yaml runs the alpine-slim image, which leaves out every add-on
    # module. A load_module line would stop nginx at startup; this says why
    # before anyone finds out that way.
    assert "load_module" not in [words[0] for _, words in nginx_directives()]
    assert "-alpine-slim@" in nginx_base_image()


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

    assert mounts == ["./nginx/nginx.conf:/etc/nginx/nginx.conf:ro",
                      "./nginx/snippets:/etc/nginx/snippets:ro",
                      "./nginx/sites/localhost:/etc/nginx/site:ro",
                      "./data/tls:/etc/nginx/tls:ro"]
    # nginx reads them as user 101, not as the files' owner. A file readable
    # by its owner only is refused at startup on Linux, the trap of Phase 04
    # in another form.
    site_files = (glob.glob(os.path.join(NGINX_SITES, "**", "*.conf"), recursive=True)
                  + glob.glob(os.path.join(NGINX_SNIPPETS, "*.conf")))
    assert site_files
    for path in [NGINX_CONF, *site_files]:
        assert os.stat(path).st_mode & stat.S_IROTH, path


# One file for every place, and a folder for each place -----------------------

def site_directives(site, name):
    """One site file's directives, as nginx_directives gives them."""
    text = without_comments(os.path.join(NGINX_SITES, site, name))
    result, blocks, words = [], [], []
    for token in TOKEN.findall(text):
        if token == "{":
            blocks.append(tuple(words))
            words = []
        elif token == "}":
            blocks.pop()
        elif token == ";":
            result.append((tuple(blocks), words))
            words = []
        else:
            words.append(token)
    assert not blocks and not words, f"{site}/{name} did not parse"
    return result


def test_nginx_conf_itself_names_no_place():
    # Every name, certificate and redirect lives in a site's folder, so
    # nginx.conf is the same file wherever PSells runs, and a rule added to
    # it reaches every place at once.
    words = [words for _, words in nginx_directives(site=None)]

    assert not [w for w in words if w[0] in
                {"server_name", "ssl_certificate", "ssl_certificate_key"}]
    assert "localhost" not in nginx_text(None)
    assert [w for w in words if w[0] == "include"] == [
        ["include", SITE_MOUNT + "http.conf"],
        ["include", SITE_MOUNT + "https.conf"],
        ["include", SNIPPET_MOUNT + "headers.conf"],
        ["include", SNIPPET_MOUNT + "app.conf"],
        ["include", SITE_MOUNT + "servers/*.conf"],
    ]
    # And no header or proxy rule of its own: those are in the snippets.
    assert not [w for w in words if w[0] in {"add_header", "proxy_pass",
                                            "proxy_set_header", "limit_req"}]


def test_there_is_a_site_for_the_mac_and_one_for_the_server():
    assert SITES == ["aws", "localhost"]


# The AWS server -----------------------------------------------------------------
#
# compose.aws.yaml is laid over compose.yaml on the server only. A volume in it
# replaces the one in compose.yaml with the same target; a list marked
# !override replaces the whole list.

def mounts_by_target(volumes):
    return {volume.split(":")[1]: volume for volume in volumes}


def test_the_server_publishes_its_ports_on_every_address_and_nothing_else():
    ports = compose_aws()["services"]["proxy"]["ports"]

    # !override, or Compose would add these to the 127.0.0.1 ones and fail to
    # bind the same port twice. 8090 is the load balancer's, which the
    # server's security group admits from the load balancer alone.
    assert isinstance(ports, Override)
    assert list(ports) == ["443:8443", "80:8080", "8090:8090"]
    # And nginx listens where they lead.
    listening = {listen[0] for listen, _, _ in servers("aws")}
    assert listening == {"8443", "8080", "8090", "127.0.0.1:8081"}


def test_the_server_swaps_the_site_and_certificate_and_adds_the_webroot():
    mac = mounts_by_target(compose()["services"]["proxy"]["volumes"])
    server = mounts_by_target(compose_aws()["services"]["proxy"]["volumes"])

    # The same targets as on the Mac, so these replace them, and one more.
    assert set(server) == {"/etc/nginx/site", "/etc/nginx/tls", "/var/www/acme"}
    assert set(server) - set(mac) == {"/var/www/acme"}
    assert server["/etc/nginx/site"] == "./nginx/sites/aws:/etc/nginx/site:ro"
    assert server["/etc/nginx/tls"] == "./data/letsencrypt:/etc/nginx/tls:ro"
    assert server["/var/www/acme"] == "./data/acme:/var/www/acme:ro"


def test_the_server_runs_the_published_image_by_digest_and_builds_nothing():
    app = compose_aws()["services"]["app"]

    assert app["build"] is RESET
    # Required, never defaulted: deploy.sh writes the digest it resolved.
    assert app["image"].startswith("${PSELLS_IMAGE:?")
    # The Mac still builds its own.
    assert compose()["services"]["app"]["build"] == "."


def test_the_database_host_defaults_to_the_container_and_rds_is_verified():
    url = compose()["services"]["app"]["environment"]["PSELLS_DATABASE_URL"]
    mounts = mounts_by_target(compose_aws()["services"]["app"]["volumes"])

    # Unset, as on the Mac, the address is the container's, as it always was.
    assert "@${POSTGRES_HOST:-db}:5432/" in url
    assert url.endswith("${POSTGRES_URL_OPTIONS:-}")
    # On the server the app can check RDS's certificate against AWS's CAs.
    assert mounts["/config/rds-ca.pem"] == "./data/rds-ca.pem:/config/rds-ca.pem:ro"


def test_certbot_writes_where_nginx_reads_as_nginx_own_user():
    services = compose_aws()["services"]
    certbot = services["certbot"]
    proxy = services["proxy"]
    certbot_mounts = mounts_by_target(certbot["volumes"])
    proxy_mounts = mounts_by_target(proxy["volumes"])

    # The same user as nginx, so the key is owner-only and nginx its owner.
    assert certbot["user"] == compose()["services"]["proxy"]["user"] == "101:101"
    # Started only when asked for, pinned, and off the stack's network.
    assert certbot["profiles"] == ["certbot"]
    assert PINNED_IMAGE.match(certbot["image"]), certbot["image"]
    assert certbot["network_mode"] == "bridge"
    # certbot's config folder is what nginx reads as its certificates, and
    # its webroot is what nginx serves the challenge from.
    assert (certbot_mounts["/etc/letsencrypt"].split(":")[0]
            == proxy_mounts["/etc/nginx/tls"].split(":")[0])
    assert (certbot_mounts["/var/www/acme"].split(":")[0]
            == proxy_mounts["/var/www/acme"].split(":")[0])
    # Writable by certbot, read-only to nginx.
    assert not certbot_mounts["/etc/letsencrypt"].endswith(":ro")
    assert proxy_mounts["/etc/nginx/tls"].endswith(":ro")


def test_the_server_site_serves_the_challenge_and_its_certbot_certificate():
    http = site_directives("aws", "http.conf")
    https = [words for _, words in site_directives("aws", "https.conf")]
    name = [w[1] for w in https if w[0] == "server_name"][0]
    served = compose_aws()["services"]["proxy"]["volumes"]

    # The challenge path answers from the webroot compose.aws.yaml mounts.
    assert [(blocks, words) for blocks, words in http if words[0] == "root"] == [
        ((("location", "/.well-known/acme-challenge/"),), ["root", "/var/www/acme"])]
    assert "./data/acme:/var/www/acme:ro" in served
    # And the certificate is certbot's for that name, under the tls mount.
    live = f"/etc/nginx/tls/live/{name}/"
    assert ["ssl_certificate", live + "fullchain.pem"] in https
    assert ["ssl_certificate_key", live + "privkey.pem"] in https


@pytest.mark.parametrize("site", SITES)
def test_every_site_answers_one_name_and_redirects_only_to_it(site):
    https = [words for _, words in site_directives(site, "https.conf")]
    names = [w[1:] for w in https if w[0] == "server_name"]

    # One name, and nothing in https.conf but that name and its certificate:
    # every other rule for the server is in nginx.conf.
    assert len(names) == 1 and len(names[0]) == 1, names
    assert sorted(w[0] for w in https) == [
        "server_name", "ssl_certificate", "ssl_certificate_key"]

    # Plain HTTP sends everyone to that name and nowhere else.
    redirects = [w for _, w in site_directives(site, "http.conf")
                 if w[0] == "return"]
    assert redirects == [["return", "301",
                          f"https://{names[0][0]}$request_uri"]]


@pytest.mark.parametrize("site", SITES)
def test_every_site_gives_nginx_the_same_servers(site):
    # Included, each site's files make the same three servers, the one for
    # its name carrying every header and the proxy; a site may add servers of
    # its own after them.
    https = [words for _, words in site_directives(site, "https.conf")]
    name = [w[1] for w in https if w[0] == "server_name"][0]
    own = sorted(os.path.basename(path) for path in glob.glob(
        os.path.join(NGINX_SITES, site, "servers", "*.conf")))

    listening = sorted(listen[0] for listen, _, _ in servers(site))
    common = ["127.0.0.1:8081", "8080", "8443", "8443"]
    assert listening == sorted(common + (["8090"] if own == ["lb.conf"] else []))
    assert own in ([], ["lb.conf"]), own
    served = top_level(server("8443", name, site))
    assert ["listen", "8443", "ssl"] in served
    assert sum(1 for w in served if w[0] == "add_header") == 4


def headers_of(directives):
    return {words[1]: words[2] for inner, words in directives
            if inner == () and words[0] == "add_header"}


def proxy_of(directives):
    return [words for inner, words in directives if inner == (("location", "/"),)]


def test_the_load_balancer_listener_serves_psells_exactly_as_the_main_one():
    main = server("8443", "psells.lakeshorefreight.me", "aws")
    lb = server("8090", "lb.psells.lakeshorefreight.me", "aws")

    # The same four headers and the same way to the app, from the same files.
    assert headers_of(lb) == headers_of(main)
    assert proxy_of(lb) == proxy_of(main)
    assert ["listen", "8090", "default_server"] in top_level(lb)


def test_the_load_balancer_listener_believes_only_the_vpc_and_the_last_hop():
    lb = top_level(server("8090", "lb.psells.lakeshorefreight.me", "aws"))

    # Only from the VPC's private range, where the load balancer is.
    assert [w for w in lb if w[0] == "set_real_ip_from"] == [
        ["set_real_ip_from", "172.31.0.0/16"]]
    assert ["real_ip_header", "X-Forwarded-For"] in lb
    # Recursive would walk back past the load balancer's own entry to
    # addresses the client wrote; off, only the last one is taken.
    assert not [w for w in lb if w[0] == "real_ip_recursive"]
    # And the main HTTPS server believes no forwarded address at all.
    main = [words for _, words in server("8443", "psells.lakeshorefreight.me", "aws")]
    assert not [w for w in main if w[0].startswith("set_real_ip") or w[0] == "real_ip_header"]


def test_the_mac_has_no_load_balancer_listener():
    assert "8090" not in {listen[0] for listen, _, _ in servers("localhost")}
    assert not glob.glob(os.path.join(NGINX_SITES, "localhost", "servers", "*"))


def test_the_stack_comes_back_whenever_docker_starts():
    services = compose()["services"]

    # After Docker Desktop restarts, or the server reboots. unless-stopped, so
    # a container stopped on purpose stays stopped.
    for name in ("proxy", "app", "db"):
        assert services[name].get("restart") == "unless-stopped", name
    # The throwaway test database is not part of the running stack.
    assert "restart" not in services["db-test"]
    # And the server's overlay does not take it away.
    for name, service in compose_aws()["services"].items():
        assert "restart" not in service or service["restart"] == "unless-stopped", name


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
PINNED_IMAGE = re.compile(r"^[\w./-]+:v?\d+\.\d+(\.\d+)?[\w.-]*@sha256:[0-9a-f]{64}$")


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


NGINX_DOCKERFILE = os.path.join(PROJECT_DIR, "nginx", "Dockerfile")


def nginx_base_image():
    """The official nginx image PSells' own is built on, from its FROM line."""
    with open(NGINX_DOCKERFILE) as dockerfile:
        (base,) = re.findall(r"^FROM (\S+)$", dockerfile.read(), re.M)
    return base


def test_psells_nginx_is_the_pinned_official_image_with_alpines_fixes_only():
    with open(NGINX_DOCKERFILE) as dockerfile:
        lines = [line for line in dockerfile.read().splitlines()
                 if line and not line.startswith("#")]

    assert PINNED_IMAGE.match(nginx_base_image())
    assert nginx_base_image().startswith("nginx:")
    # One upgrade of named packages, from no cache, and nothing copied in:
    # the configuration stays mounted read-only from nginx/.
    assert lines[1:] == [
        "RUN apk upgrade --no-cache zlib pcre2 libssl3 libcrypto3"]


def test_the_stack_lint_and_ci_all_use_psells_nginx_image():
    lint = workflow(os.path.join(PROJECT_DIR, ".github", "workflows",
                                 "lint.yml"))["jobs"]["nginx"]
    lint_steps = "\n".join(step.get("run", "") for step in lint["steps"])
    matrix = workflow(os.path.join(PROJECT_DIR, ".github", "workflows",
                                   "image.yml"))["jobs"]["app"]["strategy"]["matrix"]["include"]

    # The Mac builds it from nginx/, as it builds the app from the top.
    assert compose()["services"]["proxy"]["build"] == "./nginx"
    assert "image" not in compose()["services"]["proxy"]
    # nginx -t runs on that same image, built the same way, for both sites.
    assert "docker build --tag psells-nginx:lint nginx" in lint_steps
    assert lint_steps.count("psells-nginx:lint nginx -t") == 2
    assert "NGINX_IMAGE" not in lint_steps and "env" not in lint
    # CI builds, scans and publishes it on both architectures.
    assert sorted((entry["image"], entry["arch"], entry["context"])
                  for entry in matrix if entry["image"] == "nginx") == [
        ("nginx", "amd64", "nginx"), ("nginx", "arm64", "nginx")]


def test_the_server_runs_the_published_nginx_image_by_digest():
    proxy = compose_aws()["services"]["proxy"]
    with open(os.path.join(PROJECT_DIR, "deploy", "aws", "deploy.sh")) as script:
        deploy = script.read()

    assert proxy["image"].startswith("${PSELLS_NGINX_IMAGE:?")
    assert proxy["build"] is RESET
    assert '"$REGISTRY_IMAGE:nginx-$commit"' in deploy
    assert 'nginx_image="$REGISTRY_IMAGE@$nginx_published"' in deploy
    assert "PSELLS_NGINX_IMAGE=$nginx_image" in deploy


def test_dependabot_watches_the_nginx_image_psells_builds_on():
    with open(os.path.join(PROJECT_DIR, ".github", "dependabot.yml")) as file:
        updates = yaml.safe_load(file)["updates"]

    assert {"package-ecosystem": "docker", "directory": "/nginx"}.items() <= [
        u for u in updates if u.get("directory") == "/nginx"][0].items()


# Each image job's exceptions file. The app's and nginx's images, which PSells
# builds, have none: only the agent's, which it does not.
GRYPE_EXCEPTIONS = {"alloy": "monitoring/grype-exceptions.yaml"}


def scan_steps(job):
    return [step for step in job["steps"]
            if step.get("uses", "").startswith("anchore/scan-action@")]


def image_jobs():
    return workflow(os.path.join(PROJECT_DIR, ".github", "workflows",
                                 "image.yml"))["jobs"]


@pytest.mark.parametrize("job", sorted(GRYPE_EXCEPTIONS))
def test_only_each_jobs_failing_scan_reads_its_own_exceptions(job):
    jobs = image_jobs()
    listing, failing = scan_steps(jobs[job])

    assert failing["with"]["config"] == GRYPE_EXCEPTIONS[job]
    assert failing["with"]["fail-build"] is True
    # The listing still shows everything, and the app's image skips nothing.
    assert "config" not in listing["with"]
    for step in scan_steps(jobs["app"]):
        assert "config" not in step["with"]
    # The scan action reads a .grype.yaml it finds unless given a file.
    assert not glob.glob(os.path.join(PROJECT_DIR, ".grype*"))
    # The job checks its own file's date, no other.
    expiry = [step["run"] for step in jobs[job]["steps"]
              if step.get("name") == "Fail once the exceptions have expired"]
    assert len(expiry) == 1 and GRYPE_EXCEPTIONS[job] in expiry[0]


@pytest.mark.parametrize("job", sorted(GRYPE_EXCEPTIONS))
def test_each_exception_names_one_flaw_in_one_version_of_one_package(job):
    with open(os.path.join(PROJECT_DIR, GRYPE_EXCEPTIONS[job])) as file:
        config = yaml.safe_load(file)

    assert set(config) == {"ignore"}
    assert config["ignore"]
    for rule in config["ignore"]:
        assert set(rule) == {"vulnerability", "package"}, rule
        assert set(rule["package"]) == {"name", "version", "type"}, rule


@pytest.mark.parametrize("job", sorted(GRYPE_EXCEPTIONS))
def test_the_exceptions_have_not_expired(job):
    # Each job checks the same line, so it fails on the same day.
    with open(os.path.join(PROJECT_DIR, GRYPE_EXCEPTIONS[job])) as file:
        expires = re.findall(r"^# expires: (\d{4}-\d\d-\d\d)$", file.read(), re.M)

    assert len(expires) == 1
    assert datetime.date.today() < datetime.date.fromisoformat(expires[0]), (
        f"{GRYPE_EXCEPTIONS[job]} has expired: check for a fixed image, and "
        "remove or renew each exception")


def test_the_agent_is_scanned_as_the_server_runs_it_and_checked_for_openssl():
    job = image_jobs()["alloy"]
    names = [step.get("name") for step in job["steps"]]

    assert job["env"]["ALLOY_IMAGE"] == alloy()["image"]
    # The OpenSSL exception rests on the agent never loading libssl, checked
    # before the failing scan.
    assert names.index("Fail if the agent links OpenSSL") < names.index(
        "Fail on a high or critical vulnerability that has a fix")
    check = job["steps"][names.index("Fail if the agent links OpenSSL")]["run"]
    assert "ldd" in check and "! grep -q libssl" in check
    assert "packages" not in job.get("permissions", {})


def test_every_commit_is_scanned_for_secrets_with_a_pinned_scanner():
    job = workflow(os.path.join(PROJECT_DIR, ".github", "workflows",
                                "security.yml"))["jobs"]["secrets"]
    checkout = job["steps"][0]
    scan = job["steps"][1]["run"]

    assert PINNED_IMAGE.match(job["env"]["GITLEAKS_IMAGE"])
    # The whole history, not the one commit a checkout fetches by default.
    assert checkout["with"]["fetch-depth"] == 0
    assert "--log-opts=--all" in scan
    assert "--redact" in scan
    assert ":/repo:ro" in scan


def test_only_a_job_without_third_party_code_can_publish_and_only_from_main():
    jobs = workflow(os.path.join(PROJECT_DIR, ".github", "workflows",
                                 "image.yml"))["jobs"]
    main_push = "github.event_name == 'push' && github.ref == 'refs/heads/main'"

    # The scanner runs where the token can write nothing.
    for name, job in jobs.items():
        if name != "publish":
            assert "packages" not in job.get("permissions", {}), name
    publish = jobs["publish"]
    assert publish["permissions"] == {"packages": "write"}
    assert publish["if"] == main_push
    assert publish["needs"] == "app"
    # Nothing runs beside the token but GitHub's own artifact action.
    actions = [step["uses"].split("@")[0] for step in publish["steps"]
               if "uses" in step]
    assert actions == ["actions/download-artifact"]


def test_what_is_published_is_what_was_scanned():
    jobs = workflow(os.path.join(PROJECT_DIR, ".github", "workflows",
                                 "image.yml"))["jobs"]
    app = "\n".join(step.get("run", "") for step in jobs["app"]["steps"])
    publish = "\n".join(step.get("run", "") for step in jobs["publish"]["steps"])
    builds = sorted((entry["image"], entry["arch"], entry["runner"])
                    for entry in jobs["app"]["strategy"]["matrix"]["include"])

    # Both images on both architectures, each built on its own kind of machine.
    assert builds == [("app", "amd64", "ubuntu-24.04"),
                      ("app", "arm64", "ubuntu-24.04-arm"),
                      ("nginx", "amd64", "ubuntu-24.04"),
                      ("nginx", "arm64", "ubuntu-24.04-arm")]
    # The ID of the scanned image is recorded, and a loaded image that does
    # not have it is refused before anything is pushed.
    assert "docker image inspect --format '{{.Id}}' psells:ci > image-id" in app
    assert '[ "$id" = "$scanned" ] ||' in publish
    assert publish.index('[ "$id" = "$scanned" ]') < publish.index("docker push")
    # Tagged by commit, never by a name that moves, such as latest.
    assert "latest" not in publish
    assert '"$IMAGE:${prefix}${{ github.sha }}"' in publish
    assert '[ "$image" = nginx ] && prefix="nginx-"' in publish


def deploy_workflow():
    return workflow(os.path.join(PROJECT_DIR, ".github", "workflows", "deploy.yml"))


def test_a_deploy_waits_for_every_check_on_main():
    document = deploy_workflow()
    # PyYAML reads the key "on" as True.
    triggers = document[True]
    gate = document["jobs"]["gate"]["steps"][0]["run"]
    checks = {os.path.basename(path): workflow(path)["name"] for path in WORKFLOWS
              if not path.endswith("deploy.yml")}

    # Started by every other workflow, on main only, and by hand.
    assert sorted(triggers["workflow_run"]["workflows"]) == sorted(checks.values())
    assert triggers["workflow_run"]["branches"] == ["main"]
    assert triggers["workflow_run"]["types"] == ["completed"]
    assert list(triggers["workflow_dispatch"]["inputs"]) == ["commit"]
    # The gate asks about every one of them, for pushes to main, and only
    # a full commit hash gets past it.
    assert sorted(re.search(r"for workflow in ([^;]+);", gate).group(1).split()) \
        == sorted(checks)
    assert "branch=main&event=push" in gate
    assert '[[ "$commit" =~ ^[0-9a-f]{40}$ ]]' in gate
    # One deploy at a time, and a running one is never cancelled halfway.
    assert document["concurrency"] == {"group": "deploy",
                                       "cancel-in-progress": False}


def test_the_deploy_holds_no_key_and_runs_no_third_party_code():
    document = deploy_workflow()
    jobs = document["jobs"]
    with open(os.path.join(PROJECT_DIR, ".github", "workflows",
                           "deploy.yml")) as source:
        text = source.read()

    assert jobs["gate"]["permissions"] == {"actions": "read"}
    assert jobs["deploy"]["permissions"] == {"id-token": "write"}
    assert jobs["deploy"]["needs"] == "gate"
    assert jobs["deploy"]["if"] == "needs.gate.outputs.go == 'yes'"
    # No action at all: the AWS CLI and curl on the runner do everything.
    assert not [step for job in jobs.values() for step in job["steps"]
                if "uses" in step]
    # No stored AWS key; the role comes from a repository variable.
    assert "secrets.AWS" not in text
    assert jobs["deploy"]["env"]["ROLE"] == "${{ vars.AWS_DEPLOY_ROLE_ARN }}"
    assert "--document-name psells-deploy" in text
    assert "AWS-RunShellScript" not in text


def test_nothing_from_the_event_is_written_into_a_script():
    for job in deploy_workflow()["jobs"].values():
        for step in job["steps"]:
            # Event values and inputs reach a script only through env.
            assert "github.event" not in step.get("run", "")
            assert "inputs." not in step.get("run", "")


def test_a_deploy_is_checked_from_outside_and_against_its_digest():
    steps = "\n".join(step.get("run", "") for step in
                      deploy_workflow()["jobs"]["deploy"]["steps"])

    assert 'grep -qx "running $IMAGE@$DIGEST" result.txt' in steps
    assert '"$SITE/login"' in steps
    # A visitor's view: an untrusted certificate fails the check.
    assert " -k" not in steps and "--insecure" not in steps


def test_dependabot_watches_every_kind_of_pin():
    with open(os.path.join(PROJECT_DIR, ".github", "dependabot.yml")) as config:
        ecosystems = {update["package-ecosystem"]
                      for update in yaml.safe_load(config)["updates"]}

    assert ecosystems == {"pip", "github-actions", "docker", "docker-compose"}


# The monitoring agent ----------------------------------------------------------
#
# Grafana Alloy runs on the AWS server only and sends the server's health and
# nginx's access log to Grafana Cloud. These hold it to what it was given:
# no Docker socket, nothing it can write but its own data, no port, a memory
# ceiling, and only the proxy's JSON lines.

ALLOY_CONFIG = os.path.join(PROJECT_DIR, "monitoring", "config.alloy")


def alloy():
    return compose_aws()["services"]["alloy"]


def alloy_config():
    with open(ALLOY_CONFIG) as config:
        return "\n".join(line.split("//", 1)[0] if not line.lstrip().startswith("//")
                         else "" for line in config)


def test_the_agent_runs_on_the_server_only_and_pinned():
    assert "alloy" not in compose()["services"]
    assert PINNED_IMAGE.match(alloy()["image"])
    assert alloy()["image"].startswith("grafana/alloy:")


def test_the_agent_is_not_root_and_cannot_gain_anything():
    agent = alloy()

    assert agent["user"] == "473:473"
    # The host's systemd-journal group, to read the journal, and no other.
    assert agent["group_add"] == ["999"]
    assert agent["read_only"] is True
    assert agent["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in agent["security_opt"]
    assert "privileged" not in agent
    assert "pid" not in agent and "network_mode" not in agent


def test_the_agent_has_no_socket_no_port_and_reads_the_host_read_only():
    agent = alloy()
    mounts = agent["volumes"]

    assert not any("docker.sock" in mount for mount in mounts)
    assert "ports" not in agent and "expose" not in agent
    for mount in mounts:
        source = mount.split(":", 1)[0]
        if source == "alloy-data":
            continue
        assert mount.split(":")[-1].split(",")[0] == "ro", mount
    assert "./monitoring/config.alloy:/etc/alloy/config.alloy:ro" in mounts
    assert "alloy-data" in compose_aws()["volumes"]


def test_the_agent_has_a_memory_ceiling_below_the_server_and_tells_grafana_nothing():
    agent = alloy()
    limit = agent["mem_limit"]

    assert re.fullmatch(r"\d+m", limit) and int(limit[:-1]) <= 256
    assert "--disable-reporting" in agent["command"]
    assert "--server.http.enable-pprof=false" in agent["command"]
    # Every setting comes from .env, which deploy.sh writes, and is required.
    for name in ("GRAFANA_METRICS_URL", "GRAFANA_METRICS_USER",
                 "GRAFANA_LOGS_URL", "GRAFANA_LOGS_USER", "GRAFANA_TOKEN"):
        assert agent["environment"][name].startswith("${" + name + ":?"), name


def test_on_the_server_nginx_logs_to_the_journal_and_on_the_mac_it_does_not():
    assert compose_aws()["services"]["proxy"]["logging"] == {"driver": "journald"}
    assert "logging" not in compose()["services"]["proxy"]


def test_the_agent_reads_only_the_proxys_json_lines_and_never_docker():
    config = alloy_config()

    assert re.findall(r'loki\.source\.\w+', config) == ["loki.source.journal"]
    assert 'matches    = "CONTAINER_NAME=psells-proxy-1"' in config
    # Startup messages and the error log, which names addresses, are dropped.
    assert re.search(r'stage\.drop \{\s*expression = "\^\[\^\{\]"', config)
    assert "docker" not in config.replace("var/lib/docker", "")
    assert "sys.env(\"GRAFANA_TOKEN\")" in config


# The app's health check asks the database ---------------------------------------
#
# Found by Phase 10's deliberate failure: with the database stopped, the app
# said healthy while every page failed. These run the health check's own
# command, with its socket part stood in, since nothing listens on port 8000
# here.

def app_health_command():
    test = compose()["services"]["app"]["healthcheck"]["test"]
    assert test[:3] == ["CMD", "python", "-c"]
    return test[3]


def run_health_check(database_url):
    stand_in_socket = (
        "import socket\n"
        "class Answered:\n"
        "    def close(self): pass\n"
        "socket.create_connection = lambda *args, **kwargs: Answered()\n")
    environment = dict(os.environ, PSELLS_DATABASE_URL=database_url)
    return subprocess.run(
        [sys.executable, "-c", stand_in_socket + app_health_command()],
        cwd=PROJECT_DIR, env=environment, capture_output=True, text=True,
        timeout=30)


def test_the_app_health_check_asks_uvicorn_and_the_database():
    command = app_health_command()

    assert "socket.create_connection(('127.0.0.1', 8000), 2)" in command
    assert "psells.connect()" in command and "SELECT 1" in command


def test_the_app_is_healthy_when_the_database_answers():
    assert run_health_check(TEST_DATABASE_URL).returncode == 0


def test_the_app_is_unhealthy_when_the_database_does_not():
    result = run_health_check(
        "postgresql://nobody:nothing@127.0.0.1:1/none?connect_timeout=2")

    assert result.returncode != 0
    assert "DatabaseUnavailable" in result.stderr
