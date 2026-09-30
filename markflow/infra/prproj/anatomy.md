# .prproj anatomy (Premiere 26.0, project Version 45)

Derived from two projects **saved by real Premiere** (`tests/fixtures/prproj/`) with `tools/prproj_anatomy.py`.
Facts marked *(seen)* were observed in the fixtures; *(open)* still needs a minimal project saved by Premiere
(empty template, exactly 1 marker / 1 MOGRT / 1 transition / 1 track effect) to be confirmed.

## File
- gzip-compressed UTF-8 XML. Root `<PremiereData Version="3">`; first children: `<Project ObjectRef="1"/>` then the real `<Project ObjectID="1" ... Version="45">`.
- Time unit: **254 016 000 000 ticks / second**. Frame duration in ticks: 60 fps = 4 233 600 000, 30 = 8 467 200 000, 29.97 = 8 475 667 200 *(seen; the real episode mixes all three)*.
- Text is UTF-8 Cyrillic; paths appear twice: `<RelativePath>.\dir\file` and `<FilePath>C:\...` inside `<Media>`.

## Identity rules (important for the writer and validator)
- Every object is a **direct child of `<PremiereData>`** with `ObjectID="<int>"` (per-project counter) or `ObjectUID="<guid>"` (sequences, tracks, master clips, media) plus `ClassID` and `Version`.
- References are `ObjectRef="<int>"` / `ObjectURef="<guid>"` on empty child elements, e.g. `<SubClip ObjectRef="186"/>`.
- **ObjectIDs are unique only among direct children of `<PremiereData>`.** Objects nested inside the first `<Project>`'s `<Properties>` (ProjectViewState, columns, ...) reuse small numbers (1, 2, 3 ...) in their own scope, so a naive "all ObjectIDs unique" check reports 60-180 false duplicates. The validator must check the root-level scope only, and resolve refs inside the nested scope locally. *(seen: 0 duplicates and 0 unresolved refs in both fixtures with this rule)*

## Chain: timeline clip -> file
```
Sequence (UID) ── TrackGroups[0..2]: VideoTrackGroup, AudioTrackGroup, DataTrackGroup
  VideoTrackGroup ── TrackGroup/Tracks/Track Index=n ObjectURef=<VideoClipTrack UID>; TrackGroup/FrameRate = ticks per frame
    VideoClipTrack ── ClipTrack/ClipItems/TrackItems/TrackItem Index=i ObjectRef=<VideoClipTrackItem>
                      ClipTrack/TransitionItems (transition items live here, not in ClipItems)
      VideoClipTrackItem ── ClipTrackItem/TrackItem/{TrackIndex, Start, End, MediaType, Type}   (ticks; Start absent = 0)
                            ClipTrackItem/SubClip ObjectRef ; ClipTrackItem/ComponentOwner/Components ObjectRef (effect chain)
        SubClip ── Clip ObjectRef=<VideoClip> ; MasterClip ObjectURef ; Name
          VideoClip ── Clip/{InPoint, OutPoint (ticks in the source), Source ObjectRef=<VideoMediaSource>, FrameRate, MarkerOwner/Markers}
            VideoMediaSource ── MediaSource/Media ObjectURef=<Media> ; OriginalDuration (ticks)
              Media (UID) ── FilePath, RelativePath, Title, VideoStream/AudioStream refs, ConformedAudioRate
```
- A cut clip = one `VideoClipTrackItem` + one `AudioClipTrackItem` per audio channel track, each with its **own** `SubClip` -> `VideoClip`/`AudioClip` pair. Video and audio items are joined through `Link` objects (`LinkRefCount` on the items) and `PersistentGroupContainer/LinkContainer` in the Sequence *(seen)*.
- Item timeline position = `Start`..`End`; the source window is `InPoint`..`OutPoint` on the Clip. Source in/out and timeline duration must agree (`End-Start == OutPoint-InPoint` at speed 100 %).
- `MasterClip` (UID) is what appears in the Project panel: `Clips` (video+audio `Clip` refs), `AudioComponentChains`, `Name`. One master clip per imported file *(seen: 726 master clips in the real episode)*.

## Markers
- `<Markers ObjectID=..>` container (one per sequence/clip: `MarkerOwner/Markers`), children are `<Marker>` objects.
- Marker payload is JSON in `<DVAMarker>`: `{"DVAMarker":{"mComment":..., "mName":..., "mStartTime":{"ticks":N}, "mType":"Comment"}}` *(seen)*. Colour / duration keys *(open: need a marker with colour and duration)*.

## Transitions
- `VideoTransitionTrackItem` / `AudioTransitionTrackItem` sit in the track's `TransitionItems`, with `Start`/`End`, `DisplayName`, `MatchName` (e.g. `AE.AE_Impact_Pop`), `Alignment`, `HasIncomingClip`/`HasOutgoingClip`, and their own `VideoFilterComponent` *(seen: 156 video + 311 audio in the real episode)*.

## Effects
- `VideoFilterComponent` (UID/ID) with `MatchName` (`AE.ADBE Motion`, `AE.ADBE Opacity`, `AE.ADBE Lumetri`, `AE.Impact_Focus_Blur_FX`, ...), `DisplayName`, `Params` -> `VideoComponentParam`/`PointComponentParam`/`ArbVideoComponentParam`; opaque `PremiereFilterPrivateData` (base64) for some. Every clip carries Motion+Opacity by default *(seen)*.

## MOGRT / graphics
- A MOGRT on the timeline is an ordinary `VideoClipTrackItem` whose `TrackItem/Node/Properties` contains `BE.RushInspectorPanel.MogrtIdentifier` (GUID) and `VSMOffset`; its SubClip points to a media source of an `.aegraphic` file under `Motion Graphics Template Media\<guid>\name.aegraphic` *(seen: 172 in the real episode)*. Editable text/params live in the item's component chain *(open: minimal 1-MOGRT project)*.

## Numbers from the fixtures
| | small (`premiere_saved_small_6seq`) | real episode |
|---|---|---|
| sequences | 2 (this one was generated as FCP XML, imported and saved by Premiere) | 17 |
| video / audio track items | 6 / 6 | 3 146 / 4 161 |
| markers / transitions (v/a) | 2 / 0 | 12 / 156 / 311 |
| master clips | 8 | 726 |
| objects (root scope) | 339 | 132 410 |

## Rules that follow for `infra/prproj/writer` (draft)
1. Start from a project Premiere saved; never write a project from scratch.
2. Allocate new ObjectIDs as `max(root-level ObjectID)+1...`; new UIDs = uuid4; keep every ref resolvable.
3. Append items to a track's `ClipItems/TrackItems` with increasing `Index`, keep `Start` monotonic per track, no overlaps.
4. Never touch existing items (CLAUDE.md rule 1); a stage only adds.
5. Close the project in Premiere before writing (`*.prlock`), reopen after.
