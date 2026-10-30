# Releasing converge-sdk

A release is a `v*` tag. `.github/workflows/release.yml` tests, builds and publishes it to PyPI through **trusted publishing** (OIDC). No API token is created or stored.

## One-time setup (maintainer)

These steps need the project owner's accounts. Nobody else does them for you.

1. **Claim the name on PyPI.** Sign in at pypi.org with the organization's account. Under *Your projects → Publishing*, add a **pending trusted publisher** for the project `converge-sdk`:
   - Owner: `TANTIRA`, repository: `CSDK-Python`
   - Workflow: `release.yml`
   - Environment: `pypi`

   That reserves the name, and the first tagged release creates the project.
2. **Create the `pypi` environment** in this repository (*Settings → Environments*). Optionally require a reviewer, so every publish waits for an approval.
3. **Turn on GitHub Actions** for this repository (*Settings → Actions*), and make sure the organization's Actions billing allows jobs to run.

For the TypeScript SDK, the same owner should also claim the npm scope `@converge` (or use `@tantira/converge-sdk` if `@converge` is taken). That is documented in its own repository.

## Every release

1. Update `version` in `pyproject.toml` and `__version__` in `converge_sdk/__init__.py`.
2. Move the entries in `changelog/@unreleased/` into `changelog/<version>/`.
3. Merge that through a pull request.
4. Tag the merge commit and push the tag:

   ```sh
   git tag v0.1.0 && git push origin v0.1.0
   ```

The workflow refuses a tag that does not match the package version.

## Platform copy

The Converge platform keeps a pinned copy of a tagged release (it serves the package to its own deployments, which cannot reach PyPI). After tagging, update that copy in the platform repository. Its drift test names the tag and the hash of the files.
