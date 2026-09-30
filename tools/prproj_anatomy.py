# -*- coding: utf-8 -*-
"""Dump the anatomy of a Premiere .prproj (gzip XML) and check the invariants MarkFlow's validator will rely on.
    python tools/prproj_anatomy.py file.prproj
"""
import collections, gzip, sys
from lxml import etree

TICKS = 254016000000  # per second

def load(path):
    raw = open(path, "rb").read()
    try: raw = gzip.decompress(raw)
    except OSError: pass
    return etree.fromstring(raw)

def invariants(root):
    ids, uids, dup = {}, {}, []
    # Only DIRECT children of <PremiereData> share one ID namespace. Objects nested inside the Project's
    # <Properties> (ProjectViewState, columns ...) reuse small numbers (1, 2, 3 ...) on purpose.
    for e in root:
        if e.get("ObjectID") and e.get("ClassID"):
            if e.get("ObjectID") in ids: dup.append(("ObjectID", e.get("ObjectID")))
            ids[e.get("ObjectID")] = e
        if e.get("ObjectUID") and e.get("ClassID"):
            if e.get("ObjectUID") in uids: dup.append(("ObjectUID", e.get("ObjectUID")))
            uids[e.get("ObjectUID")] = e
    broken = []
    for top in root:
        if top.tag == "Project" and top.get("ClassID"): continue   # nested view-state scope, refs resolve locally
        for e in top.iter():
            for k, tbl in (("ObjectRef", ids), ("ObjectURef", uids)):
                if e.get(k) is not None and e.get(k) not in tbl and not e.get("ClassID"):
                    broken.append((e.tag, k, e.get(k)))
    return ids, uids, dup, broken

def main(path):
    root = load(path); ids, uids, dup, broken = invariants(root)
    print(f"{path}\n  root: {root.tag} Version={root.get('Version')}  objects by ID: {len(ids)}  by UID: {len(uids)}")
    print(f"  duplicate ids: {len(dup)}   unresolved refs: {len(broken)} {broken[:3]}")
    proj = ids["1"]; print("  Project Version:", proj.get("Version"))
    seqs = [e for e in uids.values() if e.tag == "Sequence"]
    print(f"  sequences: {len(seqs)}")
    for s in seqs[:60]:
        print("   -", s.findtext("Name"), "| track groups:", len(s.findall("TrackGroups/TrackGroup")))
    allobj = list(ids.values()) + list(uids.values())
    kinds = collections.Counter(e.tag for e in allobj)
    for k in ("VideoClipTrackItem", "AudioClipTrackItem", "VideoTransitionTrackItem", "AudioTransitionTrackItem", "Marker", "SubClip", "MasterClip"):
        print(f"  {k}: {kinds.get(k, 0)}")
    ends = [int(e.findtext("ClipTrackItem/TrackItem/End")) for e in ids.values() if e.tag == "VideoClipTrackItem" and e.findtext("ClipTrackItem/TrackItem/End")]
    if ends: print(f"  latest video item end: {max(ends)/TICKS:.2f} s")
    fr = {e.findtext("TrackGroup/FrameRate") for e in ids.values() if e.tag == "VideoTrackGroup"}
    print("  video FrameRate ticks/frame:", fr, "-> fps", [round(TICKS / int(f), 3) for f in fr if f])

if __name__ == "__main__": main(sys.argv[1])
