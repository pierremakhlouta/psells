"""Tests for k8s/, the local Kubernetes cluster that runs PSells' sample data.

Read as text and YAML, as the Compose and Terraform tests are, so they need no
cluster. CI also creates a real kind cluster from these files and requests the
login page through it; these hold the files to the rules that made them.
"""

import os
import re

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
