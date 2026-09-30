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
- `premiere_saved_small_6seq.prproj` — 25 KB, 2 sequences (an auto-cut test built as FCP XML, imported and saved by Premiere), 6 clips, 2 markers
- `premiere_saved_real_episode_full.prproj` — 3.7 MB, the finished episode (17+ sequences, MOGRTs, transitions, effects); real-world anatomy sample

**Still missing** (need live Premiere, see docs/PLAN.md 0.3): empty template, project with exactly 1 marker,
exactly 1 MOGRT, exactly 1 transition, an effect on a track.

## script/
- `modnaya_propaganda_script.pdf` — PDF export of the script (no comments).
- `modnaya_propaganda_gdoc_text_and_threads.json` — the Google Doc read through the Drive connector: text with `<comment_start id=kix..>` anchors + 146 comment threads (140 open, 6 resolved). Anchor ids do NOT map to thread ids here.
- `modnaya_propaganda_comments_anchored.json` — the same doc exported as .docx: 193 comments (140 threads + 53 replies) each with its anchored text, paragraph index, author, resolved flag. **Resolved threads are not in the .docx export.**
