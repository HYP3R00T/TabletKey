# Maintaining and releasing TabletKey

This page is for maintainers. Publication is separate from a local build or Git commit.
The first PyPI release is in preparation; nothing in the normal application uploads packages.

## Validate the checkout

```sh
uv sync --locked --managed-python
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ty check
uvx zensical build --clean
uv build
uvx twine check --strict dist/*
```

On Linux, the tests need local Unix sockets and offscreen Qt. They use fake devices and temporary
settings; daemon subprocess tests use `--no-device`. They do not initialise or grab the attached tablet.
The docs workflow builds the existing Zensical site and deploys GitHub Pages on a push to main.
A local commit does not deploy it.

## Check the actual distributions

Inspect both the wheel and source distribution. Confirm they contain the entry point, original
`vo1060.svg`, device-access rules, module-loading configuration, and MIT license.
There must be no raw captures, private configuration, proprietary installers, or third-party product photos.
Build a wheel from the source archive as well as directly from the checkout.

Use a local wheel before an upload:

```sh
uvx --from ./dist/tabletkey-0.1.0-py3-none-any.whl tabletkey --help
uvx --from ./dist/tabletkey-0.1.0-py3-none-any.whl tabletkey
```

The second command must open the GUI from outside the source tree. Check all four tabs and resources.
The bare entry point opens settings without automatically starting hardware. For an isolated lifecycle
smoke test, set fresh `XDG_CONFIG_HOME` and `XDG_RUNTIME_DIR` directories and use `daemon start --no-device`.
Never stop a user's real daemon merely to test a package.

## Refresh screenshots

```sh
uv run python tools/screenshots.py
```

This renders the real settings UI with a clean temporary profile and the driver stopped.
It writes the four images in `docs/assets/screenshots/`. It reads no raw tablet data, starts no daemon,
and does not change the user's settings. The pressure and detection graphs are intentionally empty.
A temporary Light touch selection illustrates the response preview; it is not the default profile.

Review each image after changes to layout, labels, assets, or tabs. Keep images small enough for
GitHub and the documentation site. The README uses absolute raw-GitHub image URLs so PyPI can render
screenshots too; push the referenced assets before checking the published package description.

## Publish deliberately

1. Confirm the version in `pyproject.toml`, package ownership, and the intended release artifacts.
2. Repeat hardware checks appropriate to any driver changes and record limits in the hardware evidence.
3. Build from the reviewed commit; inspect metadata and run strict README validation.
4. Upload to TestPyPI if desired, then verify the public package using clean environments.
5. Publish to PyPI only after explicit release approval, using a scoped token or trusted publishing.
6. Update the README and getting-started release-status wording, then check `uvx tabletkey` against PyPI.

No upload workflow or credentials are installed by this preparation. Follow
[uv's publishing guide](https://docs.astral.sh/uv/guides/package/) and
[PyPA's trusted-publishing guide](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
when configuring an actual release. Availability of the name is not a reservation.
