from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_notes.store import Vault, restore_snapshot, atomic_write, encoded, read_json
from research_notes.scholarly import identifiers, accepted_work, merge_scholarly, lookup, enrich_document, enrich_library, enrichment_due, enrichment_signature, cache_openalex, arxiv_id, openalex_key
from research_notes.store import now
from research_notes.organization import organize_page
from research_notes.metadata import parse_html

class ResearchDetailsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Vault(Path(self.temp.name) / 'vault')
        self.vault.initialize('reader')
        self.doc = self.vault.capture('https://doi.org/10.1000/example', {'title': 'A paper about clinical psychology', 'authors': ['Wrong metadata author'], 'doi': '10.1000/example'})

    def test_incremental_enrichment_skips_fresh_pages_without_requests_waits_or_snapshots(self):
        key = self.doc['id']
        metadata = read_json(self.vault.path('metadata', key))
        metadata['scholarly_lookup'] = {'checked_at': now(), 'providers': {'semantic_scholar': 'matched'}}
        metadata['scholarly_lookup']['input_hash'] = enrichment_signature(self.vault, self.doc)
        atomic_write(self.vault.path('metadata', key), encoded(metadata))
        self.assertFalse(enrichment_due(self.vault, self.vault.documents()[key]))
        with patch('research_notes.scholarly.enrich_document') as enrich, patch('research_notes.scholarly.time.sleep') as sleep, patch.object(self.vault, 'snapshot') as snapshot:
            result = enrich_library(self.vault)
        self.assertEqual(result['total'], 0)
        self.assertEqual(result['skipped'], 1)
        self.assertEqual(result['state'], 'complete')
        enrich.assert_not_called()
        sleep.assert_not_called()
        snapshot.assert_not_called()
        new = self.vault.capture('https://doi.org/10.1000/new', {'title': 'A new synthetic paper', 'doi': '10.1000/new'})
        with patch('research_notes.scholarly.enrich_document', return_value=new) as enrich, patch('research_notes.scholarly.time.sleep') as sleep:
            result = enrich_library(self.vault)
        enrich.assert_called_once_with(self.vault, new['id'], force=False)
        sleep.assert_not_called()
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['skipped'], 1)
        self.vault.update(key, title='A corrected synthetic title')
        self.assertTrue(enrichment_due(self.vault, self.vault.documents()[key]))
        metadata['scholarly_lookup']['checked_at'] = '2020-01-01T00:00:00Z'
        atomic_write(self.vault.path('metadata', key), encoded(metadata))
        self.assertTrue(enrichment_due(self.vault, self.vault.documents()[key]))

    def test_research_lookup_does_not_mark_concurrent_source_changes_as_fresh(self):
        def changed(_doc, _vault, _get, **_kwargs):
            self.vault.update(self.doc['id'], title='New manual title while lookup runs')
            return {'scholarly_lookup': {'checked_at': now(), 'providers': {'openalex': 'matched'}}}
        with patch('research_notes.scholarly.lookup', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'Source changed'):
                enrich_document(self.vault, self.doc['id'], fetch_page=False)
        doc = self.vault.documents()[self.doc['id']]
        self.assertEqual(doc['title'], 'New manual title while lookup runs')
        self.assertNotIn('scholarly_lookup', doc['metadata'])

    def test_manual_corrections_and_explicit_empty_fields_survive_capture_and_classification(self):
        key = self.doc['id']
        expected = {'link_type': 'paper', 'topics': ['health'], 'subtopics': [{'topic': 'health', 'name': 'mental health'}]}
        self.vault.update(key, metadata={'authors': ['A. Correct'], 'institutions': [], 'doi': ''}, classification=expected)
        self.vault.capture(self.doc['url'], {'authors': ['Wrong again'], 'institutions': ['Incorrect University'], 'doi': '10.1000/example'})
        organize_page(self.vault, key, force=True)
        doc = self.vault.documents()[key]
        self.assertEqual(doc['metadata']['authors'], ['A. Correct'])
        self.assertEqual(doc['metadata']['institutions'], [])
        self.assertEqual(doc['metadata']['doi'], '')
        self.assertEqual(doc['classification'], expected)
        self.assertTrue(doc['classification_manual'])
        self.vault.update(key, classification=None)
        self.assertFalse(self.vault.documents()[key]['classification_manual'])
        with self.assertRaises(ValueError): self.vault.update(key, metadata={'doi': 'invented'})
        with self.assertRaises(ValueError): self.vault.update(key, metadata={'authors': 'some person'})

    def test_first_added_is_stable_and_visits_are_separate_from_modification(self):
        self.vault.configure(auto_categorize=False)
        with patch('research_notes.store.now', return_value='2026-10-01T00:00:00Z'):
            doc = self.vault.capture('https://example.org/new', {'title': 'Original'}, visit=True)
        first = doc['created_at']
        with patch('research_notes.store.now', return_value='2026-10-02T00:00:00Z'):
            second = self.vault.capture(doc['url'], {'title': 'Changed'}, visit=True)
            self.vault.record_visit(doc['id'])
        self.assertEqual(second['created_at'], first)
        self.assertEqual(second['updated_at'], '2026-10-02T00:00:00Z')
        self.assertEqual(second['activity']['visit_count'], 2)
        with patch('research_notes.store.now', return_value='2026-10-03T00:00:00Z'):
            self.vault.record_visit(doc['id'])
        self.assertEqual(self.vault.documents()[doc['id']]['updated_at'], second['updated_at'])
        with self.vault.lock(): snapshot = self.vault.snapshot()
        restored = restore_snapshot(snapshot, Path(self.temp.name) / 'restored')
        self.assertEqual(restored.documents()[doc['id']]['activity']['visit_count'], 3)

    def test_identifiers_from_doi_and_arxiv_urls(self):
        self.assertEqual(identifiers('https://dl.acm.org/doi/pdf/10.1145/3805689.3812327', {})['doi'], '10.1145/3805689.3812327')
        self.assertEqual(identifiers('https://arxiv.org/pdf/1706.03762v2.pdf', {})['arxiv_id'], '1706.03762v2')
        self.assertFalse(identifiers('https://example.org/10.1000/fake', {})['doi'])

    def test_title_matching_rejects_ambiguous_short_and_conflicting_records(self):
        title = 'An exact title with enough specific words'
        work = {'title': title, 'doi': 'https://doi.org/10.1000/one'}
        self.assertEqual(accepted_work([work], title, {}), work)
        self.assertIsNone(accepted_work([work, work], title, {}))
        self.assertIsNone(accepted_work([{'title': 'Introduction'}], 'Introduction', {}))
        self.assertIsNone(accepted_work([work], title, {'doi': '10.1000/two'}))
        self.assertIsNone(accepted_work([{'title': title + ' revised'}], title, {}))

    def test_index_lookup_merges_identities_only_within_matched_work_and_preserves_counts(self):
        oa = {'id': 'https://openalex.org/W123', 'title': 'Correct source title', 'doi': 'https://doi.org/10.1000/example', 'authorships': [{'author': {'display_name': 'Ada Reader', 'id': 'https://openalex.org/A123', 'orcid': 'https://orcid.org/0000-0000-0000-000X'}, 'institutions': [{'id': 'https://openalex.org/I123', 'display_name': 'Example University'}]}], 'cited_by_count': 12, 'abstract_inverted_index': {'A': [0], 'clinical': [1], 'trial.': [2]}}
        s2 = {'paperId': 'a' * 40, 'title': 'Correct source title', 'externalIds': {'DOI': '10.1000/example', 'ArXiv': '1706.03762'}, 'authors': [{'name': 'Ada Reader', 'authorId': '123'}], 'citationCount': 9}
        def get(url, **kw):
            self.assertNotIn('api_key=', url)
            return oa if 'openalex' in url else s2
        result = lookup(self.doc, self.vault, get)
        self.assertEqual(result['citation_counts'], {'openalex': 12, 'semantic_scholar': 9})
        self.assertEqual(len(result['author_identities']), 1)
        self.assertEqual(result['author_identities'][0]['semantic_scholar_id'], '123')
        self.assertEqual(result['abstract'], 'A clinical trial.')
        self.vault.update(self.doc['id'], metadata={'institutions': ['My correction']})
        updated = enrich_document(self.vault, self.doc['id'], get=get, fetch_page=False)
        self.assertEqual(updated['metadata']['authors'], ['Ada Reader'])
        self.assertEqual(updated['metadata']['institutions'], ['My correction'])
        self.assertEqual(updated['title'], 'Correct source title')
        with patch('research_notes.scholarly.get_json', side_effect=AssertionError('cached')):
            cached = enrich_document(self.vault, self.doc['id'], get=lambda *_a, **_kw: self.fail('cached'))
        self.assertEqual(cached['metadata']['openalex_id'], 'https://openalex.org/W123')

    def test_one_provider_failure_preserves_the_other_and_never_invents_affiliation(self):
        def get(url, **_):
            if 'openalex' in url: raise RuntimeError('unavailable')
            return {'paperId': 'b' * 40, 'title': 'Title', 'authors': [{'name': 'Ada', 'authorId': '123'}], 'citationCount': 0}
        result = lookup(self.doc, self.vault, get)
        self.assertEqual(result['scholarly_lookup']['providers']['openalex'], 'unavailable')
        self.assertEqual(result['citation_counts']['semantic_scholar'], 0)
        self.assertEqual(result['institutions'], [])

    def test_changed_work_identifiers_do_not_reuse_previous_author_ids_or_citations(self):
        old = {'doi': '10.1000/old', 'openalex_id': 'https://openalex.org/W1', 'citation_counts': {'openalex': 99}, 'author_identities': [{'name': 'A', 'openalex_id': 'https://openalex.org/A1'}], 'authors': ['A']}
        new = {'doi': '10.1000/new', 'semantic_scholar_id': 'b'*40, 'citation_counts': {'semantic_scholar': 2}, 'authors': ['B'], 'author_identities': [{'name': 'B', 'semantic_scholar_id': '2'}]}
        result = merge_scholarly(old, new)
        self.assertNotIn('openalex_id', result)
        self.assertEqual(result['citation_counts'], {'semantic_scholar': 2})
        self.assertEqual(result['authors'], ['B'])
        self.assertEqual(len(result['author_identities']), 1)

    def test_jsonld_and_description_extract_title_author_affiliation_and_abstract(self):
        result = parse_html('<title>Site</title><meta name="description" content="Page summary"><script type="application/ld+json">{"@type":"ScholarlyArticle","headline":"Specific title","author":[{"name":"Ada","affiliation":{"name":"Example University"}}],"abstract":"Full abstract"}</script>', 'https://example.org')
        self.assertEqual(result['authors'], ['Ada'])
        self.assertEqual(result['institutions'], ['Example University'])
        self.assertEqual(result['abstract'], 'Full abstract')
        self.assertEqual(result['description'], 'Page summary')

    def openalex_work(self):
        return {'id': 'https://openalex.org/W123', 'title': 'A paper about clinical psychology',
                'doi': 'https://doi.org/10.1000/example', 'authorships': [],
                'topics': [{'id': 'https://openalex.org/T1', 'display_name': 'Clinical Psychology', 'score': .98,
                            'field': {'id': 'https://openalex.org/fields/32', 'display_name': 'Psychology'}}],
                'keywords': [{'id': 'https://openalex.org/keywords/mental-health', 'display_name': 'Mental health', 'score': .8}],
                'locations': [{'landing_page_url': 'https://arxiv.org/abs/1706.03762v2', 'pdf_url': None}],
                'cited_by_count': 5, 'extra_api_field': {'preserve': [1, 2, 3]}}

    def index_document(self):
        path = self.vault.path('metadata', self.doc['id'])
        atomic_write(path, encoded(read_json(path) | {'openalex_id': 'https://openalex.org/W123'}))

    def test_openalex_singleton_is_saved_in_full_and_drives_topics_and_flat_keywords(self):
        work = self.openalex_work()
        calls = []
        def get(url, **_):
            calls.append(url)
            return work if 'openalex' in url else {}
        doc = enrich_document(self.vault, self.doc['id'], get=get, fetch_page=False)
        self.assertIn('https://api.openalex.org/works/W123', calls)
        self.assertEqual(read_json(self.vault.path('openalex', 'W123')), work)
        self.assertEqual(doc['metadata']['openalex_topics'], work['topics'])
        self.assertEqual(doc['metadata']['openalex_keywords'], work['keywords'])
        self.assertEqual(doc['classification']['topics'], ['Clinical Psychology'])
        self.assertEqual(doc['classification']['keywords'], ['Mental health'])
        self.assertEqual(doc['classification']['subtopics'], [])
        self.assertEqual(doc['classification_source'], 'openalex')
        self.assertEqual(doc['metadata']['arxiv_id'], '1706.03762v2')
        with self.vault.lock(): snapshot = self.vault.snapshot()
        restored = restore_snapshot(snapshot, Path(self.temp.name) / 'restored-index')
        self.assertEqual(read_json(restored.path('openalex', 'W123')), work)
        self.assertEqual(restored.documents()[self.doc['id']]['classification'], doc['classification'])

    def test_openalex_backfill_uses_known_id_and_preserves_manual_corrections(self):
        self.index_document()
        correction = {'link_type': 'paper', 'topics': ['My Topic'], 'subtopics': [], 'keywords': ['My Keyword']}
        self.vault.update(self.doc['id'], metadata={'authors': ['Manual Author']}, classification=correction)
        calls = []
        def get(url, **_):
            calls.append(url)
            return self.openalex_work()
        result = cache_openalex(self.vault, get=get)
        self.assertEqual(calls, ['https://api.openalex.org/works/W123'])
        self.assertEqual(result['failed'], 0)
        doc = self.vault.documents()[self.doc['id']]
        self.assertEqual(doc['classification'], correction)
        self.assertEqual(doc['metadata']['authors'], ['Manual Author'])
        self.vault.update(self.doc['id'], classification=None)
        self.assertEqual(self.vault.documents()[self.doc['id']]['classification']['topics'], ['Clinical Psychology'])
        cached = cache_openalex(self.vault, get=lambda *_a, **_k: self.fail('cache should prevent request'))
        self.assertEqual(cached['cached'], 1)

    def test_empty_openalex_labels_clear_old_labels_and_failed_refresh_preserves_cache(self):
        self.index_document()
        cache_openalex(self.vault, get=lambda *_a, **_k: self.openalex_work())
        empty = self.openalex_work() | {'topics': [], 'keywords': []}
        cache_openalex(self.vault, force=True, get=lambda *_a, **_k: empty)
        doc = self.vault.documents()[self.doc['id']]
        self.assertEqual(doc['classification']['topics'], [])
        self.assertEqual(doc['classification']['keywords'], [])
        before = self.vault.path('metadata', self.doc['id']).read_bytes()
        def unavailable(*_a, **_k): raise RuntimeError('offline')
        result = cache_openalex(self.vault, force=True, get=unavailable)
        self.assertEqual(result['failed'], 1)
        self.assertEqual(self.vault.path('metadata', self.doc['id']).read_bytes(), before)
        self.assertEqual(read_json(self.vault.path('openalex', 'W123')), empty)

    def test_manual_identifier_changes_remove_stale_openalex_classification(self):
        self.index_document()
        cache_openalex(self.vault, get=lambda *_a, **_k: self.openalex_work())
        self.vault.update(self.doc['id'], metadata={'doi': '10.1000/different'})
        doc = self.vault.documents()[self.doc['id']]
        self.assertNotIn('openalex_topics', doc['metadata'])
        self.assertNotEqual(doc['classification_source'], 'openalex')
        self.assertTrue(self.vault.path('openalex', 'W123').exists())

    def test_arxiv_ids_are_validated_and_derived_for_unenriched_sources(self):
        self.assertEqual(openalex_key('https://api.openalex.org/w4404356212'), 'W4404356212')
        self.assertIsNone(openalex_key('https://evil.example/W123'))
        self.assertEqual(arxiv_id('https://arxiv.org/pdf/hep-th/9901001v2.pdf'), 'hep-th/9901001v2')
        self.assertEqual(arxiv_id('https://evil.example/abs/1706.03762'), '')
        doc = self.vault.capture('https://arxiv.org/pdf/1706.03762.pdf', {'title': 'Paper'})
        self.assertEqual(doc['metadata']['arxiv_id'], '1706.03762')
        self.vault.update(doc['id'], metadata={'arxiv_id': ''})
        self.assertEqual(self.vault.documents()[doc['id']]['metadata']['arxiv_id'], '')

if __name__ == '__main__': unittest.main()
