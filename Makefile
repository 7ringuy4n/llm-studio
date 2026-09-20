SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

.PHONY: help inspect setup validate build start stop restart status logs smoke smoke-model resources rotate-key test

help:
	@printf '%s\n' \
	  'make inspect     Read-only VPS inspection -> docs/environment.md' \
	  'make setup       Inspect, validate, build, start, and smoke-test' \
	  'make validate    Validate Compose without starting services' \
	  'make build       Build the LLM Studio API image' \
	  'make start       Start only the llm-studio services' \
	  'make stop        Stop only the llm-studio services (data is preserved)' \
	  'make restart     Restart only the llm-studio API' \
	  'make status      Show LLM Studio service status' \
	  'make logs        Follow LLM Studio logs (prompts are not logged)' \
	  'make smoke       Test authentication and model discovery' \
	  'make smoke-model Download/load the model and test generation' \
	  'make resources   Show host and LLM Studio resource use' \
	  'make rotate-key  Rotate the API key and recreate the API container' \
	  'make test        Run local static/setup tests'

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
	@source scripts/common.sh && assert_env_file && compose restart api

status:
	@source scripts/common.sh && assert_env_file && compose ps

logs:
	@source scripts/common.sh && assert_env_file && compose logs --follow --tail 100 api

smoke:
	@./scripts/smoke_test.sh

smoke-model:
	@./scripts/model_smoke_test.sh

resources:
	@./scripts/resource_check.sh

rotate-key:
	@./scripts/rotate_api_key.sh

test:
	@./tests/run.sh
