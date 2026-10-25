**Sidenote feature map — 24 October 2026**

Sidenote's strongest potential distinction is organizing research around the
reader's own comments, questions, explicit reactions, and repeated visits while
keeping the Hypothesis annotation workflow. Its largest functional gaps are
complete source ingestion, embedding-based retrieval, interoperability, and a
workflow for revisiting saved ideas.

This is a feature comparison, not a measured quality ranking. Sidenote was
reviewed against the current checkout at parent commit `097db59`, including its
existing generated native checkouts. Other projects were assessed through their
current first-party documentation and repository READMEs. No competitor was
installed or benchmarked. No personal vault data was used.

**How to read the map**

- **Implemented:** a documented workflow corroborated by the relevant local code.
- **Limited:** part of the capability exists, with the limitation stated.
- **Experimental:** available behind an experimental setting or optional runtime.
- **Gap:** no corresponding workflow was found in the reviewed sidenote subsystem.
- **ND:** no equivalent documented in the competitor sources reviewed; this does
  not prove absence. Configurable scripts or additional plugins could reproduce it.

Compare a Zotero plugin as a contribution to Zotero, rather than a complete
replacement application. Zotero itself already supplies attachment storage,
full-text indexing, bibliography generation, duplicate detection, and sync. A
combined Zotero setup can assemble features from several plugins, although their
combined operation was not tested. Nodus desktop capabilities below are separate
from the narrower standalone Nodus Zotero plugin. Readwise includes Reader and
the Readwise highlight-review application where specified.

**Features sidenote has, and where they stand out**

| Capability | Sidenote today | Comparison and significance |
| --- | --- | --- |
| Annotate the original web page and browser PDF | Implemented through the modified Hypothesis client. Hosted annotation posting is separate from local research fields. | Reader also supports open-web highlighting. Zotero's Connector captures pages and attachments into its library. This is a useful workflow choice, not a unique feature. [S1], [R1], [Z1] |
| Automatic Questions collection | Implemented: local English-oriented question heuristics over comments and highlights. | Equivalent ready-made collection ND across the reviewed projects. Nodus generates open questions, which is a different operation from collecting questions the reader actually saved. A plausible differentiator; detection is heuristic. [S2], [N1] |
| Automatic Liked collection from personal comments | Implemented: VADER sentiment over reader comments; source quotations and question-only sentences do not establish liking. Explicit dislikes take precedence. | This exact ready-made workflow is ND. Ratings, favorite tags, custom rules, and review feedback elsewhere are adjacent capabilities. It should be presented as a suggested collection, not reliable inference of endorsement. [S2], [R7], [AT], [ST] |
| Visit Often collection from saved-page revisits | Implemented: at least three recorded visits in 30 days; active saved-page loads/tab returns, five-minute deduplication, unrelated/incognito pages excluded. | Equivalent browser-revisit collection ND. Ethereal Style tracks page-level PDF reading time and annotation density; Reader tracks progress and last location. These measure different behavior. [S2], [S3], [ST], [R2] |
| Reading dashboard across topics, authors, annotations, and visits | Implemented: activity periods, label/author rankings, and linked library filters. | Ethereal Style has finer PDF reading measures. Topic/author dashboards integrated with the preceding collections are useful, but broader superiority was not measured. [S3], [ST] |
| Separate source words, personal notes, explicit reactions, and generated analysis | Implemented: raw exports, manual overrides, annotation state, derived analysis, and personal-note markers remain separate. | Other tools support notes and source citations. This explicit data model is a defensible design characteristic; documentation does not establish that all competitors lack comparable internal separation. [S2], [S4], [S5] |
| Cited concept wiki and evidence-backed relationships | Experimental: Wiki and Knowledge graph require developer mode. Claims require matching saved quotes; disagreements require two source documents. Changed evidence invalidates affected synthesis. | Nodus also provides source-linked ideas, contradictions, and argument maps. Better Notes and Ethereal Style provide relationship graphs. A graph or cited answer alone is not a differentiator. Sidenote's explicit quote/staleness checks deserve comparison, without claiming they establish factual correctness. [S4], [S5], [N1], [BN], [ST] |
| Hierarchical atlas of saved annotations and personal notes | Optional runtime: Kura summarizes all saved evidence, embeds/clusters locally, and creates topic hierarchy/map views. Model summarization sends text to the signed-in service after an explicit action. | Nodus provides theme/idea exploration; Heptabase provides whiteboards and AI over a space. Hierarchical automatic organization of the saved annotation corpus is a useful specific capability; it is not proof of better topic quality. [S4], [N1], [H1] |
| Paper discovery seeded from positive-comment collection | Implemented, limited: Semantic Scholar recommendations use resolved papers in Liked (Auto); annotation text remains local. | ResearchRabbit provides broader citation-network exploration. ZotSeek finds similar papers already in the library. Sidenote's particular comment-to-seed connection is distinctive in this sample, while external discovery itself is not. [S6], [RR1], [ZS] |
| Local knowledge files and recoverable annotation history | Implemented: Markdown source notebooks, preserved personal writing, raw records, checksummed snapshots, and optional daily backup. | Local storage and Markdown are shared with Gooseberry, Obsidian Annotator, Better Notes workflows, and Nodus. Sidenote's recovery and derived/manual boundaries are strengths, not evidence of exclusivity. [S1], [S5], [GB], [OA], [BN], [N1] |

**Shared capabilities that should not be advertised as unique**

| Capability | Documented alternatives | Sidenote's practical boundary |
| --- | --- | --- |
| Automatic metadata capture | Zotero, Paperlib, Nodus, Karakeep. [Z1], [PL], [N1], [KK] | Has browser citation extraction and OpenAlex/Semantic Scholar enrichment; this is not a full reference-manager workflow. [S3], [S7] |
| Automatic tags and organization | Actions & Tags, Paperlib extensions, Karakeep, Reader, Nodus. [AT], [PL], [KK], [R3], [N1] | Local taxonomy fallback is English-oriented and uneven across domains; enriched papers use a separate OpenAlex vocabulary. [S2] |
| Search notes and annotations | Zotero ecosystem, Gooseberry, Reader, Nodus, Heptabase. [Z2], [GB], [R4], [N1], [H1] | Searches saved highlights/comments, notes, and metadata; does not index complete source documents. [S4], [S8] |
| AI answers with source links | Nodus, Zotero MCP, Reader Global Ghostreader, Heptabase. [N2], [ZM], [R4], [H1] | Optional signed-in model; Ask selects up to eight source matches with a 48 KB saved-context budget. Conversations are not automatically persisted. [S4], [S8] |
| Markdown portability | Better Notes, Gooseberry, Obsidian Annotator; Heptabase export. [BN], [GB], [OA], [H2] | Personal-note sections can be edited in external tools, but this is not general two-way synchronization of annotations, metadata, and wiki pages. [S4], [S5] |
| Private/local processing options | ZotSeek, Nodus, Karakeep with local models; the Zotero library is local. [ZS], [N2], [KK], [Z2] | Baseline organization and search are local; model synthesis/Kura summaries use a cloud model and scholarly recommendations contact Semantic Scholar. [S2], [S4], [S6] |

**Features competitors have that sidenote lacks or only partly covers**

| Feature | Sidenote status | Documented reference | Why it matters |
| --- | --- | --- | --- |
| Complete PDF/article text ingestion and indexing | Gap: only saved excerpts, personal notes, titles, abstracts, and descriptions enter research retrieval. | Zotero, ZotSeek, Nodus, Karakeep, Reader. [Z2], [ZS], [N2], [KK], [R5] | Recover an idea even when the reader did not highlight its passage. |
| Embedding-based semantic retrieval | Gap in Find/Ask retrieval: BM25 plus optional AI query expansion. Kura embeddings serve clustering, not library search. | ZotSeek, Nodus, Zotero MCP; Paperlib extensions; Karakeep. Readwise MCP documents hybrid search. [ZS], [N2], [ZM], [PL], [KK], [R6] | Match paraphrases and concepts whose words differ from the query. |
| Similarity search from a selected passage or paper | Gap in the reading workflow. External recommendations use the whole automatic seed collection. | ZotSeek's PDF-selection search and Find Similar Documents. [ZS] | Turn a confusing or interesting passage into related material with one action. |
| Preserved source files and offline original reading | Gap: annotation snapshots are not page/PDF archives. | Zotero attachment snapshots; Karakeep full-page archival; Reader offline document cache; Nodus originals. [Z3], [KK], [R2], [N1] | Survive changed or deleted URLs and retain complete source context. |
| EPUB, scanned-page OCR, figures/tables, and richer media workflows | Gap as an integrated ingestion/analysis pipeline. Browser annotations on a source do not supply its whole content. | Nodus plugin vision; Karakeep image OCR; Reader EPUB/video/TTS; Heptabase media/transcripts; Obsidian Annotator EPUB. [N2], [KK], [R1], [R8], [H3], [OA] | Bring books, scans, talks, and visual evidence into the same research corpus. |
| General two-way Markdown synchronization | Limited to preserved personal-note sections and generated exports. Wiki exports are replaced on update. | Better Notes synchronizes Zotero notes and external Markdown files. [BN] | Let users edit in their preferred writing tool without a separate reconciliation process. |
| Reusable note templates and a general event/action engine | Limited: fixed organization, enrichment, backup, and analysis operations. | Better Notes templates; Actions & Tags triggers and scripts; Karakeep rules; Reader custom AI skills. [BN], [AT], [KK], [R4] | Support user-defined workflows without changing application code. |
| Bibliographic import/export, formatted citations, and writing integration | Gap in the complete workflow. Metadata enrichment is already present. | Zotero CSL/BibTeX/RIS and Word/LibreOffice/Google Docs; Paperlib reference insertion; Nodus CSL and Word companion. [Z4], [Z5], [PL], [N1] | Carry research into an actual manuscript and exchange it with existing libraries. |
| General duplicate-library detection and merge | Gap in the user workflow; recommendation identities are deduplicated separately. | Zotero duplicate detection/merge; Zotero MCP merge tools. [Z6], [ZM] | Reconcile the same work saved through DOI, publisher, arXiv, and PDF URLs. |
| Ready-made agent integration through MCP | Gap: a project CLI and local bridge exist, but no packaged MCP server was found. | ZotSeek, Zotero MCP, Readwise MCP. Heptabase also documents an agent-facing CLI. [ZS], [ZM], [R6], [H2] | Make the library usable in external assistants without a custom adapter. |
| Citation and author network discovery | Gap: current graph represents saved concepts/evidence/metadata, not an external scholarly citation network. | ResearchRabbit earlier/later/similar work and citation/author maps. [RR1], [RR2] | Explore a field beyond the saved library and see why papers connect. |
| User-selected recommendation seeds and iterative discovery | Limited: only Liked (Auto) supplies seeds; a manual Like alone is insufficient; negativePaperIds is empty. | ResearchRabbit lets users choose papers/collections and iterate with discovered papers. [RR2], [RR3] | Give users control over the question or collection driving discovery. Sending negative seeds is a sidenote opportunity, not a verified ResearchRabbit feature claim. |
| A review queue, active recall, and spaced repetition | Gap: Questions and Visit Often are collections, not a scheduled learning workflow. | Readwise Daily Review/Mastery; Nodus Study vault. [R7], [N1] | Close the loop between saving information and remembering or resolving it. |
| PDF reading progress and page-level time | Limited: saved-page visits and annotation activity, without reader position or time-on-page distribution. | Ethereal Style; Reader progress/last location. [ST], [R2] | Distinguish a bookmarked, skimmed, partially read, and completed paper. |
| Freeform whiteboards and manual visual synthesis | Gap: graph drag/pan/layout does not create an authored whiteboard. | Heptabase cards, embedded highlights, and whiteboards. [H3] | Let readers deliberately assemble an argument or explanation. |
| RSS/newsletter intake and an incoming reading feed | Gap. | Paperlib RSS; Karakeep RSS ingestion; Reader RSS and newsletters. [PL], [KK], [R1] | Bring new material into a repeatable reading routine. |
| Mobile access and local-library synchronization across devices | Gap in sidenote's local metadata/wiki/collections layer. Hypothesis annotation sync does not synchronize that layer. | Reader; Karakeep mobile clients; Zotero sync; Heptabase mobile/sync. Nodus server access is experimental. [R2], [KK], [Z7], [H2], [N1] | Continue the same research workflow away from the desktop. |
| Shared research collections/workspaces | Limited to hosted Hypothesis annotation sharing; local research state is personal. | Karakeep collaborative lists; ResearchRabbit shared collections; Heptabase collaboration. [KK], [RR4], [H4] | Collaborate on the organized corpus, not only individual annotation threads. |

**Comparison with every project in the initial shortlist**

The left column below describes sidenote capabilities beyond each project's
documented focus. It should not be read as an exhaustive proof of missing features.

| Project | Sidenote capability beyond its documented focus | Their feature to learn from |
| --- | --- | --- |
| [Better Notes][BN] | Automatic question/comment-sentiment/revisit collections; external paper recommendations; integrated reading analytics. | Two-way Markdown sync, reusable note templates, linked-note editor and preview, DOCX/PDF/mind-map export. |
| [Actions & Tags][AT] | Ready-made research library, automatic question detection and sentiment collections, wiki/atlas and paper recommendations. | General event triggers, shortcuts, reusable user scripts, and configurable actions. |
| [Ethereal Style][ST] | Browser-page revisit collection, comment-derived organization, cited concept synthesis, external recommendations. | PDF page-level reading-time/annotation-density displays, progress/status, ratings and nested tags. It already has a related-item graph. |
| [ZotSeek][ZS] | Questions/sentiment/revisit collections, cited concept wiki/atlas, external scholarly recommendations. | Local hybrid semantic search, matched passage preview, selected-text search, local similar documents, and MCP. Attached-note embeddings are optional; annotation comments use its keyword channel. |
| [Zotero MCP][ZM] | An opinionated dashboard and automatic collections integrated into browser annotation. | Packaged assistant access, page-aware PDF reading/annotation, collection/tag actions, duplicate merging, and local embedding options. |
| [Nodus][N1] / [Zotero plugin][N2] | The exact Hypothesis-native + comment/question/revisit collection workflow is ND in Nodus. Cited ideas, local storage, and graph synthesis are shared. | Full-source ingestion, local semantic search, local model options, scanned-page/visual analysis, argument maps, citation/writing tools, and study workflows. |
| [Gooseberry][GB] | Native integrated library UI, local inferred collections, bibliographic enrichment, model synthesis/atlas, and paper recommendations. | Highly configurable plaintext templates, grouping/hierarchy, and bulk annotation/tag CLI operations. Its knowledge-base wiki is template-generated, not concept synthesis. |
| [Obsidian Annotator][OA] | Integrated scholarly metadata, automatic collections/analytics, external recommendations, and dedicated research workspace. | Local PDF/EPUB annotation inside an existing vault, annotation block links, and drag-highlight links into notes. Existing Obsidian features belong to the host application. |
| [Paperlib][PL] | Hypothesis browser annotation workflow and the exact automatic reader-signal collections. | Full-text search, PDF acquisition, RSS, reference insertion, desktop distribution, and extension-based semantic/AI features. |
| [Karakeep][KK] | Scholarly enrichment, comment/question-driven collections, cited concept wiki/atlas, and paper recommendations. | Source archival, full-content/semantic retrieval, OCR, RSS, mobile capture, rules, and collaborative lists. |
| [Readwise + Reader][R1] | Open-source local research layer and the exact ready-made question/comment/revisit collections. Auto-tagging, cited AI answers, and reader history are shared territory. | Multi-format reading, full-document search, Daily Review/active recall, TTS, mobile/offline, broad exports, and MCP. |
| [Heptabase][H3] | Ready-made reader-signal collections, topic/author activity analytics, and external paper recommendations. | Authored whiteboards, reusable/embedded highlight cards, Zotero imports, PDF/media context, and cross-device collaboration. |
| [ResearchRabbit][RR1] | Passage-level annotations and personal-note research corpus, local NLP collections, and cited concept synthesis. | External citation/author networks, explicit seed selection, iterative discovery, collection exchange, and shared collections. |

**Product direction suggested by the map**

These are priorities inferred from the feature comparison, not validated user
demand or measured implementation estimates.

| Order | Feature lane | Concrete next behavior | Reason |
| --- | --- | --- | --- |
| 1 | Retrieve more of what was read | Keep BM25; add optional local embeddings and hybrid ranking over the current excerpt/note corpus. Add complete document ingestion as a separate opt-in expansion, retaining passage locations and provenance. | Improves recall immediately without requiring every source to be downloaded first. ZotSeek/Nodus show the capability; retrieval quality still needs evaluation. |
| 2 | Turn detected questions into useful follow-up | Add unresolved/resolved/snoozed states and a review queue; resurface related saved evidence and let the reader attach an answer. Keep highlighted author questions distinct from the reader's own questions. | Builds on sidenote's more distinctive existing signals and addresses remembering/using saved reading. Readwise provides the review-loop reference. |
| 3 | Connect the existing research ecosystem | Start with DOI-based identity matching, Zotero import/export or a bridge, and BibTeX/RIS export. Then expose a read-only MCP interface over existing search/evidence operations. | Lets sidenote complement established libraries and assistants. Avoid duplicating all of Zotero's citation/editor features first. |
| 4 | Make recommendations controllable | Allow explicit papers or any selected collection as seeds; show seed provenance; let users exclude/dismiss papers and deliberately supply negative seeds where supported. | Removes the current dependence on positive-comment heuristics. Preserve the rule that a highlight alone is not endorsement. |
| 5 | Preserve context | Offer optional HTML/PDF source retention, clear storage controls, and source-linked extraction; add OCR only for supported formats when needed. | Protects against link rot and enables full-document retrieval while keeping annotation backups distinct from source archives. |
| 6 | Make the workflow easier to adopt | Reduce build/pairing steps, provide a supported distribution/update path, and define a deliberate mobile reading/sync story. | Existing source-build and unpacked-extension setup is a practical adoption gap even when features compare well. |

An initial product position worth testing is: **a research memory built from
what you highlighted, questioned, liked, rejected, and returned to**. Generic
tagging, graph views, Markdown export, and AI chat already have substantial
competition. The distinctive opportunity is making these reader signals useful
without demanding constant manual filing.

**Local evidence**

- [S1: Setup and storage boundaries][S1]
- [S2: Classification, local NLP collections, and limitations][S2]
- [S3: Current library, analytics, and experimental feature gates][S3]
- [S4: Search/wiki/graph/Kura workflows and limitations][S4]
- [S5: Preserved notes, raw data, and snapshot implementation][S5]
- [S6: Recommendation seeds, exclusions, and transfer boundaries][S6]
- [S7: Scholarly enrichment implementation][S7]
- [S8: Actual search corpus and BM25 retrieval implementation][S8]
- [S9: Saved-page visit tracking implementation][S9]

**First-party competitor sources**

Links identify the current documentation inspected on the date above, not frozen
release guarantees. Features described as extensions, optional model paths, or
experimental server access retain those qualifications.

[S1]: SETUP.md
[S2]: ../research-partner/docs/CLASSIFICATION.md
[S3]: ../hypothesis/DASHBOARD.md
[S4]: ../research-partner/docs/RESEARCH-WORKSPACE.md
[S5]: ../research-partner/research_notes/store.py
[S6]: RECOMMENDATIONS.md
[S7]: ../research-partner/research_notes/scholarly.py
[S8]: ../research-partner/research_notes/knowledge.py
[S9]: ../hypothesis/browser-extension/src/background/saved-page-visits.ts
[BN]: https://github.com/windingwind/zotero-better-notes
[AT]: https://github.com/windingwind/zotero-actions-tags
[ST]: https://github.com/MuiseDestiny/zotero-style
[ZS]: https://github.com/introfini/ZotSeek
[ZM]: https://github.com/54yyyu/zotero-mcp
[N1]: https://github.com/jorgepb96/nodus
[N2]: https://nodusresearch.com/zotero-plugin/
[GB]: https://github.com/out-of-cheese-error/gooseberry
[OA]: https://github.com/elias-sundqvist/obsidian-annotator
[PL]: https://github.com/Future-Scholars/paperlib
[KK]: https://github.com/karakeep-app/karakeep
[Z1]: https://www.zotero.org/support/quick_start_guide
[Z2]: https://www.zotero.org/support/preferences/search
[Z3]: https://www.zotero.org/support/attaching_files
[Z4]: https://www.zotero.org/support/creating_bibliographies
[Z5]: https://www.zotero.org/support/word_processor_integration
[Z6]: https://www.zotero.org/support/duplicate_detection
[Z7]: https://www.zotero.org/support/preferences/sync
[R1]: https://readwise.io/read
[R2]: https://docs.readwise.io/reader/docs/faqs
[R3]: https://docs.readwise.io/reader/docs/faqs/ghostreader
[R4]: https://docs.readwise.io/reader/guides/ghostreader/global
[R5]: https://docs.readwise.io/reader/docs/faqs/searching
[R6]: https://docs.readwise.io/tools/mcp
[R7]: https://docs.readwise.io/readwise/guides/mastery
[R8]: https://docs.readwise.io/reader/docs/faqs/text-to-speech
[H1]: https://wiki.heptabase.com/work-with-ai
[H2]: https://wiki.heptabase.com/roadmap
[H3]: https://wiki.heptabase.com/pdf-annotation
[H4]: https://support.heptabase.com/en/articles/10510497-collaboration-and-permissions
[RR1]: https://learn.researchrabbit.ai/en/articles/12454660-how-does-researchrabbit-work
[RR2]: https://learn.researchrabbit.ai/en/articles/12439701-how-to-do-a-literature-review-with-researchrabbit
[RR3]: https://learn.researchrabbit.ai/en/articles/12796541-using-the-zotero-importer
[RR4]: https://learn.researchrabbit.ai/en/articles/13192798-how-to-share-papers-and-collections
