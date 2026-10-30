# Updating the changelog

Edit `CHANGELOG.md` directly. These guidelines apply equally to people and coding agents.
No changelog tool or fragment files are needed.

## Writing an entry

- Put new user-visible changes under `## Unreleased` at the top, above previous versions.
- Group short bullets under **Added**, **Changed**, **Fixed**, or **Breaking**. Omit empty groups.
- Explain the effect on someone using the tablet. Name the feature and what changed.
- For breaking changes, explain what the user needs to do.
- Keep hardware and compatibility claims accurate; distinguish implementation from physical verification.
- Skip internal refactors, test-only changes, and routine dependency updates unless they affect users.
- Keep previous version entries intact.

Good: “Light touch reaches full pressure with a comfortable stroke.”
Avoid: “Refactored the pressure mapper and updated tests.”

## Preparing a version

Replace the Unreleased heading with the version being published, matching `project.version` in
`pyproject.toml`. Review the wording alongside the code. Commit and push when authorised.
The publishing workflow leaves the version and changelog untouched.
