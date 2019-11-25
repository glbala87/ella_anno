FROM debian:buster-20191014
ENV DEBIAN_FRONTEND noninteractive \
    LANGUAGE C.UTF-8 \
    LANG C.UTF-8 \
    LC_ALL C.UTF-8

RUN echo 'Acquire::ForceIPv4 "true";' | tee /etc/apt/apt.conf.d/99force-ipv4

# Install as much as reasonable in one go to reduce image size
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    autoconf \
    pkg-config \
    gawk \
    gnupg2 \
    python \
    python-dev \
    python-tk \
    python-numpy \
    bash \
    curl \
    make \
    build-essential \
    gcc \
    supervisor \
    ca-certificates \
    less \
    sudo \
    htop \
    fontconfig \
    watch \
    vim \
    python3-dev \
    python3-pip \
    rsync \
    wget \
    git \
    zlib1g-dev \
    libbz2-dev \
    liblzma-dev \
    libarchive-extract-perl \
    libarchive-zip-perl \
    libdbi-perl \
    libjson-perl \
    libmodule-build-perl \
    libperlio-gzip-perl \
    libset-intervaltree-perl \
    default-mysql-client \
    postgresql \
    postgresql-common \
    postgresql-client && \
    # Additional tools
    curl -SLk 'https://bootstrap.pypa.io/get-pip.py' | python && \
    curl -L https://github.com/tianon/gosu/releases/download/1.7/gosu-amd64 -o /usr/local/bin/gosu && chmod u+x /usr/local/bin/gosu && \
    # Cleanup
    cp -R /usr/share/locale/en\@* /tmp/ && rm -rf /usr/share/locale/* && mv /tmp/en\@* /usr/share/locale/ && \
    rm -rf /usr/share/doc/* /usr/share/man/* /usr/share/groff/* /usr/share/info/* /tmp/* /var/cache/apt/* /root/.cache

ADD pip-requirements /dist/requirements.txt
RUN pip install -r /dist/requirements.txt

# Init UTA Postgres database
ENV UTA_VERSION uta_20180821
ENV PGDATA /pg_uta
RUN wget http://dl.biocommons.org/uta/${UTA_VERSION}.pgd.gz
COPY ops/pg_startup /usr/bin/pg_startup
RUN /usr/bin/pg_startup init

ENV UTA_DB_URL postgresql://uta_admin@localhost:5432/uta/${UTA_VERSION}
ENV ANNO /anno
ENV FASTA /anno/data/FASTA/human_g1k_v37_decoy.fasta
ENV PYTHONPATH /anno/src
ENV TARGETS /targets
ENV TARGETS_OUT /targets-out
ENV SAMPLES /samples
ENV PATH /anno/bin:$TARGETS/targets:$PATH
ENV PERL5LIB /anno/thirdparty/ensembl-vep-release/lib/:/anno/thirdparty/vcftools/lib
ENV WORKFOLDER /tmp/annowork
ENV HGVS_SEQREPO_DIR /anno/data/seqrepo/2017-11-18

# See .dockerignore for files that are ignored
COPY . /anno
WORKDIR /anno

# Set supervisor as default cmd
CMD /bin/bash -c "python3 unpack_lfs.py && supervisord -c /anno/ops/supervisor.cfg"
