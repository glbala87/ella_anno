# debian:bullseye-20210511
FROM debian@sha256:f230ae5ea58822057728fbc43b207f4fb02ab1c32c75c08d25e8e511bfc83446 AS base

ENV DEBIAN_FRONTEND=noninteractive \
    LANGUAGE=C.UTF-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PERL5LIB=/anno/thirdparty/ensembl-vep-release:/anno/thirdparty/vcftools/lib

RUN echo 'Acquire::ForceIPv4 "true";' | tee /etc/apt/apt.conf.d/99force-ipv4

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    bash \
    bcftools \
    build-essential \
    bzip2 \
    ca-certificates \
    curl \
    cython3 \
    file \
    fontconfig \
    gawk \
    gcc \
    git \
    gnupg2 \
    gosu \
    htop \
    jq \
    less \
    libarchive-extract-perl \
    libarchive-zip-perl \
    libbz2-dev \
    libcurl4-openssl-dev \
    libdbi-perl \
    libjson-perl \
    liblzma-dev \
    libperlio-gzip-perl \
    libset-intervaltree-perl \
    libssl-dev \
    libwww-perl \
    make \
    mlocate \
    postgresql \
    postgresql-client \
    postgresql-common \
    procps \
    python3 \
    python3-dev \
    python3-pip \
    python3-venv \
    rsync \
    tcl \
    vim \
    watch \
    wget \
    zlib1g-dev && \
    echo "Cleanup:" && \
    apt-get clean && \
    apt-get autoclean && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /usr/share/doc/* /usr/share/man/* /usr/share/groff/* /usr/share/info/* /tmp/* /var/cache/apt/* /root/.cache

ENV ANNO_USER=anno-user
RUN useradd -ms /bin/bash ${ANNO_USER}

ARG pipenv_version=2021.5.29
RUN pip3 install -U pip setuptools wheel pipenv==${pipenv_version}

# create default ANNO_DATA / ANNO_RAWDATA dirs and set permissions to let data actions be run without root
RUN mkdir -p /dist /anno/data /anno/rawdata /anno/thirdparty && \
    chown ${ANNO_USER}. /dist /anno /anno/data /anno/rawdata /anno/thirdparty && \
    chmod +s /dist /anno/data /anno/rawdata /anno/thirdparty

# do all copying / installing as anno-user
USER ${ANNO_USER}

ENV PIPENV_PIPFILE=/anno/Pipfile \
    PIPENV_NOSPIN=1 \
    PIPENV_VERBOSITY=-1 \
    WORKON_HOME=/dist
ENV VIRTUAL_ENV=${WORKON_HOME}/anno-python

WORKDIR ${WORKON_HOME}
COPY --chown=${ANNO_USER}:${ANNO_USER} Pipfile Pipfile.lock /anno/
# we want VIRTUAL_ENV available for the eventual symlink, but it gets in the way during
# initial installation as there is nothing there yet
RUN VIRTUAL_ENV= pipenv install --deploy && \
    ln -s anno-NiVSU3vV ${VIRTUAL_ENV}
# the hash after anno is deterministic and won't change as long the Pipfile is in the same place
#   ref: https://pipenv.pypa.io/en/latest/install/#virtualenv-mapping-caveat

USER root

LABEL org.opencontainers.image.authors="OUS AMG <ella-support@medisin.uio.no>"

ENV PATH=${VIRTUAL_ENV}/bin:/anno/bin:${PATH}

#####################
# Builder - for installing thirdparty and generating / downloading data
#####################

FROM base AS builder

# add the google-cloud repo for gsutil/google-cloud-sdk, used to more easily download the gnomAD data
# It is not used by anno, so is only included in the builder image
RUN apt-get update && \
    apt-get install -y apt-transport-https apt-utils curl ca-certificates gnupg && \
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
    | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    autoconf \
    default-mysql-client \
    g++ \
    google-cloud-sdk \
    libmodule-build-perl \
    libxml-xpath-perl \
    pkg-config

WORKDIR /anno
USER ${ANNO_USER}
RUN pipenv install --dev --deploy

COPY --chown=${ANNO_USER}:${ANNO_USER} ./ops/install_thirdparty.py ./ops/util.py /anno/ops/
COPY --chown=${ANNO_USER}:${ANNO_USER} ./bin /anno/bin
# install thirdparty packages
RUN python3 /anno/ops/install_thirdparty.py --clean

COPY --chown=${ANNO_USER}:${ANNO_USER} ./scripts /anno/scripts/
COPY --chown=${ANNO_USER}:${ANNO_USER} ./ops /anno/ops/

#####################
# Devcontainer
#####################

# part builder, part prod

FROM builder AS dev

USER root
ARG SHFMT_VERSION=v3.3.1
# need to manually install shfmt for shell-format extension
RUN wget https://github.com/mvdan/sh/releases/download/${SHFMT_VERSION}/shfmt_${SHFMT_VERSION}_linux_amd64 -O /root/shfmt && \
    install -m=755 /root/shfmt /usr/local/bin/shfmt

RUN apt-get update && apt-get install -y --no-install-recommends shellcheck

ENV ANNO=/anno \
    FASTA=/anno/data/FASTA/human_g1k_v37_decoy.fasta.gz \
    TARGETS=/targets \
    PYTHONPATH=/anno/src \
    TARGETS_OUT=/targets-out \
    SAMPLES=/samples \
    LD_LIBRARY_PATH=/anno/thirdparty/ensembl-vep-release/htslib \
    WORKFOLDER=/tmp/annowork \
    ANNO_DATA=/anno/data
ENV PATH=${TARGETS}/targets:${PATH}

RUN umask 000 && mkdir -p ${TARGETS} ${TARGETS_OUT} ${SAMPLES} /scratch && \
    chown ${ANNO_USER}:${ANNO_USER} ${TARGETS} ${TARGETS_OUT} ${SAMPLES} /scratch

# set up perms for extension volume/cache
RUN mkdir -p /home/${ANNO_USER}/.vscode-server/extensions && \
    chown -R ${ANNO_USER}:${ANNO_USER} /home/${ANNO_USER}

# Set supervisor as default cmd
CMD ["/anno/ops/entrypoint.sh"]


#####################
# Production
#####################

FROM base AS prod

WORKDIR /anno

COPY --chown=${ANNO_USER}:${ANNO_USER} --from=builder /anno/thirdparty /anno/thirdparty
COPY --chown=${ANNO_USER}:${ANNO_USER} --from=builder /anno/bin /anno/bin
COPY --chown=${ANNO_USER} . /anno

ENV ANNO=/anno \
    FASTA=/anno/data/FASTA/human_g1k_v37_decoy.fasta.gz \
    TARGETS=/targets \
    PYTHONPATH=/anno/src \
    TARGETS_OUT=/targets-out \
    SAMPLES=/samples \
    LD_LIBRARY_PATH=/anno/thirdparty/ensembl-vep-release/htslib \
    WORKFOLDER=/tmp/annowork \
    ANNO_DATA=/anno/data
ENV PATH=${TARGETS}/targets:${PATH}

RUN umask 000 && mkdir -p ${TARGETS} ${TARGETS_OUT} ${SAMPLES} /scratch && \
    chown ${ANNO_USER}:${ANNO_USER} ${TARGETS} ${TARGETS_OUT} ${SAMPLES} /scratch

# Set supervisor as default cmd
CMD ["/anno/ops/entrypoint.sh"]
