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
	docker build -t $(IMAGE_NAME) $(BUILD_OPTS) .

run:
	docker run -d \
	-e UTA_DB_URL=postgresql://uta_admin@localhost:5432/uta/$(UTA_VERSION) \
	-e UTA_VERSION=$(UTA_VERSION) \
	-e TARGET_DATA=/target_data \
	$(ANNO_OPTS) \
	--restart=always \
	--name $(CONTAINER_NAME) \
	-p $(API_PORT):6000 \
	-v $(shell pwd):/anno \
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
	-v $(shell pwd):/anno \
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


#---------------------------------------------
# RELEASE
#---------------------------------------------

check-release-tag:
	@$(call check_defined, RELEASE_TAG, 'Missing tag. Please provide a value on the command line')
	git rev-parse --verify "refs/tags/$(RELEASE_TAG)^{tag}"
	git ls-remote --exit-code --tags origin "refs/tags/$(RELEASE_TAG)"

release: # check-release-tag
	[ -e thirdparty.tar.gz ] || tar cvzf thirdparty.tar.gz thirdparty/
	[ -e data.tar ] || tar cvf data.tar data/
	mkdir -p release/
	tar -C .. cvf --exclude="thirdparty" --exclude=".git*" --exclude="*data" --exclude="release" --include="thirdparty.tar" anno-$(RELEASE_TAG)-src.tar anno
	mv ../anno-$(RELEASE_TAG)-src.tar release/
	# git archive -o anno-$(RELEASE_TAG)-src.tar $(RELEASE_TAG)
