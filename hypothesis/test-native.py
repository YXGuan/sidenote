#!/usr/bin/env python3
"""Exercise the built original Hypothesis extension with an isolated test vault."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'research-partner'))
from research_notes.native import mirror_annotation
from research_notes.organization import organize_batch
from research_notes.server import make_server, pairing_key
from research_notes.store import Vault


def main():
    with tempfile.TemporaryDirectory(prefix='hypothesis-native-test-') as temporary:
        vault = Vault(Path(temporary) / 'vault')
        vault.initialize('demo-reader')
        vault.configure(hypothesis_token='synthetic-local-account-token')
        annotation = {'id': 'native-test-annotation', 'created': '2026-10-17T12:00:00.000001Z', 'updated': '2026-10-17T12:00:00.000001Z', 'user': 'acct:demo-reader@hypothes.is', 'uri': 'https://example.org/paper', 'document': {'title': ['Learning across a lifetime']}, 'text': 'I like this approach because it makes evidence reusable.', 'tags': ['learning'], 'group': '__world__', 'permissions': {'read': ['group:__world__'], 'update': ['acct:demo-reader@hypothes.is'], 'delete': ['acct:demo-reader@hypothes.is']}, 'target': [{'source': 'https://example.org/paper', 'selector': [{'type': 'TextQuoteSelector', 'exact': 'Reading is more useful when ideas stay connected.'}]}], 'links': {'html': 'https://hypothes.is/a/native-test-annotation', 'incontext': 'https://hyp.is/native-test-annotation/example.org/paper'}, 'user_info': {'display_name': 'Demo Reader'}, 'hidden': False, 'flagged': False}
        mirror_annotation(vault, annotation)
        examples = [
            ('ai', 'How language models learn', 'paper', ['research','technology'], [('research','ai')], 'Ada Reader', 'Example Institute', 'like'),
            ('social', 'Networks and collective behavior', 'paper', ['research'], [('research','computational social science')], 'Camila Scholar', 'Example University', None),
            ('finance', 'Understanding index investing', 'blog', ['finance'], [('finance','investing')], 'Morgan Analyst', 'Independent', 'like'),
            ('news', 'The next chapter of public policy', 'news', ['politics'], [('politics','public policy')], 'Jordan Reporter', 'Daily Example', 'bad'),
            ('sports', 'The science of a perfect shot', 'video', ['sports'], [('sports','basketball')], 'Alex Coach', 'Example Sports', 'hate'),
            ('learning', 'Building a lifelong learning practice', 'podcast', ['education'], [('education','lifelong learning')], 'Taylor Educator', 'Learning Studio', None),
        ]
        for slug, title, kind, topics, subtopics, author, institution, reaction in examples:
            doc = vault.capture('https://example.org/' + slug, {'title':title,'authors':[author],'institutions':[institution]})
            vault.update(doc['id'], reaction=reaction, groups=['For later'] if slug == 'social' else [])
        for index in range(3):
            mirror_annotation(vault, annotation | {'id':f'native-extra-{index}', 'uri':'https://example.org/social', 'created':'2026-10-16T12:00:00.000001Z', 'updated':'2026-10-16T12:00:00.000001Z', 'document':{'title':['Networks and collective behavior']}, 'text':'An additional synthetic research note.', 'target':[]})
        def classify(pages, taxonomy):
            rows=[]
            for page in pages:
                sample=next((value for value in examples if page['url'].endswith('/'+value[0])), None)
                rows.append({'document_id':page['document_id'],'tags':['contextual-learning','evidence'] if sample is None else [sample[3][0],sample[4][0][1]],'link_type':'paper' if sample is None else sample[2], 'topics':['research','education'] if sample is None else sample[3], 'subtopics':[{'topic':'research','name':'ai'}] if sample is None else [{'topic':topic,'name':name} for topic,name in sample[4]]})
            return {'pages':rows}
        organize_batch(vault, list(vault.documents().values()), runner=classify)
        server = make_server(vault, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        config = Path(temporary) / 'browser.json'
        config.write_text(json.dumps({'port': server.server_port, 'key': pairing_key(vault), 'annotation': annotation}))
        try:
            result = subprocess.run(['node', str(ROOT / 'test-native.mjs'), str(config)], cwd=ROOT, timeout=120)
            return result.returncode
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    raise SystemExit(main())
