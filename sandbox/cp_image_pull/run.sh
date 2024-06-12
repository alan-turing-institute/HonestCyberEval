#! /bin/sh

set -e

echo "Starting CP image loader"

until docker version >/dev/null 2>/dev/null; do
	echo "Waiting for Docker daemon to start"
	sleep 5
done

echo "${GITHUB_TOKEN}" | docker login ghcr.io -u "${GITHUB_USER}" --password-stdin

for cp in "${AIXCC_CP_ROOT}"/*; do
	echo "Fetching image for CP at ${cp}"
	cd "$cp"
	make docker-pull
done
