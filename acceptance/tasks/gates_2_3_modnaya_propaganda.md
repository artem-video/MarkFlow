# Gates 2 + 3 on the PC (Cowork): «МОДНАЯ ПРОПАГАНДА», MF1_draft

Branch: `claude/adoring-turing-sfhe0z`. Everything reads the originals only; every result is a new file.
Commit every report you get (OK or FAIL) under `acceptance/reports/claude-adoring-turing-sfhe0z/` and push.

## 0. Install (once)
```
cd <repo> && git fetch origin && git checkout claude/adoring-turing-sfhe0z && git pull
pip uninstall -y onnxruntime onnxruntime-gpu
pip install -e .[dev,asr]
python -m pytest -q                       (must be all green)
python -c "import onnxruntime as o; print(o.get_available_providers())"   (must list CUDAExecutionProvider)
```
Optional, to read the script live from Google instead of the saved export:
`pip install google-api-python-client google-auth`, share the doc with the service account, and
`set MARKFLOW_GOOGLE_CREDENTIALS=<path to the JSON>` (never inside the repo).

## 1. Stage 2.1 transcripts
Follow `acceptance/tasks/stage2_1_transcribe.md` (fixtures dump + report). Gate 2 below also transcribes
whatever is missing from the cache, so this step can be skipped if time is short.

## 2. The base project (in Premiere, once)
1. Open `%USERPROFILE%\Videos\Макашенец\МОДНАЯ ПРОПАГАНДА\МОДНАЯ ПРОПАГАНДА.prproj` and **immediately**
   File > Save As… `MF_base.prproj` in the same folder. From now on work only in `MF_base.prproj`.
2. Make sure these are imported (File > Import if not): `Копия 20260828_B0001…B0004.MP4`,
   `Копия 20260915_B0001.MP4`, `Копия Keyed-Video_2608311425_0001.mov`, `VO_MAKASHENETS_20260904.wav`.
3. In the Project panel: right-click «МОДНАЯ ПРОПОГАНДА ч2 в» > Duplicate. Rename the copy to `MF_DRAFT`,
   open it, select everything on the timeline (Ctrl+A) and Delete. It must be completely empty
   (4K, 29.97 fps, 13 video / 10 audio tracks are kept).
4. Save, then **close the project in Premiere** (the tool never writes a project Premiere holds open).

If the Premiere MCP is available you may do 2–3 through it; the result must be the same.

## 3. Gate 2
```
python -m acceptance.gate2 acceptance/episodes/modnaya_propaganda.yaml
```
Prints `OK` or `FAIL` + a list. Writes `MF_base_MF1_draft.prproj` (+ `.edit_plan.json`) next to `MF_base.prproj`,
and into `acceptance/reports/claude-adoring-turing-sfhe0z/`: `gate2_modnaya_propaganda.md`,
`source_map_modnaya_propaganda.md`, `draft_modnaya_propaganda.md`, `gate3_frames_modnaya_propaganda.txt`.
If a source path is wrong, fix the glob in `acceptance/episodes/modnaya_propaganda.yaml` (commit the fix).

## 4. Gate 3 (Premiere)
1. Open `MF_base_MF1_draft.prproj` in Premiere. Open the `MF_DRAFT` sequence. **An empty or short timeline = FAIL**
   — write that into the report and stop.
2. File > Save As… `MF_base_MF1_gate3.prproj` (Premiere rewrites the whole file — that is the test).
3. For each time in `gate3_frames_modnaya_propaganda.txt`: put the playhead there, File > Export > Frame (JPEG),
   save into `acceptance/reports/claude-adoring-turing-sfhe0z/frames_modnaya_propaganda/`.
4. Run:
```
python -m acceptance.gate3 "<folder>\MF_base_MF1_draft.edit_plan.json" "<folder>\MF_base_MF1_gate3.prproj" ^
  --sequence MF_DRAFT --frames acceptance\reports\claude-adoring-turing-sfhe0z\frames_modnaya_propaganda
```
5. Look at the timeline and write 3–5 lines of your own into `gate3_notes_modnaya_propaganda.md`: are the cuts on
   words, are the improvised bits coloured, are the markers readable, do the label colours look right.

## 5. Commit
`git add acceptance/reports/claude-adoring-turing-sfhe0z && git commit -m "Gates 2-3 reports: МОДНАЯ ПРОПАГАНДА" && git push`
(no .prproj, no media except the 5 small JPEG frames).
