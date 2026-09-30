# Stage 2.1 acceptance on the PC (Cowork)

Goal: every talking-head source of «МОДНАЯ ПРОПАГАНДА» transcribed by GigaAM v3 + Parakeet-v3 into the cache,
on the GPU, plus the 15 fixture excerpts transcribed by both engines (small JSON, committed for the cloud).
Sources are only read. Branch: `claude/adoring-turing-sfhe0z`.

## 1. Install (once)
```
cd %USERPROFILE%\Videos\MarkFlow\repo            (or wherever the repo is cloned)
git fetch origin && git checkout claude/adoring-turing-sfhe0z && git pull
pip uninstall -y onnxruntime onnxruntime-gpu
pip install -e .[asr]
python -c "import onnxruntime as o; print(o.get_available_providers())"
```
The last line must list `CUDAExecutionProvider`. If not — stop and report (the tool refuses CPU on purpose).

## 2. Fixtures (≈1 min) — data for the cloud
```
python -m tools.transcribe_episode tests\fixtures\audio --cache %TEMP%\mf_fixture_cache --dump tests\fixtures\transcripts\asr
```
Commit `tests/fixtures/transcripts/asr/*.json` (45 small files).

## 3. The episode
Talking-head sources only (not the lives):
```
set EP=%USERPROFILE%\Videos\Макашенец\МОДНАЯ ПРОПАГАНДА
python -m tools.transcribe_episode ^
  "%EP%\Копия 20260828_B0001.MP4" "%EP%\Копия 20260828_B0002.MP4" "%EP%\Копия 20260828_B0003.MP4" ^
  "%EP%\Копия 20260828_B0004.MP4" "%EP%\20260915_B0001.MP4" "%EP%\VO_MAKASHENETS_20260904.wav" ^
  "%EP%\_test_downloads\keyed_audio_16k.wav"
```
(Adjust file names to what is really in the folder; Keyed-Video = its extracted 16 kHz audio from stage 0.4,
or the .mov through Drive for Desktop.) Default cache: `%USERPROFILE%\Videos\MarkFlow\cache`.

## 4. Report
Copy `%USERPROFILE%\Videos\MarkFlow\cache\report_2_1.md` to
`acceptance/reports/claude-adoring-turing-sfhe0z/stage2_1_transcripts.md`, add one line with the GPU name and
the total run time, commit, push.

**OK when:** every source has words from both engines, merged ≥ each single engine, run on CUDA.
Anything else → write what failed in that report file.
