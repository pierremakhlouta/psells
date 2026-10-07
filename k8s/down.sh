#!/bin/bash
#
# Removes PSells' local kind cluster, and with it everything k8s/up.sh made:
#
#     k8s/down.sh
#
# The cluster holds the invented sample records only, so nothing is lost that
# up.sh cannot make again; the database password is made afresh with the next
# cluster. Deletes the one cluster named psells and nothing else: not the
# Compose stack, its containers or its volumes, and not the certificate in
# ~/PSells-Kind/tls, which up.sh loads again.

set -euo pipefail

CLUSTER=psells

if kind get clusters | grep -qx "$CLUSTER"; then
    kind delete cluster --name "$CLUSTER"
else
    echo "no cluster $CLUSTER to remove"
fi
