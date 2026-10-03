# Pilot Server working guide

## Project overview

- XR Lab experiment controller: Python 3.11 (requirements target 3.11.4), Flask/Jinja, plain JavaScript/CSS, PyAudio, Whisper, PyTorch/Transformers, OSC, GoDirect, and HDF5/CSV storage.
- `app.py` is the entry point and route/orchestration module. It creates global managers for one active participant, test, recorder, and sensor streams. Importing it initializes audio, binds an OSC socket, and loads models; do not import it as a harmless smoke check.
- `templates/index.html` is the experiment dashboard; it opens `templates/subject_gui.html` through `/subject_gui` in a separate browser window. Subject progression/timers live in browser JavaScript. HTTP requests mutate shared server state; `/stream` sends transient SSE notices to the experiment dashboard. Room/PRS windows read task context from `localStorage`.
- `static/js/scripts.js` contains shared browser helpers; `static/css/` and other `static/` folders contain styling, audio, and video. Much workflow logic remains inline in templates, and PRS HTML is inline in `app.py`.
- Root `*_manager.py` modules handle subjects, questions, recording, transcription, forms, and files. Active sensor implementations are `emotibit_streamer_2.py` and `vernier_manager.py`; `gdx/` contains device support code.
- `test_files/` contains question JSON; `surveys/` contains form links; `SER_MODEL/` and `label_maps/` support emotion classification. `subject_data/` holds participant records/results; `tmp/` holds working audio. Vernier outputs use `respiratory_data/` within the participant folder.
- `metrics_unittests/` contains a standalone metrics check and sample CSV. Root Vernier test scripts exercise real hardware. PostgreSQL/AWS helper modules exist but are not wired into the active dashboard workflow.

## Build and test commands

Run from the repository root unless stated otherwise. Use the project's Python environment:

```sh
source venv/bin/activate
```

If creating a new environment, use `python3.11 -m venv venv` first. Install dependencies only when setup or the task requires it:

```sh
python -m pip install -r requirements.txt
python -m pip install git+https://github.com/openai/whisper.git
```

PortAudio and ffmpeg are external prerequisites; on macOS: `brew install portaudio ffmpeg`. PostgreSQL is needed only for work using the database helper, not the active dashboard path.

| Purpose | Exact command / current status |
| --- | --- |
| Run application | `python app.py` — open `http://127.0.0.1:8000/`; keep debug/reloader disabled. Requires audio/model assets. README references to `exp_server.py` and port 5000 are stale. |
| Existing metrics check | `(cd metrics_unittests && PYTHONDONTWRITEBYTECODE=1 python metrics_unittest.py)` — reads local `emotibit_data.csv`; verified passing. |
| Explicit pytest check | `PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider metrics_unittests/metrics_unittest.py` — currently fails because `bi_values` and `ppg_values` fixtures are missing. Do not report this as a passing suite. |
| Targeted Python syntax | `python -c 'import ast, pathlib, sys; [ast.parse(pathlib.Path(p).read_text(), filename=p) for p in sys.argv[1:]]' app.py` — replace `app.py` with changed Python paths; does not import the application or write bytecode. |
| Patch whitespace | `git diff --check` |
| Manual Vernier check | `python vernier_godirect_test.py` or `python vernier_gdx_test.py` — only with intended hardware available; these are device exercises, not isolated automated tests. |
| Lint / build | No configured linter, formatter, frontend build, or packaging build command. Do not invent `npm` commands or install tooling just to claim these checks passed. |

Avoid blanket pytest discovery: root `*_test.py` files initialize hardware during import. The metrics assertions are limited smoke checks, not scientific validation of the algorithms.

## Working agreements

- Before making changes for any new task or fix, create and switch to a new branch from the intended base branch unless the user explicitly requests otherwise. Never make task changes directly on `main`.
- Do not use a `codex/` branch prefix. Use a purpose-based prefix such as `fix/`, `feat/`, `docs/`, or `chore/` followed by a short descriptive name; for example, `fix/participant-experimenter-workflow`.
- Read the existing code first. Follow local patterns, keep changes scoped, and preserve user edits. Inspect `git status --short` before work; never clean up unrelated changes or tracked bytecode as a side task.
- Present the approach before changes likely to exceed five lines. Ask when a tradeoff materially changes behavior. Keep updates short and final summaries direct: files changed, checks run, and remaining limitations.
- Keep existing Python indentation/naming and nearby JavaScript style. Avoid unrelated formatting, new frameworks, generic abstractions, or dependency upgrades. Preserve the Flask 2.2 / Werkzeug `<3.0` compatibility constraint.
- Treat the dashboards as coupled views of one active participant. Preserve task IDs, markers, condition labels, route payloads, survey prefill placeholders, and CSV/HDF5 formats unless the task explicitly changes them. Trace both dashboards and task windows when changing shared behavior.
- Read `CONTEXT.md` for MAT, SART, PRS, ZIPER, IPR, and PSS terminology. ZIPER surveys use Google Forms; existing IPR labels likely refer to ZIPER, but this mapping is provisional. PSS means pre-screening surveys in the lab's terminology; confirm its relationship to the existing `pss10` identifier before renaming or changing that survey. Do not infer lab protocol from hidden DOM sections. Ask about undefined concepts such as N/A/D/P categories, experiment versus trial, and where SART runs and stores results when relevant.
- Preserve subject attribution, timestamps, and saved recordings. Do not use real participant sessions for smoke tests or commit participant data, temporary audio, credentials, model binaries, environments, or generated caches. Existing email-derived IDs are reversible Base64, not encryption.
- Keep interfaces restrained and usable; verify text fit and responsive layouts. Avoid decorative clutter or a frontend rewrite for a small workflow change.
- Do not add tests that only mirror implementation. Favor observable behavior: failed requests, completion delivery, reloads, timers, recording outcomes, and participant attribution. Isolate hardware/model effects in tests where needed.

## Validation before completion

1. Review the final diff and `git status --short`; run `git diff --check`. Confirm only intended files changed and no sensitive/generated outputs were added. Inspect new untracked files explicitly because ordinary `git diff` omits them.
2. For Python edits, run the targeted syntax command above on every changed Python file. Run relevant isolated tests; for metrics changes, also run the standalone metrics command. Identify pre-existing failures separately from regressions.
3. For dashboard/workflow edits, exercise the affected path with synthetic participant data in both windows when runtime prerequisites are available. Check launch, progression/completion indicators, affected request failures, and refresh/reopen behavior. For visual edits, check browser console errors and narrow/wide layouts.
4. For recording or sensor edits, verify affected start/stop behavior and saved timestamps, markers, conditions, and file attribution with suitable test doubles or intended hardware. Never describe mocked checks as hardware verification.
5. For documentation-only changes, verify commands and paths against the repository; application startup and hardware checks are unnecessary. Check that this file remains below 32 KiB with `wc -c AGENTS.md`.
6. Report exactly what passed, failed, or could not be exercised. Missing hardware, models, fixtures, or browser access must be stated; do not claim unrun checks passed.
