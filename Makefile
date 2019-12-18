BRANCH ?= $(shell git rev-parse --abbrev-ref HEAD)
API_PORT ?= 6000-6100
TARGETS_FOLDER ?= /home/oyvinev/repositories/anno-targets
TARGETS_OUT ?= /media/oyvinev/Storage/anno-targets-out
SAMPLE_REPO ?= /media/oyvinev/Storage/sample-repo
#TARGET_DATA ?= /media/oyvinev/Storage/vcpipe-bundle/dev
BUNDLE ?= /media/oyvinev/1E51A9957C59176F/vcpipe-bundle
SENSITIVE_DB ?= /media/oyvinev/1E51A9957C59176F/vcpipe-bundle/fake-sensitive-db
CONTAINER_NAME ?= anno-$(BRANCH)-$(USER)
IMAGE_NAME = local/anno-$(BRANCH)
ANNOBUILDER_CONTAINER_NAME ?= annobuilder-$(BRANCH)
ANNOBUILDER_IMAGE_NAME = local/annobuilder-$(BRANCH)
ANNOBUILDER_OPTS = -e ENTREZ_API_KEY=$(ENTREZ_API_KEY)
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
	$(eval RUN_CMD := python3 /anno/ops/sync_data.py --download)
	$(annobuilder-template)

download-package:
	@$(call check_defined, PKG_NAME, 'Use PKG_NAME to specify which package to download')
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
	$(eval RUN_CMD := python3 /anno/ops/sync_data.py --generate)
	$(annobuilder-template)

generate-package:
	@$(call check_defined, PKG_NAME, 'Use PKG_NAME to specify which package to generate')
	$(eval RUN_CMD := python3 /anno/ops/sync_data.py --generate -d $(PKG_NAME))
	$(annobuilder-template)

install-thirdparty:
	$(eval RUN_CMD := python3 /anno/ops/sync_thirdparty.py --clean)
	$(annobuilder-template)

install-package:
	@$(call check_defined, PKG_NAME, 'Use PKG_NAME to specify which package to install')
	$(eval RUN_CMD := python3 /anno/ops/sync_thirdparty.py --clean -p $(PKG_NAME))
	$(annobuilder-template)

tar-data:
	tar cvf data.tar data/

tar-thirdparty:
	tar cvzf thirdparty.tar.gz thirdparty/

tar-all: tar-thirdparty tar-data


#---------------------------------------------
# RELEASE
#---------------------------------------------

check-release-tag:
	@$(call check_defined, RELEASE_TAG, 'Missing tag. Please provide a value on the command line')
	git rev-parse --verify "refs/tags/$(RELEASE_TAG)^{tag}"
	git ls-remote --exit-code --tags origin "refs/tags/$(RELEASE_TAG)"

release: tar-all check-release-tag
	mkdir -p release/
	tar cvf release/anno-$(RELEASE_TAG)-src.tar --exclude=thirdparty --exclude=".git*" --exclude="*data" --exclude=release --exclude=.vscode ./
	# git archive -o anno-$(RELEASE_TAG)-src.tar $(RELEASE_TAG)
