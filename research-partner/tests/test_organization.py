import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_notes.native import mirror_annotation
from research_notes.organization import organize_library, organize_page, validate_batch
from research_notes.store import Vault, restore_snapshot
from research_notes.hypothesis import sync
from research_notes.local_classifier import local_classify


class OrganizationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.vault = Vault(Path(self.temporary.name) / 'vault')
        self.vault.initialize('luke_ai')
        self.doc = mirror_annotation(self.vault, {'id':'one','user':'acct:luke_ai@hypothes.is','uri':'https://example.org/paper','created':'2026-10-17T12:00:00Z','text':'A note about research.','tags':['source-tag'],'target':[],'document':{'title':['Research paper']}})

    def runner(self, pages, taxonomy):
        return {'pages':[{'document_id':page['document_id'],'tags':['ai'],'link_type':'paper','topics':['research','technology'],'subtopics':[{'topic':'research','name':'ai'}]} for page in pages]}

    def test_auto_tags_and_multilabel_groups_do_not_replace_manual_tags_or_annotation_tags(self):
        self.vault.update(self.doc['id'], tags=['manual'])
        result = organize_page(self.vault, self.doc['id'], runner=self.runner)
        self.assertEqual(result['manual_tags'], ['manual'])
        self.assertEqual(result['auto_tags'], ['ai'])
        self.assertEqual(result['classification']['topics'], ['research','technology'])
        self.assertEqual(result['annotations'][0]['tags'], ['source-tag'])
        self.assertEqual(result['annotation_states'], {})
        self.vault.update(self.doc['id'], excluded_auto_tags=['ai'])
        self.assertEqual(self.vault.documents()[self.doc['id']]['auto_tags'], [])

    def test_reaction_and_likes_group_stay_consistent_without_touching_annotation_state(self):
        for reaction in ('like','love'):
            result = self.vault.update(self.doc['id'], reaction=reaction)
            self.assertIn('Likes', result['groups'])
        result = self.vault.update(self.doc['id'], reaction='hate')
        self.assertNotIn('Likes', result['groups'])
        self.assertEqual(result['annotation_states'], {})
        result = self.vault.update(self.doc['id'], groups=['Likes','For later'])
        self.assertEqual(result['reaction'], 'like')
        result = self.vault.update(self.doc['id'], groups=['For later'])
        self.assertIsNone(result['reaction'])

    def test_default_and_custom_groups_survive_empty_membership_and_snapshot_restore(self):
        self.assertEqual(self.vault.groups(), ['For later','Likes'])
        self.vault.create_group('Lab reading')
        self.vault.create_group('lab reading')
        self.assertEqual(self.vault.groups().count('Lab reading'), 1)
        self.vault.update(self.doc['id'], groups=['Lab reading'])
        self.vault.update(self.doc['id'], groups=[])
        with self.vault.lock():
            snapshot = self.vault.snapshot()
        restored = restore_snapshot(snapshot, Path(self.temporary.name)/'restored')
        self.assertIn('Lab reading', restored.groups())
        self.assertEqual(restored.documents()[self.doc['id']]['groups'], [])

    def test_missing_duplicate_and_invalid_parent_classifications_are_rejected(self):
        result = self.runner([{'document_id':self.doc['id']}], {})
        with self.assertRaises(ValueError): validate_batch({'pages':[]}, [self.doc['id']])
        with self.assertRaises(ValueError): validate_batch({'pages':result['pages']*2}, [self.doc['id']])
        result['pages'][0]['subtopics'][0]['topic']='sports'
        with self.assertRaises(ValueError): validate_batch(result, [self.doc['id']])

    def test_cached_bulk_organization_skips_unchanged_pages_and_never_overwrites_a_concurrent_manual_edit(self):
        calls=[]
        def runner(pages, taxonomy):
            calls.append(pages)
            return self.runner(pages, taxonomy)
        first=organize_library(self.vault, runner=runner)
        second=organize_library(self.vault, runner=runner)
        self.assertEqual(first['applied'],1)
        self.assertEqual(second['total'],0)
        self.assertEqual(len(calls),1)
        def concurrent(pages, taxonomy):
            self.vault.update(self.doc['id'], title='A newer title')
            return self.runner(pages, taxonomy)
        result=organize_library(self.vault, force=True, runner=concurrent)
        self.assertEqual(result['applied'],0)
        self.assertEqual(self.vault.documents()[self.doc['id']]['title'],'A newer title')

    def test_failed_batch_leaves_saved_classifications_and_manual_data_intact(self):
        self.vault.update(self.doc['id'], tags=['keep-me'], reaction='bad')
        result=organize_library(self.vault, runner=lambda *_: {'pages':[]})
        self.assertEqual(result['state'],'partial')
        self.assertEqual(result['failed'],1)
        doc=self.vault.documents()[self.doc['id']]
        self.assertEqual(doc['manual_tags'],['keep-me'])
        self.assertEqual(doc['reaction'],'bad')

    def test_new_users_categorize_every_imported_page_without_codex_and_cache_unchanged_inputs(self):
        row = self.doc['annotations'][0] | {'uri':'https://arxiv.org/abs/2601.12345', 'document':{'title':['Machine learning for computational social science']}}
        class Client:
            def annotations(self, **_): return [row]
        with patch('research_notes.intelligence.subprocess.Popen', side_effect=AssertionError('Local classification must not start Codex')):
            first = sync(self.vault, public_only=True, client=Client())
            second = sync(self.vault, public_only=True, client=Client())
        self.assertEqual(first['organization']['state'], 'complete')
        self.assertGreaterEqual(first['organization']['applied'], 1)
        self.assertEqual(second['organization']['total'], 0)
        classified = next(doc for doc in self.vault.documents().values() if 'arxiv.org' in doc['url'])
        self.assertEqual(classified['classification']['link_type'], 'paper')
        self.assertIn({'topic':'social science','name':'computational social science'}, classified['classification']['subtopics'])
        self.assertEqual(classified['analysis']['provider'], 'local-rules')

    def test_local_rules_abstain_on_ambiguous_evidence_and_keep_multiple_parent_topics(self):
        result = local_classify([
            {'document_id':'ambiguous','url':'https://example.org','title':'A new model'},
            {'document_id':'mixed','url':'https://example.org/blog/notes','title':'AI research and investing in index funds'},
            {'document_id':'video','url':'https://www.youtube.com/watch?v=synthetic','title':'Basketball tactics'},
        ])['pages']
        self.assertEqual(result[0]['link_type'],'unknown')
        self.assertEqual(result[0]['topics'],[])
        self.assertEqual(result[1]['link_type'],'blog')
        self.assertIn('finance', result[1]['topics'])
        self.assertNotIn('research', result[1]['topics'])
        self.assertEqual(result[2]['link_type'],'video')

    def test_automatic_categorization_can_be_disabled_and_failure_cannot_fail_an_import(self):
        from research_notes.organization import auto_organize
        self.vault.configure(auto_categorize=False)
        self.assertEqual(auto_organize(self.vault)['state'],'disabled')
        self.vault.configure(auto_categorize=True)
        class Client:
            def annotations(inner, **_): return self.doc['annotations']
        with patch('research_notes.organization.organize_library', side_effect=RuntimeError('unavailable')):
            result = sync(self.vault, public_only=True, client=Client())
        self.assertEqual(result['organization']['state'],'failed')
        self.assertTrue((self.vault.root / result['snapshot']).exists())
        self.assertEqual(len(self.vault.records('raw')), 1)

    def test_codex_requires_explicit_context_approval_and_uses_different_cache_from_local(self):
        organize_library(self.vault)
        before = self.vault.records('analysis')
        with self.assertRaisesRegex(ValueError,'Confirm sending'):
            organize_library(self.vault, provider='codex')
        self.assertEqual(before, self.vault.records('analysis'))
        with patch('research_notes.organization.codex_classify', side_effect=self.runner) as model:
            result = organize_library(self.vault, provider='codex', approved=True)
        self.assertEqual(result['applied'],1)
        model.assert_called_once()
        self.assertEqual(self.vault.documents()[self.doc['id']]['analysis']['model'],'gpt-6-luna')

if __name__ == '__main__': unittest.main()
