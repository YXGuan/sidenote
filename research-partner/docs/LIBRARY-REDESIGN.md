# Local library redesign

**Compact** is the library's only layout, with a slate table, added/modified
dates, a navigation rail, and page details. Library, Dashboard, Collections,
Research, and Settings share the same local vault. Library is the landing page.
Previous layout preferences migrate to Compact; saved sorting survives reloads.

Append `&tab=dashboard` or `&tab=collections` to open those tabs.
Old `design` parameters and `view=list|overview|table|board` links remain accepted,
using Compact while preserving the requested page or tab.

Build the extension and run the browser checks from the workspace root:

```sh
./hypothesis/build
node hypothesis/test-library-routing.mjs
```

Routing checks use the real library components with synthetic data in a temporary
directory that is removed afterward. They do not need a design preview folder.
See [development](../../docs/DEVELOPMENT.md#browser-integration) for native smoke
tests and optional screenshot output.

After rebuilding the extension, reload **sidenote** in `chrome://extensions` and
refresh its library and source tabs. Pairing is retained. Respect browser-tool
access limits; automated checks use isolated profiles and synthetic data.

## Navigation and filtering

Dashboard charts default to annotation counts by topic,
subtopic, and source authors. Each annotation ID is counted once per label,
including across repeated labels or source aliases. An annotation contributes to
each of its page's topics and coauthors. Charts show all entries, sorted by count,
and filter the library when clicked. The count selector retains saved-page rankings
as an option, also without a limit.

Library has an **Open page ↗** link on each saved item;
it opens the source in a new tab. Items with only a PDF identifier and no source
URL show it disabled. Library also has quick Like and For later controls and a details panel. Collections
includes Liked, For later, user-created collections, **Liked (Auto)**, **Questions
(Auto)**, and **Visit Often**. Automatic membership is derived locally using NLTK,
VADER and rolling visit counts; see [the rules](CLASSIFICATION.md#automatic-collections-with-local-nlp).
The original local
collection name `Likes` remains compatible with existing data. Love and Hate
controls are removed; historical Love displays as Like, Hate as Dislike, without
rewriting historical records. The API accepts legacy values for compatibility.

Search includes notes, source descriptions, abstracts, bibliographic IDs, tags,
authors, institutions and topics. Visible source/topic/author selectors have
counts. The expanded filter area adds subtopic, institution, collection, reaction,
metadata gaps, and inclusive added-date boundaries. Each applied filter has a
removable chip. Filters apply across tabs, including dashboard graphs.

Dashboard shows actual page/annotation/session totals, metadata coverage, source
types, top subjects/authors and monthly activity. Charts have an accessible data
table. Annotation dates come from saved annotation creation times, not an estimate
based on when a page was saved. Monthly activity buckets use UTC.

## Metadata, history and manual corrections

Page details → **Edit details** edits source type, topics, parent-linked subtopics,
authors, institutions, journal, DOI, arXiv ID and publication date. Separate
multiple author/institution names with semicolons, topics with commas, and
subtopics with semicolons in `topic / name` form. Manual corrections live in
`overrides/`, survive re-extraction and classification, and can explicitly clear
an incorrect field. **Use automatic classification** removes the classification
override. Citation corrections remain separately preserved.

First added is the earliest available annotation creation timestamp or initial
capture timestamp. Capture timestamps are now retained immutably rather than
moving forward on every metadata refresh. Last modified includes annotation,
metadata, classification and manual edits, not visits. Earlier capture-only
records use the earliest timestamp still available; lost historical dates cannot
be reconstructed with certainty.

Page activity shows annotation/visit counts over six months, first added,
last modified and last recorded visit. Updated extensions count active saved-page
loads and tab returns, even without opening the sidebar. Unrelated and incognito
pages are excluded. Five-minute deduplication covers sidebar captures and browser
events together. Earlier counts represent sidebar captures only; browser history
is not imported. Visit Often requires three visits within the last 30 UTC days
and sorts by that count; its table shows the count for each page.
Activity records are included in checksummed snapshots and restores.

## Scholarly resolution

**Settings → Enrich research** runs an incremental library pass. Fresh cached
pages are skipped without network requests or per-page waits. Automatic enrichment
checks new, changed, and expired sources after saves and every 15 minutes while
the bridge is running; its switch and scholarly API keys live in Settings.
**Find research metadata** refreshes
one page. New research captures and mirrored saves also queue enrichment on the
local backend when scholarly API keys are configured. Annotation saves succeed
independently of lookup failures.

The pipeline reads embedded citation/JSON-LD metadata, retrieves arXiv/ACL landing
pages when useful, resolves DOI/arXiv/PubMed identifiers, and uses conservative
title search when needed. A title search must have a unique close match; short or
fuzzy titles require author corroboration. Ambiguity is left unresolved. Exact
IDs are preferred. OpenAlex resolution can follow a Semantic Scholar DOI or a
verified title returned for an arXiv record.

Observed results include titles, abstracts, authors, publication dates,
institutions, OpenAlex work IDs, arXiv IDs, Semantic Scholar paper/author IDs,
OpenAlex author IDs, ORCIDs, and provider-specific citation counts with an as-of
date. Counts are kept separately because indexes differ. Canonical author
crosswalks use a unique exact normalized name within the same resolved work;
names alone never merge people globally. Provider identities remain separate
when evidence is insufficient. Institutions are paper-linked affiliations when
available, not a guessed current university.

The backend reads `S2_API_KEY` and `OPENALEX_API_KEY` from the ignored mode-600
`.env`; keys never enter frontend bundles, local snapshots, or model context.
Credentials are sent only to their official HTTPS API host and are not forwarded
across host redirects. Successful lookups cache for seven days; partial/unresolved
lookups retry after one hour or immediately on an explicit per-page refresh.
Provider outages retain existing metadata and manual corrections.

```sh
./research-partner/notes enrich-research
./research-partner/notes enrich-research DOCUMENT_ID --force
```

References: [OpenAlex API](https://help.openalex.org/api/),
[OpenAlex authentication and fields](https://help.openalex.org/api/llm-quick-reference/),
[Semantic Scholar Academic Graph](https://api.semanticscholar.org/api-docs/).

## Classification and Luna trial

`research_notes/taxonomy.json` is the versioned local subject hierarchy. Source
type is independent of subject: a paper no longer automatically gets “research.”
Computer science, social science, philosophy, religion and the other domains have
specific subtopics and synonym rules. Generic isolated words in an abstract do
not automatically assign a broad topic. Missing evidence remains unclassified.

The optional Codex provider uses `gpt-6-luna` with low reasoning and structured
output. It can summarize supplied abstracts/notes; it does not invent authors,
affiliations, titles or citation counts. Without a model, the interface shows a
source description or bounded abstract excerpt, labeled accordingly. The default
automatic provider remains local; a small trial does not silently change it.

The [public-paper trial](../experiments/research_trial.py) used seven real public
abstracts from OpenAlex and no private notes. One selected paper was omitted
because no abstract was available. Subject micro-F1 was **0.842 local / 0.952
Luna**, with **4/7 / 6/7** exact subject-set matches. Measured batch times were
**0.046 s / 8.645 s**, including CLI/network overhead for Luna. The generated
summaries were not independently scored. This is a small hand-selected, reviewed
sample, not a blinded or held-out benchmark. DOI fixtures and local rules were
corrected during the pilot, so these scores cannot establish general accuracy.
See [complete results](../experiments/research-trial-results.json).

[Official OpenAI model documentation](https://learn.chatgpt.com/docs/models)
identifies Luna as a focused-task model; availability depends on the signed-in
account. The trial ran successfully through the existing local Codex adapter.

## Verification

- Backend: 66 tests, including automatic NLP collections, immutable dates, visit deduplication, snapshot
  recovery, persistent manual corrections, ambiguous-title rejection, author-ID
  crosswalks, partial provider failures and zero citation counts.
- Client: typecheck, changed-file lint, and 150 targeted metadata/library/tag/app regressions.
- Extension: typecheck and 189 regression tests, including saved-page visit tracking.
- Library follow-up: 24 targeted tests covering the Compact preference migration,
  distinct annotation counts, chart filtering, and saved-page count switching.
- Actual component preview: Studio/Paper/Compact/Classic, tabs, search/filters, metadata
  editor and collection actions verified with synthetic data.

The initial enrichment and targeted retry resolved **73 of 77** saved research pages on October 22, 2026 (66 OpenAlex work IDs, 69 Semantic Scholar paper IDs). Four remained unresolved. This is identifier coverage, not an independently audited extraction accuracy score.
