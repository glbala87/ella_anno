FROM debian:buster-20200908 AS base

LABEL maintainer="OUS AMG <ella-support@medisin.uio.no>"

ENV DEBIAN_FRONTEND=noninteractive \
    LANGUAGE=C.UTF-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH=/anno/bin:$PATH \
    PERL5LIB=/anno/thirdparty/ensembl-vep-release/:/anno/thirdparty/vcftools/lib

RUN echo 'Acquire::ForceIPv4 "true";' | tee /etc/apt/apt.conf.d/99force-ipv4

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    bash \
    bcftools \
    build-essential \
    bzip2 \
    ca-certificates \
    curl \
    cython \
    cython3 \
    file \
    fontconfig \
    gawk \
    gcc \
    git \
    gnupg2 \
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
    rsync \
    supervisor \
    vim \
    watch \
    wget \
    zlib1g-dev && \
    echo "Cleanup:" && \
    apt-get clean && \
    apt-get autoclean && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /usr/share/doc/* /usr/share/man/* /usr/share/groff/* /usr/share/info/* /tmp/* /var/cache/apt/* /root/.cache

RUN useradd -ms /bin/bash anno-user

COPY pip-requirements /dist/
RUN pip3 install -U setuptools wheel && \
    pip3 install -r /dist/pip-requirements

COPY pip-requirements-py3 /dist/
RUN pip3 install -U setuptools wheel && \
    pip3 install -r /dist/pip-requirements-py3

RUN curl -L https://github.com/tianon/gosu/releases/download/1.7/gosu-amd64 -o /usr/local/bin/gosu && chmod u+x /usr/local/bin/gosu && \
    # Cleanup
    cp -R /usr/share/locale/en\@* /tmp/ && rm -rf /usr/share/locale/* && mv /tmp/en\@* /usr/share/locale/ && \
    rm -rf /usr/share/doc/* /usr/share/man/* /usr/share/groff/* /usr/share/info/* /tmp/* /var/cache/apt/* /root/.cache

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

COPY ./ops/install_thirdparty.py ./ops/util.py /anno/ops/
COPY ./bin /anno/bin
# install thirdparty packages
RUN python3 /anno/ops/install_thirdparty.py --clean

COPY ./scripts /anno/scripts/
COPY ./ops/sync_data.py ./ops/spaces_config.json ./ops/datasets.json ./ops/package_data ./ops/unpack_data ./ops/postgresql.conf ./ops/pg_sourceme /anno/ops/



#####################
# Production
#####################

FROM base AS prod

WORKDIR /anno

ENV ANNO=/anno \
    FASTA=/anno/data/FASTA/human_g1k_v37_decoy.fasta.gz \
    PYTHONPATH=/anno/src \
    TARGETS=/targets \
    TARGETS_OUT=/targets-out \
    SAMPLES=/samples \
    PATH=/anno/bin:$TARGETS/targets:$PATH \
    LD_LIBRARY_PATH=/anno/thirdparty/ensembl-vep-release/htslib \
    WORKFOLDER=/tmp/annowork \
    ANNO_DATA=/anno/data

COPY . /anno
COPY --from=builder /anno/thirdparty /anno/thirdparty
COPY --from=builder /anno/bin /anno/bin
RUN [ -d /anno/data ] || mkdir /anno/data

# Set supervisor as default cmd
CMD /anno/ops/entrypoint.sh
