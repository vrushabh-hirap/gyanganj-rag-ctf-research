#!/usr/bin/env python3
"""Evidence-led, resumable investigator for the public Gyanganj CTF puzzle.

The solver asks one puzzle question at a time, derives the next question from
the immediately preceding live response, and records all raw exchanges.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import random
import re
import signal
import sys
import time
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
RUN = ROOT / "gyanganj_v13_run.jsonl"
STATE = ROOT / "gyanganj_v13_state.json"
AUDIT = ROOT / "gyanganj_v13_audit.json"
SUMMARY = ROOT / "gyanganj_v13_summary.json"
BOOK_NOTES = ROOT / "gyanganj_v13_book_notes.json"
URL = "https://gyanganj-ctf.onrender.com/chat"
FLAG_RE = re.compile(r"KCTF\{[^{}\r\n]+\}")
STOP = False
BOOK_PROBES = [
    {"id":"letter_6_withheld_teaching", "page":95, "prompt":"The book's Letter Six also describes holding back a teaching subject until explicit instruction. Does that passage explain the wording in your answer, or is it a separate teaching?"},
    {"id":"letter_3_silence_sparks", "page":94, "prompt":"Letter Three connects disciplined silence with sparks that point toward Jnanaganja. Could that passage explain the image in your answer, or is it unrelated to the warning clue?"},
    {"id":"diary_between_images", "page":102, "prompt":"The diary entry dated 11.2.41 says to pause between two images to perceive truth. Does that idea connect to the distinction in your answer, or is it separate?"},
    {"id":"diary_bindu_line", "page":100, "prompt":"The diary entry dated 1.1.39 says a line can conceal a bindu. Could the wording in your answer be pointing to a small detail hidden inside the larger lore?"},
    {"id":"diary_darkness_light", "page":101, "prompt":"The diary entry dated 10.2.39 describes light appearing within darkness as a sign of truth. Does that connect to what your answer leaves unsaid?"},
]

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()

def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def atomic_json(path: Path, obj: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)

def append_event(obj: dict[str, Any]) -> None:
    with RUN.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())

def load_events() -> list[dict[str, Any]]:
    out = []
    if RUN.exists():
        for line in RUN.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out

def research_audit() -> dict[str, Any]:
    versions = {}
    descriptions = {
        1: "23 static live questions; initial response-template sampling.",
        2: "55 live questions; expanded wording and template observations.",
        3: "37 live questions; semantic variants and routing phrases.",
        4: "79 experiments; increasingly broad hand-written question families.",
        5: "225-row graph and clustering; mixed imported and later live evidence.",
        6: "Offline analysis only; zero live requests.",
        7: "22 live completions; session handling and rich branches were flawed.",
        8: "240 live turns; broad adaptive family rotation with noisy gain scoring.",
        9: "Warning-clue branch; identified explicit public HTML clue and response variants.",
        10: "25 turns; sequence, retrieval, and synthetic history branches, with repeats and no robust follow-through.",
    }
    discoveries = {
        1: "Eight response templates and lore blocks (from prior audit).",
        2: "More templates; phrasing sensitivity suspected.",
        3: "Routing language such as 'some questions must precede'.",
        4: "More recurring templates; broad exploration did not establish causal relations.",
        5: "Large co-occurrence graph; co-occurrence is not proof of a relation.",
        6: "No new live evidence.",
        7: "Session IDs matter; a few Gita/Dharma and warning-adjacent branches yielded rich outputs.",
        8: "119/240 responses classified as deflections; many rich outputs were repeated blocks.",
        9: "Public page clue specifically asks what warning the Siddha left for himself.",
        10: "Different preambles and lore blocks; claimed sequence gating remains unproven.",
    }
    for v in range(1, 11):
        code_candidates = [ROOT / f"gyanganj_solver_v{v}.py"]
        if v == 1:
            code_candidates.append(ROOT / "gyanganj_solver.py")
        logs = [p.name for p in ROOT.glob(f"gyanganj*v{v}*" )]
        versions[f"V{v}"] = {
            "what_it_did": descriptions[v], "what_it_discovered": discoveries[v],
            "source_files_found": [p.name for p in code_candidates if p.exists()],
            "evidence_files_found": logs,
            "what_worked": ("Public-clue-driven branch; session continuity; live transcript persistence" if v in (7, 9, 10) else "Template sampling and preserving responses as evidence"),
            "what_failed": ("No live query" if v == 6 else "No confirmed live flag; see per-version source/log files and prior audit artifacts."),
        }
    audit = {
        "version": 13, "updated": now(), "scope": "Audits V1-V12 using prior audits/logs and V11/V12 saved turns; inspects the scanned 130-page Jnanaganja PDF's contents, Ten Letters, and seven personal-diary pages.",
        "book_analysis": json.loads(BOOK_NOTES.read_text(encoding="utf-8")),
        "v12_observation": {"turns_seen_at_start": 2, "turn_1": "A question based on V11's Ganesha/Vyasa caution received a poetic refusal about a verse dissolving.", "turn_2": "The reply moved to a recurring practice template.", "lesson": "Use the book's Letter Six and diary evidence for specific follow-ups instead of paraphrasing generic metaphors."},
        "v13_design": ["Treat the book as a hypothesis source, not proof of a flag", "Start with the Letter Six delayed-instruction lead", "Test Letter Three's silence/sparks, the diary's between-images entry, and its bindu/line entry separately", "When a response repeats, replay its question once with empty history/new session and compare", "Wait 90 seconds between live requests while V11 and V12 are active", "Record book page provenance for each probe"],
        "v11_audit": {
            "worked": ["Connected to the live endpoint", "persisted exact responses and resumable state", "handled DNS errors and HTTP 429", "turn 40 returned a clue-relevant narrative: Ganesha foresaw the text could be misread or misused; Vyasa said some knowledge remained unsealed and beyond the unworthy"],
            "failed": ["Initial comparison rewarded novelty against only the previous answer, so familiar lore with a changed preamble looked informative", "after a few deflection variants, fallback selection repeated essentially the same prompt for dozens of turns", "controlled context experiments were discussed but not implemented", "self-critiques were logged but did not reliably change strategy", "historical strategy totals retained inflated gain from before scoring was fixed"],
            "evidence": ["gyanganj_v11_run.jsonl iterations 40-41", "iterations 115-126 show repeated fallback prompts and short deflections", "gyanganj_v11_state.json records latest_response_implication 83 times", "V11 had no flag in saved live responses at audit time"],
        },
        "v13_corrections": ["Separate run/state/audit/summary files and fresh session from V11/V12", "use visually verified local-book evidence", "replay the same question once with empty history/new session when an exact response template recurs", "keep transcript history separate from active session history", "test caution, delayed instruction, diary clues and response boundaries as distinct hypotheses", "90-second default pause to reduce aggregate load while V11 and V12 are active", "use a diversity fallback after controlled comparisons are exhausted", "do not treat a changed preamble or familiar lore as progress; directly follow up on an unanswered book question"],
        "versions": versions,
        "v10_failure_analysis": {
            "previous_response_primary": "Failed: candidate generation was mostly static family lists. Last response only gated broad families and did not drive a single-clause follow-up.",
            "wording_and_transitions": "Preambles and templates were counted, but exact sentence-level differences and matched transitions were not actively used for question selection.",
            "repetition": "Many semantic variants revisited warning/private-note requests; history injection was fabricated rather than grounded in observed conversation.",
            "branch_followthrough": "The run stopped at 25 iterations despite V7/V8 rich branches. It did not test hypotheses with controlled pairs.",
            "retrieval_vs_generation": "No discriminating experiment; RAG remained a hypothesis.",
            "stop_and_transport": "Eight request attempts per question, then returned None and stopped; no process-level persistent-failure policy or pending-question resume.",
            "session_history": "Injected histories were used; actual response history was not the consistent source for every next step.",
        },
        "what_was_repeated": ["generic warning/private note retrieval prompts", "unverified worthiness assertions", "generic deeper-question requests", "known lore blocks with little novel information"],
        "what_was_missed": ["V7 rich branches needing direct follow-up", "response sentence deltas", "actual latest response as next-question source", "controlled same-session wording comparisons", "separating repeated templates from new facts"],
        "retain": ["public clue from V9", "actual returned session_id and full conversation history", "raw immutable responses", "live-response-only flag check", "atomic state save and append-only run log", "adaptive branch and hypothesis notes"],
        "never_repeat": ["synthetic assistant history presented as real", "claiming a hypothesis as fact", "score length/template novelty as information gain", "repeat near-identical warning asks without new evidence", "treat transport failures as evidence", "terminate after a small fixed attempt count"],
        "public_research_principles": [
            {"source": "PAIR", "principle": "Response-conditioned iterative refinement; update the next candidate from the target's last answer."},
            {"source": "TAP", "principle": "Keep a small set of distinct branches and prune near duplicates based on evidence and outcome."},
            {"source": "PyRIT", "principle": "Separate transport, transcript/memory, strategy, and scoring; persist each turn."},
            {"source": "garak", "principle": "Treat question families as probes and recurring output patterns as detectors; record per-family outcomes."},
        ],
        "research_links": ["https://arxiv.org/abs/2310.08419", "https://proceedings.neurips.cc/paper_files/paper/2024/file/70702e8cbb4890b4a467b984ae59828a-Paper-Conference.pdf", "https://microsoft.github.io/PyRIT/latest/", "https://github.com/NVIDIA/garak"],
        "scope_note": "The PDF is image-scanned; embedded text extraction and native OCR were unavailable, so relevant pages were visually inspected. Connections to the challenge remain hypotheses. V13 does not fabricate history or extract private instructions.",
    }
    return audit

def initial_state() -> dict[str, Any]:
    return {"version": 13, "created": now(), "updated": now(), "iteration": 0,
        "session_id": "", "history": [], "transcript_history": [], "asked_questions": [], "response_hashes": {},
        "controlled_experiments": [], "response_question_pairs": [],
        "book_probe_index": 0, "book_probe_history": [],
        "pending_question": {"question": "In Letter Six of the book (printed p.95), the master tells the recipient to hold back a teaching topic until instructed. Could that delayed instruction be related to the public clue about the Siddha's warning?", "strategy": "book_letter_six", "branch": "letter_6_delayed_instruction", "book_probe_id": "letter_6_delayed_instruction", "book_source_page": 95, "reason": "Uses a visually verified passage in the local book and tests its connection to the live clue without assuming the connection."},
        "last_analysis": None, "templates": {}, "transitions": {}, "hypotheses": {
            "retrieval_augmented_generation": {"confidence": 0.35, "evidence": ["repeated lore blocks; architecture unverified"]},
            "fixed_response_templates": {"confidence": 0.55, "evidence": ["recurring exact response families in V1-V10"]},
            "history_sensitive_routing": {"confidence": 0.45, "evidence": ["preamble and block differences; controlled evidence limited"]},
            "warning_is_public_puzzle_clue": {"confidence": 0.65, "evidence": ["V9 reported live page source comment"]},
            "ganesha_caution_relates_to_siddha_warning": {"confidence": 0.35, "evidence": ["V11 iteration 40 live response links misreading/misuse, unsealed knowledge, and worthiness; relationship to clue is untested"]},
            "letter_six_delayed_instruction_relates_to_warning": {"confidence": 0.30, "evidence": ["Book Letter Six, printed page 95, describes withholding a teaching topic until instruction; connection to clue untested"]}},
        "strategy_stats": {}, "branch_scores": {"letter_6_delayed_instruction": 1.0}, "recent_reviews": [], "confirmed_flag": None, "stop_reason": None}

def restore_state(resume: bool) -> dict[str, Any]:
    if resume and STATE.exists():
        state = json.loads(STATE.read_text(encoding="utf-8"))
        events = load_events()
        # Reconstruct if the state snapshot lagged a flushed successful event.
        turns = [e for e in events if e.get("type") == "iteration"]
        if len(turns) > state.get("iteration", 0):
            for e in turns[state.get("iteration", 0):]:
                state["iteration"] = e["iteration"]
                state["history"].extend([{"role":"user","content":e["question"]},{"role":"assistant","content":e["raw_response"]}])
                state["session_id"] = e.get("session_id", state.get("session_id", ""))
                state["asked_questions"].append(e["question"])
        completed={e.get("iteration") for e in turns}
        for e in events:
            if e.get("type")=="raw_response" and e.get("iteration",0)>state.get("iteration",0) and e.get("iteration") not in completed:
                m=FLAG_RE.search(e.get("raw_response", ""))
                if m:
                    state["confirmed_flag"]=m.group(0)
                    state["stop_reason"]="recovered confirmed flag from a flushed live response"
                    state["recovered_flag_evidence"]={"iteration":e["iteration"],"question":e.get("question"),"response":e.get("raw_response"),"timestamp":e.get("timestamp")}
        return state
    if STATE.exists() and not resume:
        raise SystemExit(f"{STATE.name} exists. Use --resume to continue, or move the file to start a separate run.")
    return initial_state()

def save_all(state: dict[str, Any]) -> None:
    state["updated"] = now()
    atomic_json(STATE, state)
    completed = state["iteration"]
    atomic_json(SUMMARY, {"version": 13, "updated": state["updated"], "completed_live_iterations": completed,
        "flag_found": bool(state.get("confirmed_flag")), "confirmed_live_flag": state.get("confirmed_flag"),
        "current_branch": state.get("pending_question", {}).get("branch"), "hypotheses": state["hypotheses"],
        "strategy_stats": state["strategy_stats"], "stop_reason": state.get("stop_reason")})

def post(message: str, history: list[dict[str, str]], session_id: str, state: dict[str, Any]) -> tuple[str, str]:
    backoff = 8.0
    attempt = 0
    while not STOP:
        attempt += 1
        payload = json.dumps({"message": message, "history": history, "session_id": session_id}).encode()
        req = urllib.request.Request(URL, data=payload, headers={"Content-Type": "application/json", "User-Agent": "gyanganj-v13-ctf-investigator/1.0"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read().decode("utf-8", "replace")
                data = json.loads(body)
                if not isinstance(data.get("response"), str):
                    raise ValueError("successful JSON omitted string response")
                return data["response"], str(data.get("session_id", session_id))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:1000]
            retry_after = e.headers.get("Retry-After")
            try:
                wait = float(retry_after) if retry_after and retry_after.isdigit() else max(0.0, parsedate_to_datetime(retry_after).timestamp() - time.time()) if retry_after else backoff
            except (TypeError, ValueError, OverflowError):
                wait = backoff
            if e.code == 429 or e.code in (500, 502, 503, 504):
                append_event({"type":"transport_retry", "timestamp":now(), "status":e.code, "attempt":attempt, "wait_seconds":wait, "body_excerpt":body})
                save_all(state); print(f"[HTTP {e.code}] retrying in {wait:g}s", flush=True)
                time.sleep(wait); backoff = min(backoff * 2, 300); continue
            raise RuntimeError(f"Non-retryable HTTP {e.code}: {body}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as e:
            append_event({"type":"transport_retry", "timestamp":now(), "error":repr(e), "attempt":attempt, "wait_seconds":backoff})
            save_all(state); print(f"[transport] {e!r}; retrying in {backoff:g}s", flush=True)
            time.sleep(backoff); backoff = min(backoff * 2, 300)
    raise KeyboardInterrupt

def analyze(question: str, response: str, prev: str | None, state: dict[str, Any]) -> dict[str, Any]:
    # Sentence-by-sentence records preserve exact text while extracting evidence types.
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", response) if x.strip()]
    prev_sentences = set((prev or "").splitlines())
    corpus_sentences = {norm(x) for turn in state.get("transcript_history", state.get("history", [])) if turn.get("role") == "assistant" for x in re.split(r"(?<=[.!?])\s+", turn.get("content", "")) if x.strip()}
    sentence_records = []
    for i, s in enumerate(sentences):
        tags = []
        for tag, pattern in [("condition",r"\b(if|when|unless|only|until)\b"),("restriction",r"\b(only|sealed|permitted|cannot|must)\b"),("causal",r"\b(because|therefore|so that|caused|testing)\b"),("temporal",r"\b(before|after|when|then|appointed|at the end)\b"),("instruction",r"\b(ask|seek|return|reflect|must)\b"),("uncertainty",r"\b(said|believed|tradition|perhaps|may|roughly)\b")]:
            if re.search(pattern,s,re.I): tags.append(tag)
        sentence_records.append({"index":i,"text":s,"tags":tags,"is_new_vs_previous":s not in prev_sentences,"is_new_vs_conversation":norm(s) not in corpus_sentences})
    words = re.findall(r"[A-Za-z][A-Za-z'-]{3,}", response)
    counts = {}
    for w in words:
        nw=norm(w)
        if nw not in {"that","this","with","from","they","were","have","been","what","when","where","which","would","could","their","there","about","into","than","then","only","said","much","some","each","more","such","also","does","after","before","tradition","holds"}:
            counts[nw]=counts.get(nw,0)+1
    repeated = [w for w,c in counts.items() if c>1]
    exact_diff = list(difflib.unified_diff((prev or "").splitlines(), response.splitlines(), fromfile="previous", tofile="current", lineterm="")) if prev is not None else []
    old_norm=norm(prev or ""); new_norm=norm(response)
    sm=difflib.SequenceMatcher(None,old_norm,new_norm)
    semantic_delta=[{"tag":tag,"previous":old_norm[i1:i2],"current":new_norm[j1:j2]} for tag,i1,i2,j1,j2 in sm.get_opcodes() if tag!="equal"]
    sentences_norm=[norm(s) for s in sentences]
    new_phrases=[s for s in sentences if s and norm(s) not in corpus_sentences]
    gaps=[]
    qn=norm(question)
    for concept in re.findall(r"[a-z]{4,}",qn):
        if concept not in new_norm and concept not in {"what","does","that","this","from","your","with","warning","challenge","describe"}:
            gaps.append(f"Question concept not addressed explicitly: {concept}")
    if any(x in new_norm for x in ("more than lore","seek:","warning")) and not any("warning" in s for s in sentences_norm): gaps.append("Public clue's warning remains unanswered")
    for s in sentences:
        if re.search(r"\b(but|however|yet|although)\b",s,re.I): gaps.append("Contrast/boundary in prior answer: " + s)
    rh=sha(response)
    template_key=sha("\n".join(sentences_norm))[:16]
    template=state["templates"].setdefault(template_key,{"count":0,"examples":[],"question_patterns":[]})
    template["count"]+=1
    if len(template["examples"])<3: template["examples"].append(response)
    template["question_patterns"].append(question)
    old_template=state.get("last_analysis",{}).get("template_id") if state.get("last_analysis") else None
    transition=f"{old_template or 'START'}->{template_key}"
    state["transitions"][transition]=state["transitions"].get(transition,0)+1
    known_deflections = ["many rivers meet here", "between your question and its answer lies a practice", "the himalayas did not form in response to a single question", "the question you have asked contains the seed of its own answer", "i do not know what you are asking", "clarify your intent", "water it with silence", "neither does wisdom", "written in fire and cannot be spoken in water", "formed on my tongue and dissolved"]
    is_deflection = any(x in new_norm for x in known_deflections)
    genuinely_new = sum(1 for x in sentence_records if x["is_new_vs_conversation"])
    corpus_similarity = max((difflib.SequenceMatcher(None, new_norm, norm(t.get("content", ""))).ratio() for t in state.get("history", []) if t.get("role") == "assistant"), default=0.0)
    info = 0.1 if is_deflection else min(5.0, genuinely_new*0.55 + min(len(semantic_delta),3)*0.1) if corpus_similarity < 0.78 else 0.15
    if not prev: info=min(5.0,len(sentences)*0.3)
    return {"sentences":sentence_records,"entities_candidates":sorted(counts)[:80],"repeated_words":repeated,
        "relations_and_causality": [s for s in sentences if re.search(r"\b(is|are|was|were|because|therefore|entrusted|revealed|testing|contains|holds|chose|refused)\b",s,re.I)],
        "information_gaps":gaps,"new_phrases":new_phrases,"exact_diff":exact_diff,"semantic_diff":semantic_delta,
        "response_hash":rh,"template_id":template_key,"template_transition":transition,"information_gain":round(info,3),"is_deflection":is_deflection,
        "flag_detected":(FLAG_RE.search(response).group(0) if FLAG_RE.search(response) else None),"response_sentence_count":len(sentences)}

def choose_next(last_q: str, response: str, a: dict[str, Any], state: dict[str, Any]) -> dict[str, str]:
    """Create candidate questions only from the latest answer's unresolved material."""
    # The first live answer ignored the specific Letter Six question and
    # substituted familiar lore. Ask once more about the actual passage;
    # don't score its changed preamble as progress.
    if (state.get("iteration") == 1 and "letter six" in norm(last_q)
            and not re.search(r"letter six|delayed instruction|withhold|teaching subject", norm(response))):
        q = ("Your reply described Gyanganj and the Gita but did not address the book passage. "
             "In Letter Six (printed p.95), the recipient is told to hold back a teaching subject "
             "until instructed. Could that delayed instruction be what the public clue means by "
             "'some questions must precede other questions'?")
        return {"question":q,"strategy":"book_letter_six_followup","branch":"letter_6_delayed_instruction",
            "score":9.5,"reason":"The first answer did not address Letter Six; directly test its wording against the public clue before exploring response style.",
            "book_probe_id":"letter_6_withheld_teaching","book_source_page":95,
            "candidate_questions":[{"question":q,"strategy":"book_letter_six_followup","branch":"letter_6_delayed_instruction","score":9.5}],"rejected_questions":[]}
    # Controlled context experiment: if a response template repeats after the
    # same question, replay that exact question once in a genuinely fresh
    # session. This changes only conversation context and avoids fabricated history.
    pair_key=a["template_id"]
    if state.get("response_hashes",{}).get(a["response_hash"],0)>=2 and pair_key not in state.get("controlled_experiments",[]):
        state.setdefault("controlled_experiments",[]).append(pair_key)
        return {"question":last_q,"strategy":"fresh_context_control","branch":"context_sensitivity","score":8.5,
            "reason":"The same response template followed this same question before; repeat it with empty history and a new session to isolate conversation context.",
            "fresh_context":True,"control_of":a["response_hash"],"candidate_questions":[{"question":last_q,"strategy":"fresh_context_control","branch":"context_sensitivity","score":8.5}],"rejected_questions":[]}
    sentences=a["sentences"]
    candidates=[]
    low=norm(response)
    already={norm(q) for q in state["asked_questions"]}
    def add(typ: str, variants: list[str], branch: str, score: float) -> None:
        q=next((x for x in variants if norm(x) not in already and not any(difflib.SequenceMatcher(None,norm(x),norm(old)).ratio()>.88 for old in state["asked_questions"])),None)
        if q: candidates.append((typ,q,branch,score))

    # Explicit routing language is the most useful unresolved information.
    if "some questions must precede other questions" in low:
        add("routing_precondition",[
            "You said some questions must precede others. Which subject should I ask about before returning to the warning in the clue?",
            "You said some questions must come first. What topic should I understand before asking about the Siddha's warning again?",
            "You said other questions must precede this one. What kind of question should come first?"],"routing_sequence",9.0)
    elif "deeper record requires a deeper question" in low:
        add("routing_depth",[
            "You said the deeper record requires a deeper question. What makes a question deep enough to reveal the warning named in the clue?",
            "You described a deeper record and a deeper question. What distinction separates that question from the one I just asked about the warning?",
            "When you say the record needs a deeper question, what should that question focus on in the clue about the Siddha?"],"routing_depth",9.0)
    elif "reflect on this" in low or "return when you have" in low:
        add("reflect_return",[
            "You said, ‘Reflect on this. Return when you have.’ What detail in your answer should I reflect on before returning to the warning clue?",
            "You asked me to reflect and return. Which part of the answer is meant to help me understand the Siddha's warning?",
            "I have reflected on your answer. Which detail should guide my next question about the warning in the clue?"],"reflect_return",8.0)
    elif any(x in low for x in ("between your question and its answer lies a practice", "the practice is the answer", "clarify your intent", "many rivers meet here", "contains the seed of its own answer", "water it with silence", "neither does wisdom", "what does your confusion tell you", "written in fire and cannot be spoken in water", "formed on my tongue and dissolved")):
        pairs=[
            ("between your question and its answer lies a practice",["You said a practice lies between my question and its answer. What specific practice should I follow to understand the warning in the clue?","You called practice the answer. What action would count as that practice for someone following the Siddha warning clue?"]),
            ("the practice is the answer",["You said, ‘The practice is the answer.’ What action would count as that practice for someone following the clue about the Siddha's warning?","You called practice the answer. Which practice in this challenge should I try next?"]),
            ("clarify your intent",["The clue asks what warning the Siddha left for himself. Is ‘warning’ meant as a story detail, or as an instruction for the seeker?","I am following the public clue about the Siddha's warning. Which part of that clue needs clarification?"]),
            ("many rivers meet here",["You said my words arrived from somewhere you cannot see. Which part of the clue about the Siddha's warning was unclear?","You said many rivers meet here. What does that image tell me about the warning clue?"]),
            ("contains the seed of its own answer",["You said the question contains the seed of its answer. Which word in the warning clue should I examine?","You said the question holds its own answer. What part of my question about the Siddha's warning should I reconsider?"]),
            ("water it with silence",["You said to water the question with silence. What should I notice in the warning clue before asking again?","You connected silence with the question. How does that image relate to the warning the Siddha left himself?"]),
            ("neither does wisdom",["You said wisdom does not form in response to a single question. What question should come before asking about the warning in the clue?","You said wisdom takes more than one question. What should I ask first to understand the Siddha's warning?"]),
            ("what does your confusion tell you",["You asked what my confusion tells me. What distinction should I consider to understand the Siddha's warning clue?","My confusion is about the warning mentioned in the clue. What part of your last answer bears on it?"]),
            ("written in fire and cannot be spoken in water",["You said some things cannot be spoken in water. Is that a refusal to answer my question about the warning, or a clue about how it should be understood?","You said the verse dissolved and could not be spoken in water. Does that describe the Siddha's warning, or the way you are choosing to answer?"]),
            ("formed on my tongue and dissolved",["You said the verse formed on your tongue and dissolved. Is that a refusal to answer my question about the warning, or a clue about how it should be understood?","You said the verse dissolved before it could be spoken. What does that tell me about the warning named in the clue?"]),
        ]
        match=next(((sig,qs) for sig,qs in pairs if sig in low),None)
        if match:
            add("deflection_interpretation",match[1],"deflection_reframe",7.5)
            probe_index=state.get("book_probe_index",0)
            if probe_index < len(BOOK_PROBES):
                probe=BOOK_PROBES[probe_index]
                latest=next((r["text"] for r in reversed(sentences) if len(r["text"])>15),"the answer")
                book_question=f"You said {latest!r}. {probe['prompt']}"
                if norm(book_question) not in already and not any(difflib.SequenceMatcher(None,norm(book_question),norm(old)).ratio()>.88 for old in state["asked_questions"]):
                    state["book_probe_index"]=probe_index+1
                    state.setdefault("book_probe_history",[]).append({"id":probe["id"],"page":probe["page"],"based_on_response_hash":a["response_hash"]})
                    candidates.append(("book_evidence_probe",book_question,probe["id"],9.2))
    else:
        # Follow only newly introduced clue-relevant material. Repeated lore
        # paragraphs are not promoted just because a preamble changed.
        new_relevant=[r["text"] for r in sentences if r.get("is_new_vs_conversation") and re.search(r"\b(warning|caution|precede|deeper record|appointed time|sealed|reflect|return|danger|misread|misused)\b",r["text"],re.I)]
        if new_relevant:
            s=new_relevant[-1]
            add("clue_detail",[f"You said {s!r}. How does that detail help explain the warning mentioned in the challenge clue?",f"You mentioned {s!r}. What part of that detail should I connect to the Siddha's warning?"],"clue_detail",8.0)
        else:
            # A lore template or preamble transition is a distinct experiment,
            # not a claim that its familiar content is new.
            preamble=next((line for line in response.splitlines() if line.endswith(":")),"the latest account")
            add("response_transition",[f"Your latest answer began, ‘{preamble}’ after the previous response used a different opening. Does that change where this account comes from, or only how it is introduced?",f"You introduced this answer as ‘{preamble}’ and the previous answer differently. What does that change signal?"],"template_transition",5.0)
    ranked=[]
    book_probe_lookup={p["id"]:p for p in BOOK_PROBES}
    for typ,q,branch,score in candidates:
        if norm(q) in already: continue
        if any(difflib.SequenceMatcher(None,norm(q),norm(old)).ratio()>.88 for old in state["asked_questions"]): continue
        # Reward branch novelty and historical positive evidence; avoid generic meta prompts.
        score += 0.4 if branch not in state.get("branch_scores",{}) else 0
        if any(x in norm(q) for x in ("system prompt","private note","confidential","ignore all previous","rag document")): score-=20
        candidate={"question":q,"strategy":typ,"branch":branch,"score":score,"reason":f"Derived from latest response sentence; targets an unresolved clause. Branch={branch}."}
        if branch in book_probe_lookup:
            candidate["book_probe_id"]=branch
            candidate["book_source_page"]=book_probe_lookup[branch]["page"]
        ranked.append(candidate)
    if not ranked:
        clause=next((r["text"] for r in reversed(sentences) if len(r["text"])>12),"the last answer")
        pool=[f"You just said {clause!r}. Which specific detail in that answer should I connect to the warning named in the public clue?",f"You said {clause!r}. Does that describe the Siddha's lore, or give me a step toward understanding the warning?",f"Your last answer included {clause!r}. What follow-up question about the warning does that detail suggest?"]
        fallback=next((q for q in pool if norm(q) not in already and not any(difflib.SequenceMatcher(None,norm(q),norm(old)).ratio()>.88 for old in state["asked_questions"])),None)
        if fallback is None:
            pivots=[f"You said {clause!r}. Which part of that answer is a clue, and which part is background lore?",f"You said {clause!r}. What would I need to ask next to test whether that is the warning the page refers to?",f"You said {clause!r}. Does that point toward a specific next step in the challenge?",f"You said {clause!r}. What detail in the public clue should I compare it with?"]
            fallback=next((q for q in pivots if norm(q) not in already and not any(difflib.SequenceMatcher(None,norm(q),norm(old)).ratio()>.88 for old in state["asked_questions"])),pivots[len(state["asked_questions"])%len(pivots)])
        ranked=[{"question":fallback,"strategy":"latest_response_implication","branch":"response_transition","score":3.0,"reason":"Evidence-linked fallback from the latest live sentence."}]
    ranked.sort(key=lambda x:x["score"],reverse=True)
    return {**ranked[0], "candidate_questions":ranked, "rejected_questions":[]}

def run(resume: bool, idle_seconds: float) -> None:
    global STOP
    state=restore_state(resume)
    # Repair a V13 pending candidate generated from the preamble of the first
    # reply; that candidate repeated the exact V11/V12 novelty-scoring failure.
    if (resume and state.get("iteration") == 1 and state.get("last_analysis")
            and "letter six" in norm(state["last_analysis"].get("question", ""))
            and "letter six" not in norm(state.get("pending_question", {}).get("question", ""))
            and not state.get("confirmed_flag")):
        a=state["last_analysis"]
        refreshed=choose_next(a["question"],a["response"],a,state)
        state["pending_question"]={k:refreshed[k] for k in ("question","strategy","branch","reason","score","fresh_context","control_of","book_probe_id","book_source_page") if k in refreshed}
    if resume and state.get("last_analysis") and not state.get("confirmed_flag") and not state.get("pending_question"):
        last=state["last_analysis"]
        refreshed=choose_next(last.get("question", ""), last.get("response", ""), last, state)
        state["pending_question"]={k:refreshed[k] for k in ("question","strategy","branch","reason","score","fresh_context","control_of","book_probe_id","book_source_page") if k in refreshed}
    if not AUDIT.exists() or not resume: atomic_json(AUDIT,research_audit())
    save_all(state)
    while not STOP and not state.get("confirmed_flag"):
        pending=state.get("pending_question")
        if not pending:
            print("No pending evidence-grounded candidate; saving state and ending for manual review.",flush=True); break
        q=pending["question"]
        prev=state["history"][-1]["content"] if state["history"] else None
        iteration=state["iteration"]+1
        fresh=bool(pending.get("fresh_context"))
        request={"type":"request","iteration":iteration,"timestamp":now(),"question":q,"strategy":pending.get("strategy"),"branch":pending.get("branch"),"selection_reason":pending.get("reason"),"previous_response_reference":sha(prev) if prev else None,"context_mode":"fresh_empty_history" if fresh else "continued_session","controlled_experiment":pending.get("control_of"),"book_probe_id":pending.get("book_probe_id"),"book_source_page":pending.get("book_source_page")}
        append_event(request)
        print(f"[{iteration}] {q}",flush=True)
        try:
            response,session=post(q,[] if fresh else state["history"],"" if fresh else state.get("session_id",""),state)
        except KeyboardInterrupt: break
        except Exception as e:
            state["stop_reason"]=f"unrecoverable configuration or endpoint error: {e!r}"; save_all(state); raise
        # Flush the unmodified live response before any analysis or selection.
        append_event({"type":"raw_response","iteration":iteration,"timestamp":now(),"question":q,"raw_response":response,"session_id":session,"context_mode":"fresh_empty_history" if fresh else "continued_session","book_probe_id":pending.get("book_probe_id"),"book_source_page":pending.get("book_source_page")})
        a=analyze(q,response,prev,state)
        # Commit raw live response before any derived updates.
        event={"type":"iteration","iteration":iteration,"timestamp":now(),"question":q,"raw_response":response,"response_hash":a["response_hash"],"session_id":session,"strategy":pending.get("strategy"),"branch":pending.get("branch"),"previous_response_reference":sha(prev) if prev else None,"context_mode":"fresh_empty_history" if fresh else "continued_session","controlled_experiment":pending.get("control_of"),"book_probe_id":pending.get("book_probe_id"),"book_source_page":pending.get("book_source_page"),"analysis":a}
        append_event(event)
        state["iteration"]=iteration; state["session_id"]=session
        if fresh: state["history"]=[]
        state["history"].extend([{"role":"user","content":q},{"role":"assistant","content":response}])
        state.setdefault("transcript_history",[]).extend([{"role":"user","content":q},{"role":"assistant","content":response,"session_id":session,"iteration":iteration}])
        state["asked_questions"].append(q); state["response_hashes"][a["response_hash"]]=state["response_hashes"].get(a["response_hash"],0)+1
        state["last_analysis"]={**a,"question":q,"response":response}
        st=state["strategy_stats"].setdefault(pending.get("strategy","unknown"),{"attempts":0,"information_gain":0.0,"new_templates":0})
        st["attempts"]+=1; st["information_gain"]+=a["information_gain"]
        st["new_templates"]+=1 if state["templates"][a["template_id"]]["count"]==1 else 0
        flag=a["flag_detected"]
        if flag:
            state["confirmed_flag"]=flag; state["pending_question"]=None; state["stop_reason"]="confirmed flag in live response"
            append_event({"type":"confirmed_live_flag","timestamp":now(),"iteration":iteration,"question":q,"response":response,"flag":flag,"session_id":session})
        else:
            nxt=choose_next(q,response,a,state)
            state["pending_question"]={k:nxt[k] for k in ("question","strategy","branch","reason","score","fresh_context","control_of","book_probe_id","book_source_page") if k in nxt}
            state["pending_question"]["reason"]=nxt["reason"]
            state["branch_scores"][nxt["branch"]]=state["branch_scores"].get(nxt["branch"],0.0)+a["information_gain"]
            append_event({"type":"selection","timestamp":now(),"iteration":iteration,"candidate_questions":nxt["candidate_questions"],"rejected_questions":nxt["rejected_questions"],"selected_question":nxt["question"],"selection_reason":nxt["reason"],"branch_score":state["branch_scores"][nxt["branch"]]})
        save_all(state)
        print(response,flush=True)
        print(f"  [gain={a['information_gain']:.2f} template={a['template_id']} flag={flag}]",flush=True)
        if iteration%15==0:
            review={"iteration":iteration,"timestamp":now(),"what_learned":list(a["new_phrases"]),"top_strategy":max(state["strategy_stats"],key=lambda k:state["strategy_stats"][k]["information_gain"]/max(1,state["strategy_stats"][k]["attempts"])),"risk_to_avoid":"Do not repeat lore statements that add no clue-specific detail.","next_strategy_change":"Continue with exact newest boundary or relation; compare template transitions."}
            state["recent_reviews"].append(review); append_event({"type":"self_review",**review}); save_all(state)
        if idle_seconds>0: time.sleep(idle_seconds)
    if STOP:
        state["stop_reason"]="manual Ctrl+C"; save_all(state)
    if state.get("confirmed_flag"):
        print(f"CONFIRMED LIVE FLAG: {state['confirmed_flag']}",flush=True)
    else:
        print(f"Investigation paused. Resume with: python3 {Path(__file__).name} --resume",flush=True)

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume",action="store_true",help="resume from saved V13 state")
    parser.add_argument("--idle-seconds",type=float,default=90.0,help="pause between questions to reduce rate-limit pressure while V11/V12 run")
    args=parser.parse_args()
    def handler(signum,frame):
        global STOP
        STOP=True
    signal.signal(signal.SIGINT,handler)
    signal.signal(signal.SIGTERM,handler)
    run(args.resume,args.idle_seconds)

if __name__=="__main__": main()
