ROOT_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
THIS_FILE := $(lastword $(MAKEFILE_LIST))

# variables that control the volumes
LOGS_DIR = $(ROOT_DIR)/logs

# variables that control the CP repos
CP_ROOT_DIR = $(ROOT_DIR)/cp_root
CP_CONFIG_FILE ?= $(ROOT_DIR)/config/cp_config.yaml

# location of local env file
HOST_ENV_FILE = $(ROOT_DIR)/.env

# Determine CP repo targets
CP_TARGETS_DIRS = $(shell yq -r '.cp_targets | keys | .[]' $(CP_CONFIG_FILE))
CP_MAKE_TARGETS = $(addprefix $(CP_ROOT_DIR)/.pulled_, $(subst :,_colon_, $(subst /,_slash_, $(CP_TARGETS_DIRS))))

.PHONY: help cps/clean cps env-file-required github-creds-required

help: ## Display available targets and their help strings
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_/-]+:.*?## / {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}' $(THIS_FILE) | sort

env-file-required:
	@if [ -z "$(ENV_FILES_PRESENT)" ]; then exit 1; fi

github-creds-required: env-file-required
	@if [ -n "$(INVALID_GITHUB_ENV_VARS)" ]; then exit 1; fi
	@if [ "$(GITHUB_ENV_VAR_COUNT)" -lt 2 ]; then exit 1; fi

## Internal target to clone and pull the CP source for each CP repo
$(CP_ROOT_DIR)/.pulled_%:
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

cps: $(CP_MAKE_TARGETS) ## Clone CP repos

cps-clean: ## Clean up the cloned CP repos
	@git -C $(CP_ROOT_DIR) clean -f -f -X -d

logs-clean:
	@git -C $(LOGS_DIR) clean -f -X

clean: logs-clean cps-clean
