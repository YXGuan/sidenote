# More specific classification: sycophancy diagnostic

Status: **exploration, not a production taxonomy migration**. The active label
catalog is [TAXONOMY.md](TAXONOMY.md); the source is
[taxonomy.json](../research_notes/taxonomy.json). This experiment does not open a
vault, change the configured provider, or apply labels to saved pages.

## What is going wrong

The current local provider matches phrases, rather than identifying a paper's
central contribution. Its two-level taxonomy has 15 topics and 27 subtopics,
with no sycophancy concept, primary-topic ranking, or research-area field.
Psychology and ethics can be relevant secondary disciplines, but a flat list
does not explain what the paper primarily studies.

There is also a concrete vocabulary problem: `llm` does not match `LLMs`, and
`language model` does not match `language models`. One incidental subtopic phrase
can add its entire parent discipline. NLTK and VADER currently power automatic
question/sentiment collections; neither performs subject classification here.

Switching to Luna with the existing schema can improve recognition, but cannot
provide a stable three-part hierarchy that the schema does not represent.
Free-text auto tags are also different from controlled subject paths.

## Proposed representation

For the user's example, store and display:

| Field | Value |
| --- | --- |
| Primary topic | Artificial Intelligence → Machine Learning → Large Language Models (LLMs) |
| Core research area | LLM Alignment, Safety, and Evaluation |
| Specific concept | Model Sycophancy → Social Sycophancy & Behavioral Biases |
| Secondary disciplines | Social Psychology; Human-AI Interaction, when supported |

This is an editorial classification supported by the
[paper's introduction, keywords and methods](https://arxiv.org/html/2510.01395v1),
not the claim that arXiv or OpenAlex assigns this exact hierarchy. Keep the
external index categories and their provenance separately.

The [experimental vocabulary](../experiments/hierarchy-taxonomy.json) expresses
these fields as complete paths with stable IDs, definitions and exclusions.
For example, `llm.alignment.sycophancy.social` maps to the three rows above.
This twelve-path subset tests a design; it is deliberately not a complete
replacement for the active cross-domain catalog. A full revision should retain
the existing domains and expand branches using reviewed examples, rather than
forcing every page into an AI path.

## Small trial completed

The [runner](../experiments/hierarchy_trial.py) compared local rules, Luna with
the active taxonomy, and Luna with the proposed paths. Inputs were two public
arXiv titles/abstracts and five explicitly synthetic controls. Expected primary
paths were set before calling the model. No personal highlights, comments,
existing library tags or private metadata were sent.

| Diagnostic | Local rules / active taxonomy | Luna / active taxonomy | Luna / experimental paths |
| --- | --- | --- | --- |
| User's paper, public title + abstract | computer science; no subtopic | AI evaluation/safety and psychology, plus research/statistics | Desired LLM → alignment/safety → social sycophancy path; psychology/HCI secondary |
| Related ELEPHANT paper | language models; no sycophancy label | language models, AI evaluation/safety, psychology | Social sycophancy path |
| Arithmetic capability benchmark | No subject | Language models **and** AI evaluation/safety | Capabilities and evaluation |
| LLM inference engineering | No subject | Language models/software engineering | LLMs, without an invented safety area |
| Human workplace sycophancy | Psychology | Psychology | Social psychology, without AI |
| Traditional sentiment classification | NLP | NLP | NLP → text classification → sentiment analysis |
| Insufficient metadata | Unknown | Unknown | Unknown |

Recorded [results](../experiments/hierarchy-trial-results.json): **7/7 proposed
primary paths matched the diagnostic expectations**. The two Luna batches took
7.361 seconds with the active taxonomy and 5.111 seconds with the experimental
paths, including CLI/network time. These selected, partly synthetic cases are
not a held-out evaluation, a general accuracy estimate, or a reliable speed
comparison. The proposed prompt and vocabulary are designed around this known
failure, which makes a separate evaluation essential.

The experiment checks valid path IDs, complete/unique page results, and exact
input excerpts supporting selections. The report retains evidence hashes rather
than redistributing abstracts. Exact quotation checks **do not prove semantic
support for every ancestor**. In particular, the user's paper's abstract says
AI; its author keywords and introduction explicitly identify LLMs. Luna selected
the desired LLM path from the shorter abstract-only input, but its title quote
alone does not justify that specificity. Production should include those public
keywords or a short relevant source excerpt, and check evidence separately for
domain, research area and specific concept.

The similarly named [ELEPHANT preprint](https://arxiv.org/abs/2505.13995) and
[user-titled preprint](https://arxiv.org/abs/2510.01395) have distinct arXiv IDs.
They are related work; do not automatically treat matching authors or a related
publication DOI as proof that every title/abstract/version can be merged.
Source identity and metadata provenance should be checked before classification.

## Recommended next implementation

1. **Improve evidence first.** Use verified title, abstract, author keywords and,
   when needed, a bounded introduction/methods excerpt. Keep personal annotation
   interests separate from the paper's subject. Record missing evidence and
   source/version disagreements.
2. **Expand a defined hierarchy.** Give each path a stable ID, aliases, inclusion
   and exclusion rules, and examples. Separate primary subject, research area and
   specific concept from secondary disciplines. Preserve source format separately.
3. **Classify within that hierarchy.** Compare optional Luna structured output
   against the existing local embedding experiment. Allow broad-only results and
   unknown; validate complete paths rather than unconstrained subtopic strings.
   Require evidence for each level, not a self-reported confidence number alone.
   There is no automatic cloud fallback for local/private pages.
4. **Evaluate beyond this example.** Review 50–100 diverse papers with labels
   fixed before model output. Reserve a held-out portion, include hard negatives,
   missing abstracts, non-English text and topics outside the vocabulary. Compare
   primary-path accuracy, area/concept precision and recall, secondary-label
   precision, abstention, repeated-run consistency, latency and resource use.
   Inspect disagreement cases; do not optimize only a broad-topic score.
5. **Preview before backfill.** Show old/new labels and evidence for changed
   pages. Version the derived results and migration mapping; preserve manual
   corrections and the ability to restore old results. Update filters/dashboard
   grouping for the new fields before applying a reviewed migration.

The preferred next step is a controlled hierarchical classifier and a reviewed
evaluation set, rather than adding sentiment libraries or another handful of
keywords. Local embeddings remain a useful fully local candidate, but no local
semantic model has been quality-tested on this proposed hierarchy yet.

## Reproduce

From the repository root:

```sh
# Offline synthetic baseline; no model, vault or network.
python3 -B research-partner/experiments/hierarchy_trial.py --synthetic-only

# Download only the two public abstracts and run local rules.
python3 -B research-partner/experiments/hierarchy_trial.py

# Optional: public/synthetic text goes to the signed-in Codex service in two batches.
python3 -B research-partner/experiments/hierarchy_trial.py --provider codex --output /tmp/hierarchy-trial.json

# No-model boundary checks and catalog freshness.
python3 -B -m unittest discover -s research-partner/tests -p test_hierarchy_trial.py -v
python3 -B tools/render_taxonomy.py --check
```

The model run explicitly requires `gpt-6-luna`, low reasoning, through the existing
isolated headless adapter; it refuses a different `NOTES_CODEX_MODEL` rather than
silently substituting a model. Sign-in/model access is required. Official OpenAI
documentation lists [Luna](https://developers.openai.com/api/docs/models/gpt-6-luna)
and [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
Schema constraints control output shape and vocabulary, not factual accuracy.
