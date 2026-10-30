# Maintaining and publishing TabletKey

## Changelog

Maintain `CHANGELOG.md` directly using the [writing guidelines](changelog.md).
Agents can update it alongside the code. There are no fragments, collection commands, or generated release notes.

## Publish to PyPI

1. Update the package version in `pyproject.toml` and its entry in `CHANGELOG.md`.
2. Push the changes and confirm CI passes for the commit you intend to publish.
3. In GitHub Actions, select **Publish to PyPI**, choose `main`, and click **Run workflow**.

The workflow checks out that commit, installs uv with setup-uv, runs `uv build`, and runs `uv publish`.
It uses the repository secret **UV_PUBLISH_TOKEN**, which must contain a PyPI API token.
It does not create Git tags or GitHub releases, change versions, or commit files.
Tests and package validation stay in the existing CI workflow; publishing does not rerun or wait for CI.

`uv build` is necessary because each job starts without built distribution files. The workflow builds
and publishes in one job, without artifact transfers or extra release tooling.
Use a new package version for each update; PyPI does not allow replacing an existing release file.

## Screenshots and documentation

Refresh the four settings screenshots with:

```sh
uv run python tools/screenshots.py
```

This uses temporary settings and offscreen Qt, with no hardware access or daemon startup.
Check the images after changing the interface. Build or preview the website with
`uvx zensical build --clean` or `uvx zensical serve`.

See [uv's publishing guide](https://docs.astral.sh/uv/guides/package/) for the publishing command and authentication.
