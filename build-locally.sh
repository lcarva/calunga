#!/bin/bash
set -euo pipefail

PACKAGE=$1

cd "$(dirname "${BASH_SOURCE[0]}")"

echo "Building ${PACKAGE}"

PREFETCH_DEPS_IMAGE="$(
    < .tekton/build-pipeline.yaml \
    yq '.spec.tasks[] | select(.name == "prefetch-dependencies").taskRef.params[] | select(.name == "bundle") | .value'
)"

# HERMETO_IMAGE="quay.io/konflux-ci/hermeto:latest"
HERMETO_IMAGE="$(
    tkn bundle list -o json "${PREFETCH_DEPS_IMAGE}" | \
    jq -r '.spec.steps[] | select(.name == "prefetch-dependencies") | .image'
)"

# Make sure we're using the latest and greatest hermeto image
podman pull "${HERMETO_IMAGE}"

hermeto() {
    podman run --rm -v "$(pwd):/mnt/workdir:Z" -w /mnt/workdir "${HERMETO_IMAGE}" "$@"
}

hermeto --version

HERMETO_WORKDIR='hermeto-workdir'
HERMETO_OUTPUT_DIR="${HERMETO_WORKDIR}/output"
HERMETO_ENV_FILE="${HERMETO_WORKDIR}/hermeto.env"

HERMETO_BUILD_CONTAINERFILE='Containerfile.hermeto'
HERMETO_BUILD_VOLUME="/hermeto"

ORIGINAL_CONTAINERFILE="$(
    < .tekton/packages-on-push.yaml \
    yq '. | select(.metadata.name == "'$PACKAGE'-on-push") | .spec.params[] | select(.name == "dockerfile") | .value'
)"

rm -rf "${HERMETO_WORKDIR}"
mkdir "${HERMETO_WORKDIR}"

hermeto fetch-deps --output "${HERMETO_OUTPUT_DIR}" '{
  "type": "pip", "path": "./packages/'${PACKAGE}'", "allow_binary": "false"
}'

hermeto generate-env --output "${HERMETO_ENV_FILE}" --format env "${HERMETO_OUTPUT_DIR}"\
    --for-output-dir "${HERMETO_BUILD_VOLUME}/output"

cp "${ORIGINAL_CONTAINERFILE}" "${HERMETO_BUILD_CONTAINERFILE}"

# Read in the whole file (https://unix.stackexchange.com/questions/533277), then
# for each RUN ... line insert the cachi2.env command *after* any options like --mount
sed -E -i \
    -e 'H;1h;$!d;x' \
    -e 's@^\s*(run((\s|\\\n)+-\S+)*(\s|\\\n)+)@\1. /hermeto/hermeto.env \&\& \\\n    @igM' \
    "${HERMETO_BUILD_CONTAINERFILE}"

set -x
buildah build \
    --network=none \
    --no-cache \
    --volume "${PWD}/${HERMETO_WORKDIR}:${HERMETO_BUILD_VOLUME}:Z" \
    -f "${HERMETO_BUILD_CONTAINERFILE}" \
    -t "calunga-${PACKAGE}:latest" \
    --build-arg-file "packages/${PACKAGE}/argfile.conf" \
    "packages/${PACKAGE}"
