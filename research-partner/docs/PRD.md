# sidenote — product requirements

Version 0.2 · 2026-10-17 · Owner: Luke · Status: implementation directly in the original Hypothesis client and browser-extension repositories; later milestones proposed.

The interface must remain Hypothesis: its existing layout, styling, annotation
cards, editor, group controls, and profile. Add requested capabilities within those
components. A separate reading app or companion popup is outside this product scope.

## Product intent

Help a person turn everyday reading into durable understanding. Keep the source,
what they highlighted, what they thought, and what they later learned connected
over years. The long-term product is a thought partner that learns with its
owner and helps them question, remember, connect, and share ideas.

Academic research and university learning are the first use cases. The underlying
objects must also work for a blog post, technical documentation, a conversation,
a class, a book, a diary entry, or an ongoing personal question. A semester is
one period in a person's learning history, not a disposable notebook boundary.

The immediate promise is concrete: **annotate where you already read; recover and
reuse your thinking from files you control, with less housekeeping.**

## Problem and audience

Reading, annotation, reference management, notes, and AI conversations currently
happen in separate places. A person can remember discussing an idea without
remembering which tool, course, or paper contains the evidence. Manual tagging,
metadata repair, export, and note migration compete with learning itself.

Initial user: a research student or lab member who already uses Hypothesis,
Zotero/Mendeley, and a text editor or Obsidian, and is comfortable running a local
tool. Luke is the first design partner. Later users include lifelong learners,
domain experts, reading groups, and teams with shared research questions.

Core jobs:

1. “While I read, capture the passage and my reaction without switching to a new workspace.”
2. “Tomorrow, retrieve the idea and my reasoning even if the original service is unavailable.”
3. “Months later, connect this paper to my course notes and see how my understanding changed.”
4. “When I ask a question, ground the answer in my actual sources and distinguish my view from theirs.”
5. “With permission, see what colleagues consider useful and share a deliberate part of my work.”

## Principles and product decisions

| Principle | Consequence |
| --- | --- |
| Reuse existing tools and repos | Modify the original Hypothesis client/extension directly; preserve their UI; reuse citation standards and optionally Zotero translators; read/write editor-friendly files. |
| Headless Codex for LLM calls | Use a subprocess adapter and structured outputs; do not add parallel model-provider SDK integrations. |
| Ownership and portability | Original JSON and ordinary Markdown remain accessible independently of this app. A separate local Git repo is supported. |
| Evidence before fluency | Answers, summaries, metadata, and suggestions identify their sources. Missing information stays unknown. |
| Human intent has priority | Explicit reactions and curated edits take precedence over model inference. Suggestions remain reviewable. |
| Fit existing habits | Extend the browser and existing note editors before introducing a standalone destination. |
| General-purpose foundation | Citation fields are optional; learning questions and relationships can span academic and non-academic material. |
| Deliberate sharing | Personal reading and thought history stay personal until the owner selects what to share. |

## Current systems and data location

The Hypothesis extension wraps its browser annotation client. Its documented
server architecture persists annotations in PostgreSQL and indexes them for
search. Cloning the extension does not move a user's stored annotations onto
their computer. [Browser extension](https://github.com/hypothesis/browser-extension),
[client](https://github.com/hypothesis/client),
[storage architecture](https://h.readthedocs.io/en/latest/arch/adr-001/).

The first version adds a local knowledge vault alongside the hosted service.
Hypothesis remains authoritative for original annotation bodies, selectors,
visibility, and edits created there. The vault is authoritative for custom
titles, explicit reactions, locally curated tags, and personal Markdown notes.
AI results are derived proposals. Daily imports reconcile hosted annotation edits
without overwriting those local fields.

Zotero's translators are an existing ecosystem for site-specific reference
extraction. We implement common embedded standards first and provide a local
translation-server adapter rather than claiming identical publisher coverage.
[Translator documentation](https://www.zotero.org/support/dev/translators),
[translation server](https://github.com/zotero/translation-server).

## Scope of the first release

| ID | Requirement | Acceptance criteria | Current delivery |
| --- | --- | --- | --- |
| R1 | Organize pages automatically | Generate up to eight Auto tags independently of Manual tags; classify type, multiple topics, and parent/subtopics; prefer existing vocabulary and cache unchanged inputs. | Offline local classifier by default after imports/captures; optional GPT-6 Luna through headless Codex; separate automatic fields and dismissible tags. |
| R2 | Daily recoverable backup | Export the user's accessible annotations daily; label public/authenticated scope; retain disappeared records; reject incomplete scans; verify restore into an empty folder; show last successful sync. | CLI importer, snapshots/checksums, restore, status, and macOS daily LaunchAgent. |
| R3 | Capture citation metadata | Extract available title, authors, institutions, journal, date, DOI, and publisher; preserve source evidence; leave absent fields unknown; support general web pages without citation metadata. | Embedded standards/JSON-LD, browser capture, public landing-page enrichment, optional Crossref and local Zotero service. |
| R4 | Give a source a useful personal title | Save a title in under ten seconds; show it in the custom Hypothesis build/local notes and optionally the displayed Hypothesis profile; retain the source title in raw data; survive the next import. | Inline pencil/editor in the existing Hypothesis profile plus the Page Notes section of the native client. Titles are reapplied automatically on reload; the hosted server record is preserved. |
| R5 | Infer stance from comments | Separate the source author's words from the reader's view; retain evidence, confidence, and model provenance; abstain for highlight-only or ambiguous cases. | Structured per-annotation Codex stance; evidence checks and 70% confidence floor; explicit reaction is independent. |
| R6 | Quick browser reactions and collections | Rate a page Like/Love/Bad/Hate in Page Notes; retain separate annotation reactions; add pages to For later, Likes, or custom groups. | Native page controls and manual collections; positive page ratings stay consistent with Likes. The original annotation action bar keeps its independent thumbs. |
| R7 | Preserve the next product decisions | A reviewable PRD explains architecture, tradeoffs, future experiences, metrics, dependencies, and unresolved hypotheses. | This document and linked architecture/validation notes. |

Release boundaries: one local user and vault per configured account; Chrome/
Chromium custom Hypothesis build; macOS scheduling; no source-page/PDF archive; no automatic
Git push; no automatic writes back to Hypothesis; no full reference-manager
replacement. Browser PDFs use landing-page metadata. The sync adapter preserves
HTTP(S), PDF URN, and local-file source identifiers; it does not read local PDF
bytes or assume a URN can be fetched over the web.

## First-release user experience

**Setup:** build the actual Hypothesis extension linked to the modified actual client,
verify a developer token locally for private imports, and enter the local pairing
key in Hypothesis extension options. Install **sidenote** alongside the
official extension in the same Chrome profile, using its own stable public
key/ID. Its original Log in control uses the paired backend's configured account;
the official extension keeps its independent OAuth login. Backups must work without Codex; model outages
must not prevent exports.

**During reading:** highlight/comment in Hypothesis. The existing metadata/frame pipeline captures
citation information. Page Notes contains citation metadata, a personal page title,
Manual and Auto tags, automatic groupings, manual collections, and page ratings. Each annotation action bar records its own reaction and analyzes only
that annotation. The original annotation tag editor retains its normal behavior.
Automatic fields remain separate from the person's manually edited fields.

**During review:** open the local folder in VS Code or Obsidian, search ordinary
Markdown, and write lasting notes below the preserved personal-notes marker.
Return to a source through its URL or annotation permalink. The custom Hypothesis build shows
when proposals are stale after edits.

**During recovery:** verify a snapshot's checksum and restore it to an empty
folder. The restored library must remain readable without Hypothesis or a model.
Recovery restores local data; it does not republish annotations to the service.

## Knowledge model

| Object | Essential fields and relationships |
| --- | --- |
| Source/document | Stable internal ID, original and canonical URLs, optional DOI/identifiers, original metadata, aliases, provenance, optional type/language. |
| Annotation | External service/ID, author, created/updated timestamps, source, exact quote plus prefix/suffix/position selectors, comment, tags, visibility/group, external permalink. |
| Personal interpretation | Custom title, explicit reaction, curated tags, personal notes, edit timestamps; kept independent of imported fields. |
| Inference | Input digest, policy/model runner provenance, generation time, proposed tags, per-annotation stance, evidence, confidence, staleness. |
| Learning question — future | User's evolving question, linked sources/annotations/concepts, current explanation, open uncertainties, checkpoints. |
| Concept/wiki page — future | Human-edited explanation, supporting/contradicting sources, backlinks, generated proposals, revision history. |
| Sharing collection — future | Explicitly selected records, owner, members, visibility, provenance, removal policy; no implicit access to the underlying private vault. |

Keep quoted evidence, the reader's comment, explicit preference, and model inference
as distinct fields. Disagreement with an argument can coexist with finding a paper
useful. A future reaction system may need separate “useful,” “agree,” and “want to
revisit” dimensions; the first release's ratings must not be treated as a
complete psychological profile.

URLs identify documents initially. Add DOI/URL alias reconciliation later, with
merge previews and an undo path. A preprint and final publication may deserve
linked but distinct versions. Institutions eventually need author-specific
relationships; a flat list is sufficient only for the first metadata display.

## Implementation architecture

The original Hypothesis client sends typed messages to the original extension
background worker. That worker holds the local pairing key and calls the loopback
service. The Hypothesis developer token stays in the backend. The Python CLI and
bridge share the same file store. The importer performs
read-only API calls. The model adapter launches headless Codex in a temporary
directory with a JSON output schema, no user integrations, and read-only execution.

The vault contains original JSON, metadata, local overrides, derived proposals,
Markdown views, and checksummed snapshots. Runtime secrets and logs are excluded
from both Git and snapshots. The implementation initializes a separate local Git
repository for the vault, but creating a GitHub remote and publishing remain
explicit user operations. See [ARCHITECTURE.md](ARCHITECTURE.md).

Longer term, add connector boundaries rather than a universal ingestion scraper.
Each connector must declare its source identity, permissions, incremental cursor,
deletion behavior, and evidence format. A search index or vector store may improve
retrieval but must always be rebuildable from owned source records.

## Roadmap and exit criteria

These are proposed milestones in dependency order, not delivery-date commitments.

| Milestone | Capability | Exit criteria |
| --- | --- | --- |
| M0 — native Hypothesis enhancements | R1–R7 within the original client/extension: backups, metadata, local edits, reactions, and Codex proposals. | Successful live import and Codex run; corruption-safe restore; regression suite; browser flow checked. |
| M1 — coverage and packaging | Broader publisher coverage, DOI/URL alias reconciliation, PDF metadata resolution, optional hosted profile persistence, durable background service packaging. | Browser capture to local note in fewer than three intentional actions; no loss of existing annotation behavior; title scope explained in UI. |
| M2 — search and grounded chat | Full-text retrieval, optional local embeddings, source filters, conversational questions over the vault, saved answers and open questions. | Answer set evaluated against known sources; every factual answer links evidence; unsupported questions abstain; private data stays within the selected vault. |
| M3 — evolving wiki and learning | Concept-page proposals, contradiction/comparison views, course-to-lifelong topic links, optional spaced review and a daily synthesis. | Proposed wiki edits show source diffs and require acceptance; a user can explain how an answer or belief changed across revisions. |
| M4 — recommendations | Revisit suggestions, missing context/prerequisites, related sources, alternate explanations; recommendation controls. | Reasons cite the user's selected goals/context; dismiss/feedback controls work; evaluation measures useful learning rather than clicks. |
| M5 — collaboration | Opt-in lab reading lists, annotations/collections, reading recommendations from selected peers, shareable evidence-backed briefs. | Only deliberately shared data appears; permission/revocation tests pass; individual private notes and reactions stay private by default. |
| M6 — broader memory | Explicit imports of ChatGPT exports, selected Chrome history, diaries, course notes, Obsidian and reference-manager records. | Preview and source selection before import; deduplication; sensitive-source controls; export and removal by connector. |

ChatGPT history and Chrome history are future connectors, not current background
collection. Use user-provided exports first so source provenance and scope are
understandable before considering live account access.

## Quality, privacy, and operations

Backup reliability is a release gate. Tests must show pagination, account matching,
retention through remote disappearance/public-only scans, local edit preservation,
incomplete-scan failures, checksum verification, restore, and secret exclusion.
A failed model run must not erase proposals or block source backups.

Daily sync has an expected recovery window of up to one day while the machine is
available. Offline periods extend that window. Local backups do not cover device
loss without an off-device copy. Snapshot retention is unlimited initially;
introduce a reviewed retention policy only after storage behavior is measured.

Model outputs must be schema-validated, contain known annotation IDs, and quote
the reader's actual comment for non-unknown stance. The 70% threshold is a product
heuristic, not a guarantee of correctness. Maintain an evaluation set including
sarcasm, questions, multilingual comments, quote-only highlights, disagreement with
a useful paper, and conflicting reactions. Never use inferred preference alone
to decide what a user should believe.

Collaboration and recommendation features require a new permission design.
Existing Hypothesis group membership must not imply consent to share a local
diary, history, private note, or inferred preference. A shared derivative can
also reveal private context; generated briefs need a source visibility review.

## Success criteria and validation plan

The following are target hypotheses to validate with Luke and a small research
cohort; they are not measured outcomes.

| Measure | Initial target | Method |
| --- | --- | --- |
| Recoverability | 100% of a known export's IDs/quotes/comments restored correctly | Automated round-trip and a real restore drill |
| Backup freshness | Successful sync within 24 hours when the Mac is available | Local success timestamp, visible stale status |
| Housekeeping | At least 50% less weekly organizing time versus current workflow | Before/after diary over two weeks |
| Metadata quality | At least 90% author/title/DOI correctness on a selected publisher set; missing fields counted separately | Human-reviewed set of 50 sources |
| Tag usefulness | At least 70% of suggested tags accepted or lightly edited | Local opt-in review events, no hidden telemetry |
| Reaction friction | Reaction takes under five seconds once paired | Observed browser task |
| Retrieval | Find an old idea in under one minute in 8/10 known-item tasks | Timed tasks with sources hidden beforehand |
| Grounded chat — M2 | All evaluated factual answers cite relevant evidence; no private-vault leakage | Held-out question set and permission cases |
| Lasting learning — M3 | Reuse material from an earlier course/project weekly | User-reported reuse with evidence links |

Track usefulness and retrieval/reuse before engagement. More captured pages or
more minutes in the app are not sufficient evidence of better understanding.

## Moat and positioning hypotheses

There is little reason to expect auto-tagging, generic chat over PDFs, or a wrapper
around an LLM to be durable differentiation. Those are useful entry features.
The strategic hypothesis is that a trusted, permissioned history of a person's
questions, evidence, revisions, and preferences enables unusually relevant help.
That advantage must be earned through continued usefulness; it must not depend
on making export difficult.

Potential defensibility to test:

1. A longitudinal understanding of how a domain expert reasons, with evidence and correction history.
2. Reliable integration into existing reading and note workflows, with a portable knowledge model.
3. High-quality concept/source relationships that improve retrieval and synthesis over time.
4. Deliberately shared lab context and expert curation that help a group avoid duplicated work.
5. User trust built through recoverability, transparency, and control over private context.

People already have preferred tools. Position the product as the connective
layer between them. A replacement reference manager or compulsory new editor
would add adoption cost before establishing a unique benefit.

## Monetization hypotheses

Start by proving personal utility. An open-source, local core may be the right
outcome even if no business emerges. No pricing is justified by the current
prototype.

Candidate paid value, in increasing complexity:

| Candidate | Buyer and value | Experiment |
| --- | --- | --- |
| Managed backup and device sync | Individuals paying for reliable recovery and convenience | Interview whether local setup/maintenance prevents continued use |
| Lab/workgroup workspace | Labs paying for permissions, shared reading context, and research briefs | Run an opt-in shared reading-list pilot |
| Expert-curated learning collections | Readers paying an expert for interpretation and a maintained collection | Publish one intentionally authored collection with the expert's agreement |
| Private organizational knowledge tooling | Teams paying for administration, hosting, and evidence-based retrieval | Explore only after local and lab workflows work |

The owner's data and thought process can be valuable, especially in a specialized
domain, but raw reading history is not automatically a product the owner wishes
to sell. Prefer explicit expert-authored collections, insights, or consultations
over ambient resale of behavioral data. Any future marketplace needs selection,
preview, compensation terms, rights checks, and controls for withdrawal or future
updates. Access to already delivered material cannot be assumed reversible.

Selling private data without deliberate participation would undermine the trust
required for the thought partner to work. Willingness to pay, audience demand,
and the economics of any expert marketplace remain unvalidated.

## Open decisions

| Question | Current assumption | Evidence needed |
| --- | --- | --- |
| Maintain the Hypothesis fork | Required: actual original repos and interface; changes remain narrow and reproducible as patches | Track upstream changes and review native diffs |
| Personal title on the hosted profile? | Inline local editing and automatic reapplication delivered; hosted server persistence later | Which screen Luke actually uses to revisit work |
| Does “like” mean agreement or usefulness? | One explicit preference initially, with separate inferred stance | Examples of valuable papers Luke disagrees with |
| Taxonomy per project or across life? | Reuse a shared tag vocabulary; add project views later | Existing course/lab note organization |
| How much automation is welcome? | Automatic proposals can be enabled; curated edits remain deliberate | Acceptance/dismissal patterns over two weeks |
| Local-only or optional hosted service? | Local-first core; remote convenience later | Setup burden and recovery needs across devices |
| What makes the thought partner worthwhile? | Better retrieval and links between old and new questions | Repeated tasks that existing tools cannot satisfy well |

Next product review: use the first week of real annotations and backups to choose
whether broader metadata coverage, background-service packaging, or grounded
search should be the next implementation priority.

## Local dashboard and field ownership

The original client now includes a Local library view, opened through the user
menu or extension options. It lists backed-up URLs, searches titles/authors/URLs/
page tags, expands stored page details and annotations, and shows backup status.
This is implemented in the actual client repository.

Page-level fields are personal title, observed authors/institutions/journal/DOI,
manual and automatic page tags, automatic groupings, manual collections, and page
ratings. They appear in Page Notes. Annotation reactions and inferred sentiment
belong to individual annotation IDs, with independent explicit and inferred values. Source highlights alone do not imply agreement.

Publishing through the original Post control writes to the user's actual hosted
Hypothesis account with existing sharing controls. Additional page fields and
annotation states stay local. The backend reads its credential from an ignored
.env file; credentials are excluded from the recoverable knowledge snapshots.

## Organization and dashboard extension

Page-level manual and automatic tags are separate. Automatic classification
creates local link-type, topic, and parent/subtopic groupings with multiple labels
per page. Manual collections always include For later and Likes and support
custom names directly in the sidebar. Page reactions are like/love/bad/hate; they
are separate from annotation reactions and inferred sentiment. Positive page
ratings and membership in Likes remain consistent.

The local client offers a profile-style List plus three alternative layouts: an overview with
clickable topic/subtopic/author charts, a compact comparison table, and a board by
manual collection or automatic dimension. Search covers saved notes, highlights,
metadata and both tag sources, and supports field queries. Filters combine with
search; sorting supports saved/updated dates, title, and reaction strength. Unknown
metadata/classification is visible rather than fabricated.

New users receive automatic local classification of all imported sources and
browser captures. Unknown evidence stays unknown. Optional Codex categorization
uses GPT-6 Luna with low reasoning and sends selected saved page context to the
signed-in Codex service only after explicit approval. It runs in bounded batches, validates IDs
and topic/subtopic relationships, caches unchanged inputs, preserves manual
fields and concurrent edits, and snapshots results. The default background
annotation backup remains independent of model calls.

The default dashboard now follows the hosted profile: white background, compact
source rows grouped by saved month, grey domains, dark expandable titles, and a
right summary column. Overview, Table, and Board remain selectable. Local NLP
options and an embeddings experiment are documented in
[the classifier assessment](CLASSIFICATION.md); no pretrained local model is
claimed to be evaluated or production-ready.
