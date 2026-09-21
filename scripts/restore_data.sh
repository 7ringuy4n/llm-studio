#!/usr/bin/env bash

set -Eeuo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"
umask 077

[[ "$(id -u)" == 0 ]] || die 'run restore with sudo so ownership can be mapped to the new login user'
require_command realpath
require_command rsync
require_command sha256sum

[[ $# -ge 1 && $# -le 2 ]] \
  || die "usage: sudo $0 /backup/llm-studio-backup-TIMESTAMP [target-data-dir]"
backup_dir="$(realpath -e "$1")"
target_data="$(realpath -m "${2:-/opt/data/llm-studio}")"
[[ -f "${backup_dir}/BACKUP_COMPLETE" && -f "${backup_dir}/SHA256SUMS" ]] \
  || die 'backup is incomplete or is not an LLM Studio directory backup'
[[ -f "${backup_dir}/llm-studio.env" && -d "${backup_dir}/data" ]] \
  || die 'backup is missing configuration or data'
if [[ -d "${target_data}" && -n "$(find "${target_data}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  die "target data directory is not empty: ${target_data}"
fi
[[ ! -e "${ENV_FILE}" ]] || die "${ENV_FILE} already exists; restore into a clean clone or move it aside explicitly"

log 'Verifying every backup file before restore'
(cd "${backup_dir}" && sha256sum --check SHA256SUMS)
install -d -m 0750 -- "${target_data}"
rsync -aHAX --numeric-ids --info=progress2 "${backup_dir}/data/" "${target_data}/"
install -m 0600 -- "${backup_dir}/llm-studio.env" "${ENV_FILE}"

restore_uid="${SUDO_UID:-10001}"
restore_gid="${SUDO_GID:-10001}"
chown -R "${restore_uid}:${restore_gid}" -- "${target_data}"
chown "${restore_uid}:${restore_gid}" -- "${ENV_FILE}"
log 'Restore complete. Run sudo ./scripts/setup.sh to validate, rebuild, and start the isolated stack.'
