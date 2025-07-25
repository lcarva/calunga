#!/bin/bash
#
# This script assumes the following:
# * First argument is the name of the package to build.
# * The directory /cachi2 exists. This contains the cachi2.env file, and all the dependencies for
#   executing the build. This directory and its contents are generated via hermeto.
#
# Upon completion, the "build" directory (relative to the current directory) will contain the built
# wheel and the source tarball.
#
# Why is this not included in the calunga CLI? To reduce the builder footprint, we don't want all
# the dependencies of the calunga CLI to be installed in the builder image.
#
set -euo pipefail

PACKAGE_NAME="$1"

# This creates the PIP_FIND_LINKS environment variable.
. /cachi2/cachi2.env
echo "PIP_FIND_LINKS: ${PIP_FIND_LINKS}:"
ls -la "${PIP_FIND_LINKS}"

OUTPUT_DIR="$(pwd)/build"
mkdir -p "${OUTPUT_DIR}"

# Find and prepare the source tarball.
PACKAGE_TARBALLS=$(find "${PIP_FIND_LINKS}" -name "${PACKAGE_NAME}-*.tar.gz" -printf "%f\n")
case "$(echo "${PACKAGE_TARBALLS}" | wc -l)" in
  0)
    echo "Error: No tarball found for '${PACKAGE_NAME}' in ${PIP_FIND_LINKS}" >&2
    exit 1
    ;;
  1)
    PACKAGE_TARBALL="${PACKAGE_TARBALLS}"
    ;;
  *)
    echo "Error: Expected exactly one tarball for '${PACKAGE_NAME}', found multiple:" >&2
    echo "${PACKAGE_TARBALLS}" >&2
    exit 1
    ;;
esac

# Create a temporary directory for extraction to keep workspace clean
TEMP_DIR=$(mktemp -d)
cp "${PIP_FIND_LINKS}/${PACKAGE_TARBALL}" "${OUTPUT_DIR}/"
tar -xvf "${OUTPUT_DIR}/${PACKAGE_TARBALL}" -C "${TEMP_DIR}"
PACKAGE_DIR=$(basename "${PACKAGE_TARBALL}" .tar.gz)

pushd "${TEMP_DIR}/${PACKAGE_DIR}" > /dev/null
# Build the wheel.
python -m build --wheel --outdir "${OUTPUT_DIR}" .
popd > /dev/null

# Make the wheel readable. When this script is executed in a Tekton Task, the output may have to be
# read by another step within the Task that may be running as a different user/group. This ensures
# the built wheel and source tarball are readable in all cases.
chmod +r "${OUTPUT_DIR}"/*

echo "Build output:"
ls -la "${OUTPUT_DIR}"

# Clean up temporary directory
rm -rf "${TEMP_DIR}"
