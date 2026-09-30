# Gate 2 — МОДНАЯ ПРОПАГАНДА — FAIL (not run on the PC)

Run date: 2026-09-30, cloud sandbox (Linux, no GPU, no Premiere, no user files).

## Step 0 (install)
- `pip install -e .[dev]` — OK. `[asr]` and the onnxruntime swap were NOT done (no GPU in the cloud).
- `python -m pytest -q` — **218 passed** (this is Gate 1 only).
- `CUDAExecutionProvider` check — not applicable in the cloud, NOT verified.

## Step 3 (Gate 2)
Command: `python -m acceptance.gate2 acceptance/episodes/modnaya_propaganda.yaml`

Output:
```
script: 338 blocks (saved export modnaya_propaganda_gdoc_text_and_threads.json)
none of the sources exist — check the paths in the episode file
```
Cause: the paths in the episode file point to `%USERPROFILE%\Videos\Макашенец\МОДНАЯ ПРОПАГАНДА\...`
on Artem's PC. The cloud session cannot see them (CLAUDE.md rule 6). This is not a glob error,
so the episode file was NOT changed.

## Not done (needs the PC)
- Step 1 (transcripts), Step 2 (MF_base.prproj, MF_DRAFT in Premiere): not done.
- Gate 2 outputs (`MF_base_MF1_draft.prproj`, `source_map_*`, `draft_*`, `gate3_frames_*`): not produced.
- Gate 3: not run (see `gate3_modnaya_propaganda.md`).

## Verdict
Gates 2 and 3 are NOT passed. The module must not be called done.

## Update 19:20 — sources are now reachable, Gate 2 still cannot run here
Artem connected `МОДНАЯ ПРОПАГАНДА`. Found: `Копия 20260828_B0001..B0004.MP4`, `Копия 20260915_B0001.MP4`,
`Копия Keyed-Video_2608311425_0001.mov`, `VO_MAKASHENETS_20260904.wav` (about 120 GB together).
Missing: `MF_base.prproj` (step 2 not done; only the original `МОДНАЯ ПРОПАГАНДА.prproj` and an older `MarkFlow модная пропоганда.prproj` exist).
Blocker: the shell that can see the files is a Linux VM (Cowork) without GPU and without Windows Python, so
`%USERPROFILE%` paths, `CUDAExecutionProvider` and GigaAM/Parakeet ASR on 120 GB cannot run there. Gate 2 must be run in a
Windows terminal (or Cowork with a Windows shell) on the PC. Status stays FAIL (not run).
