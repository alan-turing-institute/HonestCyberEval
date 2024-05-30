ROOT_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
THIS_FILE := $(lastword $(MAKEFILE_LIST))
DOCKER_COMPOSE_FILE = $(ROOT_DIR)/compose.yaml
DOCKER_COMPOSE_PORTS_FILE = $(ROOT_DIR)/sandbox/compose_local_overrides.yaml
DOCKER_COMPOSE_LOCAL_ARGS = -f $(DOCKER_COMPOSE_FILE) -f $(DOCKER_COMPOSE_PORTS_FILE) --profile development
DOCKER_COMPOSE_LOCAL_MOCK_CRS_ARGS = -f $(DOCKER_COMPOSE_FILE) -f $(DOCKER_COMPOSE_PORTS_FILE) --profile mock-crs

# variables that control the volumes
HOST_CRS_SCRATCH = $(ROOT_DIR)/crs_scratch
HOST_DIND_CACHE = $(ROOT_DIR)/dind_cache
HOST_CAPI_LOGS = $(ROOT_DIR)/capi_logs

# variables that control the CP repos
HOST_CP_ROOT_DIR = $(ROOT_DIR)/cp_root
CP_CONFIG_FILE ?= $(ROOT_DIR)/cp_config.yaml

# Check for required file that will error out elsewhere if not present
ifeq (,$(wildcard $(CP_CONFIG_FILE)))
$(error Required file not found: $(CP_CONFIG_FILE))
endif

# Check for required executables (dependencies)
__UNUSED_REQUIRED_EXE = yq docker kompose
__UNUSED_EVAL_EXES := $(foreach exe,$(__UNUSED_REQUIRED_EXE), \
	$(if $(shell command -v $(exe)),,$(warning Required executable not in PATH: $(exe))))

# Check yq version
__UNUSED_YQ_REQUIRED_MAJOR_VERSION ?= 4
__UNUSED_YQ_ACTUAL_MAJOR_VERSION = $(shell yq --version | grep -o "version v.*" | grep -Eo '[0-9]+(\.[0-9]+)+' | cut -f1 -d'.')
ifneq ($(__UNUSED_YQ_REQUIRED_MAJOR_VERSION),$(__UNUSED_YQ_ACTUAL_MAJOR_VERSION))
$(error Unexpected major version of 'yq'. Expected: $(__UNUSED_YQ_REQUIRED_MAJOR_VERSION), Actual: $(__UNUSED_YQ_ACTUAL_MAJOR_VERSION)))
endif

# Determine CP repo targets
CP_TARGETS_DIRS = $(shell yq -r '.cp_targets | keys | .[]' $(CP_CONFIG_FILE))
CP_MAKE_TARGETS = $(addprefix $(HOST_CP_ROOT_DIR)/.pulled_, $(subst :,_colon_, $(subst /,_slash_, $(CP_TARGETS_DIRS))))

.PHONY: help build up start down destroy stop restart logs logs-crs logs-litellm logs-iapi ps crs-shell litellm-shell cps/clean cps computed-env clear-dind-cache

help: ## Display available targets and their help strings
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_/-]+:.*?## / {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}' $(THIS_FILE) | sort

build: ## Build the project
	@docker compose $(DOCKER_COMPOSE_LOCAL_ARGS) build $(c)

computed-env:
	@sed -i '/CAPI_AUTH_HEADER=*/d' sandbox/env
	$(eval include sandbox/env)
	@echo -n "CAPI_AUTH_HEADER=\"Basic " >> sandbox/env
	@echo -n "${CAPI_ID}:${CAPI_TOKEN}" | base64 | tr -d '\n' >> sandbox/env
	@echo \" >> sandbox/env

local-volumes:
	mkdir -p $(HOST_CP_ROOT_DIR) $(HOST_CRS_SCRATCH) $(HOST_DIND_CACHE) $(HOST_CAPI_LOGS)

up: local-volumes cps computed-env ## Start containers
	@docker compose $(DOCKER_COMPOSE_LOCAL_ARGS) up -d $(c)

up-attached: cps computed-env ## Start containers
	@docker compose $(DOCKER_COMPOSE_LOCAL_ARGS) up --build --abort-on-container-exit $(c)

mock-crs/up-attached: cps computed-env ## Start containers
	@docker compose $(DOCKER_COMPOSE_LOCAL_MOCK_CRS_ARGS) up --build --abort-on-container-exit $(c)

start: ## Start containers
	@docker compose $(DOCKER_COMPOSE_LOCAL_ARGS) start $(c)

down: ## Stop and remove containers
	@docker compose $(DOCKER_COMPOSE_LOCAL_ARGS) down --remove-orphans $(c)

destroy: clear-dind-cache ## Stop and remove containers with volumes
	@docker compose $(DOCKER_COMPOSE_LOCAL_ARGS) down --volumes --remove-orphans $(c)

clear-dind-cache: ## Clears out DIND cached artifacts
	@sudo rm -rf $(ROOT_DIR)/dind_cache/*

stop: ## Stop containers
	@docker compose $(DOCKER_COMPOSE_LOCAL_ARGS) stop $(c)

restart: computed-env ## Restart containers
	@docker compose $(DOCKER_COMPOSE_LOCAL_ARGS) stop $(c)
	@docker compose $(DOCKER_COMPOSE_LOCAL_ARGS) up -d $(c)

logs: ## Show logs for containers
	@docker compose $(DOCKER_COMPOSE_LOCAL_ARGS) logs --tail=100 -f $(c)

logs-crs: ## Show logs for crs container
	@docker compose $(DOCKER_COMPOSE_LOCAL_ARGS) logs --tail=100 -f crs

logs-litellm: ## Show logs for litellm container
	@docker compose $(DOCKER_COMPOSE_LOCAL_ARGS) logs --tail=100 -f litellm

logs-iapi: ## Show logs for iapi container
	@docker compose $(DOCKER_COMPOSE_LOCAL_ARGS) logs --tail=100 -f iapi

ps: ## List containers
	@docker compose $(DOCKER_COMPOSE_LOCAL_ARGS) ps

crs-shell: ## Access the crs shell
	@docker compose $(DOCKER_COMPOSE_LOCAL_ARGS) exec crs /bin/bash

litellm-shell: ## Access the litellm shell
	@docker compose $(DOCKER_COMPOSE_LOCAL_ARGS) exec litellm /bin/bash

## Internal target to clone and pull the CP source for each CP repo
$(HOST_CP_ROOT_DIR)/.pulled_%:
	$(eval REVERT_CP_TARGETS_DIRS_ESCAPE_STR=$(subst _colon_,:,$(subst _slash_,/,$*)))
	$(eval CP_ROOT_REPO_SUBDIR=$(@D)/$(REVERT_CP_TARGETS_DIRS_ESCAPE_STR))
	@$(RM) -r $(CP_ROOT_REPO_SUBDIR)
	@mkdir -p $(CP_ROOT_REPO_SUBDIR)
	@yq -r '.cp_targets["$(REVERT_CP_TARGETS_DIRS_ESCAPE_STR)"].url' $(CP_CONFIG_FILE) | \
		xargs -I {} git clone {} $(CP_ROOT_REPO_SUBDIR)
	@yq -r '.cp_targets["$(REVERT_CP_TARGETS_DIRS_ESCAPE_STR)"] | .ref // "main"' $(CP_CONFIG_FILE) | \
		xargs -I {} sh -c \
			"git -C $(CP_ROOT_REPO_SUBDIR) fetch --depth 1 origin {}; \
			git -C $(CP_ROOT_REPO_SUBDIR) checkout --quiet {};"
	make -C $(CP_ROOT_REPO_SUBDIR) cpsrc-prepare
	@touch $@

cps: local-volumes $(CP_MAKE_TARGETS) ## Clone CP repos

cps/clean: ## Clean up the cloned CP repos
	@rm -rf $(HOST_CP_ROOT_DIR)

loadtest: computed-env ## Run k6 load tests
	@docker compose -f $(DOCKER_COMPOSE_FILE) --profile loadtest up --exit-code-from test --build $(c)
loadtest/destroy: ## Stop and remove containers with volumes
	@docker compose -f $(DOCKER_COMPOSE_FILE) --profile loadtest down --volumes --remove-orphans $(c)

k8s: k8s/clean build ## Generates helm chart locally for the development profile for kind testing, etc. build is called for local image generation
	@kind create cluster --wait 1m
	@docker pull ghcr.io/aixcc-sc/iapi:v4.0.3
	@docker pull ghcr.io/berriai/litellm-database:main-v1.35.10
	@docker pull docker:24-dind
	@docker pull postgres:16.2-alpine3.19
	@docker pull ghcr.io/aixcc-sc/crs-sandbox/mock-crs:v2.0.0
	@kind load docker-image ghcr.io/aixcc-sc/iapi:v4.0.3 ghcr.io/berriai/litellm-database:main-v1.35.10 docker:24-dind postgres:16.2-alpine3.19
	@mkdir $(ROOT_DIR)/charts
	@COMPOSE_FILE="$(ROOT_DIR)/compose.yaml $(ROOT_DIR)/kompose_development_overrides.yaml" kompose convert --profile development --chart --out tmp_charts
	@mv tmp_charts $(ROOT_DIR)/charts/crs
	@rm -rf ./tmp_charts
	@yq eval ".description = \"AIxCC Competitor CRS\"" -i $(ROOT_DIR)/charts/crs/Chart.yaml
	@yq eval ".name = \"crs\"" -i $(ROOT_DIR)/charts/crs/Chart.yaml
	@helm install crs $(ROOT_DIR)/charts/crs

k8s/clean:
	@rm -rf tmp_charts
	@rm -rf $(ROOT_DIR)/charts
	@kind delete cluster

k8s/competition: k8s/clean ## Generates the competition helm chart for use during pregame and the competition
	@COMPOSE_FILE="$(ROOT_DIR)/compose.yaml $(ROOT_DIR)/kompose_competition_overrides.yaml" kompose convert --profile competition --chart --out tmp_charts
	@mkdir $(ROOT_DIR)/charts
	@mv tmp_charts $(ROOT_DIR)/charts/crs
	@rm -rf ./tmp_charts
	@yq eval ".description = \"AIxCC Competitor CRS\"" -i $(ROOT_DIR)/charts/crs/Chart.yaml
	@yq eval ".name = \"crs\"" -i $(ROOT_DIR)/charts/crs/Chart.yaml

clean-volumes:
	rm -rf $(HOST_CP_ROOT_DIR) $(HOST_CRS_SCRATCH) $(HOST_DIND_CACHE) $(HOST_CAPI_LOGS)

clean: cps/clean k8s/clean down clear-dind-cache

force-reset: ## Remove all local docker containers, networks, volumes, and images
	@docker system prune --all
