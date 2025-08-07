#!/bin/bash
set -euo pipefail

OUTPUT_DIR="mass-onboard-output"
rm -rf "${OUTPUT_DIR}"
mkdir "${OUTPUT_DIR}"

< package_list.txt \
    parallel --progress --eta -i -j 5 --joblog mass-onboard-output.log \
    "./add-package-with-commit.sh {} > ${OUTPUT_DIR}/{}.stdout 2> ${OUTPUT_DIR}/{}.stderr"