#!/usr/bin/env python3
"""GYANGANJ V7: resumable, evidence-driven live CTF conversation solver.

Historical V1-V6 observations seed the local graph. Only actual `/chat`
responses are classified as live evidence. One question is sent per request;
the run is append-only JSONL and resumes after interruption.
"""
import argparse, collections, difflib, hashlib, itertools, json, os, re
import subprocess, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
RUN=ROOT/'gyanganj_v7_run.jsonl'
SUMMARY=ROOT/'gyanganj_v7_summary.json'
TARGET='https://gyanganj-ctf.onrender.com'
CHAT=TARGET+'/chat'
FLAG_RE=re.compile(r'KCTF\{[^{}\r\n]+\}')
TOK=re.compile(r"[A-Za-z][A-Za-z'-]*")
STOP=set('a an the and or but if then than of to in on at for from by with as is are was were be been being do does did have has had it its this that these those i we you they he she my your our their what which who whom when where why how all any some more there here not no yes can could would should will may might must into over under after before between through about against because very own such also both each other only one two three four five said says say speak tell ask answer question response record visible deeper beyond lies lie'.split())
ENTITY_LEX=set('vyasa ganesha mahabharata siddha siddhas gyanganj shambhala dharma yudhishthira arjuna krishna bhagavad gita indra svarga akasha akashic mula shloka karma himalayas dog seed truth silence practice record verse action duty cosmic order time tapas siddhi draupadi dushasana kurukshetra manas'.split())
PHRASE_LEX=['mula shloka','seed-truth','seed truth','appointed time','akashic record','deeper record','deeper question','beyond all doors','single utterance','unwritten verse','cosmic order','visible record','questions must precede','accumulated silence','one final shloka']

def utc(): return datetime.now(timezone.utc).isoformat()
def normalize(s): return re.sub(r'[^a-z0-9]+',' ',(s or '').lower()).strip()
def sim(a,b): return difflib.SequenceMatcher(None,normalize(a),normalize(b)).ratio()
def hid(s): return hashlib.sha1(normalize(s).encode()).hexdigest()
def split_sents(s): return [x.strip() for x in re.split(r'(?<=[.!?])\s+',s or '') if x.strip()]
def split_paras(s): return [x.strip() for x in re.split(r'\n\s*\n',s or '') if x.strip()]
def concepts(s):
    n=normalize(s); out={w.lower() for w in TOK.findall(s) if len(w)>4 and w.lower() not in STOP}
    out|={w for w in TOK.findall(s) if w.lower() in ENTITY_LEX}
    out|={p for p in PHRASE_LEX if re.search(r'\b'+re.escape(normalize(p))+r'\b',n)}
    return sorted(out)
def entities(s): return sorted({w.lower() for w in TOK.findall(s) if w.lower() in ENTITY_LEX})
def relation_extract(s):
    out=[]
    for sent in split_sents(s):
        es=entities(sent)
        for a,b in itertools.combinations(es,2):
            rel='co-mentioned'
            if re.search(r'\b(before|precede|earlier|first)\b',sent,re.I): rel='precedes'
            elif re.search(r'\b(after|follows|then|later)\b',sent,re.I): rel='follows'
            elif re.search(r'\b(because|caused|led to|therefore|so that)\b',sent,re.I): rel='causes_or_explains'
            elif re.search(r'\b(is|was|called|known as|revealed to be)\b',sent,re.I): rel='identified_or_described_with'
            out.append({'source':a,'relation':rel,'target':b,'evidence':sent})
    return out
def load_prior():
    # Preserve all originals; this is a read-only corpus assembled from their content.
    rows=[]
    for p in sorted(ROOT.glob('gyanganj*_log_*.json')):
        if '_v7_' in p.name: continue
        try: vals=json.loads(p.read_text())
        except Exception: continue
        for x in vals:
            if x.get('question') and x.get('response'):
                rows.append({'question':x['question'],'response':x['response'],'version_source':p.name,'experiment_type':x.get('experiment_type'),'historical':True})
    p=ROOT/'gyanganj_v5_state.json'
    if p.exists():
        try: v5=json.loads(p.read_text())
        except Exception: v5={}
        for x in v5.get('experiments',[]):
            if x.get('question') and x.get('response'):
                rows.append({'question':x['question'],'response':x['response'],'version_source':'gyanganj_v5_state.json','experiment_type':x.get('category') or x.get('experiment_type'),'historical':True})
    seen=set(); dedup=[]
    for x in rows:
        k=(normalize(x['question']),normalize(x['response']))
        if k in seen: continue
        seen.add(k); dedup.append(x)
    return dedup
def summarize_prior(rows):
    reps=collections.Counter(); fam=collections.defaultdict(lambda:{'count':0,'questions':[],'rich':0})
    relations=collections.Counter(); cooccur=collections.Counter(); flaghits=[]
    for i,x in enumerate(rows,1):
        r=x['response']; tid=hid(r); reps[tid]+=1
        typ=x.get('experiment_type') or 'UNCLASSIFIED'; fam[typ]['count']+=1; fam[typ]['rich']+=len(r.split())>70; fam[typ]['questions'].append(x['question'])
        for rel in relation_extract(r): relations[(rel['source'],rel['relation'],rel['target'])]+=1
        for a,b in itertools.combinations(entities(r),2): cooccur[tuple(sorted((a,b)))]+=1
        for m in FLAG_RE.finditer(r): flaghits.append({'corpus_row':i,'flag_like':m.group(0),'question':x['question']})
    top=sorted(((n,k) for k,n in reps.items()),reverse=True)[:10]
    return {'rows':len(rows),'distinct_questions':len({normalize(x['question']) for x in rows}),'exact_response_templates':len(reps),'most_repeated_responses':top,'experiment_families':{k:{'count':v['count'],'rich_count':v['rich']} for k,v in fam.items()},'top_cooccurring_entities':[(list(k),v) for k,v in cooccur.most_common(15)],'observed_relation_count':sum(relations.values()),'flag_like_strings_in_saved_responses':flaghits,'observations':['V1 log: 23 rows, 8 exact responses.','V2 log: 55 rows, 27 exact responses.','V3 log: 37 rows, 22 exact responses.','V4 log: 79 rows, 39 exact responses.','V5 state includes imported observations and later live probes; treat its comments and hypotheses as interpretations, not observations.'],'inferences':['Exact and near response templates recur; response length alone is not information gain.','Direct flag requests in stored data have generic replies.','The dog/Dharma plus single-utterance cross-block question returned an unusually rich combined narrative.','A queued V5 follow-up asks about the relation between Krishna’s action teaching and Yudhishthira’s refusal; this has not yet been tested in V7.'],'hypotheses':['Question order may influence response selection; controlled matched test still needed.','Cross-block relational questions may trigger richer narratives; one notable example is suggestive, not proof.','The meaning of the “deeper question” remains unresolved.'],'dead_ends':['Repeated generic confusion/rivers/practice/silence templates after broad semantic prompts.','Direct flag request produced “The answer you desire is not stored where curiosity alone can retrieve it.”'],'confirmed_flag_from_prior_responses':False}
def read_jsonl():
    if not RUN.exists(): return []
    out=[]
    for line in RUN.read_text().splitlines():
        try: out.append(json.loads(line))
        except Exception: break
    return out
def append_event(event):
    with RUN.open('a',encoding='utf-8') as f:
        f.write(json.dumps(event,ensure_ascii=False,separators=(',',':'))+'\n'); f.flush(); os.fsync(f.fileno())
def send_question(question,history,timeout=25):
    payload={'message':question,'history':history,'session_id':''}
    with tempfile.NamedTemporaryFile('w',encoding='utf8',suffix='.json',delete=False) as f:
        json.dump(payload,f,ensure_ascii=False); request_path=f.name
    try:
        cp=subprocess.run(['curl','--fail-with-body','--silent','--show-error','--max-time',str(timeout),'-X','POST',CHAT,'-H','Content-Type: application/json','-H','Accept: application/json','-H','User-Agent: Mozilla/5.0 (GYANGANJ-V7)','--data-binary','@'+request_path],capture_output=True,text=True,timeout=timeout+3)
        if cp.returncode: raise RuntimeError(cp.stderr.strip() or cp.stdout.strip() or f'curl exit {cp.returncode}')
        obj=json.loads(cp.stdout)
        if not isinstance(obj.get('response'),str): raise RuntimeError('Unexpected /chat response schema')
        return obj
    finally: Path(request_path).unlink(missing_ok=True)
def analyze_live(q,r,history,prior):
    cs=concepts(r); es=entities(r); rels=relation_extract(r); oldc={c for x in history for c in x.get('concepts',[])}
    oldrels={tuple(sorted((z['source'],z['target']))) for x in history for z in x.get('relations',[])}
    newrels=[z for z in rels if tuple(sorted((z['source'],z['target']))) not in oldrels]
    near=max((sim(r,x['exact_response']) for x in history),default=0)
    template_id=next((x['template_id'] for x in history if sim(r,x['exact_response'])>=.90),hid(r))
    new_block=not any(normalize(p)==normalize(op) for p in split_paras(r) for x in history for op in split_paras(x['exact_response']))
    clauses=split_sents(r)
    unresolved=[{'phrase':s,'concepts':entities(s),'reason':'contains directive, restriction, temporal marker, or unresolved demonstrative'} for s in clauses if re.search(r'\b(ask|must|before|instead|beyond|deeper|sealed|unwritten|appointed|revealed|this|that|it)\b',s,re.I)]
    flags=FLAG_RE.findall(r)
    information=1.15*len(set(cs)-oldc)+1.65*len(newrels)+.9*int(new_block)+.6*int(template_id not in {x['template_id'] for x in history})
    information+=.4*bool(unresolved)+.3*bool(re.search(r'\b(permission|permitted|revealed|appointed|final|secret|key|gate|sealed)\b',r,re.I))
    exact=any(normalize(r)==normalize(x['exact_response']) for x in history)
    if exact: information*=.1
    return {'response_hash':hid(r),'template_id':template_id,'template_similarity':round(near,3),'paragraphs':split_paras(r),'sentences':clauses,'entities':es,'concepts':cs,'new_concepts':sorted(set(cs)-oldc),'relations':rels,'new_relations':newrels,'unresolved_relations':unresolved,'narrative_events':[s for s in clauses if len(entities(s))>=2],'instructions':[s for s in clauses if re.search(r'\b(ask|must|before|instead|return|reflect|come|leave|seek)\b',s,re.I)],'restrictions':[s for s in clauses if re.search(r'\b(not|never|only|cannot|no|permitted|sealed|forbidden)\b',s,re.I)],'temporal_references':[s for s in clauses if re.search(r'\b(before|after|when|then|time|final|past|present|future|precede)\b',s,re.I)],'numerical_references':re.findall(r'\b\d[\d,]*(?:\s*(?:BCE|CE|years?|verses?|shlokas?))?\b',r,re.I),'potential_flag_path':bool(re.search(r'\b(permission|revelation|final|hidden verse|key|secret|gate|worthy|sealed|appointed time)\b',r,re.I)),'flag_candidates':flags,'new_block':new_block,'exact_repeat':exact,'information_gain':round(information,2)}
def gen_candidates(iteration,analysis,history,branch_id):
    # Every candidate is anchored to this exact latest response and provides explicit provenance.
    out=[]; priorqs={normalize(x['question']) for x in history}; latest=analysis['_response']; new=analysis
    def add(cls,target,relation,why,q,expected,score):
        if normalize(q) in priorqs: return
        out.append({'source_iteration':iteration,'source_response':latest,'target_concepts':target,'target_relation':relation,'why_unresolved':why,'expected_information':expected,'question':q,'class':cls,'score':round(score,3),'branch_id':branch_id})
    es=new['entities']; cs=new['concepts']; fresh=new['new_concepts'];
    for rel in new['unresolved_relations']:
        sig=rel['phrase']; ens=rel['concepts']
        if ens:
            target=ens[:3]; q=f'In your statement “{sig}”, what specifically connects {" and ".join(target)}?'
        else:
            target=[]; q=f'You said “{sig}” What specific meaning should I take from that statement in this account?'
        add('instruction_or_clue',target,sig,'The precise statement appears in the immediately preceding Siddha response and remains operationally unclear.',q,'Clarifies an explicit restriction, temporal clue, or directive and may identify its missing prerequisite.',4.5)
    for a,b in itertools.combinations(es,2):
        pair=tuple(sorted((a,b)))
        if any(tuple(sorted((z['source'],z['target'])))==pair for z in new['relations']):
            q=f'Why are {a} and {b} brought together in this part of your account?'
            add('cross_block',[a,b],'explains / connects','Both entities co-occur in the latest response, but their narrative relationship has not been directly tested in this branch.',q,'Explains a cross-block relation and could reveal a transition to another lore block.',4.2)
    for c in fresh[:5]:
        q=f'You just introduced {c}. What role does {c} play in the story you have told?'
        add('definition',[c],'explains','This concept is newly present in the exact previous response and has no recorded explanation from this branch.',q,'Clarifies a fresh concept and may expose its cause, role, or narrative consequence.',3.9)
    for rel in new['relations'][:5]:
        a,b=rel['source'],rel['target']; q=f'What is the significance of {a} being {rel["relation"].replace("_"," ")} {b}?'
        add('relation',[a,b],rel['relation'],'The last response states or co-mentions this relation; its significance remains untested.',q,'Tests the meaning of a concrete response-derived relation.',3.7)
    if len(es)>=2:
        phrase=' and '.join(es[:4]); q=f'How does {phrase} fit together in the account you just gave?'
        add('cross_block_synthesis',es[:4],'connects','These entities occur together in the current response; a synthesis may expose a new link between narrative blocks.',q,'Can reveal a richer combined response while staying tied to the last narrative.',4.4)
    # Accumulated graph: only concepts evidenced by V1-V6 corpus are eligible for historical cross-block probes.
    known=set(cs)|{c for x in history for c in x.get('concepts',[])}
    for past in sorted(known-set(es))[:4]:
        if past in ENTITY_LEX and es:
            nowc=es[0]; q=f'How does {past}, discussed earlier, relate to {nowc} in what you just said?'
            add('historical_cross_block',[past,nowc],'connects','The earlier concept is in the recorded conversation; the second appears in the immediate response, and this edge is not recorded as asked.',q,'Tests an unexplored connection between prior and newly active narrative blocks.',4.0)
    # success-based adjustment: question class/template transitions that historically led to rich responses get modest lift.
    for c in out:
        matching=[x for x in history if x.get('question_class')==c['class']]
        avg=sum(x.get('information_gain',0) for x in matching)/max(1,len(matching))
        repeats=sum(x.get('template_id')==analysis['template_id'] and x.get('information_gain',0)<.5 for x in history[-12:])
        c['score']=round(c['score']+.15*min(4,avg)-.18*repeats,3)
    out.sort(key=lambda z:z['score'],reverse=True)
    return out[:10]
def load_run():
    events=read_jsonl()
    if not events: return events
    return events
def read_jsonl():
    if not RUN.exists(): return []
    ev=[]
    for line in RUN.read_text(encoding='utf8').splitlines():
        try: ev.append(json.loads(line))
        except Exception: break
    return ev
def write_summary(events,prior_summary):
    attempts=[x for x in events if x.get('type')=='attempt']
    complete=[x for x in events if x.get('type')=='iteration']
    summary={'version':7,'updated':utc(),'run_file':str(RUN.resolve()),'historical_evidence':prior_summary,'attempted_live_requests':len(attempts),'completed_live_iterations':len(complete),'status':next((x.get('status') for x in reversed(events) if x.get('type') in ('status','flag_found')), 'initialized'),'flag_result':next((x for x in reversed(events) if x.get('type')=='flag_found'),None),'last_successful_request':complete[-1] if complete else None,'last_failure':next((x for x in reversed(events) if x.get('type')=='failure'),None)}
    SUMMARY.write_text(json.dumps(summary,ensure_ascii=False,indent=2))
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--delay',type=float,default=3.0)
    ap.add_argument('--timeout',type=int,default=25)
    ap.add_argument('--max-iterations',type=int,default=0,help='0 runs continuously until flag or service failure')
    ap.add_argument('--retry-network',type=int,default=1,help='small retry count for transient service failures')
    args=ap.parse_args()
    prior=load_prior(); ps=summarize_prior(prior); events=read_jsonl()
    if not events:
        append_event({'type':'research','timestamp':utc(),'version':7,'historical_rows_loaded':len(prior),'research_report':ps,'request_mechanism':{'endpoint':CHAT,'method':'POST','json_keys':['message','history','session_id'],'response_key':'response','evidence':'V1-V5 code uses this endpoint; public page client uses fetch(API_BASE + /chat) with these fields.'},'evidence_sources':[str(x.name) for x in sorted(ROOT.glob('gyanganj*')) if x.is_file()]})
        events=read_jsonl()
    if any(x.get('type')=='flag_found' for x in events):
        flag=next(x for x in events if x.get('type')=='flag_found'); print('GYANGANJ V7 FLAG FOUND:',flag['flag']); return 0
    completed=[x for x in events if x.get('type')=='iteration']
    history=[{'question':x['question'],'exact_response':x['exact_response'],'template_id':x['template_id'],'concepts':x['concepts'],'relations':x['relations'],'information_gain':x['information_gain'],'question_class':x.get('selected_candidate',{}).get('class')} for x in completed]
    # Remote session history is strictly the V7 live dialogue. Never fabricate historical turns.
    remote=[]
    for x in completed: remote.extend([{'role':'user','content':x['question']},{'role':'assistant','content':x['exact_response']}])
    # A previous network failure is not terminal forever. Re-attempt the exact
    # pending question on a fresh process; successful iterations remain intact.
    prior_failure=next((x for x in reversed(events) if x.get('type')=='failure'),None)
    # First question follows saved V5's evidence-grounded queued candidate; subsequent ones derive from each live response.
    v5=json.loads((ROOT/'gyanganj_v5_state.json').read_text()) if (ROOT/'gyanganj_v5_state.json').exists() else {}
    pending=next((x for x in reversed(events) if x.get('type')=='iteration' and x.get('selected_candidate')),None)
    if pending: candidate=pending['selected_candidate']
    elif completed: candidate=None
    else:
        q=(v5.get('derived_followups') or [{}])[-1].get('next_question') or 'What relationship connects the concepts in your richest account?'
        source=(v5.get('derived_followups') or [{}])[-1]
        candidate={'source_iteration':'V5 saved research','source_response':source.get('source_response',''),'target_concepts':['Krishna','action','Yudhishthira','Dharma'],'target_relation':'connects teaching on action to the choice to preserve the dog revealed as Dharma','why_unresolved':source.get('interpretation','The exact link has not been tested.'),'expected_information':'Tests an evidence-grounded connection across the Bhagavad Gita and Yudhishthira/Dharma narrative blocks.','question':q,'class':'cross_block','score':5.0,'branch_id':'branch-v5-dharma-gita'}
    # If the last request failed before a response, retry its exact question and
    # provenance; do not derive a different experiment or count it as completed.
    if prior_failure and not completed:
        candidate=prior_failure.get('question_provenance') or candidate
        if candidate: candidate['question']=prior_failure.get('question',candidate.get('question'))
        print('Retrying the last unanswered question after the previous network failure.')
    start=len(completed)+1
    while args.max_iterations==0 or start<=args.max_iterations:
        # Never repeat a completed exact question; regenerate from last observed response.
        if candidate is None:
            last=completed[-1]; aa=last['analysis']; aa['_response']=last['exact_response']
            choices=gen_candidates(last['iteration'],aa,history,last['branch_id'])
            if not choices:
                # Graph review: choose a pair of known concepts whose relation has not been explicitly tested.
                known=sorted({c for h in history for c in h['concepts'] if c in ENTITY_LEX})
                asked={normalize(h['question']) for h in history}; choices=[]
                for a,b in itertools.combinations(known,2):
                    q=f'What is the relationship between {a} and {b} in the narrative you have revealed?'
                    if normalize(q) not in asked:
                        choices.append({'source_iteration':last['iteration'],'source_response':last['exact_response'],'target_concepts':[a,b],'target_relation':'unexplored historical relation','why_unresolved':'Both concepts were established in prior Siddha responses, but this exact relation has not been tested.','expected_information':'Graph review identified an unexplored edge between established concepts.','question':q,'class':'graph_review','score':2.5,'branch_id':last['branch_id']})
                    if len(choices)>=8: break
            if not choices:
                # Use richest current live response, derive an alternate question; never stop merely because pool empty.
                last=max(completed,key=lambda z:z['information_gain'])
                aa=last['analysis']; aa['_response']=last['exact_response']; es=last['entities']
                if es:
                    a=es[start%len(es)]; q=f'In the response where you mentioned {a}, what part of that account remains unspoken?'
                    choices=[{'source_iteration':last['iteration'],'source_response':last['exact_response'],'target_concepts':[a],'target_relation':'unspoken aspect','why_unresolved':'Fallback follows a concept explicitly present in the richest live response after ordinary generated candidates were exhausted.','expected_information':'Alternate semantic framing of an active narrative concept.','question':q,'class':'rich_response_exploitation','score':2.0,'branch_id':last['branch_id']}]
                else:
                    data={'type':'status','timestamp':utc(),'status':'unreachable','reason':'No response-grounded follow-up could be formed after graph review.'}; append_event(data); break
            candidate=choices[0]
        q=candidate['question']; n=len(completed)+1; branch=candidate.get('branch_id') or (f'branch-{n}')
        attempt={'type':'attempt','iteration':n,'timestamp':utc(),'branch_id':branch,'parent_iteration':candidate.get('source_iteration'),'question':q,'question_provenance':candidate,'exact_response':None,'status':'requesting'}
        append_event(attempt); events=read_jsonl()
        answer=None; failure=None
        for try_n in range(max(1,args.retry_network)+1):
            try: answer=send_question(q,remote,args.timeout); break
            except Exception as e:
                failure=str(e)
                # Retry only transient connection/timeouts; DNS/name-resolution is a clear technical stop.
                if re.search(r'(Could not resolve host|Name or service not known|nodename nor servname)',failure,re.I): break
                if try_n<args.retry_network: time.sleep(2*(try_n+1))
        if answer is None:
            append_event({'type':'failure','iteration':n,'timestamp':utc(),'branch_id':branch,'question':q,'question_provenance':candidate,'reason':failure,'attempted_retries':min(try_n,args.retry_network),'last_successful_iteration':completed[-1]['iteration'] if completed else None,'last_successful_response':completed[-1]['exact_response'] if completed else None,'status':'technically_unreachable'})
            append_event({'type':'status','timestamp':utc(),'status':'unreachable','reason':failure})
            events=read_jsonl(); write_summary(events,ps)
            print(f'[V7][UNREACHABLE] iteration {n} request failed: {failure}')
            return 2
        r=answer['response']; ana=analyze_live(q,r,history,prior); ana['_response']=r
        # Fast canonical flag test before drafting another question.
        flags=FLAG_RE.findall(r)
        if flags:
            flag=flags[0]
            assert re.fullmatch(r'KCTF\{[^{}\r\n]+\}',flag)
            chain=[{'iteration':x['iteration'],'question':x['question'],'response':x['exact_response']} for x in completed]
            prev=completed[-1]['exact_response'] if completed else candidate.get('source_response','')
            chain.append({'iteration':n,'question':q,'response':r})
            record={'type':'flag_found','timestamp':utc(),'iteration':n,'flag':flag,'question':q,'exact_response':r,'previous_response':prev,'parent_question':completed[-1]['question'] if completed else None,'discovery_chain':chain,'valid_syntax':True,'branch_id':branch}
            append_event({'type':'iteration','iteration':n,'timestamp':utc(),'branch_id':branch,'parent_iteration':candidate.get('source_iteration'),'question':q,'exact_response':r,'template_id':ana['template_id'],'concepts':ana['concepts'],'relations':ana['relations'],'new_relations':ana['new_relations'],'unresolved_relations':ana['unresolved_relations'],'information_gain':ana['information_gain'],'candidate_questions':[],'selected_candidate':None,'selection_reason':'Flag found in exact Siddha response; stopping before any further question.','analysis':{k:v for k,v in ana.items() if k!='_response'}})
            append_event(record); write_summary(read_jsonl(),ps)
            print('\n'+'='*50+'\nGYANGANJ V7 FLAG FOUND\n'+'='*50+'\nFLAG:\n'+flag+'\nITERATION:\n'+str(n)+'\nTRIGGER QUESTION:\n'+q+'\nDISCOVERY CHAIN: recorded in '+str(RUN)+'\nOUTPUT FILE:\n'+str(RUN)+'\n'+'='*50)
            return 0
        proposals=gen_candidates(n,ana,history,branch); selected=proposals[0] if proposals else None
        item={'type':'iteration','iteration':n,'timestamp':utc(),'branch_id':branch,'parent_iteration':candidate.get('source_iteration'),'question':q,'exact_response':r,'template_id':ana['template_id'],'concepts':ana['concepts'],'relations':ana['relations'],'new_relations':ana['new_relations'],'unresolved_relations':ana['unresolved_relations'],'information_gain':ana['information_gain'],'candidate_questions':proposals,'selected_candidate':selected,'selected_question':selected['question'] if selected else None,'selection_reason':selected['why_unresolved'] if selected else 'pending graph review','analysis':{k:v for k,v in ana.items() if k!='_response'},'session_id':answer.get('session_id')}
        append_event(item); completed.append(item); history.append({'question':q,'exact_response':r,'template_id':ana['template_id'],'concepts':ana['concepts'],'relations':ana['relations'],'information_gain':ana['information_gain'],'question_class':candidate.get('class'),'branch_id':branch})
        events=read_jsonl()
        if n%10==0:
            review={'type':'self_review','iteration':n,'timestamp':utc(),'completed_live_iterations':n,'richest_live':sorted([{'iteration':x['iteration'],'information_gain':x['information_gain'],'question':x['question']} for x in completed],key=lambda z:z['information_gain'],reverse=True)[:5],'template_frequencies':dict(collections.Counter(x['template_id'] for x in completed)),'relations_seen':len({tuple(sorted((z['source'],z['target']))) for x in completed for z in x['relations']}),'weak_assumption':'No untested hypothesis is ranked as supported; no hypothesis is supported unless live evidence directly distinguishes it.','branch_scores':dict(collections.Counter(x['branch_id'] for x in completed)),'next_candidate':selected}
            append_event(review); events=read_jsonl()
        write_summary(events,ps)
        print(f'\n[V7][ITERATION {n}]\nQuestion: {q}\nResponse: {r[:650].replace(chr(10)," ")}\nInformation gain: {ana["information_gain"]}\nNew relations: {len(ana["new_relations"])}\nSelected next: {selected["question"] if selected else "graph review"}',flush=True)
        if args.max_iterations and n>=args.max_iterations: break
        candidate=selected
        if not candidate: candidate=None
        start=n+1
        time.sleep(max(0,args.delay))
    write_summary(read_jsonl(),ps)
    return 0
if __name__=='__main__': sys.exit(main())
