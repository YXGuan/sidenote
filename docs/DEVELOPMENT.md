# Development and verification

Read [AGENTS.md](../AGENTS.md) and [first-run setup](SETUP.md) first. Run commands
from the repository root unless a block changes directory. Personal vault data,
tokens, local dependencies, and generated upstream checkouts are not part of a clone.

## Native patches

The parent repo tracks patches, not the nested Hypothesis repositories:

| Checkout | Pinned upstream commit | Yarn release |
| --- | --- | --- |
| `hypothesis/client` | `a7b7400d0d706d4357ec37c2a3610b25dcca89d5` | 3.6.0 |
| `hypothesis/browser-extension` | `a29dd56bc736aa231e229e34dc42a1ded49151fc` | 3.6.1 |

`hypothesis/build` is the source of truth for URLs/pins. It clones missing
repositories, applies patches, installs locked dependencies, and builds through
the upstream tools. It refuses a different HEAD and does not reset existing work.
`portal:../client` connects the extension to the actual modified client.

Before editing, inspect `git status --short` in the parent and both nested repos.
After your native edits:

```sh
./hypothesis/build --export-patches
./hypothesis/build
```

Export only from the complete, intended native source state. Exporting empty
upstream clones would erase the tracked customizations. If a build reports a
patch mismatch, inspect each nested diff and HEAD, preserve other work, and
reconcile the intended changes before export. Do not delete the checkouts or use
`git reset --hard` as a routine repair.

A parent-repo PR must include the exported patch changes. Builds/dependencies
are generated and ignored. Empty exports and checkouts at a different upstream
commit are rejected before either patch is replaced. After rebuilding, reload the Chrome extension and
refresh its tabs; restarting only the Python bridge does not update the worker.

The product mark is maintained in `assets/sidenote.svg` and the native
`SidenoteLogo.tsx` component. Run `node tools/render_brand.mjs` to regenerate
Chrome icon variants, then export the patches and rebuild. It renders only the
local vector in an isolated browser.

## Checks by subsystem

Setup helper (no installation or network; temporary fixture directories):

```sh
python3 -B -m unittest discover -s tests -v
./setup --check
```

Python backend (requires the workspace-local NLP dependencies from setup):

```sh
python3 -B -m unittest discover -s research-partner/tests -v
```

Search/wiki/graph reuse rank-bm25 and NetworkX, pinned alongside the NLP packages
in `research-partner/requirements.txt`. Install workspace dependencies with
`python3 -m pip install --target research-partner/.local-tools/python -r research-partner/requirements.txt`.
The client also pins Cytoscape.js in its package/lockfile. `research_notes/concepts.py`
shares cited concept pages/relationships between Wiki and graph; its model tests
use injected responses and synthetic vaults. A fresh reconstruction
must install the updated locked dependencies; use `./hypothesis/build --install-deps`
when updating an existing checkout with older node_modules.

`python3 -B research-partner/experiments/wiki_trial.py` exercises search, wiki
ingestion/staleness, and graph export on a temporary synthetic vault. Its optional
`--model` flag sends only its invented demo sources to the signed-in service;
never use the personal vault for tests. See the [workflow guide](../research-partner/docs/RESEARCH-WORKSPACE.md).

Client, with a targeted **test filename** expression:

```sh
cd hypothesis/client
node .yarn/releases/yarn-3.6.0.cjs typecheck
node .yarn/releases/yarn-3.6.0.cjs exec eslint src/sidebar/components/LocalLibraryView.tsx
node .yarn/releases/yarn-3.6.0.cjs test --grep 'library|Library|PageResearch|ResearchWorkspace|ResearchWiki'
```

Extension worker:

```sh
cd hypothesis/browser-extension
node .yarn/releases/yarn-3.6.1.cjs typecheck
node .yarn/releases/yarn-3.6.1.cjs exec eslint src/background/local-research.ts src/background/saved-page-visits.ts
node .yarn/releases/yarn-3.6.1.cjs test
```

Run lint on the files you changed, not only the examples above. Browser tests
start a temporary local HTTP server and isolated Chromium; they need local socket
access and a Playwright browser. If missing, run the relevant checkout's bundled
Yarn command, e.g. `node .yarn/releases/yarn-3.6.0.cjs exec playwright install chromium`.
On Linux, required OS libraries may also need installation. Follow actual errors;
do not change a personal browser profile to make tests pass.

Meaningful tests cover persistence, account boundaries, manual overrides,
classification evidence, collection membership, visit deduplication and filters.
Do not use a real personal vault for fixtures or trigger a real cloud analysis
just to verify local changes. Model/provider tests use injected synthetic data.

## Browser integration

After building the native client, run:

```sh
node hypothesis/test-library-routing.mjs
```

The routing test bundles the actual library components with synthetic data in
a temporary directory. It starts its own loopback server and isolated Chromium,
then removes the fixture directory when finished. It verifies URL navigation,
direct links, refresh, Back/Forward, collections, saved-page details, wiki and
atlas routes, Settings, maintenance actions, removal/Undo, legacy links, and
appearance preferences. It makes no model calls and creates no preview folder
in the checkout.

`python3 -B hypothesis/test-native.py` exercises the built extension in an isolated
Chromium profile with a temporary vault and synthetic publisher/API fixtures.
See [the native build guide](../hypothesis/README.md#verify) for optional browser
paths. Respect browser-tool restrictions on `chrome-extension://` pages; do not
work around them through another browser surface or hidden debugging transport.

## Data boundaries and documentation

- `raw/` stores original annotation evidence; edits use the CLI and `overrides/`.
- `analysis/` is derived; manual citation/classification corrections take precedence.
- `openalex/` preserves complete singleton Work API JSON. Test enrichment, empty
  labels, manual overrides, identifier changes and snapshot/restore with injected
  synthetic responses. `notes cache-openalex` is an explicit existing-library
  backfill, not a test; it fetches only already resolved public work IDs.
- Markdown personal notes below the marker survive render/sync.
- `activity/` is local visit history for saved pages; it is included in backups.
- Automatic collection memberships are read-time values, separate from manual groups.
- Credentials stay in ignored `.env`/`.local` files; never include them in fixtures,
  patches, preview data, URLs, logs or launch-agent definitions.

Keep executable setup steps in [SETUP.md](SETUP.md), source/build commands here,
user features in [hypothesis/DASHBOARD.md](../hypothesis/DASHBOARD.md), and classifier
details in [CLASSIFICATION.md](../research-partner/docs/CLASSIFICATION.md).
The active vocabulary lives in `research-partner/research_notes/taxonomy.json`;
regenerate its readable catalog with `python3 -B tools/render_taxonomy.py` and
verify freshness with `python3 -B tools/render_taxonomy.py --check`. Proposed
experimental vocabularies are not production migrations.
[VALIDATION.md](../research-partner/docs/VALIDATION.md) is a historical record of
specific test runs, not evidence that a fresh clone is already configured.
Update setup docs when flags, dependencies, data paths, or required manual steps change.

Research integration smoke test (temporary synthetic vault and isolated Chromium):

```sh
python3 -B hypothesis/test-research.py
```

This exercises real worker/bridge/search/wiki/graph/recommendation routes. The
recommendation fixture verifies seed transfer, cache-only reads, direct routes,
and 20/40/45 disclosure without making external API calls. Model answers and
synthesis use injected, labelled fixtures; no personal vault or cloud model is
used. Screenshots are disabled by default in both native smoke tests. To save
them explicitly, choose an output directory outside the checkout:

```sh
HYPOTHESIS_SCREENSHOT_DIR=/tmp/sidenote-ui python3 -B hypothesis/test-research.py
# The same option works with hypothesis/test-native.py.
```

Historical design alternatives and generated screenshots are not required by
the extension and are no longer kept in the repository.

Kura's optional runtime and tests:

```sh
./research-partner/setup-kura
research-partner/.local-tools/kura/bin/python -B -m unittest discover -s research-partner/tests -p test_kura_pipeline.py -v
```

The ordinary backend suite covers whole-vault evidence, model authorization,
staleness, pagination, backups, validation, and bridge routes using temporary
synthetic vaults. The optional integration test executes the real upstream
Kura pipeline with injected synthetic summaries and embeddings, including
recursive hierarchy and tiny libraries; it makes no cloud calls. The research
extension smoke test also covers the Kura map/hierarchy/size views, original
annotation and note details, filtering, and persistence with synthetic results.
See [Kura setup and data flow](../research-partner/docs/RESEARCH-WORKSPACE.md#kura-research-atlas).

## Publication checks

`python3 -B tools/check_public.py` checks tracked and new non-ignored files for personal/generated
paths and common credential shapes without printing values. It is a regression
guard, not an exhaustive secret scanner. The GitHub workflow runs baseline
Python checks on macOS/Linux and Python 3.10/3.14, plus a fresh pinned native build,
typechecks, targeted client tests, worker tests, and temporary-fixture routing. Workflow
steps have been prepared locally; a hosted CI run is separate evidence.

