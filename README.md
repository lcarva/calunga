# Calunga

**Experimental!**

Calunga is a library of python packages. Each package is built from source in
[Konflux](https://konflux-ci.dev/). This git repository is a "monorepo" with build recipes for each
package.

## Adding a new package

To add a new package to the Calunga python index, simply file a new GitHub issue from the "🌱 Add
Package" template. Once a maintainer reviews the request, they will add the `on-board` label to the
issue. This will trigger the [package-onboarding](./.github/workflows/package-onboarding.yaml)
workflow which in turn generates a new pull request with the required changes. A maintainer will
review and merge the changes as needed.

## Development

Sometimes, it is easier to debug issues locally. To add a package without using the automated
workflow described above, create a directory under the [packages](./packages) directory matching the
package name (always lower case) in [pypi.org](https://pypi.org/), then use the Calunga CLI to
generate the requirements file for that package.

## Development Setup

First, install [Poetry](https://python-poetry.org/docs/#installation) if you haven't already, then install the project dependencies with `poetry install`.

Now you can generate requirements for a package:

```bash
poetry run calunga generate
```
