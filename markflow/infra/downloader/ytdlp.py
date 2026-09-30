"""Download the lives of a script once, at source quality, without re-encoding (PLAN 4.2).

One video = one file in the cache, named ``<channel>_<title>_<id>``; a repeated link is never downloaded twice.
A link that cannot be fetched (login needed, geo block, unsupported page) is recorded with the reason: the
timeline then carries a text layer with the link instead of a clip.

H.264 + AAC is preferred because Premiere imports it everywhere; when a platform offers a better picture only in
VP9/AV1 (YouTube above 1080p) that one is taken too and the codec is written to the index so the writer can warn.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import re
import subprocess
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from markflow.shared.links import live_key

FORMAT_TMPL = (
    "bv*[vcodec^=avc1][height<=H]+ba[ext=m4a]/b[vcodec^=avc1][height<=H]/bv*[height<=H]+ba/b[height<=H]/b"
)
NAME_TMPL = "%(channel,uploader)s_%(title).60s_%(id)s"


@dataclass
class LiveFile:
    key: str
    url: str
    path: str | None = None
    id: str | None = None
    title: str | None = None
    channel: str | None = None
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    vcodec: str | None = None
    error: str | None = None


class LiveDownloader:
    def __init__(self, cache: Path, yt_dlp: str = "yt-dlp", max_height: int = 1440, log=print,
                 extra_args: tuple[str, ...] = ()):
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.yt_dlp = yt_dlp
        self.max_height = max_height
        self.log = log
        self.extra_args = list(extra_args)  # e.g. --cookies-from-browser brave: read live from the browser, never saved
        self.index_path = self.cache / "index.json"
        self._lock = threading.Lock()
        self.index: dict[str, dict] = json.loads(self.index_path.read_text(encoding="utf-8")) \
            if self.index_path.exists() else {}

    def _save(self) -> None:
        with self._lock:
            tmp = self.index_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.index, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.index_path)

    def get(self, url: str) -> LiveFile | None:
        rec = self.index.get(live_key(url))
        return LiveFile(**rec) if rec else None

    def download(self, url: str) -> LiveFile:
        key = live_key(url)
        known = self.index.get(key)
        if known and known.get("path") and Path(known["path"]).exists():
            return LiveFile(**known)
        cmd = [self.yt_dlp, *self.extra_args, "--no-playlist", "--no-warnings", "--windows-filenames", "--no-part",
               "-f", FORMAT_TMPL.replace("H", str(self.max_height)), "--merge-output-format", "mp4",
               "-P", str(self.cache), "-o", NAME_TMPL + ".%(ext)s",
               "--print-to-file", "after_move:%(filepath)s\t%(id)s\t%(title)s\t%(channel,uploader)s\t%(duration)s\t"
               "%(width)s\t%(height)s\t%(vcodec)s", str(self.cache / ".last.tsv"),
               url]
        # one private result file per call: downloads run in parallel
        res_file = self.cache / f".{re.sub(r'[^A-Za-z0-9]+', '_', key)[:60]}.tsv"
        cmd[cmd.index(str(self.cache / ".last.tsv"))] = str(res_file)
        res_file.unlink(missing_ok=True)
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        rec = LiveFile(key=key, url=url)
        if r.returncode == 0 and res_file.exists():
            f = res_file.read_text(encoding="utf-8").strip().splitlines()[-1].split("\t")
            num = lambda s: None if s in ("NA", "") else float(s)  # noqa: E731
            rec.path, rec.id, rec.title, rec.channel = f[0], f[1], f[2], f[3]
            rec.duration, rec.vcodec = num(f[4]), f[7]
            rec.width = int(num(f[5])) if num(f[5]) else None
            rec.height = int(num(f[6])) if num(f[6]) else None
        else:
            lines = [ln for ln in (r.stderr or "").splitlines() if ln.startswith("ERROR")]
            rec.error = (lines[-1] if lines else (r.stderr or "unknown error").strip().splitlines()[-1])[:300]
        res_file.unlink(missing_ok=True)
        self.index[key] = asdict(rec)
        self._save()
        return rec

    def download_all(self, urls: list[str], workers: int = 3) -> list[LiveFile]:
        seen: dict[str, str] = {}
        for u in urls:
            seen.setdefault(live_key(u), u)
        todo = list(seen.values())
        done: list[LiveFile] = []
        with cf.ThreadPoolExecutor(workers) as ex:
            for rec in ex.map(self.download, todo):
                done.append(rec)
                state = f"OK  {rec.height}p {rec.vcodec}" if rec.path else f"FAIL {rec.error}"
                self.log(f"[{len(done)}/{len(todo)}] {rec.url[:70]} -> {state}")
        return done


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="download the lives listed in a text file (one link per line)")
    ap.add_argument("urls_file")
    ap.add_argument("cache")
    ap.add_argument("--yt-dlp", default="yt-dlp")
    ap.add_argument("--height", type=int, default=1440)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--cookies-from-browser", default=None, help="brave / chrome / firefox: for 18+ and Instagram")
    ap.add_argument("--no-check-certificates", action="store_true")
    a = ap.parse_args()
    extra = (("--cookies-from-browser", a.cookies_from_browser) if a.cookies_from_browser else ()) + (
        ("--no-check-certificates",) if a.no_check_certificates else ())
    urls = [ln.strip() for ln in Path(a.urls_file).read_text(encoding="utf-8").splitlines() if ln.strip()]
    LiveDownloader(Path(a.cache), a.yt_dlp, a.height, extra_args=extra).download_all(urls, a.workers)


if __name__ == "__main__":
    main()
