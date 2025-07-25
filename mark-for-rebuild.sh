#!/bin/bash

set -euo pipefail

PACKAGE_NAME="$1"

PYPROJECT_TOML="packages/${PACKAGE_NAME}/pyproject.toml"

# Remove previous force rebuild comment
sed -i '/^# Add comment to force rebuild/d' "$PYPROJECT_TOML"

echo "# Add comment to force rebuild, $(date -u --rfc-3339=seconds)" >> "$PYPROJECT_TOML"
