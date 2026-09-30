# legacy/ — reference material, copied as-is (read-only)

Read it, port the good parts, **never import from it** (CLAUDE.md). No media, no keys.
Collected on Artem's PC on 2026-09-30 (stage 0.2, part 1).

| Folder | What | Origin |
|---|---|---|
| `egor/` | `PIPELINE_агент_монтажа.md`, `STYLE.md` — Egor's agent pipeline notes (reference only) | Videos\MarkFlow |
| `makashenets/` | Editing guide 2026 (text extracted from the PDF), «Ландыши 2» method + handover notes, neural-clothing note | Videos\MarkFlow |
| `varlamov/` | «Авто-сборка предмастера» spec, «Правки Варламов» (sample of QA edit lists for MF6_qa), editor manual (text from the .docx, provenance not verified) | Videos\MarkFlow |
| `scripts/alternate_any.py` | shot-size alternation script (basis for MF5_sizes) | Videos\MarkFlow |
| `scripts/agent_bridge/` | `bridge_watcher.py` — local faster-whisper job watcher | Videos\Макашенец\_agent_bridge |
| `markflow_attempts/` | `MARKFLOW_HANDOFF.md`, `ТЕХПЛАН_комменты_в_таймлайн.md`, earlier local scripts (`markflow_engine.py`, `master_pipeline.py`, `generate_working_xml.py`, gemini-generated XML builders) and the first cloud attempt (`cloud_attempt_1/`, sources + tests, no outputs) | Videos\Макашенец |

## Added in part 2 (2026-09-30, local Claude Code on the PC)

| Folder | What | Origin |
|---|---|---|
| `scripts/robot/` | `prep.py` (loudness-envelope cut refinement), `auto.py`, `analyze.py`, `transcribe.py`, helpers (`rms.py`, `faces.py`, `reframe.py`, `make_srt*.py`), `robot.ps1`, `spec_*.json`, `ПРАВИЛА.md` | Videos\VARLAMOV\Shorts\_Робот (no venv/work/queue/logs) |
| `autotitles/app/` | Electron window of the auto-titles app: `src/`, `test/`, `package.json` (no `node_modules`, no `.git`) | Videos\VARLAMOV\Daily Shorts\Варламов Шортс Титры\app |
| `autotitles/cep_MCPBridgeCEP/` | the CEP extension the app installs (`CSXS/manifest.xml`, `main.js`, `host.jsx`, …) | %APPDATA%\Adobe\CEP\extensions\MCPBridgeCEP |
| `autotitles/docs/` | design + plan of the Premiere bridge (2026-08-20) | same folder as the app |
| `markflow_attempts/` | `MARKFLOW_HANDOFF.md` and `ТЕХПЛАН_…` refreshed from the newer local versions (29.09 / 27.09) | Videos\Макашенец |

Secret scan (Gemini/OpenAI/GitHub keys, private keys, `api_key=`) over everything added in part 2: nothing found.

Not copied on purpose: `gemini_api.txt` (secret), the guide PDF/DOCX binaries (11 MB / 8 MB — text extracts kept instead),
screenshots, `Спец по Израилю [Сценарий].pdf`.
