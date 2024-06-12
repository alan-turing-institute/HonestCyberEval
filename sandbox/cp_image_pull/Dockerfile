FROM docker:26-cli

# hadolint ignore=DL3018
RUN apk add --no-cache make yq git bash && \
    rm -rf /var/cache/apk/* && \
    ln -s "$(which bash)" /usr/bin/bash

COPY run.sh /

ENTRYPOINT ["/run.sh"]
