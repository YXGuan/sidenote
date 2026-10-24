# Search, web answers, wiki, and knowledge graph

Open **Research** in sidenote's library navigation. See
[Development](../../docs/DEVELOPMENT.md) for rebuilding and reloading.

## Run, refresh, and update settings

Open **Update settings** above the Research view. These preferences are saved in
this browser and apply while the relevant view is visible. The interval can be
30 seconds, 1 minute (default), or 5 minutes; returning to a visible page also
refreshes enabled views. Closing the page stops automatic refresh, while an
already started analysis job can continue in the bridge.

| View | Run or update content | Reload existing content | Automatic behavior |
| --- | --- | --- | --- |
| Wiki | **Build wiki from library** / **Update wiki from library**; local, no model | **Refresh saved Wiki** | Builds are manual by default. Enable **Update Wiki automatically** to build missing or stale pages locally while Wiki is open. Synthesis remains an explicit model action. |
| Knowledge graph | Computed locally from the saved library; no separate build | **Refresh graph**; **Show all** clears the topic filter | Loads on open. Automatic refresh is on by default and preserves the applied topic filter. |
| Topic classification | **Classify all notes** / **Update topic classification**; sends annotation and personal-note text to the signed-in model | **Refresh saved results** | Reloading completed results is on by default. Analysis always requires the Classify/Update button; enabling refresh never starts it. |

Wiki opens the first topic when no specific wiki page is selected. Wiki and
Kura show their last build time and **Changes pending** when saved evidence
has changed. The graph shows the last refresh time and the visible/total node
counts. Refreshing saved Wiki or Kura results reads an existing generation;
use their Build/Update buttons to incorporate changed evidence.

An empty Wiki needs a local build. An empty Kura atlas needs annotations or
personal notes, its optional runtime, and an explicit analysis run. A graph
with no results may have a topic filter with no matches; use **Show all**.
Unavailable or incompatible service responses show an error with refresh
controls instead of a blank view. Reload the extension after rebuilding it.

## Ask + web

Enter a question and choose **Ask with library context**. The backend selects
relevant saved excerpts (up to eight source matches, within a 48 KB context
budget), and supplies relevant current wiki synthesis. The model may use live
web search by default. Uncheck **Allow web research** for saved evidence only.
Inspect the expandable context panel and answer citations.

Ask sends the question and selected saved excerpts to the signed-in Codex
service. Web queries are instructed to use public topic terms, not private
comments. This is a model instruction, not a technical data-loss prevention
guarantee. Questions and answers stay in the current UI/server job memory; they
are not silently written to annotations or the wiki.

Only answering enables `web_search="live"`. Classification, query expansion,
and wiki synthesis retain disabled web search, shell, app/plugin, browser and
computer tools. See [official OpenAI documentation](https://learn.chatgpt.com/docs/config-file/config-reference).
The configured model/account must support the requested tools. Fixture tests
do not prove live model or web behavior.

## Find in library

Try **give me all annotations related to computational social science**, choosing
Annotations or Links. The whole vault is searched, with total counts and
pagination of 50 records. Link retrieval includes saved annotations on each
source. Annotation results show the original highlight, reader comment, and
direct Hypothesis link.

Local retrieval uses NLTK stemming and **rank-bm25 BM25Plus**. **Find related terms
with AI** sends only the question to the model for up to eight related phrases.
The terms are visible and matching stays local. Uncheck it for model-free
search. This is lexical retrieval with optional model query expansion, not a
dense embedding index. Scores rank results; they are not confidence values.
Related-topic matching cannot guarantee finding every semantically relevant
record. The original exact-string CLI `notes search` remains available.

## Wiki: understand your reading

1. **Build wiki from library** prepares the evidence locally from saved topics,
   classification, highlights, abstracts, comments, and personal notes.
2. Select a topic and **Synthesize this topic** to write a readable concept page
   with **Overview**, **Key ideas**, **Disagreements**, and **Open questions**.
   The signed-in model can discover up to five related concepts with aliases and
   their own cited pages, plus directed connections between concepts. Existing
   concept names/aliases are reused when unambiguous.
3. Open **Evidence** under any statement or connection to inspect the exact
   supporting passages and original links. Reader comments, personal notes, and
   explicit source dislikes remain visible. Every statement requires a known
   record and matching quote. A disagreement requires evidence from at least
   two different source documents. Quote presence does not prove logical support.
4. **Explore connections** opens this page's focused graph. **Connected ideas**
   links to other concept pages; **Related reading** labels shared evidence
   separately. **Saved evidence** opens the underlying passages and notes.
5. **Update wiki from library** incorporates changes locally. Unverifiable
   claims/connections are removed; affected pages are marked for synthesis.
   Unrelated changes preserve current synthesis. Concurrent source/wiki edits
   reject an in-flight model result before it can overwrite saved work.
6. **Check wiki** checks quotes, missing evidence, and broken page/relationship
   links. It does not audit factual accuracy or the logic of a disagreement.

Search concept names and aliases in the sidebar. Concepts, sources, related
pages, saved evidence, and graph lists expand independently in batches of 20.
Unchanged refreshes retain expansion; direct links retain access to selected pages.
Large topics process all saved text across successive cited synthesis passes;
coverage counts show the evidence considered. Summarization can omit details.
Opening or refreshing either view never starts a model call automatically.
Full articles/PDFs are not fetched by this workflow.

The ingest/query/check workflow follows [Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).
`knowledge/state.json` is the canonical generation, with previous versions in
`knowledge/revision-*.json`. Version 1 state is read safely and upgraded on the
next local build. Legacy single-quote contradictions require review and are
not presented as validated disagreements. Exports live in `wiki/*.md`, with
`index.md` and `log.md`; topic exports link to complete source notebooks.
Recovery snapshots retain canonical state/revisions. After restoring,
`notes wiki export` recreates Markdown. Keep personal writing in `library/`
below its personal-note marker; generated wiki exports are replaced on update.

## Knowledge graph: investigate a connection

Search for a **concept, question, or source**. Local BM25 ranks matching names,
aliases, and saved passage text; choose another starting point from the search
matches. This is lexical retrieval, not semantic question answering.
The default view starts with a useful concept and its immediate neighborhood.
**Expand neighborhood** reveals another connection step, up to three. **Show all**
opens the library overview. A neighborhood displays up to 80 nodes; the selected
item and connecting paths survive truncation. Counts describe the full result.

**NetworkX** supplies graph structure, ego neighborhoods, and breadth-first
traversal. **Cytoscape.js** renders directed connections and handles layout,
selection, drag/pan, zoom, and fit. Source-stated connections use solid lines,
model-inferred connections use dashed lines, and metadata links are faint.
Select a connection on the canvas or in the accessible **Connections** list to
read its explanation, inspect its passages, or explore from either endpoint.
Select a node to open its wiki page or original source. Node lists also provide
keyboard access. Theme changes and unchanged background refreshes preserve the
current graph position and selection.

Wiki and graph share the same validated concept relationships. Stale synthesis
is excluded from the graph until its evidence and synthesis are refreshed.
Metadata relationships continue to describe filing, authorship, and containment;
they do not imply agreement or causality. Inference labels reflect the model's
assessment, not a deterministic proof of the relationship.

Graph focus links use `#/research/graph/NODE_ID`; reload and Back/Forward restore
the selected starting point. Example CLI:
`notes graph --focus CONCEPT_ID --depth 2`; `notes graph --overview` exports an overview.

## Reused projects

| Project | Role | License |
| --- | --- | --- |
| [rank-bm25](https://github.com/dorianbrown/rank_bm25) 0.2.2 | Ranking implementation | Apache-2.0 |
| [NLTK](https://github.com/nltk/nltk) | Existing stemming dependency | Apache-2.0 |
| [NetworkX](https://github.com/networkx/networkx) 3.4.2 | Directed multigraphs, ego neighborhoods, BFS | BSD-3-Clause |
| [Cytoscape.js](https://github.com/cytoscape/cytoscape.js) 3.33.1 | Layouts, pan/zoom, selection and rendering | MIT |
| Hypothesis annotation-ui | Existing sanitized Markdown renderer | Existing upstream license |

Quartz and SilverBullet were evaluated as wiki experience references; LightRAG
and Graphiti as knowledge-pipeline candidates. Their code is not bundled here.
LightRAG would add a separate model/embedding configuration, and Graphiti a
separate graph runtime. This implementation keeps the existing signed-in model
adapter and vault, reusing NetworkX, BM25, and Cytoscape rather than introducing
another required platform. Concept schemas, citation checks, and vault commits
remain application-specific integration code.

Karpathy's gist supplies the workflow, not a package. Khoj was a behavioral
reference; its code was not copied. No separate knowledge platform, vector
database, or extra service is required.

## CLI and experiment

```sh
./research-partner/notes find 'give me all annotations related to computational social science' --kind annotations
./research-partner/notes find 'how people influence one another online' --expand
./research-partner/notes ask 'What can simulations tell us about online communities?' --allow-private-context
./research-partner/notes wiki build
./research-partner/notes wiki show
./research-partner/notes wiki synthesize --page TOPIC_PAGE_ID --allow-private-context
./research-partner/notes wiki lint
./research-partner/notes graph --query 'computational social science'
```

This experiment uses a new temporary vault and invented sources. It compares
literal whole-query search with BM25, builds a wiki, adds a cautionary
annotation, checks staleness, updates, and exports before/after Markdown, a diff,
and graph JSON. It never reads your personal vault.

```sh
python3 -B research-partner/experiments/wiki_trial.py
# Optional actual synthesis over only those invented demonstration sources:
python3 -B research-partner/experiments/wiki_trial.py --model
```

The default experiment makes no model/web calls. The design preview uses
labelled illustrative responses, not actual generated answers.

## Kura research atlas

Research → **Topic classification** opens the recursive topic hierarchy first,
with independent collapse controls for every branch. Map and Topic sizes remain
available, including existing `#/research/kura/map` links. Redundant single-child
wrappers are removed when reading older results, without changing saved evidence
or requiring model analysis. Removed topic IDs remain valid evidence links.
New classifications carry single topics forward without adding wrapper levels.
Long topic lists show 20 entries initially and another 20 per **Show more** click.
The views include relative topic sizes and source-linked evidence details. Every saved annotation
and every nonempty personal note below a document's personal-note marker is
included. Metadata-only bookmarks are not evidence items. Long highlights,
comments, and notes are split into labelled fragments for summarization; there
is no library-size sample or silent character cutoff.

The adapter uses [upstream Kura](https://github.com/jxnl/kura) at
`956d95ac6a19c841c59eefe692f3341dfc2ba410`, cloned into the ignored
`research-partner/upstream/kura/`. It uses Kura's public summarization,
K-means clustering, and recursive meta-clustering pipeline with research-specific
adapters. The chat-specific prompts and safety/frustration scores are replaced
with subject summaries that distinguish source quotations from reader comments.
The [local report adaptation](https://github.com/Luke-Guan-FirstPrinciples/kura/tree/feat/gpt-6-luna-default/examples/local)
was inspected as a visual reference; it is not cloned or installed.

Install the optional runtime once (Python 3.12 recommended):

```sh
./research-partner/setup-kura
```

This preserves existing upstream work and installs dependencies in
`research-partner/.local-tools/kura/`, separate from the bridge's Python packages.
The first run downloads the pinned Apache-2.0 `all-MiniLM-L6-v2` model from
Hugging Face into workspace-local caches. It runs embeddings on the CPU. No
annotation text is sent to the embedding-model download service. Kura's optional
chat server, datasets, and hosted visualization are not installed.

Choose **Classify all notes** in Research, or explicitly authorize the same
context from the CLI:

```sh
./research-partner/notes kura run --allow-private-context
./research-partner/notes kura show
```

The model stages send all annotation and personal-note text to **OpenAI through
the signed-in Codex CLI**, using the configured `NOTES_CODEX_MODEL` (GPT-6 Luna
by default). This is an explicit action, not an automatic sync or categorization
setting. It requires that model to be available to the signed-in account.
There is no fallback to another model. Local sentence embeddings, Kura K-means,
and PCA projection need no API key. PCA axes indicate an approximate semantic
layout; they are not confidence scores. Names use representative summaries and
contrastive subjects; memberships always retain every evidence record.

Generated results, summaries, and fragment/label checkpoints live under
`knowledge/kura*.json` in the user's vault, separate from wiki state. They are
included in existing vault backups; previous complete results are retained on
updates. Raw annotations, personal-note markers, manual reactions, tags, and
classification overrides are never rewritten. An explicit dislike remains
visible, and highlights are never treated as endorsement.

The map becomes stale when its actual evidence changes. Evidence browsing then
requires an update rather than showing old analysis against changed notes.
Interrupted runs reuse completed summaries and labels. Notes changed during a
run prevent committing an outdated result. The browser polls progress in the
background and can reattach after returning to the Kura view while the bridge
stays running. Multiple CLI/bridge Kura runs on one vault are rejected.
Incomplete model batches are retried in smaller groups. A finished map is saved
only after checking that every annotation and note is covered exactly once by
the most specific clusters.

After rebuilding, restart the existing bridge, reload sidenote at
`chrome://extensions`, and refresh the library. Building files alone does not
reload an installed extension. Browser tools may prohibit extension URLs;
verification in an isolated synthetic test profile does not verify your Chrome
profile or its pairing.
