#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
readonly REPORT_PATH="${1:-${PROJECT_ROOT}/docs/environment.md}"

mkdir -p -- "$(dirname -- "${REPORT_PATH}")"

capture() {
  local title="$1"
  shift
  {
    printf '\n## %s\n\n```text\n' "${title}"
    "$@" 2>&1 || true
    printf '```\n'
  } >>"${REPORT_PATH}"
}

capture_shell() {
  local title="$1"
  local command="$2"
  {
    printf '\n## %s\n\n```text\n' "${title}"
    bash -o pipefail -c "${command}" 2>&1 || true
    printf '```\n'
  } >>"${REPORT_PATH}"
}

umask 027
{
  printf '# LLM Studio Environment Inspection\n\n'
  printf -- '- Generated (UTC): `%s`\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  printf -- '- Host: `%s`\n' "$(hostname 2>/dev/null || printf unknown)"
  printf -- '- Purpose: read-only preflight before any LLM Studio changes.\n'
  printf -- '- Secrets and container environment variables are intentionally excluded.\n'
} >"${REPORT_PATH}"

capture 'Kernel' uname -a
capture 'Operating system' sh -c 'cat /etc/os-release'
capture 'CPU count' nproc
capture 'Memory' free -h
capture 'Filesystems' df -h
capture 'Block devices' lsblk
capture 'Docker version' docker version
capture 'Docker Compose version' docker compose version
capture 'Docker containers' docker ps --no-trunc --format 'table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
capture 'Docker networks' docker network ls
capture 'Docker volumes' docker volume ls
capture 'IP addresses' ip addr
capture 'IP routes' ip route
capture 'Listening sockets' ss -lntup
capture 'OpenVPN service' systemctl status openvpn --no-pager
capture 'OpenVPN client service' systemctl status openvpn-client@ --no-pager
capture 'Docker service' systemctl status docker --no-pager
capture_shell 'Existing paths under /opt' 'for path in /opt /opt/data /opt/assistant; do printf "\n[%s]\n" "$path"; if [[ -e "$path" ]]; then find "$path" -maxdepth 2 -mindepth 1 -printf "%M %u:%g %p\n" 2>/dev/null | sort | head -n 500; else printf "not present\n"; fi; done'
capture_shell 'Hermes indicators (names and images only)' 'docker ps -a --format "{{.Names}} {{.Image}} {{.Labels}}" 2>/dev/null | grep -i hermes || printf "No container name, image, or label matched hermes. Manual verification is still required.\n"'
capture_shell 'Container mounts (source and destination; no environment)' 'for id in $(docker ps -aq 2>/dev/null); do docker inspect --format "{{.Name}}{{range .Mounts}}\n  {{.Type}}: {{.Source}} -> {{.Destination}} (RW={{.RW}}){{end}}" "$id"; done'
capture_shell 'Container networks (no environment)' 'for id in $(docker ps -aq 2>/dev/null); do docker inspect --format "{{.Name}}{{range $name, $settings := .NetworkSettings.Networks}}\n  {{$name}} {{$settings.IPAddress}}{{end}}" "$id"; done'

printf '\nEnvironment report written to %s\n' "${REPORT_PATH}"

