"""Tests for k8s/, the local Kubernetes cluster that runs PSells' sample data.

Read as text and YAML, as the Compose and Terraform tests are, so they need no
cluster. CI also creates a real kind cluster from these files and requests the
login page through it; these hold the files to the rules that made them.
"""

import os
import re
import subprocess

import yaml

import psells


K8S_DIR = os.path.join(psells.PROJECT_DIR, "k8s")
PINNED = re.compile(r"^[\w./-]+:v?\d+\.\d+(\.\d+)?[\w.-]*@sha256:[0-9a-f]{64}$")


def load(name):
    with open(os.path.join(K8S_DIR, name)) as file:
        return yaml.safe_load(file)


# The cluster ---------------------------------------------------------------------

def test_the_cluster_is_one_node_on_a_pinned_kubernetes():
    cluster = load("kind.yaml")

    assert cluster["kind"] == "Cluster"
    assert cluster["name"] == "psells"
    (node,) = cluster["nodes"]
    assert node["role"] == "control-plane"
    assert PINNED.match(node["image"]), node["image"]
    assert node["image"].startswith("kindest/node:")


def test_the_cluster_is_reached_on_this_machine_only_and_never_on_443():
    (node,) = load("kind.yaml")["nodes"]
    mappings = node["extraPortMappings"]

    assert mappings == [{"containerPort": 30443, "hostPort": 9443,
                         "listenAddress": "127.0.0.1", "protocol": "TCP"}]
    # The real stack holds 443 and 80 on the Mac.
    assert not {m["hostPort"] for m in mappings} & {443, 80}


# The manifests, as kustomize renders them for the cluster -------------------------

COMPOSE = os.path.join(psells.PROJECT_DIR, "compose.yaml")
UP = os.path.join(K8S_DIR, "up.sh")


def rendered():
    """What k8s/up.sh sends the cluster: kustomize's output, as documents."""
    result = subprocess.run(
        ["kubectl", "kustomize", "--load-restrictor", "LoadRestrictionsNone",
         K8S_DIR], capture_output=True, text=True, check=True)
    return list(yaml.safe_load_all(result.stdout))


def one(kind, name=None):
    (found,) = [d for d in rendered() if d["kind"] == kind
                and (name is None or d["metadata"]["name"] == name)]
    return found


def read(path):
    with open(path) as file:
        return file.read()


def test_everything_is_in_the_psells_namespace():
    for document in rendered():
        if document["kind"] == "Namespace":
            assert document["metadata"]["name"] == "psells"
        else:
            assert document["metadata"]["namespace"] == "psells", document["kind"]


def test_the_database_is_built_from_schema_sql_then_the_sample_records():
    (init,) = [d for d in rendered() if d["kind"] == "ConfigMap"
               and d["metadata"]["name"].startswith("database-init-")]

    # The files as they are in the repository, not copies of them.
    assert init["data"] == {
        "01-schema.sql": read(os.path.join(psells.PROJECT_DIR, "schema.sql")),
        "02-seed.sql": read(os.path.join(psells.PROJECT_DIR, "sample_data",
                                         "seed.sql")),
    }


def database_pod():
    return one("StatefulSet", "database")["spec"]["template"]["spec"]


def test_the_cluster_runs_the_same_pinned_postgres_as_compose():
    (container,) = database_pod()["containers"]
    with open(COMPOSE) as file:
        compose_image = yaml.safe_load(file)["services"]["db"]["image"]

    assert container["image"] == compose_image
    assert PINNED.match(container["image"])


def test_the_database_is_not_root_and_can_gain_nothing():
    pod = database_pod()
    (container,) = pod["containers"]

    assert pod["securityContext"]["runAsUser"] == 999
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}
    assert pod["automountServiceAccountToken"] is False
    assert container["securityContext"] == {
        "allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]}}
    assert container["resources"]["limits"]["memory"]


def test_the_password_comes_from_the_secret_and_is_written_nowhere():
    (container,) = database_pod()["containers"]
    env = {item["name"]: item for item in container["env"]}

    assert env["POSTGRES_PASSWORD"] == {
        "name": "POSTGRES_PASSWORD",
        "valueFrom": {"secretKeyRef": {"name": "psells-db", "key": "password"}}}
    assert not [d for d in rendered() if d["kind"] == "Secret"]


def test_the_database_keeps_its_own_volume_and_is_checked_by_pg_isready():
    statefulset = one("StatefulSet", "database")
    (container,) = statefulset["spec"]["template"]["spec"]["containers"]
    mounts = {m["mountPath"]: m for m in container["volumeMounts"]}

    assert statefulset["spec"]["replicas"] == 1
    (claim,) = statefulset["spec"]["volumeClaimTemplates"]
    assert mounts["/var/lib/postgresql"]["name"] == claim["metadata"]["name"]
    assert mounts["/docker-entrypoint-initdb.d"]["readOnly"] is True
    for probe in ("readinessProbe", "livenessProbe"):
        assert "pg_isready" in " ".join(container[probe]["exec"]["command"])


def test_the_app_reaches_the_database_by_the_name_it_has_in_compose():
    service = one("Service", "db")

    assert service["spec"]["clusterIP"] == "None"
    assert service["spec"]["ports"] == [
        {"name": "postgres", "port": 5432, "targetPort": "postgres"}]


# The setup script ------------------------------------------------------------------

def test_up_sh_only_ever_talks_to_the_psells_cluster():
    # A kubectl without --context acts on whatever cluster is current, which
    # could one day be a real one.
    text = read(UP)
    calls = [line for line in text.splitlines()
             if re.search(r"\bkubectl\b", line) and not line.lstrip().startswith("#")]

    assert calls
    for call in calls:
        assert ('--context "$CONTEXT"' in call
                or call.strip().startswith("kubectl kustomize")), call
    assert "CONTEXT=\"kind-$CLUSTER\"" in text and "CLUSTER=psells" in text


def test_up_sh_makes_the_password_once_and_never_prints_or_stores_it():
    text = read(UP)

    assert "openssl rand -hex 24" in text
    assert "--from-file=password=/dev/stdin" in text
    assert "--from-literal" not in text
    # Kept if it exists: the database on its volume was made with it.
    assert text.index("get secret psells-db") < text.index("openssl rand")


def test_up_sh_applies_the_rendered_manifests_server_side():
    text = read(UP)

    assert ("kubectl kustomize --load-restrictor LoadRestrictionsNone"
            in text)
    assert "apply --server-side" in text
