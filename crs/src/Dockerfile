# This is just a sample Dockerfile
# Competitors: You MUST implement your own Dockerfile here so that your container/s can be built
# and published to your CRS repo

FROM ubuntu:22.04

WORKDIR /app

ENV TZ=Europe/London
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN apt-get update && \
    apt-get -y install software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get -y install python3.12 python3-pip && \
    apt-get clean && \
    rm -rf /var/lib/{apt,dpkg,cache,log}

# Copy your source code
COPY crs/src .

RUN python3 --version

RUN pip3 install -r requirements.txt

# Run the command to start your CRS, this is just a placeholder
CMD ["python3", "py/run.py"]
