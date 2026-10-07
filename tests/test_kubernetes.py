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


# The app and nginx -----------------------------------------------------------------

def app_pod():
    return one("Deployment", "psells")["spec"]["template"]["spec"]


def container(name):
    (found,) = [c for c in app_pod()["containers"] if c["name"] == name]
    return found


def compose_service(name):
    with open(COMPOSE) as file:
        return yaml.safe_load(file)["services"][name]


def test_the_pod_runs_the_app_and_nginx_ci_published_for_one_commit():
    app_image = container("app")["image"]
    nginx_image = container("nginx")["image"]
    published = re.compile(
        r"^ghcr\.io/pierremakhlouta/psells:(nginx-)?([0-9a-f]{40})"
        r"@sha256:[0-9a-f]{64}$")

    app_match = published.match(app_image)
    nginx_match = published.match(nginx_image)
    assert app_match and not app_match.group(1), app_image
    assert nginx_match and nginx_match.group(1) == "nginx-", nginx_image
    assert app_match.group(2) == nginx_match.group(2)
    assert [c["name"] for c in app_pod()["containers"]] == ["app", "nginx"]


def test_only_nginx_can_reach_the_app_and_the_app_believes_only_nginx():
    app = container("app")
    env = {item["name"]: item for item in app["env"]}

    # uvicorn on the pod's loopback, not 0.0.0.0, so no other pod reaches it.
    assert app["command"] == ["uvicorn", "api:app", "--host", "127.0.0.1",
                              "--port", "8000"]
    assert env["FORWARDED_ALLOW_IPS"]["value"] == "127.0.0.1"
    assert "ports" not in app
    # nginx's one snippet passes to http://app:8000; here app is the loopback.
    assert "proxy_pass http://app:8000;" in read(
        os.path.join(psells.PROJECT_DIR, "nginx", "snippets", "app.conf"))
    assert app_pod()["hostAliases"] == [{"ip": "127.0.0.1",
                                          "hostnames": ["app"]}]


def test_https_reaches_nginx_on_the_port_kind_maps_and_nothing_else_is_exposed():
    service = one("Service", "psells")
    (node,) = load("kind.yaml")["nodes"]
    (mapping,) = node["extraPortMappings"]
    (port,) = service["spec"]["ports"]
    (nginx_port,) = container("nginx")["ports"]

    assert service["spec"]["type"] == "NodePort"
    assert port["nodePort"] == mapping["containerPort"] == 30443
    assert port["targetPort"] == nginx_port["name"] == "https"
    assert nginx_port["containerPort"] == 8443
    assert "listen 8443 ssl;" in read(
        os.path.join(psells.PROJECT_DIR, "nginx", "nginx.conf"))
    assert service["spec"]["selector"] == (
        one("Deployment", "psells")["spec"]["selector"]["matchLabels"])


def configmap(prefix):
    (found,) = [d for d in rendered() if d["kind"] == "ConfigMap"
                and d["metadata"]["name"].startswith(prefix + "-")]
    return found


def test_nginx_and_the_app_are_configured_from_the_repository_files_and_sample_config():
    nginx_dir = os.path.join(psells.PROJECT_DIR, "nginx")

    assert configmap("nginx-conf")["data"] == {
        "nginx.conf": read(os.path.join(nginx_dir, "nginx.conf"))}
    assert configmap("nginx-snippets")["data"] == {
        name: read(os.path.join(nginx_dir, "snippets", name))
        for name in os.listdir(os.path.join(nginx_dir, "snippets"))}
    assert configmap("nginx-site")["data"] == {
        name: read(os.path.join(nginx_dir, "sites", "localhost", name))
        for name in os.listdir(os.path.join(nginx_dir, "sites", "localhost"))}
    # The invented partner share, never data/config.json.
    assert configmap("app-config")["data"] == {
        "config.json": read(os.path.join(psells.PROJECT_DIR, "sample_data",
                                         "config.json"))}
    assert not re.search(r"(?<![\w])data/",
                         read(os.path.join(K8S_DIR, "kustomization.yaml")))


def test_nginx_mounts_its_files_where_compose_does():
    targets = {volume.split(":")[1]
               for volume in compose_service("proxy")["volumes"]}
    mounts = {m["mountPath"]: m for m in container("nginx")["volumeMounts"]}

    assert targets == set(mounts) - {"/tmp"}
    for path in targets:
        assert mounts[path]["readOnly"] is True, path


def test_both_containers_are_unprivileged_and_read_only():
    pod = app_pod()

    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}
    assert pod["automountServiceAccountToken"] is False
    assert pod["enableServiceLinks"] is False
    users = {}
    for item in pod["containers"]:
        context = item["securityContext"]
        users[item["name"]] = (context["runAsUser"], context["runAsGroup"])
        assert context["allowPrivilegeEscalation"] is False
        assert context["readOnlyRootFilesystem"] is True
        assert context["capabilities"] == {"drop": ["ALL"]}
        assert item["resources"]["limits"]["memory"]
        assert item["readinessProbe"] and item["livenessProbe"]
    # The Dockerfile's psells user, and the nginx user compose.yaml runs.
    assert users == {"app": (10001, 10001), "nginx": (101, 101)}
    assert compose_service("proxy")["user"] == "101:101"
    assert "useradd --create-home --uid 10001 psells" in read(
        os.path.join(psells.PROJECT_DIR, "Dockerfile"))


def test_the_app_probes_ask_uvicorn_and_not_the_database():
    # With the database down the app answers 503; a probe that asked the
    # database would take the pod out of the Service, or restart it, instead.
    app = container("app")
    for probe in ("readinessProbe", "livenessProbe"):
        command = " ".join(app[probe]["exec"]["command"])
        assert "('127.0.0.1', 8000)" in command
        assert "psells" not in command and "SELECT" not in command


def test_the_app_has_the_database_password_from_the_secret_alone():
    env = {item["name"]: item for item in container("app")["env"]}

    assert env["PSELLS_DATABASE_URL"]["value"] == (
        "postgresql://psells@db:5432/psells")
    assert env["PGPASSWORD"]["valueFrom"] == {
        "secretKeyRef": {"name": "psells-db", "key": "password"}}
    assert "nginx" not in {item["name"] for item in app_pod()["containers"]
                           if "env" in item}


def test_the_certificate_key_is_mounted_in_nginx_alone_and_readable_by_its_group():
    volumes = {v["name"]: v for v in app_pod()["volumes"]}
    tls = volumes["tls"]["secret"]

    assert tls["secretName"] == "psells-tls"
    assert tls["defaultMode"] == 0o440
    assert app_pod()["securityContext"]["fsGroup"] == 101
    assert {item["path"] for item in tls["items"]} == {
        "psells.localhost.crt", "psells.localhost.key"}
    https_conf = read(os.path.join(psells.PROJECT_DIR, "nginx", "sites",
                                   "localhost", "https.conf"))
    for item in tls["items"]:
        assert f"/etc/nginx/tls/{item['path']};" in https_conf
    assert "tls" not in {m["name"] for m in container("app")["volumeMounts"]}


def test_up_sh_loads_the_clusters_own_certificate_from_outside_the_repository():
    text = read(UP)

    assert 'TLS_DIR="${PSELLS_KIND_TLS_DIR:-$HOME/PSells-Kind/tls}"' in text
    assert "create secret tls psells-tls" in text
    assert "--dry-run=client" in text
    # Refuses to go on without it, before anything is applied.
    assert text.index("exit 1") < text.index("== manifests")
    assert "data/tls" not in text and "PSells-CA" not in text


def test_up_sh_waits_for_psells_to_be_rolled_out():
    assert "rollout status deployment/psells" in read(UP)
