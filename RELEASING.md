# Releasing converge-sdk

There are two ways to publish to PyPI:

- **Path A, manual:** from a maintainer's machine with a PyPI API token. The first release takes this path.
- **Path B, automated:** through `.github/workflows/release.yml` and PyPI trusted publishing (OIDC, no stored token), once GitHub Actions can run for this repository.

Only the project owner does these steps. Nobody else creates accounts, tokens or publishers for you.

## Before every release

1. Set `version` in `pyproject.toml` and `__version__` in `converge_sdk/__init__.py`.
2. Move the entries in `changelog/@unreleased/` into `changelog/<version>/`.
3. Run the tests and build locally:

   ```sh
   python -m unittest discover -s tests -t .
   python -m pip install build twine
   rm -rf dist && python -m build
   python -m twine check dist/*
   ```

   The sdist must contain only `converge_sdk/`, `LICENSE`, `NOTICE`, `README.md` and the build metadata. The wheel metadata must say `License: Apache-2.0`.
4. Merge through a pull request, then tag the merge commit: `git tag v0.1.0 && git push origin v0.1.0`.

## Path A: manual, with an API token (first release)

1. Sign in at pypi.org with the organization's account, and turn on 2FA.
2. Create an API token with scope **"Entire account"**. A token scoped to one project can only be created once the project exists, and `converge-sdk` does not exist until the first upload.
3. Upload:

   ```sh
   python -m twine upload dist/*
   # username: __token__
   # password: the token (pypi-...)
   ```

4. **Right after the first upload:** create a new token scoped to the project `converge-sdk`, use it for later manual releases, and **delete the account-wide token**.

## Path B: trusted publishing (once Actions can run)

1. On pypi.org, under the project `converge-sdk` → *Publishing*, add a trusted publisher:
   - Owner: `TANTIRA`, repository: `CSDK-Python`
   - Workflow: `release.yml`
   - Environment: `pypi`
2. In this repository, create the environment `pypi` (*Settings → Environments*). Optionally require a reviewer.
3. Set the repository variable `PYPI_TRUSTED_PUBLISHING` to `true` (*Settings → Secrets and variables → Actions → Variables*).

From then on, pushing a `v*` tag tests, builds, checks and publishes. Until the variable is set, the publish job is skipped rather than failed, and the build job still runs and keeps the dists as an artifact. The workflow also refuses a tag that does not match the package version.

## The TypeScript SDK

It is `@convergehq/sdk`, published by an owner of the npm organization `convergehq` (`@converge` belongs to someone else on npm). See RELEASING.md in TANTIRA/CSDK-Typescript.

## Platform copy

The Converge platform keeps a pinned copy of a tagged release, because its deployments cannot reach PyPI. After tagging, update that copy in the platform repository. Its drift test names the tag and the hash of the files.
