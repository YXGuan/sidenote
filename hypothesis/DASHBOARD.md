# Local library

The library uses **Compact**, with **Library**, **Dashboard**, **Collections**,
**Research**, **Recommendations**, and **Settings** tabs. Filters include removable chips, dates, authors, institutions, source
types, subjects, collections and metadata gaps. Page details now supports manual
citation/classification corrections and activity history. Love and Hate are
removed; legacy values display as Like and Dislike.

**Recommendations** finds scholarly papers with Semantic Scholar using every
applicable paper in **Liked (Auto)**, independent of Library filters. Open the tab
to read cached results, then choose **Refresh recommendations** to send paper IDs
and unresolved paper titles. Highlights, comments, and personal notes stay local.
Results and seed details each reveal 20 entries at a time. See
[matching, privacy, and limitations](../docs/RECOMMENDATIONS.md).

Search and filters appear only on the Library tab and stick to the top while you
scroll through saved pages.
Expanded filters scroll within the panel on short screens so results remain reachable.
Compact table headers provide up/down arrows to sort Page, Notes, Added, Modified,
and Visits (when shown). Topic and Authors open searchable filter lists, also
available in the toolbar. Select All topics or All authors to clear that filter.
The Actions header has no sorting or filter controls.
Use the trash icon under **Actions** to **Remove from library**. **Undo** restores the most recently
removed page. Removal persists across refreshes and annotation syncs, and excludes
the page from library counts, collections, research inputs, and visit tracking.
Original annotations, personal notes, metadata, edits, and backups are retained
locally; hosted Hypothesis annotations are unchanged.

**Settings** contains **Back up now**, **Enrich research**, and organization controls.

**Settings → Zotero** connects to Zotero desktop or your synced online library, imports RIS
or CSL JSON files, and exports references for Zotero. RIS can include highlights,
comments, and personal notes. See the [Zotero guide](../docs/ZOTERO.md).
Enable **Back up automatically every day**, choose a local time and public-only
or authenticated imports, then **Save settings**. Daily backups default to off.
The local service runs them with Chrome closed, catches up after sleep/restart,
and retries failed imports after an hour. Each run saves a local snapshot before
importing, so a connection failure still leaves a backup of local notes.

**Enrich research automatically** preserves automatic enrichment when a scholarly
API key is configured. It checks on source changes and every 15 minutes in the
local service. Manual and automatic batches process only new, changed, or expired
records: successful lookups are fresh for seven days, unresolved results for an
hour. Cached pages incur no lookup or per-page wait. Removed pages stay excluded.

Set, replace, or remove **OpenAlex** and **Semantic Scholar** API keys in Settings.
Blank fields preserve saved keys. Values are written to the existing ignored
credential file with owner-only permissions; responses show only configured status,
and snapshots exclude keys. Environment-managed keys are shown as read-only.
Hypothesis account tokens still use the hidden `notes configure` prompt.

OpenAlex-indexed pages display the API's Topics and Keywords in place of local
topics/subtopics; keyword filters and charts use those same labels. Manual corrections
take priority, and other pages retain local taxonomy labels. Page details links to
OpenAlex, its API JSON, Semantic Scholar, and arXiv when each is available. Full
OpenAlex responses are cached in the vault for offline use and backups. See the
[classification guide](../research-partner/docs/CLASSIFICATION.md) for backfilling.

When the loaded extension needs a reload for newer dashboard controls, a compact
**Dashboard update available** hint offers **How to update** and **Dismiss**.
Dismissal survives refreshes and reopening the library. Saved pages remain usable;
connection failures still offer **Retry connection**. Reload instructions also
remain in the [setup guide](../docs/SETUP.md#connect-chrome).

Navigation updates the URL. Copy or bookmark it to reopen a view; Back and Forward
restore the previous view, collection, or page details. The extension keeps its
`notebook.html?local-library=1` entry point and uses hash paths, so refreshing a
deep link works without a web server rewrite.

| Route suffix | Opens |
| --- | --- |
| `#/library` | Saved pages |
| `#/library/pages/PAGE_ID` | A saved page's details |
| `#/dashboard` | Reading dashboard |
| `#/collections` | All collections |
| `#/collections/For%20later` | For later collection |
| `#/collections/Likes/pages/PAGE_ID` | Page details within Liked |
| `#/research/ask` or `#/research/find` | Ask or library search |
| `#/research/wiki/PAGE_ID` | A specific wiki page |
| `#/research/graph` or `#/research/graph/NODE_ID` | Focused knowledge graph |
| `#/research/kura/hierarchy` | Topic classification (default); `map` and `sizes` also work |
| `#/settings` | Backup schedule, enrichment, API keys, and organization |

Collection names and identifiers are URL encoded. Kura cluster links append
`/clusters/CLUSTER_ID` to the atlas view. Old `?tab=...` and `?view=...` links still
work; an explicit hash route takes precedence. Opening a route reads existing
results; model actions still require their explicit action buttons.

**Settings → Developer mode → Enable developer mode** reveals experimental
**Wiki** and **Knowledge graph** tabs under Research. Developer mode defaults to
off and is saved automatically in this browser. Existing Wiki and graph URLs
retain their destination and offer an enable button when the mode is off;
these views do not load or refresh until enabled. Ask, Find in library, and
Topic classification remain available in the normal Research workspace.

Research's **Update settings** controls local Wiki updates and automatic graph
and saved Kura result refresh, with 30-second, 1-minute, or 5-minute intervals.
Wiki builds default to manual; graph and saved atlas refresh default to enabled
while their view is visible. Each view has manual refresh controls and freshness
status. Kura analysis and Wiki synthesis still require their explicit buttons.
See [run and refresh instructions](../research-partner/docs/RESEARCH-WORKSPACE.md#run-refresh-and-update-settings).

**Research** provides Ask + web with saved-library context, natural-language
search for links or individual annotations, a persistent Markdown wiki, and an
interactive knowledge graph. Build the wiki locally, then synthesize a topic
into cited overviews, key ideas, disagreements, open questions, and related
concept pages. **Explore connections** opens its graph neighborhood; expand it
and inspect labeled connections and their original evidence. See the [Research workspace guide](../research-partner/docs/RESEARCH-WORKSPACE.md)
for the workflow, reused projects, experiment, CLI, and data boundaries.

Every saved web page has an **Open page ↗** link, including
collection results. It opens the original source in a new tab. A saved PDF with
only an identifier shows the control as unavailable until a source URL exists.

**Compact** is the only layout. Previous layout preferences and old design links
open Compact while preserving saved sorting and the requested page or tab.
Use the header's **Dark mode** / **Light mode** button for a quick switch, or
**Settings → Appearance → Color mode** to choose **Light**, **Dark**, or **System**.
The choice is remembered in this browser and System follows operating-system
changes. Dark mode uses Console's graphite surfaces, pale text, amber selection,
and bundled Host Grotesk typography across the library, dashboard, collections,
settings, research views, and page details.

The Reading activity chart offers **Daily**, **Weekly**, and **Monthly** grouping.
Daily ranges are 7/30/90 days, weekly ranges are 4/12/26 weeks, and monthly ranges
are 3/6/12 months. The selected grouping and each grouping's range are remembered
in this browser. Dates use UTC calendar days; weeks start Monday, and the current
period includes activity through today. Pages saved, annotations, and recorded
visits are aggregated from the full matching library. **View activity data**
shows the exact bucket counts, revealing 20 periods at a time with **Show more**.

Dashboard shows separate annotation and page rankings by topic, keyword, and
source authors together. Page rankings include saved pages without annotations;
each page counts once per label, including every coauthor. Click a label in any
chart to open the matching library results. Each ranking initially shows 20 entries.
Each **Show more** click reveals another 20, with independent controls and visible
and total counts. Saved-page and collection results use the same behavior.
Filtering or sorting starts again at 20; unchanged background
refreshes retain the expanded results. Counts and filters always use all matching
data, and every entry remains accessible.
Each highlight or note counts once per label; coauthors each receive that count.

Collections also includes **Liked (Auto)** (local VADER sentiment in personal
comments), **Questions (Auto)** (local NLTK question patterns in comments/highlights),
and **Visit Often** (at least 3 visits in the last 30 days, most visited first).
They update from current notes and activity, without changing manual collections.
After reloading this extension, active saved-page openings and tab returns are
tracked with or without the sidebar. Unrelated/incognito pages are excluded;
events within five minutes count once. Older counts are sidebar captures only.

See the [redesign and enrichment guide](../research-partner/docs/LIBRARY-REDESIGN.md)
for previews, scholarly IDs/citations, the Luna trial, privacy boundaries, build
instructions and verification. The built extension is in `browser-extension/build/`.

Old `view=list|overview|table|board` links still open their corresponding tabs in
Compact. Previous `design` parameters are accepted without changing the layout.

Research → **Topic classification** clusters all saved annotations and personal notes into
an interactive map and topic hierarchy. Switch to **Topic sizes**, search topic
names, filter for annotations or personal notes, and select a cluster to read
its original evidence. Hierarchy opens first, with independent collapse controls
for each branch. Redundant single-child levels are removed from saved results
when displayed; existing topic links and evidence remain accessible without
rerunning analysis. **Classify all notes** explicitly sends that text to
your signed-in OpenAI/Codex model for summaries and labels; embeddings and
clustering run locally. Install its optional runtime first. See the
[Kura guide](../research-partner/docs/RESEARCH-WORKSPACE.md#kura-research-atlas).
