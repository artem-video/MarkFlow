# MarkFlow — Claude Code Instructions

Read this file at the start of every session. Then read `docs/PLAN.md` (what to build, in what order)
and the module spec named in the session prompt. The user-facing route map is `docs/ROUTE.md`.

## What MarkFlow is

A Windows desktop app that turns a talking-head shoot + a Google Docs script into an editable
Adobe Premiere Pro 2026 project (`.prproj`): rough cut, lives (video inserts), script comments as
markers, voice preset — then, on request, jokes, SFX, music, shot-size alternation and a pre-delivery check.

First channel and reference episode: **Makashenets — «МОДНАЯ ПРОПАГАНДА»**.
Other channels (Varlamov, Shtefanov) are added later as profiles, without code changes.

## The user

Artem is a video editor, not a programmer. He talks Russian.
- Every message addressed to him: Russian, plain words, no jargon, result first.
- Never ask him to edit code or config by hand. If he must do something, give one exact action
  ("open Cowork and paste: …").
- He wants results that work in Premiere, not reports about effort.

## Tech stack

- Core + adapters: **Python 3.11**, `pydantic` (schemas), `rapidfuzz`, `numpy`, `pytest`.
- Media: `ffmpeg` / `ffprobe` (PATH or `%USERPROFILE%\.stacher`).
- ASR: chosen by the Stage 0 benchmark (candidates: faster-whisper large-v3-turbo, GigaAM, Parakeet). GPU: RTX 4060 8 GB — one model in memory at a time.
- LLM ("thinking" stages only): **Gemini API**; fallback = task file for a Cowork session.
- Window: **Electron** (reused from the auto-titles app). Premiere bridge: **CEP** extension (reused from auto-titles).
- Google: Docs/Drive API (service account from `premiere-assembler-python` as a starting point; verify access in Stage 0).

## Architecture — layers (never violate)

```
app/ (Electron window)        premiere_ext/ (CEP bridge)
        ↓                             ↓
markflow/application/   stages & use cases: orchestrate, no business rules
        ↓
markflow/domain/        pure editing rules: no files, no network, no ffmpeg, no Premiere
        ↓
markflow/infra/         all I/O: asr, media, gdocs, gdrive, downloader, prproj, bridge, llm, assets
        ↑
markflow/shared/        pure utils: timecode/ticks, text normalisation, fuzzy match, logger
```

- **domain** receives plain objects, returns plain objects or raises typed errors. 100% testable in the cloud.
- **application** gets infra via constructor (interfaces), never imports concrete infra.
- **infra** is the only place that touches disk, network, GPU or Premiere.
- **Only `infra/prproj/writer`** may write a `.prproj`. It always starts from a project that
  real Premiere saved (a template or the user's current project). Never build a project from scratch.
- Modules talk through **`edit_plan.json`** (schema in `markflow/domain/edit_plan.py`). Change the schema only
  with a version bump and a migration test.

## Channel profiles

`profiles/<channel>/`: `profile.yaml` (rules, thresholds, track layout, asset folders), `STYLE.md` (human rules),
`template.prproj` pointer. Asset folders are **referenced, never copied**. A new client = a new folder, no code changes.

## Hard rules

1. **Never modify the user's originals.** Sources, his projects and asset folders are read-only.
   Every stage writes a **new file** next to the input: `<name>_MF1_draft.prproj`, `_MF2_jokes`, `_MF3_sfx`,
   `_MF4_music`, `_MF5_sizes`, `_MF6_qa`. A stage adds its own items and must not change any existing clip.
2. **Script beats transcript.** Re-recorded phrase = take the last take. Meaningful/funny off-script speech
   is kept and colour-labelled, never silently removed. Doubtful decisions get a `ПРОВЕРИТЬ` marker.
3. **No re-encoding of sources.** Downloads keep source quality (max 2K); no subclips, no transcodes.
4. **Secrets never in git**: `gemini_api.txt`, Google credentials, `.env*` (only `.env.example` is committed).
5. **No big media in git.** Fixtures ≤ 5 MB each (16 kHz mono WAV excerpts, mini projects saved by Premiere).
6. **Cloud cannot touch the user's PC.** Anything needing GPU, Google Drive for Desktop, yt-dlp to YouTube,
   the real episode or Premiere goes into an acceptance/benchmark task for a Cowork session.

## Definition of done — three gates

A module is **done** only when all three gates are green. Claude Code must never say "готово" / "done"
without the reports of gates 2 and 3 committed under `acceptance/reports/<branch>/`.

- **Gate 1 — cloud:** `pytest` green (unit tests on fixtures + prproj validator on fixture projects).
- **Gate 2 — PC, no Premiere:** `python -m acceptance.gate2 <episode>` runs the full chain on the real episode;
  the validator parses the output `.prproj` (unique ObjectIDs/UIDs, no broken refs, no overlaps, clip count and
  durations match `edit_plan.json`, original clips untouched) and computes the metrics from PLAN.md. Output: `OK` or a list.
- **Gate 3 — PC, Premiere:** the bridge opens the project in Premiere, reads the timeline (clips per track,
  total duration), compares with the plan, exports 5 check frames. **An empty or short timeline = FAIL.**

## Git workflow

- Repo: `https://github.com/artem-video/MarkFlow` (private). Default branch `main` — protected by habit:
  **never commit to `main` directly**.
- One module = one branch `feat/<module>`. Merge to `main` only after gate 2 + gate 3 reports say OK.
- Commit messages in English, small and frequent. Code, comments, test names in English.
- `legacy/` holds reference scripts copied as-is from the user's PC. Read them, port the good parts, never import from them.

## Session workflow

1. Read CLAUDE.md, docs/PLAN.md, the module spec.
2. State in one line which module this session builds.
3. Write/confirm the interface first, then implementation + tests together (method → test → run → fix).
4. Run all tests. Everything green before the session ends. No `skip`.
5. Update `docs/PLAN.md` status table.
6. **End every session with a block for Artem in Russian**, exactly in this shape:
   ```
   Что сделано: <1–2 строки>
   Что дальше: <Облако / Cowork на ПК>
   Скопируй и вставь: «<exact phrase>»
   ```

## Economy rules

- Don't process large media in the cloud. Work on fixtures; real episodes only in acceptance on the PC.
- Don't re-read big files; keep derived data (transcripts, loudness envelopes, indexes) cached as JSON with a hash of the source.
- Prefer deterministic code; call the LLM only in the "thinking" stages, with a per-episode cost log.

## Known pitfalls (from previous attempts — do not repeat)

- `.prproj` is gzip-compressed XML; time unit = **254016000000 ticks per second**; ObjectID/ObjectUID must stay unique and every ref must resolve.
- Premiere keeps an open project in memory (`*.prlock`): write only after the bridge saved and closed it, then reopen.
- Frame rates differ between sources (25 / 29.97 / 30 / 60p Keyed-Video). Never assume one fps.
- MCP `apply_edit_plan` ignores in/out and ripples — never use it. `add_to_timeline` needs an explicit `audio_track_index` per clip.
- Whisper word timings drift at silence edges: refine every cut on the loudness envelope (see `legacy/prep.py`).
- GigaAM is a transformer: chunk long audio, don't feed 30 min at once.
- OpenCV on Windows can't open Cyrillic paths — copy models to a temp ASCII path.
- YouTube returns 403 from the cloud; download lives on the PC only.
- Google Docs saved as HTML has text as canvas — always read the doc through the API/export.
- A previous attempt produced a project with 1 sequence and 3 clips and was reported as success. Gate 3 exists to stop this.
