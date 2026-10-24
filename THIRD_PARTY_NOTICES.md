# Third-party notices

Original project code is offered under [BSD-2-Clause](LICENSE). This does not
relicense upstream code, fonts, downloaded models, API data, or source articles.
The README's [acknowledgements](README.md#borrowed-foundations-and-acknowledgements)
identify the main repositories and design/workflow influences.

The sidenote source was copied from the Productivity project without its Git
history. Its BSD-2-Clause copyright and terms are retained in
[the original project notice](third_party/licenses/productivity.txt). The
destination repository keeps its existing [license](LICENSE).

## Reconstructed and adapted sources

| Source | Use and notice |
| --- | --- |
| [Hypothesis client](https://github.com/hypothesis/client) | Pinned at `a7b7400d0d706d4357ec37c2a3610b25dcca89d5`; BSD-2-Clause, with an MIT annotator subcomponent notice; [retained license](third_party/licenses/hypothesis-client.txt) |
| [Hypothesis browser extension](https://github.com/hypothesis/browser-extension) | Pinned at `a29dd56bc736aa231e229e34dc42a1ded49151fc`; BSD-2-Clause; [retained license](third_party/licenses/hypothesis-browser-extension.txt) |
| Hypothesis [frontend-shared](https://github.com/hypothesis/frontend-shared), [frontend-build](https://github.com/hypothesis/frontend-build), [frontend-testing](https://github.com/hypothesis/frontend-testing), [annotation-ui](https://github.com/hypothesis/annotation-ui) | UI, build, test and rendering packages from the upstream locked dependency graph; their installed package notices remain applicable |
| [Hallmark](https://github.com/nutlope/hallmark) | Design workflow and theme foundations used during earlier UI exploration; MIT; [retained license](third_party/licenses/hallmark.txt) |
| [Kura](https://github.com/jxnl/kura) | Optional runtime at `956d95ac6a19c841c59eefe692f3341dfc2ba410`, installed separately in an ignored checkout; upstream README declares MIT but that pinned checkout has no LICENSE file. Do not bundle that checkout without resolving its missing notice |
| [Local Kura report adaptation](https://github.com/Luke-Guan-FirstPrinciples/kura/tree/feat/gpt-6-luna-default/examples/local) | Related adaptation credited for the local report work; not a substituted upstream runtime |
| [Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) | Workflow inspiration, not a vendored wiki implementation |

`hypothesis/patches/*.patch` carries modifications to upstream sources. The build
recreates the actual repositories, retaining their original license files. No
upstream ownership or affiliation is implied by this project's display name.

## Direct runtime repositories

The baseline Python dependencies are [NLTK](https://github.com/nltk/nltk)
(Apache-2.0), [VADER](https://github.com/cjhutto/vaderSentiment) (MIT),
[rank-bm25](https://github.com/dorianbrown/rank_bm25) (Apache-2.0), and
[NetworkX](https://github.com/networkx/networkx) (BSD-3-Clause).
[Cytoscape.js](https://github.com/cytoscape/cytoscape.js) (MIT) renders the graph.
Versions are pinned in `research-partner/requirements.txt` and the client patch's
package/lockfile changes.

The optional Kura environment directly installs these additional projects:

| Repository | Role |
| --- | --- |
| [UKPLab/sentence-transformers](https://github.com/UKPLab/sentence-transformers) | Local embeddings; also an optional classifier experiment |
| [scikit-learn/scikit-learn](https://github.com/scikit-learn/scikit-learn) | Clustering/numerical pipeline |
| [Textualize/rich](https://github.com/Textualize/rich) | Runtime terminal output |
| [openai/openai-python](https://github.com/openai/openai-python) | Upstream Kura SDK dependency; the local model adapter uses an explicitly authorized CLI |
| [pydantic/pydantic](https://github.com/pydantic/pydantic) | Runtime data models |
| [seatgeek/thefuzz](https://github.com/seatgeek/thefuzz) | Fuzzy matching |
| [jd/tenacity](https://github.com/jd/tenacity) | Retry utilities |
| [tqdm/tqdm](https://github.com/tqdm/tqdm) | Progress utilities |

See `research-partner/requirements-kura.txt` for exact direct versions. Transitive
dependencies, model weights, and the upstream Yarn dependency graphs also have
their own licenses. This table is attribution, not a complete binary bill of
materials or a claim that every dependency has been security-reviewed.

## Fonts

Fonts retain SIL Open Font License 1.1 notices next to the actual font assets:

| Font repository | Asset location |
| --- | --- |
| [Element-Type/HostGrotesk](https://github.com/Element-Type/HostGrotesk) | Native client font assets and their OFL notice, carried in the client patch |

The native client bundles these fonts and does not call a font service.

## External services

Hypothesis, Semantic Scholar, OpenAlex, Crossref, and the optional separately
installed [Zotero translation-server](https://github.com/zotero/translation-server)
provide APIs or integrations. Their service terms and data licenses apply
independently. Article text, highlights, bibliographic abstracts, and exported
data do not become BSD-licensed because the software saves or displays them.

Before distributing packaged extension binaries or a bundled runtime, generate
a complete dependency/license inventory for that artifact and include its
required notices. This checkout currently builds an unpacked development
extension; it does not claim store-distribution clearance.
