"""Tests for analytics/ and compose.analytics.yaml: the read-only role the ETL
reads the business database as, and the warehouse it writes to.

The role's tests run analytics/etl_role.sql in the test database, as
create-etl-role.sh does in the stack, give the role an invented password, then
connect as psells_etl and try everything it must not be able to do.
"""

import os
import subprocess

import psycopg
import pytest
import yaml
from psycopg import errors, sql
from psycopg.conninfo import make_conninfo

import psells
from helpers import TEST_DATABASE_URL


ANALYTICS_DIR = os.path.join(psells.PROJECT_DIR, "analytics")
ROLE_SQL = os.path.join(ANALYTICS_DIR, "etl_role.sql")
ROLE_SCRIPT = os.path.join(ANALYTICS_DIR, "create-etl-role.sh")
COMPOSE = os.path.join(psells.PROJECT_DIR, "compose.yaml")
COMPOSE_ANALYTICS = os.path.join(psells.PROJECT_DIR, "compose.analytics.yaml")

# What the ETL reads, through psells' own functions, and nothing more.
READABLE = {"products", "sales", "returns", "payments", "products_view"}
# Invented, for the test database only.
INVENTED_PASSWORD = "invented-etl-password-for-the-tests"


def read(path):
    with open(path) as file:
        return file.read()


@pytest.fixture
def etl():
    """A connection to the test database as psells_etl, after etl_role.sql
    has run there as its owner."""
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as owner:
        owner.execute(read(ROLE_SQL))
        owner.execute(sql.SQL("ALTER ROLE psells_etl LOGIN PASSWORD {}").format(
            sql.Literal(INVENTED_PASSWORD)))
    url = make_conninfo(TEST_DATABASE_URL, user="psells_etl",
                        password=INVENTED_PASSWORD)
    with psycopg.connect(url, autocommit=True,
                         row_factory=psycopg.rows.dict_row) as connection:
        yield connection


def count(connection, name):
    return connection.execute(
        sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier(name))
    ).fetchone()["n"]


# The role ----------------------------------------------------------------------

def test_the_etl_role_reads_the_business_tables_and_the_products_view(etl):
    for name in READABLE:
        assert count(etl, name) >= 0


def test_the_etl_role_cannot_read_the_login_or_the_corrections_log(etl):
    for name in ("users", "sessions", "corrections"):
        with pytest.raises(errors.InsufficientPrivilege):
            count(etl, name)


def test_the_etl_role_has_exactly_its_grants_however_often_it_is_run(etl):
    # Run again on top, with an extra grant to be taken away.
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as owner:
        owner.execute("GRANT SELECT ON users TO psells_etl")
        owner.execute(read(ROLE_SQL))
        grants = owner.execute(
            "SELECT table_name, privilege_type FROM "
            "information_schema.role_table_grants WHERE grantee = 'psells_etl'"
        ).fetchall()

    assert set(grants) == {(name, "SELECT") for name in READABLE}


def test_every_transaction_of_the_etl_role_is_read_only(etl):
    with pytest.raises(errors.ReadOnlySqlTransaction):
        etl.execute("INSERT INTO payments (date, amount_cents) "
                    "VALUES ('2026-01-01', 100)")


def test_the_grants_alone_stop_a_write_even_with_read_only_switched_off(etl):
    # The read-only default is the client's to switch off; the grants are not.
    etl.execute("SET default_transaction_read_only = off")
    for statement in (
            "INSERT INTO payments (date, amount_cents) VALUES ('2026-01-01', 100)",
            "UPDATE sales SET quantity = 1",
            "DELETE FROM products",
            "TRUNCATE returns",
            "CREATE TABLE stolen (x int)"):
        with pytest.raises(errors.InsufficientPrivilege):
            etl.execute(statement)


def test_psells_own_readers_work_as_the_etl_role(etl):
    # The ETL calls these; each must run with the role's grants and no more.
    assert psells.all_products(etl) == []
    assert psells.sales_history(etl) == []
    assert psells.returns_history(etl) == []
    assert psells.payments_history(etl) == []
    assert psells.dashboard_totals(etl)["total_revenue"] == 0


def test_the_role_file_holds_no_password_and_the_script_keeps_it_off_the_command_line():
    role = read(ROLE_SQL)
    script = read(ROLE_SCRIPT)

    assert "PASSWORD" not in role.upper().replace("NO PASSWORD", "")
    assert "\\getenv etl_password PSELLS_ETL_PASSWORD" in script
    assert "ALTER ROLE psells_etl LOGIN PASSWORD :'etl_password';" in script
    assert "exec -T -e PSELLS_ETL_PASSWORD db" in script
    assert "ON_ERROR_STOP=1" in script
    assert os.access(ROLE_SCRIPT, os.X_OK)


def test_the_script_refuses_without_a_password_and_reaches_no_docker(tmp_path):
    project = tmp_path / "psells"
    (project / "analytics").mkdir(parents=True)
    for name in ("etl_role.sql", "create-etl-role.sh"):
        (project / "analytics" / name).write_text(
            read(os.path.join(ANALYTICS_DIR, name)))
    (project / ".env").write_text("POSTGRES_USER=psells\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    docker = bin_dir / "docker"
    docker.write_text(f'#!/bin/sh\necho "$*" >> "{calls}"\n')
    docker.chmod(0o755)

    result = subprocess.run(
        ["bash", str(project / "analytics" / "create-etl-role.sh")],
        capture_output=True, text=True,
        env=dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}"))

    assert result.returncode == 1
    assert "No PSELLS_ETL_PASSWORD in .env" in result.stderr
    assert not calls.exists()


def test_the_script_passes_the_password_by_environment_never_on_a_command_line(tmp_path):
    project = tmp_path / "psells"
    (project / "analytics").mkdir(parents=True)
    for name in ("etl_role.sql", "create-etl-role.sh"):
        (project / "analytics" / name).write_text(
            read(os.path.join(ANALYTICS_DIR, name)))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    seen = tmp_path / "seen"
    docker = bin_dir / "docker"
    # Records its arguments, the password it was handed, and its input.
    docker.write_text(
        f'#!/bin/sh\necho "$*" >> "{calls}"\n'
        f'echo "$PSELLS_ETL_PASSWORD" > "{seen}"\ncat >> "{calls}"\n')
    docker.chmod(0o755)

    result = subprocess.run(
        ["bash", str(project / "analytics" / "create-etl-role.sh")],
        capture_output=True, text=True,
        env=dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}",
                 PSELLS_ETL_PASSWORD=INVENTED_PASSWORD))

    assert result.returncode == 0, result.stderr
    recorded = calls.read_text()
    assert seen.read_text().strip() == INVENTED_PASSWORD
    assert INVENTED_PASSWORD not in recorded
    assert INVENTED_PASSWORD not in result.stdout + result.stderr
    assert recorded.startswith(
        f"compose --project-directory {project} exec -T -e PSELLS_ETL_PASSWORD db ")
    assert read(ROLE_SQL) in recorded


# The warehouse -----------------------------------------------------------------

def compose_file(path):
    with open(path) as file:
        return yaml.safe_load(file)


def test_the_warehouse_is_its_own_postgres_on_the_same_pinned_image():
    warehouse = compose_file(COMPOSE_ANALYTICS)["services"]["warehouse"]
    db = compose_file(COMPOSE)["services"]["db"]

    assert warehouse["image"] == db["image"]
    assert warehouse["volumes"] == ["warehouse:/var/lib/postgresql"]
    assert warehouse["environment"]["POSTGRES_USER"] != db["environment"]["POSTGRES_USER"]
    assert warehouse["environment"]["POSTGRES_DB"] == "psells_warehouse"
    assert warehouse["environment"]["POSTGRES_PASSWORD"].startswith(
        "${PSELLS_WAREHOUSE_PASSWORD:?")
    assert "ports" not in warehouse
    assert "pg_isready -h 127.0.0.1 " in " ".join(warehouse["healthcheck"]["test"])


def test_the_real_stack_requires_no_analytics_variable():
    # Compose reads every variable in a file it is given, even for a service
    # it is not starting; one required here would stop the real stack, its
    # login job, its backup and the demo's deploy.
    import re

    text = read(COMPOSE)
    used = set(re.findall(r"\$\{(PSELLS_(?:WAREHOUSE|ETL|READER)\w*)(:?[-?])", text))
    # The app's warehouse address is the one, and it is optional.
    assert used == {("PSELLS_WAREHOUSE_URL", ":-")}
    assert compose_file(COMPOSE)["services"]["app"]["environment"][
        "PSELLS_WAREHOUSE_URL"] == "${PSELLS_WAREHOUSE_URL:-}"
    assert "warehouse" not in compose_file(COMPOSE)["services"]


def test_the_env_example_names_both_analytics_passwords_with_placeholders():
    example = read(os.path.join(psells.PROJECT_DIR, ".env.example"))

    assert "PSELLS_WAREHOUSE_PASSWORD=change-me\n" in example
    assert "PSELLS_ETL_PASSWORD=change-me\n" in example
    assert "PSELLS_READER_PASSWORD=change-me\n" in example


# The analytics image -----------------------------------------------------------

def dockerfile_lines(path):
    """The instructions of a Dockerfile, continuation lines joined."""
    text = read(path).replace("\\\n", " ")
    return [" ".join(line.split()) for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


ANALYTICS_DOCKERFILE = os.path.join(ANALYTICS_DIR, "Dockerfile")
APP_DOCKERFILE = os.path.join(psells.PROJECT_DIR, "Dockerfile")


def test_the_analytics_image_starts_from_the_apps_pinned_base_with_its_fixes():
    analytics = dockerfile_lines(ANALYTICS_DOCKERFILE)
    app = dockerfile_lines(APP_DOCKERFILE)

    assert [l for l in analytics if l.startswith("FROM ")] == [
        l for l in app if l.startswith("FROM ")]
    assert [l for l in analytics if l.startswith("RUN apt-get")] == [
        l for l in app if l.startswith("RUN apt-get")]


def test_the_analytics_image_copies_named_files_only_and_runs_as_its_own_user():
    lines = dockerfile_lines(ANALYTICS_DOCKERFILE)

    # Named files, never a folder, so nothing else can ride along.
    assert [l for l in lines if l.startswith("COPY ")] == [
        "COPY requirements-analytics.txt .",
        "COPY psells.py analytics/etl.py analytics/warehouse.sql analytics/views.sql ./"]
    assert lines[-1] == 'CMD ["python", "etl.py"]'
    assert "RUN useradd --create-home --uid 10002 analytics" in lines
    users = [l for l in lines if l.startswith("USER ")]
    assert users == ["USER analytics"]
    assert lines.index("USER analytics") > max(
        i for i, l in enumerate(lines) if l.startswith(("RUN ", "COPY ")))


def requirement_pins(path):
    return [line.split("#")[0].strip() for line in read(path).splitlines()
            if line.split("#")[0].strip()]


def test_the_analytics_requirements_are_exact_and_share_the_apps_driver():
    root = psells.PROJECT_DIR
    analytics = requirement_pins(os.path.join(root, "requirements-analytics.txt"))
    app = requirement_pins(os.path.join(root, "requirements.txt"))

    assert analytics and all("==" in pin for pin in analytics)
    assert [p for p in analytics if p.startswith("psycopg")] == [
        p for p in app if p.startswith("psycopg")]
    # Nothing of the web's.
    assert not {p.split("==")[0] for p in analytics} & {
        "fastapi", "uvicorn", "jinja2", "python-multipart", "argon2-cffi"}


def test_the_analytics_requirements_are_tested_audited_and_watched():
    root = psells.PROJECT_DIR
    workflows = os.path.join(root, ".github", "workflows")

    assert "-r requirements-analytics.txt" in requirement_pins(
        os.path.join(root, "requirements-dev.txt"))
    assert "--requirement requirements-analytics.txt" in read(
        os.path.join(workflows, "security.yml"))
    dependabot = yaml.safe_load(read(os.path.join(root, ".github", "dependabot.yml")))
    assert {"package-ecosystem": "docker", "directory": "/analytics"}.items() <= {
        **next(u for u in dependabot["updates"]
               if u.get("directory") == "/analytics")}.items()


def test_the_etl_reads_as_the_read_only_role_and_writes_nothing_of_its_own():
    etl_service = compose_file(COMPOSE_ANALYTICS)["services"]["etl"]
    environment = etl_service["environment"]

    assert environment["PSELLS_DATABASE_URL"].startswith(
        "postgresql://psells_etl:${PSELLS_ETL_PASSWORD:?")
    assert environment["PSELLS_DATABASE_URL"].endswith("@db:5432/${POSTGRES_DB:?set POSTGRES_DB in .env}")
    assert environment["PSELLS_WAREHOUSE_URL"].startswith(
        "postgresql://psells_warehouse:${PSELLS_WAREHOUSE_PASSWORD:?")
    assert environment["PSELLS_WAREHOUSE_URL"].endswith("@warehouse:5432/psells_warehouse")
    # Only when named, never with an "up".
    assert etl_service["profiles"] == ["etl"]
    assert etl_service["build"] == {"context": ".",
                                    "dockerfile": "analytics/Dockerfile"}
    assert etl_service["read_only"] is True
    assert etl_service["cap_drop"] == ["ALL"]
    assert etl_service["security_opt"] == ["no-new-privileges:true"]
    assert "ports" not in etl_service and "volumes" not in etl_service


# The warehouse's reader --------------------------------------------------------

READER_SQL = os.path.join(ANALYTICS_DIR, "reader_role.sql")
READER_SCRIPT = os.path.join(ANALYTICS_DIR, "create-reader-role.sh")
VIEWS_SQL = os.path.join(ANALYTICS_DIR, "views.sql")
WAREHOUSE_SQL = os.path.join(ANALYTICS_DIR, "warehouse.sql")
VIEWS = {"sales_by_month", "sales_by_week", "category_performance",
         "product_performance", "kpis"}
WAREHOUSE_TABLES = {"dim_product", "dim_date", "fact_sales", "fact_returns",
                    "fact_payments", "etl_run"}


def drop_warehouse(connection):
    """warehouse.sql's DROP statements alone."""
    drops = read(WAREHOUSE_SQL).split("CREATE TABLE")[0]
    connection.execute(drops)


@pytest.fixture
def reader():
    """A connection as psells_reader to a warehouse built and committed in
    the test database, which is dropped again afterwards. Committed, because
    the reader is another connection and cannot see an open transaction."""
    from analytics import etl
    from datetime import datetime, timezone

    owner = psycopg.connect(TEST_DATABASE_URL, autocommit=True,
                            row_factory=psycopg.rows.dict_row)
    owner.execute(read(READER_SQL))
    owner.execute(sql.SQL("ALTER ROLE psells_reader LOGIN PASSWORD {}").format(
        sql.Literal(INVENTED_PASSWORD)))
    data = etl.extract(owner)
    etl.load(owner, etl.transform(data), data["totals"],
             datetime(2026, 10, 8, tzinfo=timezone.utc))
    url = make_conninfo(TEST_DATABASE_URL, user="psells_reader",
                        password=INVENTED_PASSWORD)
    try:
        with psycopg.connect(url, autocommit=True,
                             row_factory=psycopg.rows.dict_row) as connection:
            yield connection, owner
    finally:
        drop_warehouse(owner)
        owner.close()


def test_the_reader_reads_every_view(reader):
    connection, _ = reader
    for name in VIEWS:
        assert count(connection, name) >= 0, name


def test_the_reader_reads_no_table_of_the_warehouse_or_the_business(reader):
    connection, _ = reader
    for name in WAREHOUSE_TABLES | {"products", "sales", "users", "sessions"}:
        with pytest.raises(errors.InsufficientPrivilege):
            count(connection, name)


def test_the_reader_cannot_write_even_with_read_only_switched_off(reader):
    connection, _ = reader
    # Read-only by default, so a write fails with a sentence saying why.
    with pytest.raises(errors.ReadOnlySqlTransaction):
        connection.execute("CREATE TABLE stolen (x int)")
    connection.execute("SET default_transaction_read_only = off")
    for statement in ("CREATE TABLE stolen (x int)",
                      "DELETE FROM fact_sales",
                      "CREATE VIEW stolen AS SELECT 1"):
        with pytest.raises(errors.InsufficientPrivilege):
            connection.execute(statement)


def test_the_reader_has_exactly_the_views_and_keeps_them_across_a_rebuild(reader):
    from analytics import etl
    from datetime import datetime, timezone

    connection, owner = reader
    # A grant added by hand is taken away by running the role file again,
    # straight away, not only when the next rebuild replaces the table.
    owner.execute("GRANT SELECT ON fact_sales TO psells_reader")
    owner.execute(read(READER_SQL))
    with pytest.raises(errors.InsufficientPrivilege):
        count(connection, "fact_sales")
    data = etl.extract(owner)
    etl.load(owner, etl.transform(data), data["totals"],
             datetime(2026, 10, 9, tzinfo=timezone.utc))
    grants = owner.execute(
        "SELECT table_name, privilege_type FROM "
        "information_schema.role_table_grants WHERE grantee = 'psells_reader'"
    ).fetchall()

    assert {(g["table_name"], g["privilege_type"]) for g in grants} == {
        (name, "SELECT") for name in VIEWS}
    (kpis,) = connection.execute("SELECT built_at FROM kpis").fetchall()
    assert kpis["built_at"].day == 9


def test_views_sql_grants_exactly_the_views_it_makes():
    import re

    text = read(VIEWS_SQL)
    made = set(re.findall(r"^CREATE VIEW (\w+)", text, re.M))
    granted = re.search(r"GRANT SELECT ON ([^;]+?) TO psells_reader;", text,
                        re.S).group(1)

    assert made == VIEWS
    assert {name.strip() for name in granted.split(",")} == made
    assert "IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'psells_reader')" in text


def test_the_reader_script_refuses_without_a_password_and_keeps_it_off_argv(tmp_path):
    project = tmp_path / "psells"
    (project / "analytics").mkdir(parents=True)
    for name in ("reader_role.sql", "create-reader-role.sh"):
        (project / "analytics" / name).write_text(
            read(os.path.join(ANALYTICS_DIR, name)))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    docker = bin_dir / "docker"
    docker.write_text(f'#!/bin/sh\necho "$*" >> "{calls}"\ncat >> "{calls}"\n')
    docker.chmod(0o755)
    environment = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
    environment.pop("PSELLS_READER_PASSWORD", None)

    refused = subprocess.run(
        ["bash", str(project / "analytics" / "create-reader-role.sh")],
        capture_output=True, text=True, env=environment)
    assert refused.returncode == 1 and not calls.exists()
    assert "No PSELLS_READER_PASSWORD in .env" in refused.stderr

    accepted = subprocess.run(
        ["bash", str(project / "analytics" / "create-reader-role.sh")],
        capture_output=True, text=True,
        env=dict(environment, PSELLS_READER_PASSWORD=INVENTED_PASSWORD))
    recorded = calls.read_text()
    assert accepted.returncode == 0, accepted.stderr
    assert INVENTED_PASSWORD not in recorded + accepted.stdout + accepted.stderr
    assert "exec -T -e PSELLS_READER_PASSWORD warehouse psql" in recorded
    assert "-f " + str(project / "compose.analytics.yaml") in recorded
    assert read(READER_SQL) in recorded
