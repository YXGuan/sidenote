# Local storage behind Hypothesis

The interface now lives directly in the original Hypothesis repositories. Use the
[Hypothesis build instructions](../hypothesis/README.md) and load
`hypothesis/browser-extension/build/`. The separate companion extension has been
removed.

This directory contains the local storage service, daily importer, Markdown vault,
headless Codex adapter, and [PRD](docs/PRD.md). Personal data and credentials are
not distributed with the repository.
`research-partner` is the backend's earlier project name; the original Hypothesis
repositories in `../hypothesis/` provide the interface.

**First install:** use [the complete setup guide](../docs/SETUP.md), or the
[agent setup prompt](../README.md#clone-and-hand-setup-to-your-agent). It installs
dependencies, initializes your username/vault and builds the extension in order.
The commands below are reference/maintenance commands, not a substitute for
initializing a fresh vault. [AGENTS.md](../AGENTS.md) maps source and data boundaries.

## Local service

On macOS, install the persistent backend from the sidenote repository root:

```sh
python3 -m pip install --target research-partner/.local-tools/python -r research-partner/requirements.txt
./research-partner/notes service --install
./research-partner/notes service --status
```

Once installed, it starts at login and macOS restarts it if it
exits, without keeping a terminal or Codex session open. It listens only on
`127.0.0.1:8765` and reads the existing ignored `.env` file. The background bridge
and the daily backup are separate LaunchAgents. Logs are protected under
`vault/.local/bridge.log` and `bridge-error.log`.

The setup command installs local NLP dependencies inside this workspace, not the global Python
environment. NLTK tokenizes questions; VADER scores personal comments. Neither
downloads models/corpora or sends annotation text to a service at runtime.

The Collections tab includes **Liked (Auto)** (positive personal comments),
**Questions (Auto)** (questions in comments or highlights), and **Visit Often**
(at least three recorded visits within 30 days). These are computed from current
notes and activity, separate from manual groups and Likes. Explicit dislikes
override inferred liking. Editing notes updates membership automatically; visit
membership expires as visits leave the 30-day window.

After reloading the updated extension, active saved-page loads and tab returns
are tracked even with the annotation sidebar closed. The extension checks a
local saved-URL index; it never records unrelated pages or incognito visits and
does not request browser-history access. Events for the same page within five
minutes count once, including sidebar captures. Existing counts represent sidebar
captures only. The library refreshes on focus and every 30 seconds while visible.

Use `notes service --uninstall` to stop and remove it. For foreground debugging,
stop the background service first, then run `./research-partner/notes serve`.
`notes doctor --json` also reports whether the managed storage service is running.
If the dashboard was already showing an offline error, use **Retry connection**
or refresh the tab after the service starts.

Get the local key for **one-time pairing per browser profile**:

```sh
./research-partner/notes pair
```

Enter the pairing key in the actual Hypothesis extension's existing options page,
under **Local research**, and save it. If that profile is already paired, skip
this step. Pairing survives browser and backend restarts; repeat it only for a
new profile or if the saved extension settings or backend key are reset. The
local key is separate from the Hypothesis login and developer API token. Daily
sync does not require browser pairing.

The Hypothesis developer token stays in the backend's
`research-partner/.env` as `HYPOTHESIS_TOKEN`, with mode 600, outside Git and snapshots.
The service and scheduled sync read this file directly; no shell export is needed.
`./research-partner/notes configure` verifies and updates it through a hidden prompt.
The former token entry was removed from `vault/.local/config.json`.
The separately identified **sidenote** extension uses that account through
its original **Log in** control. A paired extension page can retrieve the token
into memory; it is not persisted in Chrome or exposed to profile content scripts.
Local logout does not revoke the backend token. The official extension retains
its independent OAuth login.

## Owned knowledge files

After importing or saving pages, open `vault/INDEX.md` in VS Code or Obsidian. Write personal notes
below each document's preserved personal-notes marker. Original annotations are
in `raw/`, citation evidence in `metadata/`, page titles/curated page tags in
`overrides/`, page tag proposals in `analysis/`, per-annotation reactions/sentiment
in `annotation_state/`, and checksummed backups in
`snapshots/`. To optionally initialize a separate local Git repository for your
vault, rerun `notes init --user YOUR_USERNAME --git`. It creates no remote and
pushes nothing. A custom `--vault` option must precede the subcommand.

```sh
./research-partner/notes list
./research-partner/notes search 'a remembered phrase'
./research-partner/notes title DOCUMENT_ID 'My title'
./research-partner/notes analyze DOCUMENT_ID
./research-partner/notes accept-tags DOCUMENT_ID
./research-partner/notes backup
./research-partner/notes restore SNAPSHOT.json --to /tmp/recovered-notes
```

Native browser controls use the same operations. The original Hypothesis save
continues to work if the local service is offline. Daily sync independently
reconciles remote edits, retains missing records, and captures full recovery
snapshots. PDF URNs and file identifiers are preserved without reading local files.
Snapshots contain annotation text/selectors and personal edits, not source page or
PDF bytes. Restore verifies the adjacent SHA-256 checksum and needs an empty target.

## Daily sync and account

```sh
./research-partner/notes doctor
./research-partner/notes sync
./research-partner/notes configure
./research-partner/notes schedule --install
./research-partner/notes schedule --uninstall
```

`configure` verifies a token through a hidden local prompt. `sync --public-only`
explicitly limits a scan to public annotations. Scheduled authenticated sync uses
the locally saved token and runs at 03:00 in the Mac's local timezone. Sleep,
power loss, and offline periods can delay it. Logs and last-success status are in
`vault/.local/`. The scheduled task is independent of the browser UI.

## Headless Codex and metadata

Every LLM request uses `codex exec` with a JSON output schema, ephemeral execution,
a read-only sandbox, disabled shell/browser/app/plugin integrations, and isolated
working directory. The Hypothesis token is removed from the subprocess environment.
Sign in using `codex login`; use `NOTES_CODEX_BIN` if the CLI is not on PATH.
Analysis sends the selected document's highlights/comments/notes to your signed-in
Codex service. Suggestions are reviewable, and comment stance requires supporting
reader text; highlights alone and confidence below 70% become unknown.

The original client's **Page Notes → Page details** generates Auto tags and
type/topic/subtopic groups from the URL's citation metadata, saved notes, and
highlights. Auto tags are saved separately from Manual tags; remove any auto tag
to hide it for that page. They do not edit annotation tags or drafts. The separate
**Analyze this annotation** control classifies one annotation at a time and keeps
its explicit reaction independent of inferred sentiment. Automatic page tag
suggestions can be disabled in the existing extension options.

**User menu → Local library** (also linked from Extension options) opens the local
backup dashboard inside the original client. It lists and searches the saved
pages and exposes their page details and annotations. **Back up now** refreshes
the authenticated backup. Original **Post to…** saves annotations to the real
Hypothesis account; local-only page fields and annotation states stay in this vault.

Hypothesis's own metadata extractor now also reads JSON-LD authors/institutions
into its existing citation pipeline. CLI enrichment remains available:

```sh
./research-partner/notes enrich DOCUMENT_ID
./research-partner/notes enrich DOCUMENT_ID --no-crossref
./research-partner/notes enrich DOCUMENT_ID --zotero-url http://127.0.0.1:1969
```

Unknown institutions remain unknown. The optional local Zotero translation server
is not installed. See [architecture](docs/ARCHITECTURE.md) and
[validation](docs/VALIDATION.md) for implementation details.

```sh
python3 -B -m unittest discover -s research-partner/tests -v
```

## Groups, reactions, and dashboard choices

See the [dashboard guide](../hypothesis/DASHBOARD.md) for the profile-style List and three alternative
views and their search/sort controls. Page Notes now separates Manual tags and
Auto tags and supports manual collections plus automatic type/topic/subtopic
grouping. Imports and browser captures categorize pages locally by default. Page reactions are Like and Dislike. The new library includes Studio, Paper, and Compact designs with Library, Dashboard, and Collections tabs. See the [redesign and enrichment guide](docs/LIBRARY-REDESIGN.md) for editable metadata, activity history, scholarly IDs/citations, and the public-paper Luna trial.

Automatic classifications and tags are in analysis/. Manual groups, page ratings,
and manual tags are in overrides/. Group names persist in collections/manual.json
even when empty. All are included in the checksummed recovery snapshots.

Local organization needs no model account or transfer approval:

```sh
./research-partner/notes organize --provider local
```

Optional Codex categorization uses `gpt-6-luna` with low reasoning effort and an
explicit saved-context approval. A compatible official CLI (v0.163.0) is available
inside the ignored `.local-tools/` directory; the system CLI is unchanged. Recreate
that local installation from the workspace root if needed:

```sh
npm install --prefix research-partner/.local-tools --no-save --ignore-scripts @openai/codex@0.163.0
```

The adapter prefers `NOTES_CODEX_BIN`, then the project-local CLI, then PATH.
See [classification and local NLP options](docs/CLASSIFICATION.md).
