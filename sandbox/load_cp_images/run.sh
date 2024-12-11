#! /bin/bash

set -e

ENABLE_HEALTH_ENDPOINT=${ENABLE_HEALTH_ENDPOINT:-false}
HEALTH_ENDPOINT_PORT=${HEALTH_ENDPOINT_PORT:-8080}

LOAD_CPS=${LOAD_CPS:-false}
LOAD_CP_IMAGES=${LOAD_CP_IMAGES:-true}
CP_CONFIG_FILE=${CP_CONFIG_FILE:-/cp_config.yaml}

if [ "$LOAD_CPS" = "true" ]; then
	# Only CP Root to empty if we're responsible for filling it
	echo "Resetting ${CP_ROOT}"
	rm -rf "${CP_ROOT:?}"/*

	echo "Starting CP loader"
	while read -r clone_cp; do
		bash -c "$clone_cp"
	done < <(yq -r ".cp_targets | to_entries | .[] | \"git clone \(.value.url) ${CP_ROOT}/\(.key) && cd ${CP_ROOT}/\(.key) && git checkout \(.value.ref)"\" "${CP_CONFIG_FILE}")
	# shellcheck disable=SC2156
	find "${CP_ROOT}" -maxdepth 1 -type d ! -name "lost+found" -exec bash -c "echo 'prepping {}' && cd '{}' && make cpsrc-prepare" \;
	echo "CP loading complete"
fi

if [ "$LOAD_CP_IMAGES" = "true" ]; then
	echo "Starting CP image loader"

	echo "Logging in to GHCR"
	echo "${GITHUB_TOKEN}" | docker login ghcr.io -u "${GITHUB_USER}" --password-stdin

	echo "Fetching CP Docker images"
	for cp in "${CP_ROOT}"/*; do
		if [ "$cp" = "${CP_ROOT}"/'*' ]; then
			echo "CP root folder was empty."
			exit 1
		fi

		if [ "$cp" = "${CP_ROOT}"/lost+found ]; then
			continue
		fi

		if [ ! -d "$cp" ]; then
			continue
		fi

		echo "Fetching image for CP at ${cp}"
		cd "$cp"
		make docker-pull
	done
	echo "CP image loading complete"
fi