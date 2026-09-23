SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

.PHONY: help install-docker inspect setup validate build start stop restart status logs observability-up observability-down observability-logs smoke smoke-model resources rotate-key models model-install model-activate model-remove backup restore test

help:
	@printf '%s\n' \
	  'make install-docker Install Docker CE + Compose on clean Ubuntu (sudo)' \
	  'make inspect     Read-only VPS inspection -> docs/environment.md' \
	  'make setup       Inspect, validate, build, start, and smoke-test' \
	  'make validate    Validate Compose without starting services' \
	  'make build       Build the LLM Studio API image' \
	  'make start       Start only the llm-studio services' \
	  'make stop        Stop only the llm-studio services (data is preserved)' \
	  'make restart     Restart only the llm-studio API' \
	  'make status      Show LLM Studio service status' \
	  'make logs        Follow API operational logs (request bodies are in the protected trace file)' \
	  'make observability-up    Enable and start the private OpenObserve UI' \
	  'make observability-down  Stop the UI and collector; preserve data' \
	  'make observability-logs  Follow OpenObserve and collector logs' \
	  'make smoke       Test authentication and model discovery' \
	  'make smoke-model Download/load the model and test generation' \
	  'make resources   Show host and LLM Studio resource use' \
	  'make rotate-key  Rotate the API key and recreate the API container' \
	  'make models      List selectable models and capabilities' \
	  'make model-install MODEL=qwen35-2b' \
	  'make model-activate MODEL=qwen35-2b' \
	  'make model-remove MODEL=qwen35-2b [FORCE=1]' \
	  'make backup BACKUP_DEST=/mnt/backups' \
	  'make restore BACKUP_DIR=/mnt/backups/llm-studio-backup-... [DATA_DIR=/opt/data/llm-studio]' \
	  'make test        Run local static/setup tests'

install-docker:
	@./scripts/install_docker.sh

inspect:
	@./scripts/inspect_environment.sh

setup:
	@./scripts/setup.sh

validate:
	@LLM_STUDIO_SETUP_NO_START=true ./scripts/setup.sh

build:
	@source scripts/common.sh && assert_env_file && compose build

start:
	@source scripts/common.sh && assert_env_file && compose up --detach

stop:
	@source scripts/common.sh && assert_env_file && compose stop

restart:
	@source scripts/common.sh && assert_env_file && compose up -d --force-recreate --no-deps api

status:
	@source scripts/common.sh && assert_env_file && compose ps

logs:
	@source scripts/common.sh && assert_env_file && compose logs --follow --tail 100 api

observability-up:
	@./scripts/observability.sh enable

observability-down:
	@./scripts/observability.sh disable

observability-logs:
	@source scripts/common.sh && assert_env_file && compose logs --follow --tail 100 openobserve otel-collector

smoke:
	@./scripts/smoke_test.sh

smoke-model:
	@./scripts/model_smoke_test.sh

resources:
	@./scripts/resource_check.sh

rotate-key:
	@./scripts/rotate_api_key.sh

models:
	@./scripts/models.py list

model-install:
	@test -n "$(MODEL)" || { printf 'MODEL is required\n' >&2; exit 2; }
	@./scripts/models.py install "$(MODEL)"

model-activate:
	@test -n "$(MODEL)" || { printf 'MODEL is required\n' >&2; exit 2; }
	@./scripts/models.py activate "$(MODEL)"

model-remove:
	@test -n "$(MODEL)" || { printf 'MODEL is required\n' >&2; exit 2; }
	@./scripts/models.py remove "$(MODEL)" $(if $(filter 1,$(FORCE)),--force-active,)

backup:
	@test -n "$(BACKUP_DEST)" || { printf 'BACKUP_DEST is required\n' >&2; exit 2; }
	@./scripts/backup_data.sh "$(BACKUP_DEST)"

restore:
	@test -n "$(BACKUP_DIR)" || { printf 'BACKUP_DIR is required\n' >&2; exit 2; }
	@./scripts/restore_data.sh "$(BACKUP_DIR)" $(if $(DATA_DIR),"$(DATA_DIR)",)

test:
	@./test/run.sh

test-all:
	@./test/run_all.sh

test-models:
	@python3 test/scripts/all_models_prompt_contract.py

test-realworld:
	@python3 test/scripts/realworld_api_contract.py

test-dsh:
	@python3 test/scripts/dsh_harness_contract.py

test-vision:
	@python3 test/scripts/vision_contract.py
