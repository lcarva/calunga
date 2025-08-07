#!/bin/bash
#
# Add a package to the calunga catalog.
#
# Usage:
#   add-package.sh <package-name>
#

set -euo pipefail

PKG_NAME=$1


TMP_DIR=$(mktemp -d -t "calunga-${PKG_NAME}-XXXXXX")
trap 'rm -rf "${TMP_DIR}"' EXIT

git clone "$(git config --get remote.origin.url)" "${TMP_DIR}"
cd "${TMP_DIR}"
git checkout upcoming

if [[ -d "packages/${PKG_NAME}" ]]; then
    echo "Package '${PKG_NAME}' is already onboarded."
    exit 0
fi

# We want this to fail if the directory already exists which implies the package is either already
# onboarded or something went wrong on a previous run.
mkdir "packages/${PKG_NAME}"

echo
echo "==================================================="
echo "Package dependencies ${PKG_NAME} has been resolved."
echo "==================================================="

echo "Building package locally"
while true; do
    poetry run calunga generate

    set +e
    error_output=$(./build-locally.sh "${PKG_NAME}" 2> >(tee /dev/stderr))
    success=$?
    set -e

    if [[ "${success}" -ne 0 ]]; then
        echo "Build failed, analyzing logs..."
        set +e
        # This is a bit messy, but tries to extract the missing package name from the error output
        # when the package name could be split across multiple lines.
        missing_package="$(
            echo "${error_output}" | \
            tr '\n' ' ' | \
            sed 's/  */ /g' | \
            grep -oP "ERROR: No matching distribution found for \K[\s\w\-]+" | \
            sed 's/ //g' | \
            head -n 1)"
        success=$?
        set -e

        if [[ -n "${missing_package}" ]]; then
            echo "Missing package: ${missing_package}"
            yq -i '.packages["'${PKG_NAME}'"].requirements_in += ["'${missing_package}'"] | sort_keys(..)' \
                'packages/additional-requirements.yaml'
            rm -vf packages/${PKG_NAME}/requirements*
            continue
        fi

        # Handle inconsistent package name.
        set +e
        cp_error=$(echo "${error_output}" | grep -o "cp: -r not specified; omitting directory")
        success=$?
        set -e

        if [[ -n "${cp_error}" ]]; then
            echo "Package name inconsistency detected. Setting package_name to match package name."
            yq -i '.packages["'${PKG_NAME}'"].package_name = "'${PKG_NAME}'"' \
                'packages/additional-requirements.yaml'
            rm -vf packages/${PKG_NAME}/argfile.conf
            continue
        fi

        exit 1
    fi

    break

done

echo 'Creating Konflux resources for package'
kustomize build "konflux/components/${PKG_NAME}" | oc -n calunga-tenant apply -f -

echo 'Creating a commit for onboarding the package'

git add .
git commit -m "Onboard ${PKG_NAME} package" --signoff

max_attempts=10
attempt=1
while (( attempt <= max_attempts )); do
    git fetch origin upcoming
    git rebase origin/upcoming
    if git push; then
        break
    else
        echo "Push attempt $attempt failed. Retrying..."
        ((attempt++))
        sleep 2
    fi
    if (( attempt > max_attempts )); then
        echo "Failed to push after $max_attempts attempts. Giving up."
        exit 1
    fi
done

exit 0

pr_url=$(gh pr create --base main --head "${BRANCH_NAME}" --fill)
pr_number=$(echo "$pr_url" | grep -oE '/pull/[0-9]+' | grep -oE '[0-9]+$')
echo "Created PR #$pr_number: $pr_url"

REPO='lcarva/calunga'

# Sleep a little to let things settle.
sleep 60

mergeable_state=$(gh --repo "${REPO}" pr view "$pr_number" --json mergeable --jq '.mergeable')

if [[ "$mergeable_state" != "MERGEABLE" ]]; then
    echo "PR #$pr_number: Not mergeable (State: $mergeable_state). Might have merge conflicts."
    exit 1
fi
echo "PR #$pr_number is mergeable."

# Wait for checks to complete. But ignore this output because it's too noisy.
gh --repo "${REPO}" pr checks --watch "$pr_number"

set +e
checks_output=$(gh --repo "${REPO}" pr checks "$pr_number")
set -e

# Check if any checks are failing or pending.
if echo "$checks_output" | grep -q -E 'fail|pending|expected'; then
    echo "PR #$pr_number: One or more checks are failing or still pending."
    echo "$checks_output"
    exit 1
fi

echo "PR #$pr_number has all successful checks."

echo "Merging PR #$pr_number..."
gh --repo "${REPO}" pr merge "$pr_number" --rebase
