
FROM debian:buster-20191014 AS buildtest
RUN echo "in container:" && export

FROM debian:buster-20191014 AS base
LABEL maintainer="OUS AMG <ella-support@medisin.uio.no>"

ENV DEBIAN_FRONTEND=noninteractive \
    LANGUAGE=C.UTF-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH=/anno/bin:$PATH

COPY . /anno
WORKDIR /anno


RUN echo 'Acquire::ForceIPv4 "true";' | tee /etc/apt/apt.conf.d/99force-ipv4

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash \
        build-essential \
        bzip2 \
        ca-certificates \
        curl \
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
        libdbi-perl \
        libjson-perl \
        liblzma-dev \
        libperlio-gzip-perl \
        libset-intervaltree-perl \
        libwww-perl \
        make \
        mlocate \
        postgresql \
        postgresql-client \
        postgresql-common \
        procps \
        python \
        python-dev \
        python-pip \
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
        pkg-config

RUN pip install -U setuptools wheel && pip install -r annobuilder-requirements.txt && pip3 install boto3==1.10.6

# install thirdparty packages
RUN python3 /anno/ops/sync_thirdparty.py --clean

#####################
# Production
#####################

FROM base AS prod
COPY --from=builder /anno/thirdparty /anno/thirdparty
COPY --from=builder /anno/bin /anno/bin

RUN curl -L https://github.com/tianon/gosu/releases/download/1.7/gosu-amd64 -o /usr/local/bin/gosu && chmod u+x /usr/local/bin/gosu && \
    # Cleanup
    cp -R /usr/share/locale/en\@* /tmp/ && rm -rf /usr/share/locale/* && mv /tmp/en\@* /usr/share/locale/ && \
    rm -rf /usr/share/doc/* /usr/share/man/* /usr/share/groff/* /usr/share/info/* /tmp/* /var/cache/apt/* /root/.cache

ADD pip-requirements /dist/requirements.txt
RUN pip install -U setuptools wheel && pip install -r /dist/requirements.txt

# Init UTA Postgres database
ENV UTA_VERSION=uta_20180821 \
    PGDATA=/pg_uta

RUN service postgresql stop && \
    wget http://dl.biocommons.org/uta/${UTA_VERSION}.pgd.gz -O /${UTA_VERSION}.pgd.gz && \
    /anno/ops/pg_startup init

ENV UTA_DB_URL=postgresql://uta_admin@localhost:5432/uta/${UTA_VERSION} \
    ANNO=/anno \
    FASTA=/anno/data/FASTA/human_g1k_v37_decoy.fasta \
    PYTHONPATH=/anno/src \
    TARGETS=/targets \
    TARGETS_OUT=/targets-out \
    SAMPLES=/samples \
    PATH=/anno/bin:$TARGETS/targets:$PATH \
    PERL5LIB=/anno/thirdparty/ensembl-vep-release/lib/:/anno/thirdparty/vcftools/lib \
    WORKFOLDER=/tmp/annowork \
    HGVS_SEQREPO_DIR=/anno/data/seqrepo/2019-06-20

# Set supervisor as default cmd
CMD /anno/ops/entrypoint.sh
