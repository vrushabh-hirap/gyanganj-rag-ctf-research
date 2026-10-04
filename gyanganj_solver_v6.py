#!/usr/bin/env python3
"""Offline V6 evidence analyzer; reads V1-V5 records and sends no network requests.

This tool builds response-driven follow-up proposals from saved evidence only.
It does not contact GYANGANJ, process a live challenge secret, or verify flags.
"""
import argparse, collections, json, re
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
V5=ROOT/'gyanganj_v5_state.json'
OUT=ROOT/'gyanganj_v6_offline.json'
FLAG_TOKEN=re.compile(r'KCTF\{[^{}\r\n]+\}')
ENTITIES={'vyasa','ganesha','mahabharata','siddha','siddhas','gyanganj','shambhala','dharma','yudhishthira','arjuna','krishna','bhagavad','gita','indra','svarga','akasha','akashic','mula','shloka','karma','dog','verse','action','duty','cosmic','order','time','tapas','siddhi'}
WORDS=re.compile(r"[A-Za-z][A-Za-z'-]*")

def timestamp(): return datetime.now(timezone.utc).isoformat()
def concepts(text): return sorted({w.lower() for w in WORDS.findall(text) if w.lower() in ENTITIES})
def grounded_candidate(source, signal, target, question, reason, kind):
    return {'source_response':source,'extracted_signal':signal,'question_target':target,'next_question':question,'rationale':reason,'class':kind,'status':'proposal_only_not_sent'}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--v5-state',type=Path,default=V5)
    ap.add_argument('--output',type=Path,default=OUT)
    args=ap.parse_args()
    if not args.v5_state.exists(): raise SystemExit(f'Missing evidence file: {args.v5_state}')
    state=json.loads(args.v5_state.read_text())
    rows=state.get('experiments',[])
    # Select the richest actually observed response, then preserve its verbatim text.
    richest=max(rows,key=lambda x:len(x.get('response','').split()),default=None)
    proposal=None
    if richest:
        text=richest.get('response',''); cs=concepts(text)
        signal='Co-mentioned established narrative concepts: '+', '.join(cs)
        if len(cs)>=2:
            a,b=cs[:2]
            proposal=grounded_candidate(text,signal,f'{a} ↔ {b}',f'What relationship connects {a} and {b} in this account?','Both concepts are present in the richest saved Siddha response; this asks about their explicit relationship without asserting one.', 'cross_block')
    out={'version':6,'mode':'offline_saved_evidence_analysis','created':timestamp(),'v5_source':str(args.v5_state.resolve()),'prior_experiment_count':len(rows),'prior_evidence_preserved':True,'richest_response':richest,'queued_proposal':proposal,'existing_v5_proposals':state.get('derived_followups',[]),'network_requests_sent':0,'challenge_status':'not_contacted','flag_status':'not_attempted','notice':'Offline proposal only. No question was submitted to the challenge.'}
    args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print('Offline V6 evidence analysis saved:',args.output.resolve())
    print('Prior observations retained:',len(rows))
    print('Richest response source question:',richest.get('question') if richest else 'none')
    print('Derived follow-up proposal:',proposal.get('next_question') if proposal else 'none')
    print('Network requests sent: 0')
    print('Challenge contacted: no')
    print('Flag status: not attempted')
    # Demonstrate syntactic matching only over saved evidence, without treating it as success.
    hits=[(i+1,m.group(0)) for i,row in enumerate(rows) for m in FLAG_TOKEN.finditer(row.get('response',''))]
    out['historical_flag_like_strings']=hits
    args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print('Historical flag-like strings recorded as evidence only:',len(hits))

if __name__=='__main__': main()
