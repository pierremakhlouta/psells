#!/bin/bash
#
# Sets up PSells on a local kind cluster, with the invented sample records only,
# and brings it up to date when run again:
#
#     k8s/up.sh
#
# Creates the cluster from k8s/kind.yaml if it does not exist, makes the
# secrets it needs if they do not exist, and applies k8s/ through kustomize.
# Safe to run again: an existing cluster and existing secrets are kept, so the
# database keeps the password it was created with. k8s/down.sh removes it all.
#
# Never touches the Compose stack or its data: the cluster has its own
# database, built from schema.sql and sample_data/seed.sql.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLUSTER=psells
CONTEXT="kind-$CLUSTER"
NAMESPACE=psells

kube() {
    kubectl --context "$CONTEXT" --namespace "$NAMESPACE" "$@"
}

echo "== cluster"
if kind get clusters | grep -qx "$CLUSTER"; then
    echo "kept the existing cluster $CLUSTER"
else
    kind create cluster --config "$PROJECT_DIR/k8s/kind.yaml" --wait 120s
fi

echo "== namespace and secrets"
kubectl --context "$CONTEXT" apply -f "$PROJECT_DIR/k8s/namespace.yaml"

# The database's password: made once, random, and never printed or written to
# a file; it reaches kubectl on its standard input. Kept if it exists, because
# the database on its volume was created with it.
if kube get secret psells-db > /dev/null 2>&1; then
    echo "kept the database password"
else
    openssl rand -hex 24 | tr -d '\n' |
        kube create secret generic psells-db --from-file=password=/dev/stdin
fi

echo "== manifests"
# Server-side apply: the cluster itself works out what changed. It prints
# "serverside-applied" for every object, changed or not; a StatefulSet's
# generation is what shows whether its spec moved. The older client-side
# apply reported the database "configured" on every run though it had not
# changed, and objects it made cannot then be taken over without a conflict,
# so a cluster made before this line is rebuilt with k8s/down.sh.
kubectl kustomize --load-restrictor LoadRestrictionsNone "$PROJECT_DIR/k8s" |
    kubectl --context "$CONTEXT" apply --server-side --field-manager=psells-up -f -

echo "== waiting for the database"
kube rollout status statefulset/database --timeout=180s
