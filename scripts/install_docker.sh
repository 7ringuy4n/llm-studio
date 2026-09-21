#!/usr/bin/env bash

# Install Docker CE and Compose v2 without changing daemon settings or any
# existing container, network, volume, firewall rule, or Hermes resource.
set -Eeuo pipefail

die() {
  printf '[llm-studio] ERROR: %s\n' "$*" >&2
  exit 1
}

if [[ "$(id -u)" -ne 0 ]]; then
  die "run with sudo: sudo $0 [login-user]"
fi

target_user="${1:-${SUDO_USER:-}}"
if [[ -z "${target_user}" || "${target_user}" == root ]]; then
  target_user="$(logname 2>/dev/null || true)"
fi
[[ -n "${target_user}" && "${target_user}" != root ]] \
  || die 'cannot determine the non-root login user; pass it as the first argument'
id "${target_user}" >/dev/null 2>&1 || die "user does not exist: ${target_user}"

export DEBIAN_FRONTEND=noninteractive
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  printf '[llm-studio] Docker and Compose already work; leaving them unchanged.\n'
  apt-get update
  apt-get install --yes rsync
else
  [[ -r /etc/os-release ]] || die '/etc/os-release is unavailable'
  # shellcheck disable=SC1091
  source /etc/os-release
  [[ "${ID:-}" == ubuntu || "${ID:-}" == debian ]] \
    || die "supported bootstrap systems are Ubuntu and Debian; found ${ID:-unknown}"
  codename="${VERSION_CODENAME:-}"
  [[ -n "${codename}" ]] || die 'VERSION_CODENAME is missing from /etc/os-release'

  apt-get update
  apt-get install --yes ca-certificates curl gnupg git make rsync
  install -m 0755 -d /etc/apt/keyrings
  curl --fail --silent --show-error --location \
    "https://download.docker.com/linux/${ID}/gpg" \
    --output /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/%s %s stable\n' \
    "$(dpkg --print-architecture)" "${ID}" "${codename}" \
    >/etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install --yes docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
fi

groupadd docker 2>/dev/null || true
usermod -aG docker "${target_user}"
docker --version
docker compose version
printf '[llm-studio] Docker is ready. Reconnect the %s login session before using Docker without sudo.\n' "${target_user}"
