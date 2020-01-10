BRANCH ?= $(shell git rev-parse --abbrev-ref HEAD)
API_PORT ?= 6000-6100
TARGETS_FOLDER ?= /home/oyvinev/repositories/anno-targets
TARGETS_OUT ?= /media/oyvinev/Storage/anno-targets-out
SAMPLE_REPO ?= /media/oyvinev/Storage/sample-repo

RELEASE_TAG ?= $(shell git tag -l --points-at HEAD)
ifneq ($(RELEASE_TAG),)
ANNO_BUILD := anno-$(RELEASE_TAG)
BUILDER_BUILD := annobuilder-$(RELEASE_TAG)
BUILD_OPTS += -t local/anno:$(RELEASE_TAG)
else
ANNO_BUILD = anno-$(BRANCH)
BUILDER_BUILD = annobuilder-$(BRANCH)
endif

BUNDLE ?= /media/oyvinev/1E51A9957C59176F/vcpipe-bundle
SENSITIVE_DB ?= /media/oyvinev/1E51A9957C59176F/vcpipe-bundle/fake-sensitive-db
CONTAINER_NAME ?= $(ANNO_BUILD)-$(USER)
IMAGE_NAME = local/$(ANNO_BUILD)
ANNOBUILDER_CONTAINER_NAME ?= $(BUILDER_BUILD)
ANNOBUILDER_IMAGE_NAME = local/$(BUILDER_BUILD)
ANNOBUILDER_OPTS = -e ENTREZ_API_KEY=$(ENTREZ_API_KEY)
SINGULARITY_IMAGE_NAME = $(ANNO_BUILD).sif
SINGULARITY_SANDBOX_NAME = $(ANNO_BUILD)/
SINGULARITY_INSTANCE_NAME = $(ANNO_BUILD)-$(USER)
SINGULARITY_DATA_BASE = $(shell pwd)/singularity
SINGULARITY_DEFAULTDATA = "$(SINGULARITY_DATA_BASE)/default"
SINGULARITY_USERDATA = "$(SINGULARITY_DATA_BASE)/$(USER)"
SINGULARITY_DEF_FILE = Singularity.$(ANNO_BUILD)
# Large tmp storage is needed for gnomAD data generation. Set this to somewhere with at least 50GB of space if not
# available on /tmp's partition
TMP_DIR ?= /tmp
UTA_VERSION=uta_20180821
.PHONY: help

help :
	@echo ""
	@echo "-- DEV COMMANDS --"
	@echo "make build		- build image $(IMAGE_NAME)"
	@echo "make dev			- run image $(IMAGE_NAME), with container name $(CONTAINER_NAME) :: API_PORT and ANNO_OPTS available as variables"
	@echo "make kill		- stop and remove $(CONTAINER_NAME)"
	@echo "make shell		- get a bash shell into $(CONTAINER_NAME)"
	@echo "make logs		- tail logs from $(CONTAINER_NAME)"
	@echo "make restart		- restart container $(CONTAINER_NAME)"
	@echo "make test		- run tests in container $(CONTAINER_NAME)"

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


#---------------------------------------------
# DEVELOPMENT
#---------------------------------------------
.PHONY: any build run dev kill shell logs restart automation

any:
	$(eval CONTAINER_NAME = $(shell docker ps | awk '/anno-.*-$(USER)/ {print $$NF}'))
	@true

build:
	docker build -t $(IMAGE_NAME) $(BUILD_OPTS) --target prod .

run:
	docker run -d \
	-e UTA_DB_URL=postgresql://uta_admin@localhost:5432/uta/$(UTA_VERSION) \
	-e UTA_VERSION=$(UTA_VERSION) \
	-e TARGET_DATA=/target_data \
	$(ANNO_OPTS) \
	--restart=always \
	--name $(CONTAINER_NAME) \
	-p $(API_PORT):6000 \
	-v $(shell pwd)/data:/anno/data \
	-v $(TARGETS_FOLDER):/targets \
	-v $(TARGETS_OUT):/targets-out \
	-v $(SAMPLE_REPO):/samples \
	-v $(BUNDLE):/target_data/bundle \
	-v $(SENSITIVE_DB):/target_data/sensitive-db \
	$(IMAGE_NAME)

dev: run

logs:
	docker logs -f $(CONTAINER_NAME)

stop:
	docker stop $(CONTAINER_NAME) || :

restart: stop
	docker start $(CONTAINER_NAME) || :

kill:
	docker rm -f -v $(CONTAINER_NAME) || :

update_seqrepo:
	docker run --rm \
	--name $(CONTAINER_NAME) \
	-v $(shell pwd):/anno \
	$(IMAGE_NAME) \
	make update_seqrepo_internal
	tar -C data -cf data/seqrepo.tar seqrepo

update_seqrepo_internal:
	mkdir -p /anno/data/seqrepo
	rm -rf /anno/data/seqrepo/*
	seqrepo -r /anno/data/seqrepo -v pull

test:
	docker run --rm -t \
	-v $(shell pwd)/data:/anno/data \
	--name $(CONTAINER_NAME) \
	$(IMAGE_NAME) /anno/ops/run_tests.sh

cleanup:
	docker run --rm -t \
	-v $(shell pwd):/anno \
	$(IMAGE_NAME) git clean -xdf --exclude .vscode

localclean:
	rm -rf thirdparty/ data/ rawdata/

shell:
	docker exec -it $(CONTAINER_NAME) bash

#---------------------------------------------------------------------
# AnnoBuilder: generate / download processed datasets for anno
#---------------------------------------------------------------------

define annobuilder-template
docker run --rm -t \
	$(ANNOBUILDER_OPTS) \
	-v $(TMP_DIR):/tmp \
	-v $(PWD):/anno \
	$(ANNOBUILDER_IMAGE_NAME) \
	$(RUN_CMD)
endef

build-base:
	docker build -t local/anno-base --target base .

build-annobuilder:
	docker build -t $(ANNOBUILDER_IMAGE_NAME) --target builder .

annobuilder:
	docker run -td \
		--restart=always \
		--name $(ANNOBUILDER_CONTAINER_NAME) \
		$(ANNOBUILDER_OPTS) \
		-v $(shell pwd):/anno \
		$(ANNOBUILDER_IMAGE_NAME) \
		sleep infinity

annobuilder-shell:
	docker exec -it $(ANNOBUILDER_CONTAINER_NAME) /bin/bash

annobuilder-exec:
	@$(call check_defined, RUN_CMD, 'Use RUN_CMD="python something.py opt1 ..." to specify command to run')
	$(annobuilder-template)

download-data:
	$(eval ANNOBUILDER_OPTS += --user $(shell id -u):$(shell id -g))
	$(eval RUN_CMD := python3 /anno/ops/sync_data.py --download)
	$(annobuilder-template)

download-package:
	@$(call check_defined, PKG_NAME, 'Use PKG_NAME to specify which package to download')
	$(eval ANNOBUILDER_OPTS += --user $(shell id -u):$(shell id -g))
	$(eval RUN_CMD := python3 /anno/ops/sync_data.py --download -d $(PKG_NAME))
	$(annobuilder-template)

upload-data:
	@$(call check_defined, DO_CREDS, 'Use DO_CREDS to specify a file containing SPACES_KEY and SPACES_SECRET')
	$(eval ANNOBUILDER_OPTS += $(DO_CREDS))
	$(eval RUN_CMD := python3 /anno/ops/sync_data.py --upload)
	$(annobuilder-template)

upload-package:
	@$(call check_defined, DO_CREDS, 'Use DO_CREDS to specify a file containing SPACES_KEY and SPACES_SECRET')
	@$(call check_defined, PKG_NAME, 'Use PKG_NAME to specify which package to download')
	$(eval ANNOBUILDER_OPTS += $(DO_CREDS))
	$(eval RUN_CMD := python3 /anno/ops/sync_data.py --upload -d $(PKG_NAME))
	$(annobuilder-template)

generate-data:
	@$(call check_defined, ENTREZ_API_KEY, 'Make sure ENTREZ_API_KEY is set and exported so clinvar data can be built successfully')
	$(eval RUN_CMD := python3 /anno/ops/sync_data.py --generate)
	$(annobuilder-template)

generate-package:
	@$(call check_defined, PKG_NAME, 'Use PKG_NAME to specify which package to generate')
	$(eval RUN_CMD := python3 /anno/ops/sync_data.py --generate -d $(PKG_NAME))
	$(annobuilder-template)

# installed directly in Dockerfile, but commands here for reference or local install
install-thirdparty:
	$(eval RUN_CMD := python3 /anno/ops/sync_thirdparty.py --clean)
	$(annobuilder-template)

# installed directly in Dockerfile, but commands here for reference or local install
install-package:
	@$(call check_defined, PKG_NAME, 'Use PKG_NAME to specify which package to install')
	$(eval RUN_CMD := python3 /anno/ops/sync_thirdparty.py --clean -p $(PKG_NAME))
	$(annobuilder-template)

tar-data:
	tar cvf data.tar data/


#---------------------------------------------------------------------
# SINGULARITY
#---------------------------------------------------------------------
.PHONY: singularity-test singularity-shell singularity-start singularity-stop

singularity-build: gen-singularityfile
	[ -e $(SINGULARITY_SANDBOX_NAME) ] || sudo singularity build --sandbox $(SINGULARITY_SANDBOX_NAME) $(SINGULARITY_DEF_FILE)
	mkdir -p singularity
	sudo singularity exec \
		--writable \
		-B $(shell pwd)/ops:/anno/ops \
		-B $(shell pwd)/data:/anno/data \
		-B $(shell pwd)/singularity:/anno/singularity \
		$(SINGULARITY_SANDBOX_NAME) \
		/anno/ops/pg_setup_singularity.sh
	sudo singularity build $(SINGULARITY_IMAGE_NAME) $(SINGULARITY_SANDBOX_NAME)
	@sudo rm -rf $(SINGULARITY_SANDBOX_NAME)

gen-singularityfile:
	@IMAGE_NAME=$(IMAGE_NAME) bash Singularity_template > $(SINGULARITY_DEF_FILE)

singularity-start: uta-data
	singularity instance start \
		-B $(shell pwd)/data:/anno/data \
		-B $(shell mktemp -d):/anno/.cache \
		-B $(SINGULARITY_USERDATA)/pg_uta:/pg_uta \
		$(SINGULARITY_IMAGE_NAME) $(SINGULARITY_INSTANCE_NAME)

singularity-test:
	-PYTHONPATH= singularity exec instance://$(SINGULARITY_INSTANCE_NAME) supervisorctl -c /anno/ops/supervisor.cfg stop all
	PYTHONPATH= singularity exec instance://$(SINGULARITY_INSTANCE_NAME) /anno/ops/run_tests.sh
	PYTHONPATH= singularity exec instance://$(SINGULARITY_INSTANCE_NAME) supervisorctl -c /anno/ops/supervisor.cfg start all

singularity-stop:
	singularity instance stop $(SINGULARITY_INSTANCE_NAME)

singularity-shell:
	PYTHONPATH= singularity shell instance://$(SINGULARITY_INSTANCE_NAME)

uta-data:
	[ -d $(SINGULARITY_USERDATA) ] || rsync -az $(SINGULARITY_DEFAULTDATA)/ $(SINGULARITY_USERDATA) --info=progress2
	@chmod -R 700 $(SINGULARITY_USERDATA)/pg_uta

#---------------------------------------------
# RELEASE
#---------------------------------------------

check-release-tag:
	@$(call check_defined, RELEASE_TAG, 'Missing tag. Please provide a value on the command line')
	git rev-parse --verify "refs/tags/$(RELEASE_TAG)^{tag}"
	git ls-remote --exit-code --tags origin "refs/tags/$(RELEASE_TAG)"

release: tar-data check-release-tag
	mkdir -p release/
	tar cvf release/anno-$(RELEASE_TAG)-src.tar \
		--exclude=thirdparty \
		--exclude=".git*" \
		--exclude="*data" \
		--exclude=release \
		--exclude=.vscode \
		--exclude="*.sif" \
		./

singularity-release: check-release-tag tar-data singularity-build
	mkdir -p release/
	tar cvf release/anno-$(RELEASE_TAG)-singularity.tar \
		Makefile \
		$(SINGULARITY_IMAGE_NAME) \
		singularity/
