#!/bin/bash

set -euo pipefail

PKG="$1"
gh --repo lcarva/calunga \
    issue list --state open \
    --search "in:title 'Onboard package: ${PKG}'" \
    --json number -q '.[].number' | xargs -I {} gh issue close {}
