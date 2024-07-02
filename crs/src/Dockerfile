FROM ubuntu:22.04

WORKDIR /app

# global environment variables
ENV LC_ALL=C.UTF-8 \
    LANG=C.UTF-8 \
    TZ=America/New_York

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime; \
    echo $TZ > /etc/timezone

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
        clang \
        curl \
        file \
        gnupg2 \
        git \
        git-lfs \
        gzip \
        jq \
        libcap2 \
        libclang-14-dev \
        llvm-14 \
        ltrace \
        make \
        openssl \
        patch \
        perl-base \
        python3 \
        python3-dev \
        python3-pip \
        python3-setuptools \
        python3-wheel \
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

# Install Docker for CP repo build and test
RUN set -eux; \
    install -m 0755 -d /etc/apt/keyrings; \
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc; \
    chmod a+r /etc/apt/keyrings/docker.asc; \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
        $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null; \
    DEBIAN_FRONTEND=noninteractive apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        containerd.io \
        docker-ce \
        docker-ce-cli \
        docker-buildx-plugin; \
    apt-get clean; \
    apt-get autoremove -y; \
    rm -rf /var/lib/{apt,dpkg,cache,log}

# copy requirements first so changes to code don't invalidate pip install layer
COPY crs/src/requirements.txt .
RUN pip3 install -r requirements.txt

# Copy your source code
COPY crs/src .

# Run the command to start your CRS, this is just a placeholder
CMD ["python3", "py/run.py"]
