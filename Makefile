SHELL ?= /bin/bash
PAGER ?= less

_IGNORE_VARS =
BRANCH ?= $(shell git rev-parse --abbrev-ref HEAD)
COMMIT_HASH = $(shell git rev-parse --short=8 HEAD)
COMMIT_DATE = $(shell git log -1 --pretty=format:'%cI')
# sed is important to strip out any creds (i.e., CI token) from repo URL
REPO_URL = $(shell git remote get-url origin | sed -e 's/.*\?@//; s/:/\//g')
API_PORT ?= 6000-6100
TARGETS_FOLDER ?= $(PWD)/anno-targets
TARGETS_OUT ?= $(PWD)/anno-targets-out
SAMPLE_REPO ?= $(PWD)/sample-repo
ANNO_DATA ?= $(PWD)/data
ANNO_RAWDATA ?= $(PWD)/rawdata

# set USE_REGISTRY to use the gitlab registry image names
ifeq ($(USE_REGISTRY),)
BASE_IMAGE = local/ella-anno
DOCKER_PREFIX = docker-daemon://
else
BASE_IMAGE = registry.gitlab.com/alleles/ella-anno
DOCKER_PREFIX = docker://
endif

# Docker/Singularity labels should follow OCI standard
# ref: https://github.com/opencontainers/image-spec/blob/main/annotations.md
OCI_BASE_LABEL = org.opencontainers.image
ANNO_BASE_LABEL = io.ousamg.anno
override BUILD_OPTS += --build-arg BUILDKIT_INLINE_CACHE=1 \
	--label $(OCI_BASE_LABEL).url=https://allel.es/anno-docs/ \
	--label $(OCI_BASE_LABEL).revision="$(COMMIT_HASH)" \
	--label $(ANNO_BASE_LABEL).git.url="$(REPO_URL)" \
	--label $(ANNO_BASE_LABEL).git.commit_hash="$(COMMIT_HASH)" \
	--label $(ANNO_BASE_LABEL).git.commit_date="$(COMMIT_DATE)" \
	--label $(ANNO_BASE_LABEL).git.branch="$(BRANCH)"
ifneq ($(ENTREZ_API_KEY),)
override ANNOBUILDER_OPTS += -e ENTREZ_API_KEY=$(ENTREZ_API_KEY)
endif

# Use release/annotated git tag if available, otherwise branch name
RELEASE_TAG ?= $(shell git tag -l --points-at HEAD)
ifneq ($(RELEASE_TAG),)
override BUILD_OPTS += --label $(OCI_BASE_LABEL).version=$(RELEASE_TAG)
PROD_TAG = $(RELEASE_TAG)
BUILDER_TAG = builder-$(RELEASE_TAG)
else
PROD_TAG = $(BRANCH)
BUILDER_TAG = builder-$(BRANCH)
endif
DEVC_TAG = $(PROD_TAG)-devcontainer

# combine image / tags from above for docker slug, or use provided
IMAGE_NAME ?= $(BASE_IMAGE):$(PROD_TAG)
ANNOBUILDER_IMAGE_NAME ?= $(BASE_IMAGE):$(BUILDER_TAG)
DEVC_IMAGE_NAME ?= $(BASE_IMAGE):$(DEVC_TAG)
# default names when running prod or builder docker images
CONTAINER_NAME ?= anno-$(PROD_TAG)-$(USER)
ANNOBUILDER_CONTAINER_NAME ?= anno-$(BUILDER_TAG)-$(USER)

# singularity naming should mirror docker, but ignores builder
SINGULARITY_IMAGE_NAME ?= anno-$(PROD_TAG).sif
SINGULARITY_SANDBOX_PATH = anno-$(PROD_TAG)/
SINGULARITY_INSTANCE_NAME ?= $(CONTAINER_NAME)
SINGULARITY_DATA = $(PWD)/singularity
SINGULARITY_LOG_DIR = $(HOME)/.singularity/instances/logs/$(shell hostname)/$(USER)
SINGULARITY_LOG_STDERR = $(SINGULARITY_LOG_DIR)/$(SINGULARITY_INSTANCE_NAME).err
SINGULARITY_LOG_STDOUT = $(SINGULARITY_LOG_DIR)/$(SINGULARITY_INSTANCE_NAME).out
SINGULARITY_ANNO_LOGS := $(PWD)/logs
# Large tmp storage is needed for gnomAD data generation. Set this to somewhere with at least 50GB of space if not
# available on /tmp's partition
TMP_DIR ?= /tmp

# get user / group ID so data generated/downloaded isn't root owned
UID_GID ?= $(shell id -u):$(shell id -g)

# Use docker buildkit for faster builds
DOCKER_BUILDKIT ?= 1

# if DO_CREDS is set, the file should be mounted into the docker container
ifneq ($(DO_CREDS),)
ifeq ($(shell realpath $(DO_CREDS)),)
$(error File DO_CREDS="$(DO_CREDS)" does not exist)
else
override ANNOBUILDER_OPTS += --env-file $(shell realpath $(DO_CREDS))
endif
endif

# if SPACES_CONFIG is set, the file should be mounted into the docker container
ifneq ($(SPACES_CONFIG),)
ifeq ($(shell realpath $(SPACES_CONFIG)),)
$(error File SPACES_CONFIG="$(SPACES_CONFIG)" does not exist)
else
override ANNOBUILDER_OPTS += -v $(shell realpath $(SPACES_CONFIG)):/anno/ops/spaces_config.json
endif
endif



# Check that given variables are set and all have non-empty values,
# die with an error otherwise.
#
# From: https://stackoverflow.com/questions/10858261/abort-makefile-if-variable-not-set
#
# Params:
#   1. Variable name(s) to test.
#   2. (optional) Error message to print.
check_defined = \
    $(strip $(foreach 1,$1, \
        $(call __check_defined,$1,$(strip $(value 2)))))
__check_defined = \
    $(if $(value $1),, \
      $(error Undefined $1$(if $2, ($2))))

# don't print this with make vars, they don't process right
_IGNORE_VARS += check_defined __check_defined

# if no rules / all given, just print help
.DEFAULT_GOAL := help
all: help

##---------------------------------------------
## General Development
##   Docker commands run in $IMAGE_NAME named $CONTAINER_NAME
##   Other vars: BUILD_OPTS, API_PORT, ANNO_DATA
##---------------------------------------------
.PHONY: any build run kill shell logs restart release singularity-release

# used to override the default CONTAINER_NAME to anything matching /anno-.*-$(USER)/
# must be placed _before_ the desired action
# e.g., to stop and rm the first matching container: make any kill
any:
	$(eval CONTAINER_NAME = $(shell docker ps | awk '/anno-.*-$(USER)/ {print $$NF}'))
	@true

build: ## build Docker image of 'prod' target named $IMAGE_NAME
	docker build -t $(IMAGE_NAME) $(BUILD_OPTS) --target prod .

build-release:
	git archive --format tar  $(if $(CI_COMMIT_SHA),$(CI_COMMIT_SHA),$(PROD_TAG)) | docker build -t $(IMAGE_NAME) $(BUILD_OPTS) --target prod -

pull: pull-builder pull-prod ## pull IMAGE_NAME and ANNOBUILDER_IMAGE_NAME from registry, requires USE_REGISTRY

pull-prod: ## pull IMAGE_NAME from registry, requires USE_REGISTRY
	$(call check_defined, USE_REGISTRY, You must set USE_REGISTRY to pull remote images)
	docker pull $(IMAGE_NAME)

# like build, but buildkit is disabled to allow access to intermediate layers for easier debugging
build-debug:
	DOCKER_BUILDKIT= docker build -t $(IMAGE_NAME) $(BUILD_OPTS) --target prod .

build-devcontainer:
	docker build -t $(DEVC_IMAGE_NAME) $(BUILD_OPTS) --target dev .

run: ## run image $IMAGE_NAME, with container named $CONTAINER_NAME :: API_PORT and ANNO_OPTS available as variables"
	docker run -d \
	-e TARGET_DATA=/target_data \
	$(ANNO_OPTS) \
	--restart=always \
	--name $(CONTAINER_NAME) \
	-p $(API_PORT):6000 \
	-v $(ANNO_DATA):/anno/data \
	-v $(TARGETS_FOLDER):/targets \
	-v $(TARGETS_OUT):/targets-out \
	-v $(SAMPLE_REPO):/samples \
	-v $(BUNDLE):/target_data/bundle \
	-v $(SENSITIVE_DB):/target_data/sensitive-db \
	$(IMAGE_NAME)

shell: ## get a bash shell in $CONTAINER_NAME
	docker exec -it $(CONTAINER_NAME) bash

logs: ## tail logs from $CONTAINER_NAME
	docker logs -f $(CONTAINER_NAME)

stop: ## stop $CONTAINER_NAME
	docker stop $(CONTAINER_NAME) || :

restart: stop ## restart $CONTAINER_NAME
	docker start $(CONTAINER_NAME) || :

kill: ## forcibly stop and remove $CONTAINER_NAME
	docker rm -f -v $(CONTAINER_NAME) || :

test: ## run tests with $IMAGE_NAME named $CONTAINER_NAME, requires all current data
	docker run --rm -t \
	-v $(ANNO_DATA):/anno/data \
	-v /pg_uta \
	--name $(CONTAINER_NAME)-test \
	$(IMAGE_NAME) /anno/ops/run_tests.sh

test-ops: ## run the ops tests in $IMAGE_NAME. WARNING: will overwrite data dir if attached and running manually
	docker run -t --rm \
	--name $(CONTAINER_NAME)-ops-test \
	$(IMAGE_NAME) /anno/ops/run_ops_tests.sh

test-lint: ## run shellcheck/shfmt linting on all bash scripts
	$(eval override ANNOBUILDER_OPTS += -v $(PWD)/.devcontainer:/anno/.devcontainer)
	docker run -u "$(UID_GID)" $(TERM_OPTS) -v "$(PWD):/anno" $(DEVC_IMAGE_NAME) pipenv run linter -v

localclean: ## remove data, rawdata, thirdparty dirs and docker volumes
	rm -rf thirdparty/ data/ rawdata/
	-docker volume rm ella-anno-exts

##---------------------------------------------------------------------
## AnnoBuilder: generate / download processed datasets for anno
##   Docker commands run in $ANNOBUILDER_IMAGE_NAME named $ANNOBUILDER_CONTAINER_NAME
##   Other variables: PKG_NAME, DO_CREDS, ENTREZ_API_KEY, RUN_CMD_ARGS, ANNO_DATA, ANNO_RAWDATA, DEBUG
##---------------------------------------------------------------------
.PHONY: build-annobuilder annobuilder annobuilder-shell annobuilder-exec download-data download-package
.PHONY: upload-data upload-package generate-data generate-package verify-digital-ocean install-thirdparty
.PHONY: install-package tar-data untar-data pipenv-update pipenv-check

ifeq ($(CI),)
# running locally, use interactive/tty
TERM_OPTS := -it
BASH_I = -i
else
BASH_I :=
TERM_OPTS :=
endif

# ensure $ANNO_DATA exists so it's not created as root owned by docker
# if FASTA is set, resolve its path in case of symlink, check it exists, add to docker mounts and
# set env var in container. Use override to prevent FASTA_PATH/FASTA_EXISTS being set by user/env
# NOTE: multiple if statements and evals used for clarity, can also condensed to a single $(if ...)
# TODO: add _ to FASTA_PATH, FASTA_EXISTS
define annobuilder-template
mkdir -p $(ANNO_DATA)
$(if $(FASTA),
	$(eval override FASTA_PATH = $(shell readlink -f $(FASTA))),
	$(eval override FASTA_PATH=)
)
$(if $(FASTA_PATH),
	$(eval override FASTA_EXISTS = $(shell test -e $(FASTA_PATH) && echo exists || true)),
	$(eval override FASTA_EXISTS=)
)
$(if
	$(and $(FASTA_PATH),$(FASTA_EXISTS)),
	$(eval override ANNOBUILDER_OPTS += -v $(FASTA_PATH):/anno/data/FASTA/custom.fasta)
	$(eval override ANNOBUILDER_OPTS += -e FASTA=/anno/data/FASTA/custom.fasta)
)
docker run --rm $(TERM_OPTS) \
	$(ANNOBUILDER_OPTS) \
	-u "$(UID_GID)" \
	-v $(TMP_DIR):/tmp \
	-v $(ANNO_DATA):/anno/data \
	$(ANNOBUILDER_IMAGE_NAME) \
	bash $(BASH_I) -c "$(RUN_CMD) $(RUN_CMD_ARGS)"
endef

build-annobuilder: ## build Docker image of 'builder' target named $ANNOBUILDER_IMAGE_NAME
	docker build -t $(ANNOBUILDER_IMAGE_NAME) $(BUILD_OPTS) --target builder .

pull-builder: ## pull ANNOBUILDER_IMAGE_NAME from registry, requires USE_REGISTRY
	$(call check_defined, USE_REGISTRY, You must set USE_REGISTRY to pull remote images)
	docker pull $(ANNOBUILDER_IMAGE_NAME)

# annobuilder/-shell/-exec are only run when troubleshooting data generation or adding new packages
annobuilder: ## run image $ANNOBUILDER_IMAGE_NAME named $ANNOBUILDER_CONTAINER_NAME
	docker run -td \
		--restart=always \
		--name $(ANNOBUILDER_CONTAINER_NAME) \
		-v $(ANNO_DATA):/anno/data \
		$(ANNOBUILDER_OPTS) \
		$(ANNOBUILDER_IMAGE_NAME) \
		sleep infinity

annobuilder-shell: ## get a bash shell in $ANNOBUILDER_CONTAINER_NAME
	docker exec -it $(ANNOBUILDER_CONTAINER_NAME) /bin/bash

annobuilder-exec: ## run a single command in $ANNOBUILDER_CONTAINER_NAME
	@$(call check_defined, RUN_CMD, 'Use RUN_CMD="python3 something.py opt1 ..." to specify command to run')
	$(annobuilder-template)

show-data-size: ## prints out the size of the datasets
	$(eval RUN_CMD := /anno/scripts/data_size.sh -s)
	$(annobuilder-template)

download-data: ## download all datasets from DigitalOcean
	$(eval RUN_CMD := df -ih;df -h;python3 /anno/ops/sync_data.py --download)
	$(annobuilder-template)

download-package: ## download the dataset for $PKG_NAME
	@$(call check_defined, PKG_NAME, 'Use PKG_NAME to specify which package to download')
	$(eval RUN_CMD := python3 /anno/ops/sync_data.py --download -d $(PKG_NAME))
	$(annobuilder-template)

upload-data: ## upload all new/updated datasets to DigitalOcean using $DO_CREDS credential file
	@$(call check_defined, DO_CREDS, 'Use DO_CREDS to specify a file containing SPACES_KEY and SPACES_SECRET')
	$(eval RUN_CMD := python3 /anno/ops/sync_data.py --upload)
	$(annobuilder-template)

upload-package: ## upload new/updated dataset for $PKG_NAME to DigitalOcean using $DO_CREDS credential file
	@$(call check_defined, DO_CREDS, 'Use DO_CREDS to specify the absolute path to a file containing SPACES_KEY and SPACES_SECRET')
	@$(call check_defined, PKG_NAME, 'Use PKG_NAME to specify which package to download')
	$(eval RUN_CMD := python3 /anno/ops/sync_data.py --upload -d $(PKG_NAME))
	$(annobuilder-template)

generate-data: ## generate all new/updated datasets based on the version in datasets.json
	@$(call check_defined, ENTREZ_API_KEY, 'Make sure ENTREZ_API_KEY is set and exported so clinvar data can be built successfully')
	mkdir -p $(ANNO_RAWDATA)
	$(eval override ANNOBUILDER_OPTS += -v $(ANNO_RAWDATA):/anno/rawdata)
	$(eval RUN_CMD := python3 /anno/ops/sync_data.py --generate)
	$(annobuilder-template)

generate-package: ## generate new/updated dataset for $PKG_NAME based on the version in datasets.json
	@$(call check_defined, PKG_NAME, 'Use PKG_NAME to specify which package to generate')
	mkdir -p $(ANNO_RAWDATA)
	$(eval override ANNOBUILDER_OPTS += -v $(ANNO_RAWDATA):/anno/rawdata)
	$(eval RUN_CMD := python3 /anno/ops/sync_data.py --generate -d $(PKG_NAME))
	$(annobuilder-template)

verify-digital-ocean:
	$(eval RUN_CMD := python3 /anno/ops/sync_data.py --verify-remote)
	$(annobuilder-template)


# installed directly in Dockerfile, but commands here for reference or local install
install-thirdparty: ## installs thirdparty packages locally instead of in Docker
	$(eval RUN_CMD := python3 /anno/ops/install_thirdparty.py --clean)
	$(annobuilder-template)

# installed directly in Dockerfile, but commands here for reference or local install
install-package: ## installs thirdparty package $PKG_NAME locally instead of in Docker
	@$(call check_defined, PKG_NAME, 'Use PKG_NAME to specify which package to install')
	$(eval RUN_CMD := python3 /anno/ops/install_thirdparty.py --clean -p $(PKG_NAME))
	$(annobuilder-template)

tar-data: ## packages the contents of $ANNO_DATA into $TAR_OUTPUT for use on a different server
	$(eval TAR_OUTPUT ?= data.tar)
	$(eval RUN_CMD := PKG_NAMES=$(PKG_NAMES) DATASETS=$(DATASETS) TAR_OUTPUT=$(TAR_OUTPUT) /anno/ops/package_data)
	$(annobuilder-template)

untar-data: ## extracts $TAR_INPUT into existing $ANNO_DATA, updating sources.json and vcfanno_config.json as needed
	$(eval TAR_INPUT ?= /anno/data/data.tar)
	$(eval RUN_CMD := TAR_INPUT=$(TAR_INPUT) /anno/ops/unpack_data)
	$(annobuilder-template)

# For consistency, the Docker container must be used when updating Pipfile dependencies.
# Otherwise, it will go off your local python's settings which may not match. This can happen even
# if using a Pipenv venv locally.
pipenv-update: ## updates Pipfile.lock using $IMAGE_NAME, under development
	docker run --rm -it \
		-u anno-user \
		-v $(PWD):/local_anno \
		$(ANNOBUILDER_IMAGE_NAME) \
		/anno/ops/update_pipfile.sh

# uses annobuilder image to check dev and prod dependencies
pipenv-check: ## uses pipenv to check for package vulnerabilities
	$(eval RUN_CMD := pipenv check)
	$(annobuilder-template)


##---------------------------------------------------------------------
## Singularity
##   Like the above sections, but using Singularity $SINGULARITY_IMAGE_NAME instance named
##   $SINGULARITY_INSTANCE_NAME.
##   Other vars: SINGULARITY_DATA, ANNO_DATA, SINGULARITY_ANNO_LOGS
##---------------------------------------------------------------------
.PHONY: singularity-test singularity-shell singularity-start singularity-stop

singularity-build:
	singularity build $(SINGULARITY_IMAGE_NAME) $(DOCKER_PREFIX)$(IMAGE_NAME)

# creates additional directories necessary when using read-only Singularity image
ensure-singularity-dirs:
	@mkdir -p $(SINGULARITY_DATA) $(SINGULARITY_ANNO_LOGS)

singularity-start: ensure-singularity-dirs ## start a local Singularity instance of $SINGULARITY_IMAGE_NAME named $SINGULARITY_INSTANCE_NAME
	singularity instance start \
		-B $(ANNO_DATA):/anno/data \
		-B $(SINGULARITY_ANNO_LOGS):/logs \
		-B $(shell mktemp -d):/anno/.cache \
		-B $(SINGULARITY_DATA):/pg_uta \
		--cleanenv \
		$(SINGULARITY_IMAGE_NAME) $(SINGULARITY_INSTANCE_NAME)

	ln -sf $(SINGULARITY_LOG_STDOUT) $(SINGULARITY_ANNO_LOGS)/singularity.out
	ln -sf $(SINGULARITY_LOG_STDERR) $(SINGULARITY_ANNO_LOGS)/singularity.err

singularity-test: ## run tests in a running $SINGULARITY_INSTANCE_NAME
	-singularity exec --cleanenv instance://$(SINGULARITY_INSTANCE_NAME) supervisorctl -c /anno/ops/supervisor.cfg stop all
	singularity exec --cleanenv instance://$(SINGULARITY_INSTANCE_NAME) /anno/ops/run_tests.sh
	singularity exec --cleanenv instance://$(SINGULARITY_INSTANCE_NAME) supervisorctl -c /anno/ops/supervisor.cfg start all

singularity-stop: ## stop the singularity instance $SINGULARITY_INSTANCE_NAME
	singularity exec --cleanenv instance://$(SINGULARITY_INSTANCE_NAME) supervisorctl -c /anno/ops/supervisor.cfg stop all
	singularity instance stop $(SINGULARITY_INSTANCE_NAME)

singularity-shell: ## get a bash shell in $SINGULARITY_INSTANCE_NAME
	singularity shell --cleanenv instance://$(SINGULARITY_INSTANCE_NAME)

singularity-tail-logs: ## tail logs from $SINGULARITY_INSTANCE_NAME
	tail -f $(SINGULARITY_LOG_STDOUT) $(SINGULARITY_LOG_STDERR)

# load the stderr log for $SINGULARITY_INSTANCE_NAME in $PAGER (default: less)
singularity-errlog:
	cat $(SINGULARITY_LOG_STDERR) | $(PAGER)

# load the stdout log for $SINGULARITY_INSTANCE_NAME in $PAGER (default: less)
singularity-log:
	cat $(SINGULARITY_LOG_STDOUT) | $(PAGER)

singularity-start-dev:
	[ -d $(SINGULARITY_DATA) ] || mkdir -p $(SINGULARITY_DATA)
	singularity -v instance start \
		-B $(ANNO_DATA):/anno/data \
		-B $(shell mktemp -d):/anno/.cache \
		-B $(SINGULARITY_DATA):/pg_uta \
		--cleanenv \
		$(SINGULARITY_SANDBOX_PATH) $(SINGULARITY_INSTANCE_NAME)

singularity-stop-dev: singularity-stop

singularity-shell-dev: singularity-shell

singularity-test-dev: singularity-test

singularity-untar-data: ## untar
	$(eval TAR_INPUT ?= /anno/data/data.tar)
	singularity exec --cleanenv instance://$(SINGULARITY_INSTANCE_NAME) TAR_INPUT=$(TAR_INPUT) /anno/ops/unpack_data

##---------------------------------------------
## Releases
##   Create release artifacts locally and on Gitlab
##   Variables: RELEASE_TAG, IMAGE_NAME, SINGULARITY_IMAGE_NAME
##---------------------------------------------

ci-build-docker:
	$(MAKE) build-release BUILD_OPTS="--cache-from=$(IMAGE_NAME) --cache-from=$(ANNOBUILDER_IMAGE_NAME)"
	$(MAKE) build-annobuilder BUILD_OPTS="--cache-from=$(ANNOBUILDER_IMAGE_NAME) --cache-from=$(IMAGE_NAME)"

ci-build-devcontainer:
	$(MAKE) build-devcontainer BUILD_OPTS="--cache-from=$(ANNOBUILDER_IMAGE_NAME) --cache-from=$(IMAGE_NAME)"

ci-push-docker:
	docker push $(IMAGE_NAME)
	docker push $(ANNOBUILDER_IMAGE_NAME)

ci-release-init:
	apk add --update make git python3 py3-click docker-cli bash

ci-release: pull-prod release

check-release-tag:
	@$(call check_defined, RELEASE_TAG, 'Missing tag. Please provide a value on the command line')
	git rev-parse --verify "refs/tags/$(RELEASE_TAG)^{tag}"
	git ls-remote --exit-code --tags origin "refs/tags/$(RELEASE_TAG)"

# skip tag validation if run in CI, ref .gitlab-ci.yml for use cases
release: $(if $(CI),,check-release-tag) singularity-build ## build a release SINGULARITY_IMAGE_NAME for RELEASE_TAG based on IMAGE_NAME pulled from the remote registry


##---------------------------------------------
## Help / Debugging
##  Other vars: VAR_ORIGIN, FILTER_VARS
##---------------------------------------------
.PHONY: help vars local-vars

# only use ASCII codes if running in terminal (e.g., not when piped)
ifneq ($(MAKE_TERMOUT),)
_CYAN = \033[36m
_RESET = \033[0m
endif

# Using the automatic `make help` generation:
# Lines matching /^## / are considered section headers
# Use a ## at the end of a rule to have it printed out
# e.g., `some_rule: ## some_rule help text` at the end of a rule to have it included in help output
help: ## prints this help message
	@grep -E -e '^[a-zA-Z_-]+:.*?## .*$$' -e '^##[ -]' $(MAKEFILE_LIST) \
		| awk 'BEGIN {prev = ""; FS = ":.*?## "}; {if (match($$1, /^#/) && match(prev, /^#/) == 0) printf "\n"; printf "$(_CYAN)%-30s$(_RESET) %s\n", $$1, $$2; prev = $$1}'
	@echo
	@echo "Additional comments available in this Makefile\n"

NULL_STRING :=
BLANKSPACE = $(NULL_STRING) # this is how we get a single space
_IGNORE_VARS += NULL_STRING BLANKSPACE
vars: _list_vars ## prints out variables available in the Makefile and the origin of their value
	@true

# actually prints out the desired variables, should not be called directly
# uses environment and environment_override by default, always includes file and command_line
# ref:
#        origin:  https://www.gnu.org/software/make/manual/html_node/Origin-Function.html#Origin-Function
#    .VARIABLES:  https://www.gnu.org/software/make/manual/html_node/Special-Variables.html#Special-Variables
# overall magic:  https://stackoverflow.com/a/59097246/5791702
FILTER_VARS ?=
_list_vars:
	$(eval filtered_vars = $(sort $(filter-out $(sort $(strip $(FILTER_VARS) $(_IGNORE_VARS))),$(.VARIABLES))))
	$(eval VAR_ORIGIN ?= environment environment_override)
	$(eval override VAR_ORIGIN += file command_line)
	$(foreach v, $(filtered_vars), $(if $(filter $(sort $(VAR_ORIGIN)),$(subst $(BLANKSPACE),_,$(origin $(v)))), $(info $(v) ($(origin $(v))) = $($(v)))))

_disable_origins:
	$(eval VAR_ORIGIN = )

ENV = $(shell command -v env)
local-vars: _disable_origins _list_vars ## print out vars set by command line and in the Makefile
	@true
