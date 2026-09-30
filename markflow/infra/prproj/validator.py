"""Gate 2 checks on a .prproj (stage 3.1).

1. structure: unique root-level ObjectID/ObjectUID, every reference resolves (anatomy.md scope rule),
   every clip reaches its file, no overlaps on a track, timeline length == source window length,
   links and their counters agree;
2. the plan: the target sequence holds exactly the planned clips (count, positions, source windows, files)
   and markers;
3. originals untouched: every object of the base project is byte-identical in the output, except the
   containers a stage is allowed to extend (the target sequence, its tracks and its marker list).
"""

from __future__ import annotations

import copy
from collections import Counter

from lxml import etree

from markflow.domain.edit_plan import EditPlan
from markflow.infra.prproj.project import AUDIO_MEDIA_TYPE, VIDEO_MEDIA_TYPE, Project, norm_path
from markflow.infra.prproj.reader import item_info, read_sequence


def structure_problems(project: Project, limit: int = 50) -> list[str]:
    problems: list[str] = []
    ids, uids = Counter(), Counter()
    for e in project.root:
        if e.get("ClassID") is None:
            continue
        if e.get("ObjectID") is not None:
            ids[e.get("ObjectID")] += 1
        if e.get("ObjectUID") is not None:
            uids[e.get("ObjectUID")] += 1
    problems += [f"duplicate ObjectID {k}" for k, n in ids.items() if n > 1]
    problems += [f"duplicate ObjectUID {k}" for k, n in uids.items() if n > 1]

    for top in project.root:
        if top.tag == "Project" and top.get("ClassID"):
            continue  # nested view-state scope: refs resolve locally
        for e in top.iter():
            if e is not top and e.get("ClassID"):
                continue
            ref, uref = e.get("ObjectRef"), e.get("ObjectURef")
            if ref is not None and ref not in project.by_id:
                problems.append(f"unresolved ObjectRef {ref} in <{top.tag} {top.get('ObjectID') or top.get('ObjectUID')}>")
            if uref is not None and uref not in project.by_uid:
                problems.append(f"unresolved ObjectURef {uref} in <{top.tag} {top.get('ObjectID') or top.get('ObjectUID')}>")
        if len(problems) >= limit:
            return problems[:limit]

    link_count: Counter = Counter()
    for link in project.objects("Link"):
        for t in link.findall("TrackItemGroup/TrackItems/TrackItem"):
            link_count[t.get("ObjectRef")] += 1

    for seq in project.sequences():
        name = seq.findtext("Name")
        for kind, media_type in (("V", VIDEO_MEDIA_TYPE), ("A", AUDIO_MEDIA_TYPE)):
            for index, track in enumerate(project.tracks(seq, media_type)):
                if track is None:
                    problems.append(f"{name}: {kind}{index + 1} track object missing")
                    continue
                spans = []
                for item in project.track_items(track):
                    if item is None:
                        problems.append(f"{name}: {kind}{index + 1} refers to a missing item")
                        continue
                    info = item_info(project, item, "video" if kind == "V" else "audio", index)
                    ti = item.find("ClipTrackItem/TrackItem")
                    if ti.findtext("TrackIndex") is not None and int(ti.findtext("TrackIndex")) != index:
                        problems.append(f"{name}: item {info.object_id} TrackIndex != {index}")
                    if info.end <= info.start:
                        problems.append(f"{name}: item {info.object_id} has no length")
                    subclip = project.ref(item.find("ClipTrackItem/SubClip"))
                    clip = project.ref(subclip.find("Clip")) if subclip is not None else None
                    speed = float(clip.findtext("Clip/PlaybackSpeed") or 1) if clip is not None else 1.0
                    window = info.out_point - info.in_point
                    if info.media_path and window and abs((info.end - info.start) * speed - window) > 8_475_667_200:
                        problems.append(f"{name}: item {info.object_id} timeline length != source window")
                    if clip is None:
                        problems.append(f"{name}: item {info.object_id} has no clip")
                    stored = item.findtext("ClipTrackItem/LinkRefCount")  # Premiere omits it in native saves
                    lrc = int(stored) if stored is not None else link_count.get(info.object_id, 0)
                    if lrc != link_count.get(info.object_id, 0):
                        problems.append(f"{name}: item {info.object_id} LinkRefCount {lrc} != "
                                        f"{link_count.get(info.object_id, 0)} links")
                    spans.append((info.start, info.end, info.object_id))
                spans.sort()
                for (a0, a1, aid), (b0, b1, bid) in zip(spans, spans[1:]):
                    if b0 < a1:
                        problems.append(f"{name}: {kind}{index + 1} items {aid} and {bid} overlap")
        if len(problems) >= limit:
            break
    return problems[:limit]


def plan_problems(project: Project, plan: EditPlan, sequence_name: str, base: Project | None = None) -> list[str]:
    """`base`: the project the plan was written into (its own markers on the sequence are not the plan's)."""
    info = read_sequence(project, sequence_name)
    base_markers = len(read_sequence(base, sequence_name).markers) if base is not None else 0
    problems: list[str] = []
    def base_name(path: str) -> str:  # drives and folders differ between machines; the file name does not
        return norm_path(path).rsplit("/", 1)[-1]

    paths = {s.id: base_name(s.path) for s in plan.sources}
    expected: Counter = Counter()
    for c in plan.clips:
        if c.video_track is not None:
            expected[("video", c.video_track, c.start, c.end, c.source_in, c.source_out, paths[c.source_id])] += 1
        for t in c.audio_tracks:
            expected[("audio", t, c.start, c.end, c.source_in, c.source_out, paths[c.source_id])] += 1
    actual: Counter = Counter(
        (i.kind, i.track, i.start, i.end, i.in_point, i.out_point, base_name(i.media_path)) for i in info.items)
    if sum(expected.values()) != sum(actual.values()):
        problems.append(f"{sequence_name}: {sum(actual.values())} items on the timeline, plan has "
                        f"{sum(expected.values())}")
    for key, n in (expected - actual).items():
        problems.append(f"missing on the timeline: {key[0]} {key[1] + 1} at {key[2]} ({n}x) {key[6]}")
    for key, n in (actual - expected).items():
        problems.append(f"not in the plan: {key[0]} {key[1] + 1} at {key[2]} ({n}x) {key[6]}")
    covered = {(m.script_ref, m.start) for m in plan.markers if m.kind.value == "live_missing"}  # writer skips twins
    planned_markers = len(plan.markers) + sum(1 for t in plan.text_layers
                                              if (t.script_ref, t.start) not in covered)         + len(plan.subtitles) + base_markers
    if len(info.markers) != planned_markers:
        problems.append(f"{sequence_name}: {len(info.markers)} markers, plan has {planned_markers}")
    if plan.clips and info.duration < max(c.end for c in plan.clips):
        problems.append(f"{sequence_name}: timeline shorter than the plan")
    return problems[:100]


def _canonical(e: etree._Element) -> bytes:
    return etree.tostring(e, method="c14n")


def untouched_problems(base: Project, out: Project, sequence_name: str) -> list[str]:
    """Objects of the base project that changed or vanished (allowed: the target sequence's containers)."""
    seq = base.sequence(sequence_name)
    allowed = {seq.get("ObjectUID")}
    for media_type in (VIDEO_MEDIA_TYPE, AUDIO_MEDIA_TYPE):
        allowed |= {t.get("ObjectUID") for t in base.tracks(seq, media_type) if t is not None}
    markers = seq.find("MarkerOwner/Markers")
    if markers is not None:
        allowed.add(markers.get("ObjectRef"))
    problems = []
    for key, e in list(base.by_id.items()) + list(base.by_uid.items()):
        other = out.by_id.get(key) if e.get("ObjectID") == key else out.by_uid.get(key)
        if other is None:
            problems.append(f"object {e.tag} {key} disappeared")
        elif key not in allowed and _canonical(e) != _canonical(other) and not _bin_only_grew(e, other):
            problems.append(f"object {e.tag} {key} was changed")
        if len(problems) >= 50:
            break
    return problems


def _bin_only_grew(base_el: etree._Element, out_el: etree._Element) -> bool:
    """The root bin may receive new master clips (items appended after the existing ones), nothing else."""
    if base_el.tag != "RootProjectItem":
        return False
    b_items = [(i.get("Index"), i.get("ObjectURef")) for i in base_el.findall("ProjectItemContainer/Items/Item")]
    o_items = [(i.get("Index"), i.get("ObjectURef")) for i in out_el.findall("ProjectItemContainer/Items/Item")]
    if o_items[:len(b_items)] != b_items:
        return False
    b, o = copy.deepcopy(base_el), copy.deepcopy(out_el)
    for x in (b, o):
        items = x.find("ProjectItemContainer/Items")
        if items is not None:
            items.getparent().remove(items)
    return _canonical(b) == _canonical(o)
