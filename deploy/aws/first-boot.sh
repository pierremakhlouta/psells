#!/bin/bash
#
# What a new PSells server does the first time it starts, as root, from
# cloud-init. infra/aws/server.tf gives it to the server as user data, so a
# server rebuilt from Terraform sets itself up with nobody logged in. What it
# printed is in /var/log/cloud-init-output.log on the server.
#
# Prepares the host (swap, Docker from Docker's own repository, the AWS
# CLI), clones the public repository at the head of main into /opt/psells,
# and runs deploy/aws/deploy.sh, which fetches the settings, gets a
# certificate, starts the stack with the invented sample data and installs
# the timers. Setting the demonstration's password is left to a person,
# through Session Manager, since it is typed and never stored.
#
# PSELLS_ACME_STAGING, set in the user data, is passed on to deploy.sh.
#
# Safe to run twice: each step checks whether it is already done.

set -euo pipefail

REPOSITORY=https://github.com/pierremakhlouta/psells.git
PROJECT_DIR=/opt/psells

echo "== swap: 2 GiB, used only under pressure, for the 1 GiB server"
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
fi
swapon --show | grep -q /swapfile || swapon /swapfile
grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
echo 'vm.swappiness=10' > /etc/sysctl.d/90-psells-swap.conf
sysctl -p /etc/sysctl.d/90-psells-swap.conf

echo "== docker, from Docker's apt repository"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
# The release's codename, from the file only the server has.
# shellcheck source=/dev/null
codename=$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $codename
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update -q
apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

echo "== aws cli, AWS's own snap, which deploy.sh and the backup use"
snap list aws-cli > /dev/null 2>&1 || snap install aws-cli --classic
export PATH="$PATH:/snap/bin"

echo "== the repository"
[ -d "$PROJECT_DIR/.git" ] || git clone --quiet "$REPOSITORY" "$PROJECT_DIR"
git -C "$PROJECT_DIR" log --oneline -1

echo "== deploy"
"$PROJECT_DIR/deploy/aws/deploy.sh"
