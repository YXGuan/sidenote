# Native Hypothesis validation

Verified on 2026-10-17 against the actual upstream repositories, with native
patches applied and the original interface retained.

## Builds and source

- The original client builds with its own Yarn/Gulp pipeline.
- The original extension builds with its own Makefile and links to the local
  client using `portal:../client`.
- `hypothesis/build` completed successfully; the ready-to-load directory is
  `hypothesis/browser-extension/build/`.
- Both exported patches were checked against clean copies of their original
  repositories and apply successfully.
- TypeScript checks and ESLint passed for the native changes in both repositories.
- The saved Hypothesis developer token and local pairing key are absent from
  the exported patches and built extension.

## Regression suites

- **473 client regression tests passed** during the native integration, covering the original annotation action bar,
  annotation editor/header, tag editor, save workflow, frame synchronization,
  HTML metadata extraction, the new native controls/tag suggestions, and local
  account login/logout without persisting or revoking the backend token. Account
  tokens are not supplied to another API host.
- **184 browser-extension tests passed**, including rejection of account access
  from profile content scripts, other extensions, and unpaired clients.
- **211 focused client tests passed** for page controls, library helpers, metadata,
  and the affected sidebar routes. After the profile/date-grouping changes, **72
  focused tests passed again** for PageResearch, HypothesisApp, and library helpers.
- **46 local storage tests passed**, including native annotation mirroring,
  preservation of citation metadata, API-compatible title shape, draft proposal
  caching without saving a draft as an annotation, imports, retention, restore,
  credential exclusion, authenticated loopback boundaries, multi-label classification,
  separate tag sources, page-rating/Likes consistency, persistent empty groups,
  classification caching, concurrent edits, automatic categorization after imports
  and captures, failure-independent backups, and rejection of unapproved Codex jobs.

Offline error behavior is tested through the real installed extension/browser
flow below, rather than a mocked component event.

## Real extension browser flow

`python3 -B hypothesis/test-native.py` launches the built Hypothesis extension in
an isolated Chromium profile with a temporary local vault. It exercises the real
original client rendering, original extension worker, runtime messaging, and
actual authenticated loopback HTTP bridge. Publisher/API responses and model tag
proposals use synthetic fixtures; this test does not alter the user's research.

The coexistence run also loaded a copy of the installed official extension
(`1.1769.0.0`) into the same isolated profile. Both original service workers were
present with distinct IDs/names: **sidenote** at
`lebpfahhlannplfhlllolppkmcapecge` and the official extension at
`bjfhmglciegochdpefhhlphglcehbmek`. The ordinary Chrome profile was not changed by
the test. Local login used a synthetic backend account token and the original
Log in control; the token was absent from Chrome local storage.

All checks passed:

1. The original Hypothesis toolbar activates the original sidebar.
2. Its original annotation card, quote, comment, tags, and account/group controls render.
3. An annotation-specific like is persisted through the worker and local bridge, independently of other annotations.
4. Citation metadata arrives automatically through the original frame/metadata pipeline.
5. Page Notes contains page metadata, the personal title editor, separate Manual/Auto tags, four page ratings, and manual collections.
6. A manual tag stays separate from auto tags; Love adds the page to Likes; For later and a new Lab reading group persist without hosted annotation saves.
7. With local storage simulated offline, a useful error appears while the original Edit action remains usable.
8. The existing Hypothesis profile receives an inline title editor.
9. A saved personal profile title returns after reloading the page.
10. The local library lists, searches, expands, and reloads the saved pages inside the original client.
11. Overview charts filter by topic, Table sorts by page rating, and Board groups by topics and manual collections. The chosen view survives reload.
12. Codex organization shows a data-transfer confirmation; cancelling leaves the job idle. Local organization completes without that transfer dialog.
13. The default profile-style List has white surroundings and dark expandable titles, alongside the other three views.
14. The original Post control sends an authenticated annotation update to the cloud API fixture; page edits do not call that API.

The test reported no unexpected API calls or page errors. Its isolated browser
profile is removed afterward. Load the rebuilt local extension into the ordinary
Chrome profile using the migration instructions in
[the Hypothesis README](../../hypothesis/README.md).

The historical screenshots have been removed. Current smoke tests can save
fresh synthetic captures when `HYPOTHESIS_SCREENSHOT_DIR` is set; see
[development](../../docs/DEVELOPMENT.md#browser-integration).

## Preserved live integrations

The existing authenticated export retains **608 annotations across 169 sources**,
including two PDF URN sources. The full export was independently restored and its
original JSON matched. The developer token was moved into ignored `research-partner/.env` with
mode 600 and removed from the former JSON config, outside Git and snapshots. The updated bridge reports the same 169
sources and exposes annotation IDs needed for the profile integration.

The authenticated 03:00 local daily LaunchAgent remains installed. Its first run
completed with exit code 0. Real headless codex exec generated structured tags
and comment-stance suggestions for the already-public source; all LLM work uses
that adapter. The browser test's synthetic tag response is a test fixture, not
an alternative model integration.

## Remaining scope

Personal titles/reactions remain local; hosted Hypothesis source records and
sharing controls retain their normal behavior. Publisher metadata coverage
varies with exposed fields. The optional Zotero translation server is supported
through a local adapter and is not installed. Search/chat and wiki synthesis are now implemented in the Research workspace
(see the October 22 validation below). Recommendations and collaboration remain
future milestones.

## Refreshed authenticated backup

The authenticated export on 2026-10-17 contains 608 annotations across 169 source
URLs/identifiers, including private and group annotations accessible to the
account. The self-contained snapshot and adjacent SHA-256 checksum live under
`research-partner/vault/snapshots/`. A restore to an empty temporary directory
matched all original annotation JSON records. Credentials were absent. Tests
also verify that annotation-specific reactions and analysis survive restoration
and cannot affect another annotation on the same URL.

.env storage is read directly by the CLI, server, and daily sync without shell
sourcing. The file is mode 600 and ignored by Git; API/pairing secrets are not
embedded in the extension or exported source patches.

The final page-tag workflow was also exercised with a real headless Codex call
on a temporary synthetic page. It returned three page tags and zero annotation
sentiments. Page requests use an output schema that forbids annotation
sentiments; an automated regression test checks that constraint.

## Organization and recovery verification

The optional classifier completed a real `gpt-6-luna` low-reasoning request on
eight invented pages using the official project-local Codex CLI v0.163.0. It
returned structurally valid IDs and classifications. The system CLI remains
unchanged. No existing private library data was sent to Codex.

The full existing library was then processed entirely locally: **172 sources**,
**123 with a type or topic**, **49 unclassified**. All 172 analysis records carry
`local-rules` provenance. The raw 610 annotations and manual fields are retained.
The eight-example synthetic comparison and its limits are saved in
[the benchmark results](../experiments/results.json). No accuracy or speed claim
about real research follows from that smoke test. The optional SentenceTransformers
adapter is included but its package/weights are not installed or evaluated.

The local service was restarted with the updated API. Its latest local check
contains 610 annotations across 172 sources, the same account token, and the
existing pairing key. The earlier full authenticated cloud export contained 608
annotations across 169 sources; newer local captures and mirrored saves are also
preserved. A fresh
local checksummed snapshot was restored to an empty temporary directory and all
raw records, metadata, local overrides, analysis, annotation states, group catalog,
and personal notes were compared. New snapshots include `collections/`, and
earlier snapshots remain readable.

The latest verified local recovery snapshot is
`20261018T004120.976717Z-730d9c9c2a03.json` under `vault/snapshots/`, with its
adjacent SHA-256 checksum. The API exposes separate manual/auto tags,
classification, groups, page ratings, dates, and full-text context. An unapproved
Codex organization request returns 400 and leaves the job idle. Local organization
requires no cloud-transfer approval.

After local categorization, recovery verification also compared the raw records,
metadata, overrides, annotation states, collections, and personal notes against
the pre-run snapshot: all were unchanged. Only automatic classification and its
generated Markdown views were updated. The restarted bridge reports local +
automatic, the Luna default, the original account/pairing, and the same counts.

## Dashboard loading with an older extension worker

A real Chrome inspection reproduced the reported zero dashboard: the new client
received `Unsupported local research action` from a background worker retained
from an earlier build. An optional organization request caused Promise.all to
discard the successful library result. The loader now treats status and
organization as optional, preserves loaded source records, and shows a specific
extension reload hint. Required connection errors show unavailable totals and
a Retry connection button instead of inventing an empty library.

Regression coverage includes optional request failures, required authentication
failures, valid empty/malformed responses, and the isolated native extension
flow with a deliberately unsupported organization action and a disconnected
library, followed by successful retry.

The updated build, TypeScript, ESLint, 10 focused loading/library tests, and the
real native browser flow passed after this fix. The live authenticated library
endpoint still returns 172 sources and 610 annotations. Reloading the extension
in the ordinary Chrome window was blocked by the macOS Screen Time limit, so
that final normal-profile reload must happen after Chrome is unlocked.

## Persistent bridge — 2026-10-18

The reported "Start the local Hypothesis storage service" error coincided with
no listener on port 8765. The temporary session process had not persisted. A
per-user LaunchAgent is now installed with RunAtLoad/KeepAlive; launchd reports
it running independently of the agent's shell session. The authenticated local
API returns 172 sources and 612 annotations and the original account token and
pairing still match. No model job was started. The existing daily backup job
remains separate.

All **49 backend tests passed**, including persistent agent configuration,
credential exclusion, refusal to stop an unmanaged listener, and targeting only
the bridge label on installation/removal. Live checks verified the loopback
health/library/account endpoints, KeepAlive registration, mode-600 agent/log
files, and absence of saved credentials from the agent definition.

## Dashboard annotation sorting — 2026-10-18

Added Most annotations / Fewest annotations sorting and a Table annotation-count
column. Dashboard cache updates preserve annotation counts and search context.
At the user's request, the duplicate inline Edit title & tags controls and their
component tests were removed. The existing Page details editor remains available
by expanding a saved page.

All **12 focused client tests passed**, along with TypeScript and ESLint after
removing the duplicate editor. The unpacked extension is rebuilt and exported as
reproducible patches. Synthetic browser checks cover numeric annotation sorting
in both directions, saved sort preference, absence of duplicate edit controls,
and availability of the existing dashboard title/manual-tag controls. No real
library records are modified by these tests. Reload the unpacked extension in
Chrome, then refresh the dashboard to load the change.

## Research workspace — 2026-10-22

Implemented natural-language Find for links/annotations, Ask with saved context
and optional live web search, a Karpathy-style persistent wiki, and a NetworkX
graph rendered by Cytoscape.js. Search reuses rank-bm25 with NLTK stemming and
optional model query expansion. Wiki synthesis checks exact source quotes,
concurrent changes, and canonical generations; recovery snapshots retain wiki
state and prior revisions. Current relevant wiki synthesis can supplement Ask;
stale or pending-refresh synthesis is excluded.

Verification: 81 backend tests, 4 setup tests, 31 targeted client tests, and 194
extension tests passed. Client/worker TypeScript and changed-file ESLint passed.
Both patches were exported and the unpacked extension rebuilt. The dedicated
`python3 -B hypothesis/test-research.py` smoke passed in isolated Chromium through
real pairing/worker/bridge routes: annotation retrieval, wiki generation,
synthesis with an injected model fixture, lint, interactive graph rendering, and
Ask with a fixture plus the enabled web boundary. It used a temporary synthetic
vault; no real model was called. The older full-app `test-native.py` stops at its
pre-existing removed **Love** control assertion and does not count as passing.

The standalone `experiments/wiki_trial.py` used three invented sources: literal
whole-query matching found zero annotations, BM25 found the two relevant ones,
and five wiki pages were generated. Adding a cautionary annotation triggered a
stale check, then rebuilding cleared the deterministic issues. This tiny example
is a workflow demonstration, not a general retrieval-quality benchmark.

After tests, the owner's local wiki was initialized from the existing vault
without model calls: 184 source pages and 44 topic pages. The existing managed
bridge was restarted and checked healthy. Model responses/search behavior have
fixture coverage; live web answers and actual LLM topic synthesis were not run.
The user's loaded Chrome extension still requires Reload and a refreshed library
tab; the isolated test is not evidence that their browser loaded this build.
