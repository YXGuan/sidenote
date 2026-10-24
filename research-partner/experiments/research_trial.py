#!/usr/bin/env python3
"""Small public-paper trial. No private annotations, notes, or vault data sent to Luna."""
import json
from pathlib import Path
import sys
import time
from urllib.parse import quote
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_notes.store import Vault
from research_notes.network import get_json
from research_notes.scholarly import oa_metadata
from research_notes.local_classifier import local_classify, TAXONOMY
from research_notes.organization import codex_classify, validate_batch

# Expected subjects set before seeing model outputs. This small selection is not representative.
SAMPLES = [
 ('10.1145/3586183.3606763', 'Generative Agents: Interactive Simulacra of Human Behavior', {'computer science','social science'}),
 ('10.1126/science.1167742', 'Computational Social Science', {'social science'}),
 ('10.1086/225469', 'The Strength of Weak Ties', {'social science'}),
 ('10.1038/nature14539', 'Deep learning', {'computer science'}),
 ('10.1037/0033-295X.84.2.191', 'Self-efficacy: Toward a unifying theory of behavioral change.', {'social science','health'}),
 ('10.1145/3290605.3300233', 'Guidelines for Human-AI Interaction', {'computer science'}),
 ('10.1073/pnas.1421533112', 'Climate change in the Fertile Crescent and implications of the recent Syrian drought', {'science','politics'}),
 ('10.1126/science.1252943', 'Human tRNA synthetase catalytic nulls with diverse functions', {'science'}),
]


def main():
    vault = Vault(Path(__file__).resolve().parents[1] / 'vault')
    headers = {'Authorization': 'Bearer ' + vault.secret('OPENALEX_API_KEY')} if vault.secret('OPENALEX_API_KEY') else None
    pages=[]; expected={}; errors=[]
    for i,(doi,expected_title,subjects) in enumerate(SAMPLES):
        # Psychology is a subtopic of social science in this taxonomy.
        subjects = {'social science' if s == 'psychology' else s for s in subjects}
        try:
            work = get_json('https://api.openalex.org/works/' + quote('https://doi.org/'+doi,safe=''), api_headers=headers, attempts=1)
            meta=oa_metadata(work)
            from research_notes.scholarly import normalized
            if normalized(meta.get('title')) != normalized(expected_title):
                errors.append({'doi':doi,'reason':'Title does not match the preselected paper; omitted'})
                continue
            if not meta.get('abstract'):
                errors.append({'doi':doi,'reason':'No abstract; omitted to keep evaluation grounded'})
                continue
            # Index topics and labels are withheld from both classifiers.
            meta={k:v for k,v in meta.items() if k in ('title','abstract','authors','doi')}
            page={'document_id':str(i),'title':meta['title'],'url':'https://doi.org/'+doi,'metadata':meta,'page_notes':[],'personal_notes':''}
            pages.append(page);expected[str(i)]=subjects
        except (ValueError, RuntimeError, OSError, KeyError): errors.append({'doi':doi,'reason':'Metadata unavailable'})
    if len(pages)<3:
        raise RuntimeError('Too few public abstracts available for a useful trial')
    rows={}; timings={}
    for name,provider in [('local',local_classify),('gpt-6-luna',codex_classify)]:
        started=time.perf_counter()
        rows[name]=validate_batch(provider(pages,TAXONOMY),list(expected))
        timings[name]=round(time.perf_counter()-started,3)
    scores={}
    for provider,values in rows.items():
        tp=fp=fn=exact=0
        for key,truth in expected.items():
            prediction=set(values[key]['classification']['topics'])
            tp+=len(prediction & truth);fp+=len(prediction-truth);fn+=len(truth-prediction);exact+=prediction==truth
        scores[provider]={'topic_micro_f1':round(2*tp/max(1,2*tp+fp+fn),3),'topic_exact_match':round(exact/len(expected),3),'elapsed_seconds':timings[provider]}
    report={'model':'gpt-6-luna','reasoning':'low','data':'Public OpenAlex titles/abstracts only; no private notes or vault metadata','taxonomy_version':2,'pages':len(pages),'limitations':'Small hand-selected trial with reviewed expected subjects; title/DOI correspondence verified. Labels revised after an initial pilot revealed incorrect DOI assumptions; not a blinded, held-out or representative evaluation. Topic boundaries overlap. No general accuracy claim, extraction score, cost estimate, or production auto-switch follows.','scores':scores,'omitted':errors,'results':[{'title':p['title'],'doi':p['metadata']['doi'],'expected':sorted(expected[p['document_id']]),'local':rows['local'][p['document_id']],'luna':rows['gpt-6-luna'][p['document_id']]} for p in pages]}
    output=Path(__file__).with_name('research-trial-results.json');output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2))
if __name__=='__main__': main()
