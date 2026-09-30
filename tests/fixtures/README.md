# tests/fixtures — stage 0.3

Every file ≤ 5 MB (CLAUDE.md rule 5).

## audio/
14 excerpts × 30 s from the raw «МОДНАЯ ПРОПАГАНДА» talking-head take (Keyed-Video_2608311425_0001, 16 kHz mono WAV)
+ 1 studio voice-over excerpt (`vo_*`). `manifest.json` lists source offset, tags and the faster-whisper text;
`*.words.json` = word timings relative to the excerpt start.
**Tags are a first guess from the transcript, not verified by ear** — the ground-truth labels for Gate 2 are still to be made.

Coverage: on-set commands, retakes, stutters/false starts, swearing, off-script funny remarks, long pauses,
one stretch with audible sound but no words detected (`kv_0860s_…`).

## transcripts/
`keyed_video_faster_whisper.json` (whole take, word timings), `B0002_premiere_transcript.{csv,json}` (Premiere speech-to-text of B0002),
`Keyed-Video.MediaInfo.txt`.

## prproj/ (all saved by real Premiere, project version 45)
- `premiere_saved_small_6seq.prproj` — 25 KB, 6 sequences, 4 markers, transitions, effects
- `premiere_saved_real_episode_full.prproj` — 3.7 MB, the finished episode (17+ sequences, MOGRTs, transitions, effects); real-world anatomy sample

**Still missing** (need live Premiere, see docs/PLAN.md 0.3): empty template, project with exactly 1 marker,
exactly 1 MOGRT, exactly 1 transition, an effect on a track.

## script/
`modnaya_propaganda_script.pdf` — PDF export of the script (no comments; the Google Doc must still be read through the API, stage 0.7).
