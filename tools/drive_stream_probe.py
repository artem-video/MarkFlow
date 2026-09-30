# -*- coding: utf-8 -*-
"""Stage 0.5: how to get the audio out of the 44.7 GB Keyed-Video on Google Drive.

    python tools/drive_stream_probe.py [--minutes 5] [--name Keyed-Video] [--creds path\\to\\service_account.json]

Measures, for the first N minutes of audio (16 kHz mono):
  control  local copy on disk
  A        Drive for Desktop virtual drive (G:\\ ...)  - time + network MB
  B        Drive API, ffmpeg reads over HTTPS (range requests) - needs a service account that can see the file
  C        Drive API, plain download of the first ~1 GB - throughput, extrapolated to the full file
Writes bench_out/drive.md. Sources are only read.
"""
import argparse, glob, json, os, string, subprocess, sys, time
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
LOCAL = HOME / "Videos" / "Макашенец" / "МОДНАЯ ПРОПАГАНДА"

def find_ffmpeg():
    import shutil
    p = shutil.which("ffmpeg")
    if p: return p
    for p in glob.glob(str(HOME / ".stacher" / "**" / "ffmpeg.exe"), recursive=True): return p
    sys.exit("ffmpeg not found")

def net_bytes():
    import psutil
    return psutil.net_io_counters().bytes_recv

def timed_extract(ff, src, minutes, out, extra=()):
    t0, n0 = time.time(), net_bytes()
    r = subprocess.run([ff, "-v", "error", "-y", *extra, "-i", src, "-t", str(minutes * 60), "-vn", "-map", "0:a:0",
                        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", out], capture_output=True, text=True)
    el, mb = time.time() - t0, (net_bytes() - n0) / 1e6
    ok = r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1e6
    return dict(ok=ok, seconds=round(el, 1), net_mb=round(mb), err=(r.stderr or "")[-300:])

def find_desktop_file(name):
    for d in string.ascii_uppercase[6:]:                      # G: ...
        root = f"{d}:\\"
        if not os.path.isdir(root): continue
        for base in (root + ".shortcut-targets-by-id", root + "My Drive", root + "Мой диск", root):
            if not os.path.isdir(base): continue
            for dp, dn, fn in os.walk(base):
                if dp.count(os.sep) - base.count(os.sep) > 4: dn[:] = []; continue
                for f in fn:
                    if f.startswith(name) and f.lower().endswith((".mov", ".mp4")): return os.path.join(dp, f)
    return None

def drive_token_and_file(creds, name):
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    c = service_account.Credentials.from_service_account_file(creds, scopes=["https://www.googleapis.com/auth/drive.readonly"])
    s = AuthorizedSession(c)
    r = s.get("https://www.googleapis.com/drive/v3/files", params={"q": f"name contains '{name}' and trashed=false",
              "fields": "files(id,name,size,mimeType)", "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"})
    r.raise_for_status(); fl = r.json().get("files", [])
    if not fl: return None, None, None
    c.refresh(__import__("google.auth.transport.requests", fromlist=["Request"]).Request())
    return c.token, fl[0], s

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--minutes", type=float, default=5)
    ap.add_argument("--name", default="Keyed-Video"); ap.add_argument("--creds", default="")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "bench_out")); a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True); ff = find_ffmpeg(); res = {}
    tmp = str(out / "_probe.wav")

    loc = first = next(iter(glob.glob(str(LOCAL / f"*{a.name}*.mov"))), None)
    if loc: res["control_local"] = timed_extract(ff, loc, a.minutes, tmp)
    print("control:", res.get("control_local"))

    g = find_desktop_file(a.name)
    if g:
        res["A_drive_for_desktop"] = dict(path=g, **timed_extract(ff, g, a.minutes, tmp))
    else:
        res["A_drive_for_desktop"] = dict(ok=False, err="file not found on any G:..Z: virtual drive (is Drive for Desktop running, file available?)")
    print("A:", res["A_drive_for_desktop"])

    creds = a.creds or next(iter(glob.glob(str(HOME / "premiere-assembler-python" / "credentials" / "*.json"))), "")
    if creds and os.path.exists(creds):
        try:
            tok, f, sess = drive_token_and_file(creds, a.name)
            if not f: res["B_api_ffmpeg"] = res["C_api_download"] = dict(ok=False, err="service account does not see the file (share it with the account e-mail)")
            else:
                url = f"https://www.googleapis.com/drive/v3/files/{f['id']}?alt=media&supportsAllDrives=true"
                res["B_api_ffmpeg"] = timed_extract(ff, url, a.minutes, tmp, extra=("-headers", f"Authorization: Bearer {tok}\r\n"))
                t0 = time.time(); got = 0; want = 1_000_000_000
                with sess.get(url, headers={"Range": f"bytes=0-{want-1}"}, stream=True) as r:
                    for ch in r.iter_content(1 << 20):
                        got += len(ch)
                        if got >= want: break
                el = time.time() - t0; mbps = got / 1e6 / el
                size = int(f.get("size", 0))
                res["C_api_download"] = dict(ok=True, mb_per_s=round(mbps, 1), sample_mb=round(got / 1e6),
                                              full_file_gb=round(size / 1e9, 1), est_full_minutes=round(size / 1e6 / mbps / 60, 1))
        except Exception as e:
            res["B_api_ffmpeg"] = res["C_api_download"] = dict(ok=False, err=repr(e)[:300])
    else:
        res["B_api_ffmpeg"] = res["C_api_download"] = dict(ok=False, err="no service-account json found (pass --creds)")
    print("B:", res["B_api_ffmpeg"]); print("C:", res["C_api_download"])
    if os.path.exists(tmp): os.remove(tmp)

    md = [f"# Google Drive probe (stage 0.5) - first {a.minutes:g} min of audio from '{a.name}'", "", f"Generated {time.strftime('%Y-%m-%d %H:%M')}", "",
          "| method | ok | seconds | network MB | notes |", "|---|---|---|---|---|"]
    for k, v in res.items():
        note = v.get("err") or v.get("path") or (f"{v.get('mb_per_s')} MB/s; full file {v.get('full_file_gb')} GB ~ {v.get('est_full_minutes')} min" if "mb_per_s" in v else "")
        md.append(f"| {k} | {v.get('ok')} | {v.get('seconds','-')} | {v.get('net_mb','-')} | {str(note).replace('|','/')[:200]} |")
    (out / "drive.md").write_text("\n".join(md), encoding="utf-8"); (out / "drive.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(md))

if __name__ == "__main__":
    main()
