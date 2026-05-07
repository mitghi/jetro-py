# Releasing jetro to PyPI

Wheels for every supported platform are built and published by the
`.github/workflows/release.yml` workflow. PyPI uploads use a **trusted
publisher** — no API tokens live in this repo.

## One-time setup on PyPI

1. Visit <https://pypi.org/manage/account/publishing/>.
2. Under **Add a new pending publisher**, fill in:
   - **PyPI Project Name:** `jetro`
   - **Owner:** `mitghi`
   - **Repository name:** `jetro-py`
   - **Workflow name:** `release.yml`
   - **Environment name:** `release`
3. Save. PyPI will accept uploads only from a workflow run that
   matches all four fields (and nowhere else).

If the project name is not yet reserved, the form lets you create a
**pending** publisher; it activates the moment the first matching
workflow run uploads a distribution.

## One-time setup on GitHub

1. Repo → **Settings → Environments → New environment**.
2. Name it `release` (must match the `environment.name` field in the
   workflow).
3. Optional but recommended: add **required reviewers** (yourself)
   so a release run cannot upload without an approval click.

## Cutting a release

```sh
# bump the version in Cargo.toml and pyproject.toml in the same commit
$EDITOR Cargo.toml pyproject.toml
git add Cargo.toml pyproject.toml
git commit -m "release v0.1.0"

# push the tag — release.yml triggers on any tag matching v*
git tag v0.1.0
git push origin main v0.1.0
```

The workflow then:

1. Builds wheels in parallel:
   - linux x86_64 (`manylinux2014`)
   - linux aarch64 (`manylinux2014`, QEMU on x86 runner)
   - macOS universal2 (x86_64 + aarch64)
   - windows x86_64
2. Builds the source distribution (`sdist`).
3. Waits for any required reviewers on the `release` environment.
4. Uploads every artifact to <https://pypi.org/project/jetro/> via
   OIDC trusted publishing. `--skip-existing` makes the step
   idempotent if you have to re-run it.

## Verifying the upload

```sh
pip install --upgrade jetro
python -c "import jetro; print(jetro.__file__)"
```

Confirm the version on the PyPI project page; every wheel filename
is listed under **Download files**.

## Re-running a partially failed release

`maturin upload --skip-existing` lets the publish step retry without
duplicate-version errors. Either re-run the failed jobs from the
GitHub UI or push a new tag (`v0.1.0-post1`) — both work.

## Manually triggering a build (no publish)

`workflow_dispatch` is enabled, so any release-shaped artifact set
can be produced from the **Actions** tab without tagging:

1. Actions → **release** → **Run workflow**.
2. The build jobs run; the `publish` job still triggers but skips
   already-published files via `--skip-existing`.
