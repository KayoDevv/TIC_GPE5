#!/usr/bin/env bash
# Copies the sandbox detonation images onto the k3s node, at the versions of their
# Dockerfile `ghcr-image:` headers. The analysis Jobs run imagePullPolicy: Never
# without a pull secret (KEP-2535 makes `ctr import` the only way they can use a
# private image), so an image missing from containerd fails every detonation with
# ErrImageNeverPull and every verdict degrades to a sandbox timeout.
#
# Usage: import-sandbox-agents.sh <user@host> [--missing-only]
#   --missing-only  skip images already in containerd (deploys); default re-imports.
# Needs: SSH_OPTS, a docker login to ghcr.io, passwordless `sudo k3s` on the node.
set -euo pipefail

target=${1:?usage: import-sandbox-agents.sh <user@host> [--missing-only]}
mode=${2:-}
agent_dir=apps/workers/sandbox_layer

remote() {
  # shellcheck disable=SC2086  # SSH_OPTS is a list of options
  ssh $SSH_OPTS "$target" "$@"
}

image_of() {
  local ref
  ref=$(sed -n 's|^#[[:space:]]*ghcr-image:[[:space:]]*\([^[:space:]]*\).*|\1|p' "$1" | head -1)
  [ -n "$ref" ] && [ "$ref" != "${ref##*:}" ] || return 1
  printf 'ghcr.io/kayodevv/%s' "$ref"
}

remote 'sudo -n k3s ctr images ls >/dev/null 2>&1' || {
  echo "::error::The SSH user lacks passwordless sudo for 'k3s ctr'. Run 'make import-agents-ghcr' on the node, or grant NOPASSWD for k3s."
  exit 1
}

for dockerfile in Dockerfile.agent Dockerfile.pdf-agent; do
  img=$(image_of "$agent_dir/$dockerfile") \
    || { echo "::error::no 'ghcr-image' header on $dockerfile"; exit 1; }

  if [ "$mode" = "--missing-only" ] \
    && remote "sudo -n k3s ctr images ls -q | grep -Fxq '$img'"; then
    echo "present: $img"
    continue
  fi

  docker pull "$img"
  # Drop the CRI record first, or KEP-2535 forces a re-auth pull.
  remote "sudo -n k3s crictl rmi '$img' >/dev/null 2>&1 || true"
  docker save "$img" | remote 'sudo -n k3s ctr images import -'
  remote "sudo -n k3s ctr images ls -q | grep -Fxq '$img'" \
    || { echo "::error::$img absent from containerd after import"; exit 1; }
  echo "imported: $img"
done
