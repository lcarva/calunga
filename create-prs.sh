#!/bin/bash
#
# Iterate through each package and update them.. If there are any changes, create a PR. If there
# are changes to dependencies, a PR is not created.
#
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

mapfile -d '' packages < <(find ./packages -maxdepth 1 -mindepth 1 -type d -print0 | sort -z)

function update_package() {
    local name
    local path
    local requirements_txt
    local requirements_build_txt
    local branch_name
    local old_version
    local new_version
    local prs_count

    name=$1
    path=$2

    requirements_txt="${path}/requirements.txt"
    requirements_build_txt="${path}/requirements-build.txt"

    branch_name="update-${name}"

    set +e
    # Remove any previous local changes.
    git branch -D "${branch_name}" 2>/dev/null
    set -e
    git checkout "${branch_name}" || git checkout -b "${branch_name}"

    if [[ "$(git rev-parse origin/main)" != "$(git rev-parse HEAD ~1)" ]]; then
        git rebase origin/main
    fi

    git push --force -u origin "${branch_name}"

    old_version="$(grep -ioP '^'${name}'==\K.+\w' "${requirements_txt}")"

    rm -f "${requirements_txt}" "${requirements_build_txt}"

    poetry run calunga generate

    new_version="$(grep -ioP '^'${name}'==\K.+\w' "${requirements_txt}")"

    if [[ "${old_version}" == "${new_version}" ]]; then
        echo "No new versions for ${name} package"
        # There could be other changes which we are purposely ignoring. In that case, let's throw
        # them out to avoid branch switching issues.
        git checkout .
        return
    fi

    set +e
    git diff --quiet "origin/${branch_name}" -- "${path}"
    HAS_CHANGES="$?"
    set -e

    if [[ $HAS_CHANGES -eq 0 ]]; then
        echo "No changes for ${name}"
        return
    fi

    git add "${path}"
    git commit -m "Update ${name} package to ${new_version}" --signoff
    git push --force --set-upstream origin "${branch_name}"

    prs_count="$(gh pr list --base main --head "${branch_name}" --json id | jq '. | length' -r )"

    if [[ $prs_count -gt 0 ]]; then
        echo "PR already exists for ${name}"
        return
    fi

    gh pr create --base main --head "${branch_name}" --fill
}

git checkout main
git pull

for path in "${packages[@]}"; do
    name="$(basename ${path})"

    # if [[ "${name}" != "beautifulsoup4" ]]; then
    #     continue
    # fi

    echo "Processing ${name}"

    git checkout main

    update_package "${name}" "${path}"

    echo
done