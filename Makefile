SHELL ?= /bin/bash
PAGER ?= less

_IGNORE_VARS =
BRANCH ?= $(shell git rev-parse --abbrev-ref HEAD)
COMMIT_HASH = $(shell git describe --always --dirty --abbrev=8 | sed -e 's/.*g//')
REPO_URL = $(shell git remote get-url origin)
API_PORT ?= 6000-6100
TARGETS_FOLDER ?= $(shell pwd)/anno-targets
TARGETS_OUT ?= $(shell pwd)/anno-targets-out
SAMPLE_REPO ?= $(shell pwd)/sample-repo
ANNO_DATA ?= $(shell pwd)/data
ANNO_RAWDATA ?= $(shell pwd)/rawdata

RELEASE_TAG ?= $(shell git tag -l --points-at HEAD)
ifneq ($(RELEASE_TAG),)
ANNO_BUILD := anno-$(RELEASE_TAG)
BUILDER_BUILD := annobuilder-$(RELEASE_TAG)
override BUILD_OPTS += -t local/anno:$(RELEASE_TAG)
else
ANNO_BUILD := anno-$(BRANCH)
BUILDER_BUILD = annobuilder-$(BRANCH)
endif
override BUILD_OPTS += --label git.repo_url=$(REPO_URL) --label git.commit_hash=$(COMMIT_HASH)

CONTAINER_NAME ?= $(ANNO_BUILD)-$(USER)
IMAGE_NAME ?= local/$(ANNO_BUILD)
ANNOBUILDER_CONTAINER_NAME ?= $(BUILDER_BUILD)
ANNOBUILDER_IMAGE_NAME ?= local/$(BUILDER_BUILD)
override ANNOBUILDER_OPTS += -e ENTREZ_API_KEY=$(ENTREZ_API_KEY)
SINGULARITY_IMAGE_NAME ?= $(ANNO_BUILD).sif
SINGULARITY_SANDBOX_PATH = $(ANNO_BUILD)/
SINGULARITY_INSTANCE_NAME ?= $(ANNO_BUILD)-$(USER)
SINGULARITY_DATA = $(shell pwd)/singularity
SINGULARITY_LOG_DIR = $(HOME)/.singularity/instances/logs/$(shell hostname)/$(USER)
SINGULARITY_LOG_STDERR = $(SINGULARITY_LOG_DIR)/$(SINGULARITY_INSTANCE_NAME).err
SINGULARITY_LOG_STDOUT = $(SINGULARITY_LOG_DIR)/$(SINGULARITY_INSTANCE_NAME).out
SINGULARITY_ANNO_LOGS := $(shell pwd)/logs
# Large tmp storage is needed for gnomAD data generation. Set this to somewhere with at least 50GB of space if not
# available on /tmp's partition
TMP_DIR ?= /tmp

# get user / group ID so data generated/downloaded isn't root owned
DOCKER_USER ?= $(shell id -u):$(shell id -g)

# Use docker buildkit for faster builds
DOCKER_BUILDKIT := 1

# if DO_CREDS is set, the file should be mounted into the docker container
ifneq ($(DO_CREDS),)
override ANNOBUILDER_OPTS += --env-file $(shell realpath $(DO_CREDS))
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
.PHONY: any build run kill shell logs restart release singularity-release _fix_download_perms

# used to override the default CONTAINER_NAME to anything matching /anno-.*-$(USER)/
# must be placed _before_ the desired action
# e.g., to stop and rm the first matching container: make any kill
any:
	$(eval CONTAINER_NAME = $(shell docker ps | awk '/anno-.*-$(USER)/ {print $$NF}'))
	@true

build: ## build Docker image of 'prod' target named $IMAGE_NAME
	docker build -t $(IMAGE_NAME) $(BUILD_OPTS) --build-arg BUILDKIT_INLINE_CACHE=1 --target prod .

# like build, but buildkit is disabled to allow access to intermediate layers for easier debugging
build-debug:
	DOCKER_BUILDKIT= docker build -t $(IMAGE_NAME) $(BUILD_OPTS) --target prod .

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
	--tmpfs /pg_uta \
	--name $(CONTAINER_NAME)-test \
	$(IMAGE_NAME) /anno/ops/run_tests.sh

test-ops: ## run the ops tests in $IMAGE_NAME. WARNING: will overwrite data dir if attached and running manually
	docker run -t --rm \
	--name $(CONTAINER_NAME)-ops-test \
	$(IMAGE_NAME) /anno/ops/run_ops_tests.sh

localclean: ## remove data, rawdata, thirdparty dirs and docker volumes
	rm -rf thirdparty/ data/ rawdata/
	-docker volume rm ella-anno-exts

##---------------------------------------------------------------------
## AnnoBuilder: generate / download processed datasets for anno
##   Docker commands run in $ANNOBUILDER_IMAGE_NAME named $ANNOBUILDER_CONTAINER_NAME
##   Other variables: PKG_NAME, DO_CREDS, ENTREZ_API_KEY, RUN_CMD_ARGS, ANNO_DATA, ANNO_RAWDATA, DEBUG
##---------------------------------------------------------------------
.PHONY: build-annobuilder annobuilder annobuilder-shell annobuilder-exec download-data download-package upload-data upload-package
.PHONY: generate-data generate-package verify-digital-ocean install-thirdparty install-package tar-data untar-data _fix_download_perms

ifeq ($(CI_REGISTRY_IMAGE),)
# running locally, use tty
TERM_OPTS := -it
else
TERM_OPTS := -i
endif

# ensure $ANNO_DATA exists so it's not created as root owned by docker
# in case FASTA is a symlink, resolve its path, mount directly and set env var in container
define annobuilder-template
mkdir -p $(ANNO_DATA) 
ifneq ($(FASTA),)
override ANNOBUILDER_OPTS += -v $(shell readlink -e $(FASTA)):/fasta.fa -e FASTA=/fasta.fa
endif
docker run --rm $(TERM_OPTS) \
	$(ANNOBUILDER_OPTS) \
	-u "$(DOCKER_USER)" \
	-v $(TMP_DIR):/tmp \
	-v $(ANNO_DATA):/anno/data \
	$(ANNOBUILDER_IMAGE_NAME) \
	bash -ic "$(RUN_CMD) $(RUN_CMD_ARGS)"
endef

build-annobuilder: ## build Docker image of 'builder' target named $ANNOBUILDER_IMAGE_NAME
	docker build -t $(ANNOBUILDER_IMAGE_NAME) $(BUILD_OPTS) --build-arg BUILDKIT_INLINE_CACHE=1 --target builder .

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

download-data: _fix_download_perms ## download all datasets from DigitalOcean
	$(eval RUN_CMD := python3 /anno/ops/sync_data.py --download)
	$(annobuilder-template)

download-package: _fix_download_perms ## download the dataset for $PKG_NAME
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
	$(eval ANNOBUILDER_OPTS += -v $(ANNO_RAWDATA):/anno/rawdata)
	$(eval RUN_CMD := python3 /anno/ops/sync_data.py --generate)
	$(annobuilder-template)

generate-package: ## generate new/updated dataset for $PKG_NAME based on the version in datasets.json
	@$(call check_defined, PKG_NAME, 'Use PKG_NAME to specify which package to generate')
	mkdir -p $(ANNO_RAWDATA)
	$(eval ANNOBUILDER_OPTS += -v $(ANNO_RAWDATA):/anno/rawdata)
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

# ensures that files generated / downloaded inside docker are user owned instead of root owned
_fix_download_perms:
	@true
#(eval override RUN_CMD_ARGS += ; $(PRE_RUN_CMD) chown -R $(LOCAL_UID):$(LOCAL_GID) /anno/data)


##---------------------------------------------------------------------
## Singularity
##   Like the above sections, but using Singularity $SINGULARITY_IMAGE_NAME instance named 
##   $SINGULARITY_INSTANCE_NAME.
##   Other vars: SINGULARITY_DATA, ANNO_DATA, SINGULARITY_ANNO_LOGS
##---------------------------------------------------------------------
.PHONY: singularity-test singularity-shell singularity-start singularity-stop

# NOTE: how many of the singularity rules are even used?

singularity-build: ## builds a singularity image from the Docker image $IMAGE_NAME 
	# Use git archive to create docker context, to prevent modified files from entering the image.
	@-docker rm -f ella-anno-tmp-registry
	docker run --rm -d -p 29000:5000 --name ella-anno-tmp-registry registry:2
	docker tag $(IMAGE_NAME) localhost:29000/$(IMAGE_NAME)
	docker push localhost:29000/$(IMAGE_NAME)
	SINGULARITY_NOHTTPS=1 singularity build $(SINGULARITY_IMAGE_NAME) docker://localhost:29000/$(IMAGE_NAME)
	docker rm -f ella-anno-tmp-registry

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

# Sandbox dev options so don't have to rebuild the image all the time
# Still uses same SINGULARITY_INSTANCE_NAME, so -stop, -test, -shell all still work
singularity-build-dev: gen-singularityfile
	sudo singularity build --sandbox $(SINGULARITY_SANDBOX_PATH) $(SINGULARITY_DEF_FILE)
	sudo chown -R $(whoami). $(SINGULARITY_SANDBOX_PATH)

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

check-release-tag:
	@$(call check_defined, RELEASE_TAG, 'Missing tag. Please provide a value on the command line')
	git rev-parse --verify "refs/tags/$(RELEASE_TAG)^{tag}"
	git ls-remote --exit-code --tags origin "refs/tags/$(RELEASE_TAG)"

release: ## create a clean prod Docker $IMAGE_NAME for using git tag $RELEASE_TAG
	git archive --format tar.gz $(RELEASE_TAG) | docker build -t $(IMAGE_NAME) --target prod -

singularity-release: release singularity-build ## create a prod Singularity image SINGULARITY_IMAGE_NAME based on IMAGE_NAME

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

ENV = $(shell which env)
local-vars: _disable_origins _list_vars ## print out vars set by command line and in the Makefile
	@true
