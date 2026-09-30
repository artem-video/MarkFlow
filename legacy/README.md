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

## Not found yet (needs Artem to point at the folder)

These were named in PLAN.md 0.2 but are **not inside the two folders connected to this session**
(`Videos\Макашенец`, `Videos\MarkFlow`):

- `prep.py`, `auto.py`, `analyze.py`, `transcribe.py` (loudness-envelope cut refinement etc.)
- the bridge and CEP extension from the auto-titles app (`Варламов Шортс Титры\app`)

Not copied on purpose: `gemini_api.txt` (secret), the guide PDF/DOCX binaries (11 MB / 8 MB — text extracts kept instead),
screenshots, `Спец по Израилю [Сценарий].pdf`.
