# Gyanganj RAG Challenge Research

An evolving set of Python scripts and research notes for exploring the Gyanganj RAG CTF challenge. The versions record different approaches, from response-pattern analysis to follow-up questions based on the challenge's replies. V16 also tests the **assertion-over-inquiry** idea described in the OWASP PCCOE RedKeep write-up. RedKeep is a separate challenge, so that technique is only a hypothesis here.

## Suggested GitHub repository name

**`gyanganj-rag-ctf-research`**

Other concise options: `gyanganj-ctf-investigator` or `gyanganj-rag-challenge`.

## Requirements

- Python 3.10 or newer
- Network access to the challenge service for live runs

The scripts use Python's standard library; no third-party packages are required.

## Run V16

Start a new V16 session:

```bash
python3 gyanganj_solver_v16.py
```

Resume its saved session:

```bash
python3 gyanganj_solver_v16.py --resume
```

By default, V16 waits 90 seconds between successful requests. To change the delay, pass `--idle-seconds SECONDS`. Stop the run with `Ctrl-C`; its session state and logs are saved for resuming.

V16 saves the live session state in `gyanganj_v16_state.json`, its detailed event log in `gyanganj_v16_run.jsonl`, and a readable prompt/response transcript in `gyanganj_v16_answers.txt`. These generated files are excluded from Git by `.gitignore` so challenge conversations and local run state are not published accidentally.

## Project layout

- `gyanganj_solver.py`, `gyanganj_solver_v2.py` … `gyanganj_solver_v16.py`: historical and current solver versions.
- `gyanganj_v8_research.md`, `gyanganj_v9_research.md`: research notes on observed behavior and prior attempts.
- `gyanganj_solver_v16.py`: current response-led runner with a RedKeep-inspired assertion track.

Earlier versions are retained as research history; V16 is the current entry point. Run files, state snapshots, OCR output, caches, and local challenge reference material should stay local unless you have checked that they are appropriate to share.

## Research notes and limits

- The public clue points to a warning the Siddha left for himself in the RAG source.
- The RedKeep write-up describes a backend gate for a different challenge. There is no evidence that Gyanganj uses the same mechanism.
- A flag is considered found only when a flag-shaped value appears in a live response. No success is guaranteed.
- Use this tooling only with the intended CTF challenge service and within its rules. Respect rate limits.

Reference: [OWASP PCCOE — Anantya ByteMe Writeup Series: RedKeep](https://owasppccoe.blogspot.com/2026/01/anantya-byteme-writeup-series-redkeep.html)
