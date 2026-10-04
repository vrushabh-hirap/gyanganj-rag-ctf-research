# GYANGANJ V8 research notes

## Project evidence audit

Inspected project files recursively (hidden files included, excluding `.git`): V1–V5 solver code; V1–V4 JSON logs; V5's 1.6 MB persistent model; V6 offline analyzer/output; V7 JSONL and summary; and the supplied lore PDF. `pypdf`, `pdfplumber`, `PyPDF2`, `fitz`, and `pdftotext` are unavailable, so the PDF contents were not extracted. No README, shell history, separate client source, or other challenge transcript was present.

## Reconstructed observations

* V1 log: 23 rows, 8 unique exact responses. V2: 55 rows, 27 exact responses. V3: 37 rows, 22 exact responses. V4: 79 rows, 39 exact responses. These are per-log counts, not proof the service has a fixed number of templates.
* The V5 state currently contains 225 rows, 50 learned response clusters, 33 paragraph blocks, and 24,059 co-occurrence edges. It mixes imported historic material and later live probes. Deduplicate by exact question/response for aggregate counts. Its comments and initialized hypotheses are not observations.
* The V6 artifact explicitly records zero network requests; it is analysis output, not a challenge interaction.
* V7's JSONL currently has 22 actual live response records, 25 recorded request attempts, three failures/status records, and two self reviews. V7 first received DNS errors, later completed 22 responses, then received HTTP 429. The responses include rich blocks about Gita/Kurukshetra/eighteen parvas, Vyasa/Ganesha's dictation conditions, mula shloka/seed-truth, and akashic record/Siddhas. These are live observations in V7, not claims inferred from source code.
* A cross-block prompt about the Bhagavad Gita and Yudhishthira/Dharma was already tested historically and returned a rich combined response. V7's first live question (about Krishna's action teaching and Yudhishthira's refusal) also returned a rich combined response. Its exact answer and successors are in `gyanganj_v7_run.jsonl`.
* The V7 HTTP 429 was logged after iteration 22. V8 must preserve and resume from that point, not replay successful questions.

## Implementation mistakes corrected

* V1–V4 hand-built large static banks and treated response count/richness as information. Several version comments converted correlations into confident hypotheses (e.g. Dharma as answer) without independent validation.
* V5's bag-of-words graph and hand-coded candidate pool did not reliably connect question to response, and an untested hypothesis could be called “best.” V8 reports untested hypotheses as untested and only updates them on discriminating evidence.
* V6 was offline-only, and its “richest” response selection over-weighted long text and produced a nonsensical action/akashic question. It was not a live solver.
* V7's live client sent `session_id: ""` on every call rather than carrying forward the returned session; it seeded a broad/unfiltered lexical extractor that treated ordinary prose words as concepts, produced awkward questions, repeated at least one exact question, and used an unbounded novelty formula (reported information gain over 100 for a long answer). V8 separates entities/phrases from ordinary tokens, deduplicates exact and semantic candidates, caps scores, and persists returned session IDs.
* V7's server backoff stopped on 429. V8 reads `Retry-After`, backs off exponentially on rate limits and 5xx/network errors, and appends every result/error before retrying.

## Evidence classes

**Observed:** request mechanism is `POST https://gyanganj-ctf.onrender.com/chat` with JSON `message`, `history`, `session_id`; successful response contains `response` and `session_id`. This is present in previous client code and V7 live records. Repeated generic templates and richer multi-block responses appear in logs.

**Inference:** some wording and current conversation context influence which blocks are returned; the V7 conversational response sequence supports that the client history is relevant. Cross-block questions are promising but have only a small number of strong examples.

**Hypotheses:** response order may matter; exact hidden-flag path is not known; “deeper question,” “appointed time,” and repeated numbers may be clues. No historical record contains a confirmed flag in an actual response.

**Confirmed:** only a literal syntactically valid `KCTF{...}` in an actual live response will mark V8 success. Historic strings/questions do not.

## Adaptive research ideas incorporated

* **PyRIT:** keep target transport, memory, response scoring, and strategy selection as separate components; persist all turns so strategy decisions can be reproduced. V8 uses an append-only transcript plus atomic state snapshots.
* **garak:** treat question strategies as selectable probes and response signatures as detectors; track per-strategy outcomes rather than assume any prompt family is universally effective.
* **AutoDAN / evolutionary search:** use semantic mutations of a demonstrated successful question pattern (relation, causal, contrast, narrative sequence), retaining grammatical/evidence constraints and rejecting near duplicates. No generic jailbreak payload bank is imported.
* **Trajectory-based adaptive red teaming / MCTS-style planning:** select from evidence-grounded next steps using response gain and branch history, maintain multiple active semantic branches, and review after each response. Given this target, V8 uses lightweight online bandit statistics rather than requiring another model/API.

These are algorithmic inspirations, not copied attacks. The solver optimizes for useful, grounded puzzle dialogue and verified live output.

## Public sources checked (2026-10-02)

* Microsoft PyRIT architecture and separation of targets, memory, scorers, and attacks: https://github.com/microsoft/PyRIT/blob/main/doc/code/framework.md
* PyRIT overview: https://github.com/microsoft/PyRIT/blob/main/doc/index.md
* NVIDIA garak probe selection / detectors: https://docs.nvidia.com/nemo-helix/v0.2.0/documentation/vulnerability-scanning/configurations/selecting-probes/
* AutoDAN (hierarchical genetic search): https://arxiv.org/abs/2310.04451
* Automatic LLM Red Teaming (multi-turn trajectory planning): https://arxiv.org/abs/2508.04451
* AutoRedTeamer (memory-guided strategy selection): https://arxiv.org/abs/2503.15754
