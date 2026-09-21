#!/usr/bin/env bash

set -Eeuo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"
umask 077

[[ "$(id -u)" == 0 ]] || die 'run this backup with sudo so ownership and extended attributes are preserved'
require_command docker
require_command realpath
require_command rsync
require_command sha256sum

[[ $# -eq 1 ]] || die "usage: sudo $0 /absolute/backup-destination"
assert_env_file
source_data="$(realpath -m "$(env_value LLM_STUDIO_DATA_DIR /opt/data/llm-studio)")"
destination_root="$(realpath -m "$1")"
[[ -d "${source_data}" ]] || die "data directory does not exist: ${source_data}"
[[ "${destination_root}" != "${source_data}" && "${destination_root}" != "${source_data}"/* ]] \
  || die 'backup destination must be outside the LLM Studio data directory'
install -d -m 0700 -- "${destination_root}"
backup_dir="${destination_root}/llm-studio-backup-$(date -u +%Y%m%dT%H%M%SZ)"
[[ ! -e "${backup_dir}" ]] || die "backup already exists: ${backup_dir}"
install -d -m 0700 -- "${backup_dir}/data"

was_running=false
if compose ps --status running --services | grep -Eq '^(api|traefik-local|traefik-internet)$'; then
  was_running=true
fi
restart_stack() {
  if [[ "${was_running}" == true ]]; then
    compose up --detach >/dev/null
  fi
}
trap restart_stack EXIT

log 'Stopping only the llm-studio Compose project for a consistent backup'
compose stop
log "Copying data to ${backup_dir}"
rsync -aHAX --numeric-ids --info=progress2 "${source_data}/" "${backup_dir}/data/"
install -m 0600 -- "${ENV_FILE}" "${backup_dir}/llm-studio.env"
install -m 0644 -- "${PROJECT_ROOT}/configs/models.json" "${backup_dir}/models.json"
{
  printf 'format=llm-studio-directory-backup-v1\n'
  printf 'created_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'source_data_dir=%s\n' "${source_data}"
  printf 'contains_api_key=true\n'
} >"${backup_dir}/BACKUP_INFO"
(
  cd "${backup_dir}"
  find data llm-studio.env models.json BACKUP_INFO -type f -print0 \
    | sort -z \
    | xargs -0 sha256sum >SHA256SUMS
)
touch "${backup_dir}/BACKUP_COMPLETE"
chmod -R go-rwx "${backup_dir}"
log "Backup complete: ${backup_dir}"
log 'The backup contains the API key; store and transport it as a secret.'
