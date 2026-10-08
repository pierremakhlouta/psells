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


def test_the_real_stack_never_reads_an_analytics_variable():
    # Compose reads every variable in a file it is given, even for a service
    # it is not starting; one required here would stop the real stack.
    text = read(COMPOSE)
    assert "PSELLS_WAREHOUSE" not in text and "PSELLS_ETL" not in text
    assert "warehouse" not in compose_file(COMPOSE)["services"]


def test_the_env_example_names_both_analytics_passwords_with_placeholders():
    example = read(os.path.join(psells.PROJECT_DIR, ".env.example"))

    assert "PSELLS_WAREHOUSE_PASSWORD=change-me\n" in example
    assert "PSELLS_ETL_PASSWORD=change-me\n" in example
