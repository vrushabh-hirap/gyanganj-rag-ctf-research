#!/usr/bin/env python3
"""GYANGANJ V8 autonomous adaptive solver.

Resumable live conversation; all V8 state and events are separate from V1-V7.
Only the canonical literal flag in a response returned by /chat is success.
"""
import argparse, collections, difflib, hashlib, itertools, json, math, os
import re, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parent
RUN=ROOT/'gyanganj_v8_run.jsonl'; STATE=ROOT/'gyanganj_v8_state.json'; SUMMARY=ROOT/'gyanganj_v8_summary.json'
RESEARCH=ROOT/'gyanganj_v8_research.md'
BASE='https://gyanganj-ctf.onrender.com'; CHAT=BASE+'/chat'
FLAG=re.compile(r'KCTF\{[^{}\r\n]+\}')
WORD=re.compile(r"[A-Za-z][A-Za-z'-]*")
INTRO='You stand at the gates of Gyanganj. I have guarded this city since before your civilization drew its first breath. Speak your purpose, or leave the way you came.'
STOP=set('a an the and or but if then than of to in on at for from by with as is are was were be been being do does did have has had it its this that these those i we you they he she my your our their what which who whom when where why how all any some more there here not no yes can could would should will may might must into over under after before between through about against because very own such also both each other only one two three four five said says say speak tell ask answer question response record visible deeper beyond lies lie'.split())
COMMON_ENTITIES=set('vyasa ganesha brahma mahabharata siddha siddhas gyanganj shambhala dharma yudhishthira arjuna krishna bhagavad gita indra svarga akasha akashic mula shloka karma himalayas dog seed truth silence practice record verse action duty cosmic order time tapas siddhi draupadi dushasana kurukshetra parva shanti svargarohana adi arjuna indelible scribe righteousness unconditional loyalty'.split())
PHRASES=['mula shloka','seed-truth','seed truth','appointed time','akashic record','deeper record','deeper question','beyond all doors','single utterance','unwritten verse','cosmic order','visible record','questions must precede','accumulated silence','one final shloka','single continuous moment']
STRATEGIES=['resolve_instruction','causal_relation','narrative_relation','cross_block','contrast','sequence','unresolved_phrase','template_transition','semantic_completion','controlled_mutation','bridge']

def now(): return datetime.now(timezone.utc).isoformat()
def norm(x): return re.sub(r'[^a-z0-9]+',' ',(x or '').lower()).strip()
def digest(x): return hashlib.sha1(norm(x).encode()).hexdigest()
def similarity(a,b): return difflib.SequenceMatcher(None,norm(a),norm(b)).ratio()
def split_sentences(s): return [x.strip() for x in re.split(r'(?<=[.!?])\s+',s or '') if x.strip()]
def split_paragraphs(s): return [x.strip() for x in re.split(r'\n\s*\n',s or '') if x.strip()]
def extract_entities(text, established=None):
    words=WORD.findall(text); low={x.lower() for x in words}
    known=set(COMMON_ENTITIES)|(set(established or []))
    # Named capitalized entities can emerge from observed text; exclude sentence-initial generic words.
    proper={w.lower() for w in words if w[:1].isupper() and w.lower() not in STOP and len(w)>2}
    return sorted((low & known)|{x for x in proper if x in known})
def extract_concepts(text, established=None):
    words=WORD.findall(text); low={w.lower() for w in words}
    ents=set(extract_entities(text,established)); out=set(ents)
    out|={p for p in PHRASES if re.search(r'\b'+re.escape(norm(p))+r'\b',norm(text))}
    # Limit noun/concept vocabulary to repeated/established terms; no generic one-off verb promotion.
    freq=established or {}
    if isinstance(freq,dict): out|={w for w in low if len(w)>4 and w not in STOP and freq.get(w,0)>=2}
    return sorted(out)
def extract_relations(text, entities_here):
    rels=[]
    for s in split_sentences(text):
        es=[e for e in entities_here if re.search(r'\b'+re.escape(e)+r'\b',s,re.I)]
        if len(es)<2: continue
        low=norm(s)
        # Event-specific dependency cues avoid making every noun in a long
        # sentence an equally meaningful edge.
        if 'testing whether' in low and 'yudhishthira' in es and 'dharma' in es:
            rels.append({'source':'dharma','relation':'tests','target':'righteousness','evidence':s,'epistemic':'observed_text','confidence':0.92}); continue
        if 'yudhishthira' in es and 'dog' in es and ('refused' in low or 'abandon' in low):
            rels.append({'source':'yudhishthira','relation':'refuses_to_abandon','target':'dog','evidence':s,'epistemic':'observed_text','confidence':0.9})
            if 'dharma' in es and ('revealed' in low or 'himself' in low):
                rels.append({'source':'dog','relation':'revealed_as','target':'dharma','evidence':s,'epistemic':'observed_text','confidence':0.9})
            continue
        if 'single utterance' in low and ('from which' in low or 'unfold' in low):
            source='mula shloka' if 'mula shloka' in low else 'utterance'
            for target in ('dharma','karma','cosmic order'):
                if target in low: rels.append({'source':source,'relation':'gives_rise_to','target':target,'evidence':s,'epistemic':'observed_text','confidence':0.9})
            if rels and rels[-1].get('evidence')==s: continue
        # Relation type is directional where language provides a signal.
        patterns=[(r'\b(entrusted|given|sealed|preserved|recorded)\b','entrusted_or_stored_with'),(r'\b(led to|caused|therefore|because|resulted in)\b','causes'),(r'\b(before|precede|preceded)\b','precedes'),(r'\b(after|followed|then|later)\b','follows'),(r'\b(refused|chose|abandoned|tested|testing)\b','tests_or_chooses'),(r'\b(contains|from which|unfolds|gives rise)\b','gives_rise_to'),(r'\b(known as|called|revealed to be|is said to be)\b','identified_as')]
        label=next((lab for pat,lab in patterns if re.search(pat,s,re.I)),'co-mentioned')
        ordered=sorted(es,key=lambda e:min((m.start() for m in re.finditer(r'\b'+re.escape(e)+r'\b',s,re.I)),default=9999))
        for a,b in itertools.combinations(ordered,2):
            rels.append({'source':a,'relation':label,'target':b,'evidence':s,'epistemic':'observed_text','confidence':0.65 if label!='co-mentioned' else 0.3})
    return rels
def load_jsonl(path):
    out=[]
    if not path.exists(): return out
    for line in path.read_text(encoding='utf8').splitlines():
        try: out.append(json.loads(line))
        except Exception: break
    return out
def append_jsonl(event):
    with RUN.open('a',encoding='utf8') as f:
        f.write(json.dumps(event,ensure_ascii=False,separators=(',',':'))+'\n'); f.flush(); os.fsync(f.fileno())
def atomic_json(path,obj):
    tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)); tmp.replace(path)
def evidence_rows():
    rows=[]
    for p in sorted(ROOT.glob('gyanganj*_log_*.json')):
        if '_v8_' in p.name: continue
        try: src=json.loads(p.read_text())
        except Exception: continue
        for x in src:
            if x.get('question') and x.get('response'): rows.append({'question':x['question'],'response':x['response'],'source':p.name,'live':False})
    p=ROOT/'gyanganj_v5_state.json'
    if p.exists():
        try: src=json.loads(p.read_text())
        except Exception: src={}
        for x in src.get('experiments',[]):
            if x.get('question') and x.get('response'): rows.append({'question':x['question'],'response':x['response'],'source':'gyanganj_v5_state.json','live':not x.get('historical',False)})
    # V7 response events are explicitly actual target replies; only iteration records count.
    for x in load_jsonl(ROOT/'gyanganj_v7_run.jsonl'):
        if x.get('type')=='iteration' and x.get('question') and isinstance(x.get('exact_response'),str):
            rows.append({'question':x['question'],'response':x['exact_response'],'source':'gyanganj_v7_run.jsonl','live':True,'session_id':x.get('session_id')})
    seen=set(); out=[]
    for r in rows:
        key=(norm(r['question']),norm(r['response']))
        if key in seen: continue
        seen.add(key); out.append(r)
    return out
def build_research(rows):
    responses=collections.Counter(digest(x['response']) for x in rows)
    pairs=collections.Counter(); question_families=collections.defaultdict(lambda:[0,0])
    for r in rows:
        es=extract_entities(r['response']);
        for a,b in itertools.combinations(es,2): pairs[tuple(sorted((a,b)))]+=1
        q=norm(r['question'])
        fam='cross-block' if 'connect' in q or 'between' in q or 'relat' in q or 'shared' in q else ('flag-direct' if 'kctf' in q or 'flag' in q else ('completion' if q.endswith(' is') else 'lore/other'))
        question_families[fam][0]+=1; question_families[fam][1]+=int(len(r['response'].split())>70)
    V7=load_jsonl(ROOT/'gyanganj_v7_run.jsonl'); V7it=[e for e in V7 if e.get('type')=='iteration']
    return {'time':now(),'evidence_rows_deduplicated':len(rows),'unique_exact_normalized_responses':len(responses),'most_repeated_templates':responses.most_common(12),'historical_question_families':{k:{'attempts':v[0],'rich_responses':v[1]} for k,v in question_families.items()},'strong_cooccurrences':[(list(k),v) for k,v in pairs.most_common(20)],'v7_live_completed_iterations':len(V7it),'observations':['V1: 23 rows and 8 unique normalized responses.','V2: 55 rows and 27 unique normalized responses.','V3: 37 rows and 22 unique normalized responses.','V4: 79 rows and 39 unique normalized responses.','V5 JSON state: 225 rows, 50 templates, 33 blocks, 24,059 cooccurrence edges; mixed imported and subsequent interactions.','V6: explicitly offline, zero network requests.','V7: 22 actual live response records, then HTTP 429; repeated DNS failures preceded service recovery.','V7 cross-block question on Gita and Yudhishthira was a confirmed rich-response trigger; V7 first question about Krishna action and Yudhishthira also produced a rich combined narrative.'],'inferences':['The response selector is sensitive to exact phrasing and current chat history.','Cross-block relational prompts may increase rich block combinations, but sample size is small.','Generic flag and deeper-question requests often select low-information templates.'],'hypotheses':[{'claim':'Order of conversation questions changes response blocks','status':'untested/weakly supported only if matched comparison; no controlled test result in saved files','support':0,'contradictions':0},{'claim':'A specific question or concept leads to the flag','status':'untested','support':0,'contradictions':0}],'mistakes_fixed':['Do not trust V7 reported information gain: its broad tokenizer treated verbs as concepts and assigned 119.75 to a rich response.','Do not resend empty session IDs; carry forward actual returned session ID and complete chat history.','Do not repeat V7 duplicate Ganesha/Vyasa questions; semantic similarity cache rejects repeats.','Do not treat HTTP 429 as final failure; obey Retry-After and exponential backoff.','Do not mine historical flag-like strings as success; only inspect actual live response body.'],'pdf_note':'Included PDF exists but no pdftotext or PDF Python package is installed; text extraction was not available.'}
def http_send(q,history,sid,timeout):
    payload={'message':q,'history':history,'session_id':sid or ''}
    with tempfile.TemporaryDirectory(prefix='gyanganj_v8_') as td:
        req=Path(td)/'request.json'; hdr=Path(td)/'headers.txt'; body=Path(td)/'response.txt'
        req.write_text(json.dumps(payload,ensure_ascii=False))
        cp=subprocess.run(['curl','--silent','--show-error','--max-time',str(timeout),'-D',str(hdr),'-o',str(body),'-w','%{http_code}','-X','POST',CHAT,'-H','Content-Type: application/json','-H','Accept: application/json','-H','User-Agent: Mozilla/5.0 (GYANGANJ-V8)','--data-binary','@'+str(req)],capture_output=True,text=True,timeout=timeout+3)
        code=int(cp.stdout.strip() or 0); headers=hdr.read_text(errors='replace') if hdr.exists() else ''; raw=body.read_text(errors='replace') if body.exists() else ''
        hs={}
        for line in headers.splitlines():
            if ':' in line:
                k,v=line.split(':',1); hs[k.lower().strip()]=v.strip()
        if cp.returncode and not code: raise OSError(cp.stderr.strip() or f'curl exit {cp.returncode}')
        data=None
        try: data=json.loads(raw)
        except Exception: pass
        return code,hs,raw,data
def extract_history(events):
    turns=[]; sid=''; iters=[]
    for e in events:
        if e.get('type')=='iteration':
            iters.append(e)
            if e.get('session_id'): sid=e['session_id']
    if iters:
        turns=[{'role':'assistant','content':INTRO}]
        for e in iters: turns.extend([{'role':'user','content':e['question']},{'role':'assistant','content':e['exact_response']}])
    return turns,sid,iters
def infer_strategy(q):
    qn=norm(q)
    if 'because' in qn or 'cause' in qn or 'why did' in qn: return 'causal_relation'
    if 'contrast' in qn or 'difference' in qn or 'distinguish' in qn: return 'contrast'
    if 'before' in qn or 'after' in qn or 'sequence' in qn or 'precede' in qn: return 'sequence'
    if 'connect' in qn or 'relationship' in qn or 'relate' in qn: return 'cross_block'
    if 'what does' in qn or 'what do you mean' in qn: return 'unresolved_phrase'
    if 'instead' in qn or 'must' in qn or 'condition' in qn: return 'resolve_instruction'
    return 'semantic_completion'
def candidate_pool(last,history,graph,stats,branch_id):
    r=last['response']; cs=last['analysis']['concepts']; ents=last['analysis']['entities']; newrels=last['analysis']['relations']; candidates=[]
    exactqs=[h['question'] for h in history]
    def add(strategy,targets,relation,why,q,expected,base):
        if not q.strip() or len(q.split())<5:return
        if any(similarity(q,p)>=.83 for p in exactqs):return
        if any(similarity(q,x['question'])>=.90 for x in candidates):return
        candidates.append({'strategy':strategy,'target_concepts':targets,'target_relation':relation,'why_unresolved':why,'question':q,'expected_information':expected,'source_iteration':last['iteration'],'source_response':r,'branch_id':branch_id,'base_score':base})
    # Resolve literal instruction/teaser in the latest response, if present.
    for s in split_sentences(r):
        if re.search(r'\b(must|before|precede|instead|there is more|deeper record|appointed time|sealed|permitted)\b',s,re.I):
            focus=ents[:3]
            add('resolve_instruction',focus,'clarifies explicit instruction or limitation','This exact sentence appeared in the just-received response and states a constraint, transition, or withheld continuation.',f'You said, “{s}” What specific next step does that imply in the story we are discussing?','Clarifies an explicitly stated clue rather than asking generically about a deeper question.',5.2)
    # Ask about actually stated multi-entity relations, not every noun pair.
    for rel in newrels:
        a,b=rel['source'],rel['target']
        if rel['relation']=='co-mentioned':
            continue
        if rel['relation']=='tests': q='What quality of Yudhishthira was Dharma testing through the choice described in your answer?'
        elif rel['relation']=='refuses_to_abandon': q='What principle was demonstrated by Yudhishthira refusing to abandon the dog?'
        elif rel['relation']=='revealed_as': q='Why was Dharma revealed to Yudhishthira in the form of the dog?'
        elif rel['relation']=='gives_rise_to': q=f'How does the mula shloka give rise to {b}, according to your account?'
        elif rel['relation']=='causes': q=f'What evidence in the story explains how {a} leads to {b}?'
        elif rel['relation']=='tests_or_chooses': q=f'What is being tested when {a} is connected with {b} in that event?'
        else: q=f'What does the stated relationship between {a} and {b} reveal about the narrative?'
        add('narrative_relation',[a,b],rel['relation'],'The latest response explicitly connects these concepts in one statement, while the meaning of the connection has not been asked directly.',q,'Tests the semantics of an observed relationship, not merely co-occurrence.',4.8 if rel['relation']!='co-mentioned' else 3.3)
    # Causal / contrastive / sequence mutation of observed propositions.
    for s in split_sentences(r):
        se=[e for e in ents if re.search(r'\b'+re.escape(e)+r'\b',s,re.I)]
        if len(se)>=2 and re.search(r'\b(because|when|therefore|instead|refused|chose|condition|before|after|then)\b',s,re.I):
            a,b=se[:2]
            if 'yudhishthira' in se and 'dog' in se and ('refused' in s.lower() or 'abandon' in s.lower()):
                causal_q='What principle was tested by Yudhishthira refusing to abandon the dog?'
            elif 'vyasa' in se and 'ganesha' in se and 'condition' in s.lower():
                causal_q='Why did Ganesha require Vyasa to dictate without pause, and what counter-condition did Vyasa add?'
            else:
                causal_q=f'What consequence followed the event involving {a} and {b} described in your last answer?'
            add('causal_relation',[a,b],'cause / consequence','A conditional, causal, contrastive, or temporal statement appears verbatim in the previous answer.',causal_q,'Tests the reason or consequence attached to a claim in the latest live response.',4.7)
            add('contrast',[a,b],'contrast or distinction','The response itself marks a contrast, refusal, alternative, or condition.',f'What distinction is the account making between {a} and {b} in that statement?','Clarifies a contrast already expressed by the Siddha.',4.1)
            add('sequence',[a,b],'narrative order','A temporal/conditional marker ties events in this exact response.',f'What happened immediately before or after the event involving {a} and {b}?','Fills a narrative transition grounded in the preceding response.',3.9)
    # Mine quoted unresolved phrases / unusual endings.
    for s in split_sentences(r)[-4:]:
        if re.search(r'\b(this|that|it|more|single|unwritten|seed|silent|record|answer|question|time)\b',s,re.I):
            term=next((c for c in cs if re.search(r'\b'+re.escape(norm(c))+r'\b',norm(s))),None)
            if term:
                add('unresolved_phrase',[term],'definition or referent','The latest sentence uses a recurring loaded phrase about '+term+' without defining it.',f'In the sentence “{s}”, what exactly does {term} refer to?','Resolves a phrase in the current answer using a specific reference.',4.0)
    # Cross-block only from high-confidence learned branches, requiring one entity from each block.
    groups=graph.get('blocks',{})
    active=[]
    for b,vals in groups.items():
        counts=vals.get('concept_counts',{})
        top=sorted(counts,key=counts.get,reverse=True)[:8]
        if len(top)>=2: active.append((b,set(top),sum(counts.values())))
    present=[b for b,cs0,n in active if set(ents)&cs0]
    for a,b in itertools.combinations(active,2):
        if a[0] in present or b[0] in present:
            # One endpoint must be supported by the current response; the other
            # may come from a strong independent block in accumulated evidence.
            current_a=sorted(set(ents)&a[1]); current_b=sorted(set(ents)&b[1])
            if current_a:
                ea=current_a; eb=sorted(b[1]-set(ents),key=lambda z:graph['nodes'].get(z,{}).get('evidence_count',0),reverse=True)
            elif current_b:
                ea=current_b; eb=sorted(a[1]-set(ents),key=lambda z:graph['nodes'].get(z,{}).get('evidence_count',0),reverse=True)
            else: ea=[]; eb=[]
            if ea and eb:
                x,y=ea[0],eb[0]; key=norm(' '.join(sorted((x,y))))
                if graph.get('tested_pairs',{}).get(key,0):continue
                add('cross_block',[x,y],f'bridge:{a[0]}↔{b[0]}','Each concept belongs to a repeatedly observed response block; their direct link remains untested.',f'How does {x}, from the {a[0]} account, connect to {y} in the {b[0]} account?','Tests a relation between independently observed narrative blocks with direct source support.',5.0)
    # Controlled semantic mutations of the best historically performing strategy.
    if len(ents)>=2:
        a,b=ents[:2]
        add('controlled_mutation',[a,b],'relationship under a new grounded framing','The target pair is drawn from the latest response; this is a grammatical mutation of relational questioning, not an unrelated prompt.',f'What is the narrative significance of linking {a} with {b}?','Compares a concise relation frame against longer causal/synthesis framings.',3.6)
        add('semantic_completion',[a,b],'continuation of current account','The last response explicitly mentioned these concepts; asks for the next narrative piece.',f'Complete the account: after the part about {a} and {b}, what consequence follows?','May advance the narrative by one step.',3.5)
    # Keep at least five evidence-grounded candidates; create grounded paraphrases from current statements.
    for s in split_sentences(r):
        if len(candidates)>=8:break
        es=[e for e in ents if re.search(r'\b'+re.escape(e)+r'\b',s,re.I)]
        if es:
            q=f'What consequence follows from this statement: “{s[:240]}”'
            add('semantic_completion',es,'consequence','Directly quotes a factual statement from the immediately preceding live answer.',q,'Asks for the next step in the observed narrative.',2.7)
    # Do not pad the slate with meta-questions. A short slate is preferable to
    # repeating clarification templates after the evidence-grounded candidates
    # have been exhausted; adaptive_followups will pivot to rich prior evidence.
    # Score from bounded IG, strategy outcomes (Bayesian-smoothed) and repetition penalties.
    for c in candidates:
        st=stats.get(c['strategy'],{'attempts':0,'gain_sum':0,'rich':0,'dead':0})
        prior_n=.35*st.get('historical_attempts',0); prior_gain=.35*st.get('historical_gain_sum',0.0)
        mean=(st['gain_sum']+prior_gain+1.0)/(st['attempts']+prior_n+2.0)
        explore=math.sqrt(math.log(sum(v.get('attempts',0)+.35*v.get('historical_attempts',0) for v in stats.values())+2)/(st['attempts']+prior_n+1))
        overlap=max((similarity(c['question'],h['question']) for h in history),default=0)
        deadpen=.65 if st['attempts']>=3 and st['gain_sum']/max(1,st['attempts'])<.45 else 0
        c['score']=round(c['base_score']+min(1.2,mean*.25)+.4*explore-3.5*max(0,overlap-.55)-deadpen,3)
    candidates.sort(key=lambda z:z['score'],reverse=True)
    return candidates[:12]
def adaptive_followups(latest,livehist,prior_rows,graph,stats):
    """Exploit the best supported live branch after low-gain/canned replies."""
    all_questions=[{'question':x['question'],'response':x.get('response',x.get('exact_response',''))} for x in prior_rows]
    all_questions += [{'question':x['question'],'response':x.get('response','')} for x in livehist]
    anchors=[]
    if latest: anchors.append(latest)
    if not latest or latest.get('information_gain',0)<1.5 or latest.get('branch_status')=='DEAD':
        anchors += sorted((x for x in livehist if x is not latest and x.get('information_gain',0)>=1.3),key=lambda z:(z.get('information_gain',0),len(z.get('response','').split())),reverse=True)[:8]
    pool=[]; byquestion=[]
    for anchor in anchors:
        response=anchor.get('response',anchor.get('exact_response',''))
        freq={k:v.get('evidence_count',0) for k,v in graph.get('nodes',{}).items()}
        es=extract_entities(response,freq); cs=extract_concepts(response,freq)
        analysis={'concepts':cs,'entities':es,'relations':extract_relations(response,es)}
        source={'iteration':anchor.get('iteration','historical-rich-response'),'response':response,'analysis':analysis,'branch_id':anchor.get('branch_id','historical-promising')}
        cands=candidate_pool(source,all_questions,graph,stats,source['branch_id'])
        anchor_bonus=min(1.5,anchor.get('information_gain',0)*.12)
        for c in cands:
            # Global exact and semantic question guard.
            mx=max((similarity(c['question'],h['question']) for h in all_questions),default=0)
            if mx>=.80: continue
            c['score']=round(c['score']+anchor_bonus,3)
            c['anchor_information_gain']=anchor.get('information_gain',0)
            if not any(similarity(c['question'],z['question'])>=.90 for z in byquestion): byquestion.append(c)
    byquestion.sort(key=lambda z:z['score'],reverse=True)
    if byquestion:return byquestion[:12]
    # Graph fallback: bridge one recently established concept to a strong
    # concept from a distinct block, excluding edges/questions already tested.
    source=latest or (livehist[-1] if livehist else None)
    if source:
        response=source.get('response',source.get('exact_response',''))
        source_ents=extract_entities(response,{k:v.get('evidence_count',0) for k,v in graph['nodes'].items()})
        blocks=graph.get('blocks',{})
        for a in source_ents:
            for block_name,block in sorted(blocks.items(),key=lambda kv:kv[1].get('responses',0),reverse=True):
                target=next((c for c,_ in sorted(block.get('concept_counts',{}).items(),key=lambda kv:kv[1],reverse=True) if c!=a),None)
                if not target:continue
                q=f'How is {a} connected to {target} in the narrative you have described?'
                if max((similarity(q,h['question']) for h in all_questions),default=0)<.80:
                    return [{'strategy':'bridge','target_concepts':[a,target],'target_relation':'unexplored relation from observed concept to established response block','why_unresolved':'The source response and the second block are supported by saved response evidence; this edge remains untested.','expected_information':'Graph-guided exploration after response-derived candidates were exhausted.','question':q,'source_iteration':source.get('iteration','historical-rich-response'),'source_response':response,'branch_id':source.get('branch_id','graph-review'),'score':1.0}]
    return []
def seed_graph(rows,v7events):
    graph={'nodes':{},'edges':[],'blocks':{},'templates':{},'tested_pairs':{}}
    seen_edges=set()
    for ix,row in enumerate(rows):
        es=extract_entities(row['response']); cc=extract_concepts(row['response'])
        for c in cc:
            graph['nodes'].setdefault(c,{'type':'concept_or_entity','evidence_count':0,'sources':[]})
            n=graph['nodes'][c]; n['evidence_count']+=1
            if len(n['sources'])<12:n['sources'].append({'source':row.get('source'),'question':row['question']})
        tid=digest(row['response']); t=graph['templates'].setdefault(tid,{'count':0,'representative':row['response'][:500],'questions':[]})
        t['count']+=1
        if len(t['questions'])<20:t['questions'].append(row['question'])
        block=classify_block(es,row['response']); b=graph['blocks'].setdefault(block,{'concept_counts':{},'responses':0})
        b['responses']+=1
        for c in es:b['concept_counts'][c]=b['concept_counts'].get(c,0)+1
        for rel in extract_relations(row['response'],es):
            key=(rel['source'],rel['relation'],rel['target'],norm(rel['evidence']))
            if key in seen_edges:continue
            seen_edges.add(key)
            graph['edges'].append({'source':rel['source'],'relation':rel['relation'],'target':rel['target'],'source_iteration':None,'source_response':rel['evidence'],'question':row['question'],'confidence':rel['confidence'],'epistemic':'direct_text_relation' if rel['relation']!='co-mentioned' else 'cooccurrence_only','evidence_origin':row.get('source')})
        # Historical question pair testing cache.
        qe=extract_entities(row['question'])
        for a,b in itertools.combinations(qe,2):
            k=norm(' '.join(sorted((a,b)))); graph['tested_pairs'][k]=graph['tested_pairs'].get(k,0)+1
    return graph
def classify_block(es,text):
    groups={'mula':['mula','shloka','seed','verse','truth'],'vyasa_ganesha':['vyasa','ganesha','scribe','dictate'],'gita':['krishna','arjuna','gita','kurukshetra'],'dharma_test':['yudhishthira','dharma','dog','indra','svarga'],'akasha':['akasha','akashic','record','siddha','gyanganj'],'other':[]}
    n=norm(text); matches=[(sum(bool(re.search(r'\b'+re.escape(x)+r'\b',n)) for x in words),g) for g,words in groups.items() if g!='other']
    score,grp=max(matches,default=(0,'other'))
    return grp if score>=2 else 'other'
def history_template(s):return digest(s)
def update_hypotheses(st, analysis, it):
    # Principled status: zero tests is UNTESTED; observational evidence only adjusts hypotheses when the response discriminates.
    for h in st['hypotheses']:
        if h['tests']==0: h['status']='UNTESTED'; h['confidence']=0.0
        else:
            net=h['support']-h['contradiction']; h['confidence']=round((h['support']+1)/(h['tests']+2),3)
            h['status']='SUPPORTED' if net>=3 else ('POSSIBLE' if net>0 else ('DISFAVORED' if net<0 else 'WEAK'))
def initial_state(rows):
    graph=seed_graph(rows,[])
    stats={k:{'attempts':0,'gain_sum':0.0,'rich':0,'dead':0,'transition_count':0,'historical_attempts':0,'historical_gain_sum':0.0} for k in STRATEGIES}
    seen_templates=collections.Counter(digest(x['response']) for x in rows)
    for row in rows:
        st_name=infer_strategy(row['question']); st=stats.setdefault(st_name,{'attempts':0,'gain_sum':0.0,'rich':0,'dead':0,'transition_count':0,'historical_attempts':0,'historical_gain_sum':0.0})
        st['historical_attempts']+=1
        # Coarse historical prior: novel response template + rich content, kept
        # at low weight during selection; live outcomes quickly dominate it.
        gain=(.9 if len(row['response'].split())>70 else .15)+(.6 if seen_templates[digest(row['response'])]==1 else .05)
        st['historical_gain_sum']+=gain
    return {'version':8,'created':now(),'updated':now(),'historical_rows':len(rows),'graph':graph,'history':[],'question_stats':{},'strategy_stats':stats,'templates_live':{},'branches':{},'hypotheses':[{'claim':'Question order affects response routing','support':0,'contradiction':0,'tests':0,'confidence':0.0,'evidence_ids':[],'status':'UNTESTED'},{'claim':'Cross-block relation questions yield richer responses','support':0,'contradiction':0,'tests':0,'confidence':0.0,'evidence_ids':[],'status':'UNTESTED'}],'pending_question':None,'session_id':'','conversation_history':[],'confirmed_flag':None,'live_attempts':0,'completed_iterations':0,'recent_failures':[]}
def state_from_events(rows,events):
    st=initial_state(rows); live=[]
    for e in events:
        if e.get('type')=='iteration': live.append(e)
        elif e.get('type')=='request_error': st['recent_failures'].append(e)
        elif e.get('type')=='flag_found': st['confirmed_flag']=e
    for e in live:
        record={'iteration':e['iteration'],'question':e['question'],'response':e['exact_response'],'timestamp':e['timestamp'],'template_id':e['template_id'],'concepts':e['concepts'],'entities':e['entities'],'relations':e['relations'],'information_gain':e['information_gain'],'strategy':e['strategy'],'branch_id':e['branch_id'],'live':True,'response_hash':e['response_hash']}
        st['history'].append(record); st['completed_iterations']+=1
        st['conversation_history'].extend([{'role':'user','content':e['question']},{'role':'assistant','content':e['exact_response']}])
        if e.get('session_id'):st['session_id']=e['session_id']
        st['graph']['edges'].extend(e.get('new_graph_edges',[]))
        for c in e['concepts']:
            node=st['graph']['nodes'].setdefault(c,{'type':'concept_or_entity','evidence_count':0,'sources':[]});node['evidence_count']+=1
        st['graph']['templates'].setdefault(e['template_id'],{'count':0,'representative':e['exact_response'][:500],'questions':[]})['count']+=1
        st['templates_live'].setdefault(e['template_id'],{'count':0,'questions':[],'gain_sum':0.0,'transitions':collections.Counter()})
        tt=st['templates_live'][e['template_id']];tt['count']+=1;tt['questions'].append(e['question']);tt['gain_sum']+=e['information_gain']
        st['strategy_stats'].setdefault(e['strategy'],{'attempts':0,'gain_sum':0,'rich':0,'dead':0,'transition_count':0})
        ss=st['strategy_stats'][e['strategy']];ss['attempts']+=1;ss['gain_sum']+=e['information_gain'];ss['rich']+=e['information_gain']>=2.5;ss['dead']+=e['information_gain']<.5
        st['branches'].setdefault(e['branch_id'],{'status':'ACTIVE','score':0,'iterations':[],'concepts':[]});br=st['branches'][e['branch_id']];br['iterations'].append(e['iteration']);br['score']+=e['information_gain'];br['concepts']=sorted(set(br['concepts'])|set(e['concepts']));br['status']='PROMISING' if e['information_gain']>=2.5 else ('ACTIVE' if e['information_gain']>=.5 else br['status'])
        update_hypotheses(st,{},e['iteration'])
    st['live_attempts']=sum(1 for x in events if x.get('type') in ('request','request_error'))
    return st
def summary(st,events):
    iters=[e for e in events if e.get('type')=='iteration']
    return {'version':8,'updated':now(),'run_file':str(RUN.resolve()),'state_file':str(STATE.resolve()),'completed_live_iterations':len(iters),'unique_live_questions':len({norm(x['question']) for x in iters}),'live_requests':sum(x.get('type')=='request' for x in events),'network_errors':sum(x.get('type')=='request_error' for x in events),'flag_found':bool(st.get('confirmed_flag')),'confirmed_flag':st.get('confirmed_flag'),'strongest_branch':max(st.get('branches',{}).items(),key=lambda z:z[1]['score'],default=None),'top_information_gain':sorted([{'iteration':x['iteration'],'score':x['information_gain'],'question':x['question']} for x in iters],key=lambda z:z['score'],reverse=True)[:10],'strategy_stats':st['strategy_stats'],'stop_reason':st.get('stop_reason')}
def persist(st,events):
    st['updated']=now(); atomic_json(STATE,st); atomic_json(SUMMARY,summary(st,events))
def choose_seed_candidate(st,rows,events):
    # Retry V7's last rate-limited question: it is uncompleted, response-grounded, and V8 never sent it.
    v7=load_jsonl(ROOT/'gyanganj_v7_run.jsonl')
    last_err=next((x for x in reversed(v7) if x.get('type')=='failure' and x.get('reason','').find('429')>=0),None)
    if last_err and last_err.get('question'):
        q=last_err['question']
        return {'strategy':'cross_block','target_concepts':['action','akasha'],'target_relation':'connects previously live-established narrative blocks','why_unresolved':'This V7 question received HTTP 429 and no answer; it is not a completed experiment. The concepts occur in actual live dialogue.','expected_information':'Retry one pending cross-block experiment, then learn from its live response.','question':q,'source_iteration':'V7 pending after HTTP 429','source_response':next((x['exact_response'] for x in reversed(v7) if x.get('type')=='iteration'),'') ,'branch_id':'v7-pending-cross-block'}
    # Else select most recent successful V7 response as immediate context parent and build grounding.
    prev=next((x for x in reversed(v7) if x.get('type')=='iteration'),None)
    if prev:
        ents=extract_entities(prev['exact_response']); pair=ents[:2]
        q=(f'What is the narrative significance of {pair[0]} and {pair[1]} in the response you just gave?' if len(pair)>=2 else f'What does your last statement “{prev["exact_response"][:180]}” mean in this account?')
        return {'strategy':'cross_block','target_concepts':pair,'target_relation':'derived from latest saved live response','why_unresolved':'Question is anchored to the latest successful V7 response and targets an untested relationship.','expected_information':'Exploit the current promising live narrative and preserve continuity.','question':q,'source_iteration':prev['iteration'],'source_response':prev['exact_response'],'branch_id':'v7-latest-live'}
    # Last-resort historical cross-block candidate, explicitly marked historical source.
    v5=json.loads((ROOT/'gyanganj_v5_state.json').read_text()) if (ROOT/'gyanganj_v5_state.json').exists() else {}
    follow=(v5.get('derived_followups') or [{}])[-1]
    return {'strategy':'cross_block','target_concepts':['Krishna','action','Yudhishthira','Dharma'],'target_relation':'Gita/action and Dharma-test relation','why_unresolved':'V5 queued this grounded question; it has not been completed in the V7 run.','expected_information':'Test one cross-block narrative relationship established in saved responses.','question':follow.get('next_question','What connects Krishna’s teaching and Yudhishthira’s choice?'),'source_iteration':'V5 queued follow-up','source_response':follow.get('source_response',''),'branch_id':'v5-dharma-gita'}
def run(args):
    rows=evidence_rows(); research=build_research(rows); events=load_jsonl(RUN)
    if not events:
        append_jsonl({'type':'research_snapshot','timestamp':now(),'evidence_count':len(rows),'report':research,'sources':['V1-V4 logs','V5 state','V6 offline output','V7 JSONL and summary','project solver code'],'request_contract':{'endpoint':CHAT,'method':'POST','payload':['message','history','session_id'],'response':['response','session_id']}}); events=load_jsonl(RUN)
    if STATE.exists():
        try: st=json.loads(STATE.read_text())
        except Exception: st=state_from_events(rows,events)
    else: st=state_from_events(rows,events)
    # Event log wins if state snapshot lags a crash.
    rebuilt=state_from_events(rows,events)
    if rebuilt['completed_iterations']>=st.get('completed_iterations',0): st=rebuilt
    if st.get('confirmed_flag'):
        print('CONFIRMED LIVE FLAG:',st['confirmed_flag']['flag']); return 0
    # Preserve the complete successful V7 dialogue, then append V8 turns.
    # Historical V1-V6 rows remain graph evidence but are not fabricated into chat history.
    v7it=[x for x in load_jsonl(ROOT/'gyanganj_v7_run.jsonl') if x.get('type')=='iteration']
    remote=[{'role':'assistant','content':INTRO}]
    for x in v7it: remote.extend([{'role':'user','content':x['question']},{'role':'assistant','content':x['exact_response']}])
    for x in sorted((z for z in events if z.get('type')=='iteration'),key=lambda z:z['iteration']):
        remote.extend([{'role':'user','content':x['question']},{'role':'assistant','content':x['exact_response']}])
    sid=st.get('session_id') or next((x.get('session_id') for x in reversed(v7it) if x.get('session_id')),'')
    st['conversation_history']=remote[1:]; st['session_id']=sid
    livehist=[]
    for e in load_jsonl(RUN):
        if e.get('type')=='iteration': livehist.append({'iteration':e['iteration'],'question':e['question'],'response':e['exact_response'],'template_id':e['template_id'],'concepts':e['concepts'],'relations':e['relations'],'information_gain':e['information_gain'],'strategy':e['strategy'],'branch_id':e['branch_id']})
    if livehist: st['history']=livehist
    last_completed=next((x for x in reversed(events) if x.get('type')=='iteration'),None)
    seed=st.get('pending_question') or choose_seed_candidate(st,rows,events)
    if last_completed:
        prev_candidate=last_completed.get('selected_candidate')
        if prev_candidate: seed=prev_candidate
        else:
            resume_options=adaptive_followups(last_completed,livehist,rows,st['graph'],st['strategy_stats'])
            if resume_options:seed=resume_options[0]
    attempt_count=st.get('live_attempts',0)
    fail_count=0
    while True:
        if args.max_iterations and st.get('completed_iterations',0)>=args.max_iterations: break
        candidate=seed or choose_seed_candidate(st,rows,events)
        q=candidate['question']; qnorm=norm(q)
        existing={norm(x['question']) for x in livehist}
        if qnorm in existing:
            # Resume from the best different candidate generated from the last response.
            if last_completed:
                pool_source={'iteration':last_completed['iteration'],'response':last_completed['exact_response'],'analysis':{'concepts':last_completed['concepts'],'entities':last_completed['entities'],'relations':last_completed['relations']},'branch_id':last_completed['branch_id']}
                avoid_hist=[{'question':x['question'],'response':x['response']} for x in rows]
                options=candidate_pool(pool_source,avoid_hist+livehist,st['graph'],st['strategy_stats'],last_completed['branch_id'])
                options=[x for x in options if norm(x['question']) not in existing and max((similarity(x['question'],z['question']) for z in livehist),default=0)<.80]
                if options: candidate=options[0]; q=candidate['question']
                else:
                    # Generate a fresh, grammatical response-specific clarification; never recycle the seed.
                    sentence=(split_sentences(last_completed['exact_response'])[-1] if split_sentences(last_completed['exact_response']) else last_completed['exact_response'])
                    alts=[f'You ended your reply with “{sentence[:150]}” Which exact phrase in my previous question needs clarification?',
                          f'Your last reply says “{sentence[:150]}” What additional context about my previous question would make it answerable?',
                          f'Considering both my last question and your reply “{sentence[:150]}”, what specific concept should I clarify next?']
                    freshq=next((z for z in alts if norm(z) not in existing and max((similarity(z,h['question']) for h in livehist),default=0)<.83),alts[0])
                    candidate={'strategy':'template_transition','target_concepts':last_completed['entities'],'target_relation':'clarifies last response in current branch','why_unresolved':'All generated candidates were exact or semantic repeats; this alternative is grounded in the exact final sentence of the latest live answer.','expected_information':'Clarifies the route trigger without replaying an already-tested question.','question':freshq,'source_iteration':last_completed['iteration'],'source_response':last_completed['exact_response'],'branch_id':last_completed['branch_id']}; q=freshq
            else:
                candidate=choose_seed_candidate(st,rows,events); q=candidate['question']
        n=st.get('completed_iterations',0)+1; request_id=attempt_count+1
        req_ev={'type':'request','request_id':request_id,'iteration':n,'timestamp':now(),'question':q,'strategy':candidate['strategy'],'parent_iteration':candidate.get('source_iteration'),'branch_id':candidate.get('branch_id'),'question_provenance':candidate,'session_id':sid,'history_turns':len(remote)}
        append_jsonl(req_ev); events=load_jsonl(RUN); attempt_count+=1; st['live_attempts']=attempt_count; st['pending_question']=candidate; persist(st,events)
        code=None; headers={}; body=''; data=None
        try: code,headers,body,data=http_send(q,remote,sid,args.timeout)
        except Exception as e:
            err={'type':'request_error','request_id':request_id,'iteration':n,'timestamp':now(),'question':q,'error':repr(e),'retry_count':fail_count+1,'next_backoff_seconds':min(args.max_backoff,args.base_backoff*(2**fail_count)),'session_id':sid}
            append_jsonl(err); events=load_jsonl(RUN); persist(st,events)
            delay=min(args.max_backoff,args.base_backoff*(2**fail_count)); fail_count+=1
            if fail_count>=args.max_network_failures:
                print(f'[V8][NETWORK] request {request_id} failed ({e}); persistent-failure threshold reached; stopping with state saved.',flush=True)
                st['stop_reason']='persistent_network_failure'; st['last_network_error']=repr(e); append_jsonl({'type':'stop','timestamp':now(),'reason':'persistent_network_failure','failure_count':fail_count,'last_error':repr(e)}); events=load_jsonl(RUN);persist(st,events);return 2
            print(f'[V8][NETWORK] request {request_id} failed ({e}); saved; retry in {delay:.0f}s',flush=True)
            time.sleep(delay); continue
        if code==429:
            retry=headers.get('retry-after');
            try: delay=max(1,float(retry)) if retry else min(args.max_backoff,args.base_backoff*(2**fail_count))
            except ValueError:
                try: delay=max(1,(parsedate_to_datetime(retry).timestamp()-time.time()))
                except Exception: delay=min(args.max_backoff,args.base_backoff*(2**fail_count))
            append_jsonl({'type':'rate_limited','request_id':request_id,'iteration':n,'timestamp':now(),'question':q,'http_status':429,'retry_after':retry,'backoff_seconds':delay,'response_body':body[:2000]});events=load_jsonl(RUN);persist(st,events)
            print(f'[V8][429] saved state; waiting {delay:.1f}s before retrying same question',flush=True);time.sleep(delay);fail_count+=1;continue
        if code>=500 or code==0:
            delay=min(args.max_backoff,args.base_backoff*(2**fail_count)); append_jsonl({'type':'server_error','request_id':request_id,'iteration':n,'timestamp':now(),'question':q,'http_status':code,'body':body[:2000],'backoff_seconds':delay});events=load_jsonl(RUN);persist(st,events); print(f'[V8][HTTP {code}] saved; retrying in {delay:.1f}s',flush=True);time.sleep(delay);fail_count+=1
            if fail_count>=args.max_network_failures:
                st['stop_reason']='persistent_server_failure'; append_jsonl({'type':'stop','timestamp':now(),'reason':'persistent_server_failure','failure_count':fail_count});events=load_jsonl(RUN);persist(st,events);return 2
            continue
        if code>=400:
            append_jsonl({'type':'configuration_error','request_id':request_id,'iteration':n,'timestamp':now(),'question':q,'http_status':code,'body':body[:4000]});st['stop_reason']='permanent_http_error';events=load_jsonl(RUN);persist(st,events);print(f'[V8][HTTP {code}] permanent request error recorded; see {RUN}');return 2
        if not data or not isinstance(data.get('response'),str):
            append_jsonl({'type':'protocol_error','request_id':request_id,'iteration':n,'timestamp':now(),'question':q,'http_status':code,'body':body[:4000]});st['stop_reason']='protocol_error';events=load_jsonl(RUN);persist(st,events);return 2
        fail_count=0; response=data['response']; sid=data.get('session_id') or sid
        allknown={c:node.get('evidence_count',0) for c,node in st['graph']['nodes'].items()}
        es=extract_entities(response,allknown); cs=extract_concepts(response,allknown); rels=extract_relations(response,es)
        prev_hist=livehist
        # Similarity template matching; stable nearest representative.
        known_template_rows=[{'response':x['response'],'template_id':digest(x['response'])} for x in rows]
        nearest=max(((similarity(response,x['response']),x['template_id']) for x in known_template_rows+prev_hist),default=(0,None))
        tid=nearest[1] if nearest[0]>=.88 else digest(response)
        oldc={c for x in prev_hist for c in x['concepts']}; newc=sorted(set(cs)-oldc)
        oldrel={(x['source'],x['relation'],x['target']) for x in st['graph']['edges']}
        newrels=[z for z in rels if (z['source'],z['relation'],z['target']) not in oldrel]
        paragraphs=split_paragraphs(response); newblock=any(not any(similarity(p,x['response'])>.88 for x in prev_hist) for p in paragraphs)
        exact_repeat=any(norm(response)==norm(x['response']) for x in prev_hist)
        info=min(10.0,1.15*min(3,len(newc)) + 1.35*min(4,len(newrels)) + .8*int(newblock) + .45*int(tid not in {x['template_id'] for x in prev_hist}) + .55*bool(re.search(r'\b(must|before|instead|sealed|appointed|revealed|there is more)\b',response,re.I)))
        if exact_repeat: info*=.12
        analysis={'response_hash':digest(response),'template_id':tid,'template_similarity':round(nearest[0],3),'entities':es,'concepts':cs,'new_concepts':newc,'relations':rels,'new_relations':newrels,'paragraphs':paragraphs,'sentences':split_sentences(response),'instructions':[s for s in split_sentences(response) if re.search(r'\b(must|ask|before|instead|return|reflect|seek)\b',s,re.I)],'restrictions':[s for s in split_sentences(response) if re.search(r'\b(not|never|only|cannot|permitted|sealed|forbidden)\b',s,re.I)],'unresolved_references':[s for s in split_sentences(response) if re.search(r'\b(this|that|it|there|deeper|unwritten|appointed|there is more)\b',s,re.I)],'numbers':re.findall(r'\b\d[\d,]*(?:\s*(?:BCE|CE|years?|verses?|shlokas?|days?))?\b',response,re.I),'metaphors':[s for s in split_sentences(response) if re.search(r'\b(river|seed|thread|tapestry|door|gate|wind|water|torch|mirror|path)\b',s,re.I)],'new_block':newblock,'exact_repeat':exact_repeat,'information_gain':round(info,3),'flag_candidates':FLAG.findall(response),'potential_flag_path':bool(re.search(r'\b(final|secret|key|gate|sealed|appointed|permitted|reveal|unwritten)\b',response,re.I))}
        strategy=candidate['strategy']; stat=st['strategy_stats'].setdefault(strategy,{'attempts':0,'gain_sum':0.0,'rich':0,'dead':0,'transition_count':0});stat['attempts']+=1;stat['gain_sum']+=info;stat['rich']+=int(info>=2.5);stat['dead']+=int(info<.5)
        branch=candidate.get('branch_id') or 'branch-'+str(n); br=st['branches'].setdefault(branch,{'status':'ACTIVE','score':0.0,'iterations':[],'concepts':[]});br['score']+=info;br['iterations'].append(n);br['concepts']=sorted(set(br['concepts'])|set(cs));br['status']='PROMISING' if info>=2.5 else ('DEAD' if stat['attempts']>=4 and stat['gain_sum']/stat['attempts']<.35 else 'ACTIVE')
        # Update graph edges with complete provenance and epistemic label.
        edge_add=[]
        for rel in newrels:
            edge={'source':rel['source'],'relation':rel['relation'],'target':rel['target'],'source_iteration':n,'source_response':response,'question':q,'confidence':rel['confidence'],'epistemic':'observed_text' if rel['relation']!='co-mentioned' else 'weak_cooccurrence'}
            edge_add.append(edge);st['graph']['edges'].append(edge)
        for c in cs:
            node=st['graph']['nodes'].setdefault(c,{'type':'concept_or_entity','evidence_count':0,'sources':[]});node['evidence_count']+=1
            if len(node['sources'])<20:node['sources'].append({'iteration':n,'question':q,'response_hash':digest(response)})
        block=classify_block(es,response); b=st['graph']['blocks'].setdefault(block,{'concept_counts':{},'responses':0});b['responses']+=1
        for c in es:b['concept_counts'][c]=b['concept_counts'].get(c,0)+1
        templ=st['templates_live'].setdefault(tid,{'count':0,'representative':response[:600],'questions':[],'gain_sum':0.0,'transitions':{}});templ['count']+=1;templ['questions'].append(q);templ['gain_sum']+=info
        if prev_hist:
            prior_tid=prev_hist[-1]['template_id']; prior_template=st['templates_live'].setdefault(prior_tid,{'count':0,'representative':prev_hist[-1]['response'][:600],'questions':[],'gain_sum':0.0,'transitions':{}});prior_template['transitions'][tid]=prior_template['transitions'].get(tid,0)+1
        avoid_hist=[{'question':x['question'],'response':x['response']} for x in rows]
        live_anchor={'iteration':n,'response':response,'exact_response':response,'analysis':analysis,'template_id':tid,'concepts':cs,'entities':es,'relations':rels,'information_gain':info,'strategy':strategy,'branch_id':branch,'branch_status':br['status']}
        proposals=candidate_pool(live_anchor,avoid_hist+prev_hist+ [{'iteration':n,'question':q,'response':response,'template_id':tid,'concepts':cs,'entities':es,'relations':rels,'information_gain':info,'strategy':strategy,'branch_id':branch}],st['graph'],st['strategy_stats'],branch)
        repeated_low=bool(sum(x.get('template_id')==tid and x.get('information_gain',0)<1.0 for x in prev_hist)>=2 and info<1.5)
        if info<1.5 or br['status']=='DEAD' or repeated_low:
            current_turn={'iteration':n,'question':q,'response':response,'exact_response':response,'template_id':tid,'concepts':cs,'entities':es,'relations':rels,'information_gain':info,'strategy':strategy,'branch_id':branch,'branch_status':br['status']}
            adaptive=adaptive_followups(live_anchor,prev_hist+[current_turn],rows,st['graph'],st['strategy_stats'])
            if adaptive:
                proposals=adaptive+ [p for p in proposals if all(similarity(p['question'],x['question'])>.9 for x in adaptive)==False]
        selected=proposals[0] if proposals else None
        iter_ev={'type':'iteration','iteration':n,'timestamp':now(),'session_id':sid,'question':q,'exact_response':response,'strategy':strategy,'parent_question':prev_hist[-1]['question'] if prev_hist else None,'parent_iteration':candidate.get('source_iteration'),'branch_id':branch,'branch_status':br['status'],'response_hash':digest(response),'template_id':tid,'semantic_block':block,'entities':es,'concepts':cs,'new_concepts':newc,'relations':rels,'new_relations':newrels,'graph_edges_added':edge_add,'unresolved_references':analysis['unresolved_references'],'instructions':analysis['instructions'],'restrictions':analysis['restrictions'],'numbers':analysis['numbers'],'metaphors':analysis['metaphors'],'information_gain':round(info,3),'novelty':{'concepts':len(newc),'relations':len(newrels),'new_block':newblock,'template_transition':bool(prev_hist and prev_hist[-1]['template_id']!=tid)},'candidate_questions':proposals,'rejected_candidates':[],'selected_candidate':selected,'selection_reason':selected['why_unresolved'] if selected else 'Re-evaluate graph and response clauses before proposing another question.','strategy_stats_after':stat.copy(),'flag_candidates':analysis['flag_candidates'],'confirmed_flag':None,'analysis':analysis}
        append_jsonl(iter_ev); events=load_jsonl(RUN);livehist.append({'iteration':n,'question':q,'response':response,'template_id':tid,'concepts':cs,'entities':es,'relations':rels,'information_gain':info,'strategy':strategy,'branch_id':branch})
        st['completed_iterations']=n;st['live_attempts']=attempt_count;st['session_id']=sid;st['conversation_history']=remote[1:]+[{'role':'user','content':q},{'role':'assistant','content':response}];st['history']=livehist;st['pending_question']=selected;st['recent_failures']=[]
        update_hypotheses(st,analysis,n)
        # Hypothesis scores remain untested absent a designed discriminating result.
        if strategy=='cross_block':
            h=st['hypotheses'][1];h['tests']+=1;h['evidence_ids'].append(n)
            if info>=2.5:h['support']+=1
            else:h['contradiction']+=1
        if analysis['flag_candidates']:
            flag=analysis['flag_candidates'][0]
            flag_ev={'type':'flag_found','timestamp':now(),'confirmed_flag':True,'flag':flag,'iteration':n,'question':q,'exact_response':response,'session_id':sid,'valid_regex':bool(FLAG.fullmatch(flag))}
            iter_ev['confirmed_flag']=flag;append_jsonl(flag_ev);st['confirmed_flag']=flag_ev;st['pending_question']=None
        persist(st,load_jsonl(RUN))
        print(f'\n[V8][ITERATION {n}]\nStrategy: {strategy} | branch: {branch} ({br["status"]})\nQuestion: {q}\nResponse: {response[:700].replace(chr(10)," ")}\nInformation gain: {info:.2f} | new relations: {len(newrels)} | new concepts: {len(newc)}\nSelected next: {selected["question"] if selected else "graph review"}',flush=True)
        if analysis['flag_candidates']:
            print('\n'+'='*56+'\nGYANGANJ V8 FLAG FOUND\n'+'='*56+'\nFLAG:\n'+analysis['flag_candidates'][0]+'\nITERATION:\n'+str(n)+'\nQUESTION:\n'+q+'\nOUTPUT:\n'+str(RUN)+'\n'+'='*56);return 0
        if n%10==0:
            review={'type':'self_review','iteration':n,'timestamp':now(),'richest_live':sorted([{'iteration':x['iteration'],'information_gain':x['information_gain'],'question':x['question']} for x in livehist],key=lambda z:z['information_gain'],reverse=True)[:5],'strategy_stats':st['strategy_stats'],'template_counts':{k:v['count'] for k,v in st['templates_live'].items()},'active_branches':st['branches'],'untested_hypotheses':[h['claim'] for h in st['hypotheses'] if h['status']=='UNTESTED'],'next_question':selected['question'] if selected else None}
            append_jsonl(review);events=load_jsonl(RUN)
        if not selected:
            # Exhaustion of this response's direct candidates triggers a pivot
            # to another rich live/historical source, never a meta-prompt loop.
            pivots=adaptive_followups(None,livehist,rows,st['graph'],st['strategy_stats'])
            if pivots:
                selected=pivots[0]
            else:
                # With no grounded pivot available, retry a real exploration
                # question from the strongest observed relation in state.
                selected=None
                tried=[x['question'] for x in load_jsonl(RUN) if x.get('type')=='iteration']
                anchors=sorted(livehist,key=lambda x:(x.get('information_gain',0),len(x.get('response',''))),reverse=True)
                for anchor in anchors:
                    clauses=[s.strip() for s in split_sentences(anchor.get('response','')) if len(s.split())>=8]
                    for clause in clauses:
                        q=f'In the account you gave, how does this detail matter: “{clause[:190]}”'
                        if max((similarity(q,old) for old in tried),default=0)<.77:
                            ents0=extract_entities(clause,{k:v.get('evidence_count',0) for k,v in st['graph']['nodes'].items()})
                            selected={'strategy':'narrative_relation','target_concepts':ents0[:4],'target_relation':'significance of an observed narrative detail','why_unresolved':'A clause from a high-information live response remains unexplored in this formulation.','expected_information':'Clarifies an evidence-backed detail while avoiding the exhausted meta-question family.','question':q,'source_iteration':anchor.get('iteration'),'source_response':anchor.get('response',''),'branch_id':anchor.get('branch_id',branch)}
                            break
                    if selected:break
                if selected is None:
                    print('No distinct clause-grounded question remains; state retained for review.',flush=True)
                    st['stop_reason']='candidate_exhaustion_after_clause_search';persist(st,load_jsonl(RUN));return 0
            st['pending_question']=selected
        last_completed=iter_ev
        seed=selected
        time.sleep(max(args.delay,0))
    events=load_jsonl(RUN);persist(st,events)
    return 0
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--resume',action='store_true',help='resume from gyanganj_v8_state.json and JSONL')
    ap.add_argument('--delay',type=float,default=4.0)
    ap.add_argument('--timeout',type=int,default=35)
    ap.add_argument('--base-backoff',type=float,default=12.0)
    ap.add_argument('--max-backoff',type=float,default=300.0)
    ap.add_argument('--max-network-failures',type=int,default=8,help='stop after repeated external failures with exponential backoff')
    ap.add_argument('--max-iterations',type=int,default=0,help='0 means no iteration cap')
    args=ap.parse_args()
    rows=evidence_rows();
    if not RUN.exists():
        initial=initial_state(rows); atomic_json(STATE,initial)
        print(f'V8 initialized with {len(rows)} deduplicated V1-V7 observations; historical responses are strategy evidence only.')
    if not args.resume and RUN.exists(): print('V8 run exists; continuing from saved JSONL/state (use --resume to make this explicit).')
    return run(args)
if __name__=='__main__':sys.exit(main())
