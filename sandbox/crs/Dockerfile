FROM python:3.12.7-slim-bookworm

WORKDIR /app

RUN set -eux; \
    DEBIAN_FRONTEND=noninteractive apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        7zip \
        autoconf \
        automake \
        autotools-dev \
        bash \
        bsdextrautils \
        build-essential \
        binutils \
        ca-certificates \
        curl \
        file \
        gnupg2 \
        git \
        git-lfs \
        gzip \
        jq \
        libcap2 \
        make \
        openssl \
        patch \
        perl-base \
        rsync \
        software-properties-common \
        strace \
        tar \
        tzdata \
        unzip \
        vim \
        wget \
        xz-utils \
        zip; \
    apt-get clean; \
    apt-get autoremove -y; \
    rm -rf /var/lib/{apt,dpkg,cache,log}

ARG YQ_VERSION=4.43.1
ARG YQ_BINARY=yq_linux_amd64
RUN wget -q https://github.com/mikefarah/yq/releases/download/v${YQ_VERSION}/${YQ_BINARY} -O /usr/bin/yq && \
    chmod +x /usr/bin/yq

# copy requirements first so changes to code don't invalidate pip install layer
COPY requirements.txt .
RUN pip3 install --no-cache-dir --no-deps -r requirements.txt

# Copy your source code
COPY src .

ENTRYPOINT ["python3", "run.py"]
