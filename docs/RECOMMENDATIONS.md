# Paper recommendations

Open the local library's **Recommendations** tab, or bookmark
`#/recommendations` within its existing notebook URL. Choose **Refresh
recommendations** to query the [Semantic Scholar Recommendations API](https://api.semanticscholar.org/api-docs/recommendations).
Opening the tab or its background refresh reads only the local cache.

## Seeds and matching

The backend reads the complete **Liked (Auto)** collection, the same one at
`#/collections/liked-auto`. UI filtering, sorting, and Show more do not restrict
the seeds. A manual Like alone does not create membership in that automatic
collection. Explicit dislikes take precedence over inferred positive sentiment.

All applicable papers are attempted. The resolver prefers a Semantic Scholar ID,
then DOI, arXiv ID, or PMID, and resolves them through the Graph API in batches
of at most 500. Papers without those identifiers use conservative, uniquely
matched title searches with the same safeguards as scholarly enrichment.
Unresolved papers are counted and linked for correction. Non-paper pages are
counted separately. There is no top-20 or other seed sampling limit.

Resolved papers are deduplicated and submitted together as `positivePaperIds` to
`POST /recommendations/v1/papers/`; `negativePaperIds` is empty. Only Liked (Auto)
is used as a source; other collections are not implicitly sent as negative seeds.
The request asks for up to 500 recommendations, the API's documented result
limit. Seed papers, duplicate results, and papers already saved under known
Semantic Scholar/DOI/arXiv/PMID identities are excluded. Unidentified saved pages
cannot always be recognized as the same publication.

## Privacy and refresh

An explicit refresh sends bibliographic identifiers and the titles of papers
without identifiers to Semantic Scholar. It does not send highlights, comments,
personal notes, the Hypothesis token, or the local bridge pairing key.
Semantic Scholar can infer the interests represented by the seed set. An optional
`S2_API_KEY` is read only by the backend and sent only to its official API host;
configure it through **Settings**. It is never returned to the browser client.

Requests run in a background bridge job and share the existing Semantic Scholar
request pacing/retry boundary. Rate limits or provider outages can prevent a
refresh. Previous results survive failures. A changed seed set marks cached
results stale; if seeds change during a request, its results are not committed.
No model service is involved.

The cache is private, regenerable data at `vault/.local/recommendations.json`.
It is not part of annotation snapshots or the parent repository. Removing it
does not remove sources, notes, reactions, or manual classifications.

## Reading results

Search titles, authors, and venues; sort in recommended order, by year, or by
citation count. Results and seed details each show 20 entries initially and
append 20 per Show more click. Their visible/total counts and expansion states
are independent. Filtering and sorting use all cached results. Unchanged cache
refreshes retain expansion. Abstracts and original paper links are available
without saving a recommendation or publishing an annotation.

These are scholarly suggestions based on inferred positive comments. They are
not evidence that the reader endorses every seed, a complete literature search,
or a general-web recommender. The API can lack abstracts, dates, papers, or
recommendations for otherwise valid identifiers.

After rebuilding, restart the local backend, reload the unpacked extension in
`chrome://extensions`, and refresh its library tab. A successful build alone
does not update a loaded extension. See [development](DEVELOPMENT.md) and
[setup](SETUP.md).
