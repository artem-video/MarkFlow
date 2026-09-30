# -*- coding: utf-8 -*-
"""Stage 0.4 ASR benchmark (runs on Artem's Windows PC, GPU).

    python tools/bench_asr.py all            # prepare clips -> run every model -> write report
    python tools/bench_asr.py prepare|run|report [--models a,b] [--clips x,y]

Everything is written to  <out>/  (default: bench_out next to this script's parent).
Resumable: finished (model, clip) pairs are skipped. Reads sources, never modifies them.
"""
import argparse, glob, json, os, re, shutil, subprocess, sys, threading, time, wave
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
EP = HOME / "Videos" / "Макашенец" / "МОДНАЯ ПРОПАГАНДА"
SR = 16000

# id, source (glob ok), start s, duration s, reference (glob ok, optional), kind
CLIPS = [
    dict(id="b0002_10min", src=str(EP / "Копия 20260828_B0002.MP4"), start=600, dur=600,
         ref=None),   # Premiere transcript of B0002 uses a different time base (runs past the file end) - unusable as reference
    dict(id="keyed_5min", src=str(EP / "_test_downloads" / "keyed_audio_16k.wav"), start=60, dur=300, ref=None),
    dict(id="live_a_5min", src=str(EP / "Кто выращивает*.mp4"), start=60, dur=300,
         ref=str(EP / "Кто выращивает*.txt"), ref_kind="timed_txt"),
    dict(id="live_b_5min", src=str(EP / "Оправдать*.mp4"), start=60, dur=300,
         ref=str(EP / "Оправдать*.txt"), ref_kind="timed_txt"),
    # 5 min of a Varlamov short: give a path with  --varlamov "C:\...\file.mp4"
    dict(id="varlamov_5min", src=None, start=0, dur=300, ref=None),
]
MODELS = ["whisper-turbo", "gigaam-v2-rnnt", "gigaam-v3-rnnt", "parakeet-v3",
          "canary-v2", "fastconformer-ru", "t-one", "whisper-turbo-novad", "whisper-ru-novad"]
ONNX_IDS = {"gigaam-v2-rnnt": "gigaam-v2-rnnt", "gigaam-v3-rnnt": "gigaam-v3-rnnt", "parakeet-v3": "nemo-parakeet-tdt-0.6b-v3",
            "canary-v2": "nemo-canary-1b-v2", "fastconformer-ru": "nemo-fastconformer-ru-rnnt", "t-one": "t-tech/t-one"}
WHISPER = {  # name -> (repos to try in order, vad_filter)
    "whisper-turbo": (["large-v3-turbo"], True),
    "whisper-turbo-novad": (["large-v3-turbo"], False),
    "whisper-ru-novad": (["bzikst/faster-whisper-large-v3-russian", "Ash8181/whisper-large-v3-russian-ct2"], False),
}


# ---------------------------------------------------------------- helpers
def find_ffmpeg():
    for n in ("ffmpeg",):
        p = shutil.which(n)
        if p: return p
    for p in glob.glob(str(HOME / ".stacher" / "ffmpeg*")) + glob.glob(str(HOME / ".stacher" / "**" / "ffmpeg.exe"), recursive=True):
        if os.path.isfile(p): return p
    sys.exit("ffmpeg not found (PATH or %USERPROFILE%\\.stacher)")

def first(pattern):
    g = sorted(glob.glob(pattern))
    return g[0] if g else None

def norm_words(text):
    t = text.lower().replace("ё", "е")
    t = re.sub(r"[^\w\s]", " ", t)
    return t.split()

def wer_counts(ref, hyp):
    """Levenshtein on word lists -> (edits, len(ref))."""
    n, m = len(ref), len(hyp)
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        ri = ref[i - 1]
        for j in range(1, m + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ri != hyp[j - 1]))
        prev = cur
    return prev[m], n

def split_points(samples, sr, max_len=20.0, min_len=8.0):
    """Chunk boundaries (in samples) placed at the quietest 50 ms inside [min_len, max_len]."""
    import numpy as np
    win = int(0.05 * sr)
    n = len(samples)
    cuts, pos = [0], 0
    while n - pos > max_len * sr:
        a, b = pos + int(min_len * sr), pos + int(max_len * sr)
        seg = np.abs(samples[a:b]).astype("float32")
        k = (len(seg) // win) * win
        e = seg[:k].reshape(-1, win).mean(axis=1)
        pos = a + int(e.argmin()) * win + win // 2
        cuts.append(pos)
    cuts.append(n)
    return cuts

def tokens_to_words(tokens, stamps, total_end):
    """SentencePiece tokens ('▁' starts a word) + token start times -> [(word, start, end)]."""
    words, cur, st = [], "", None
    for tok, t in zip(tokens, stamps):
        if tok.startswith("▁") or tok.startswith(" ") or cur == "":
            if cur: words.append([cur, st, t])
            cur, st = tok.lstrip("▁ "), t
        else:
            cur += tok
    if cur: words.append([cur, st, total_end])
    return [(w, s, min(e, total_end)) for w, s, e in words if w.strip()]

def read_wav(path):
    import numpy as np
    with wave.open(path, "rb") as w:
        assert w.getframerate() == SR and w.getnchannels() == 1
        return np.frombuffer(w.readframes(w.getnframes()), dtype="int16").astype("float32") / 32768.0


# ---------------------------------------------------------------- prepare
def prepare(out, clips, varlamov):
    ff = find_ffmpeg()
    (out / "clips").mkdir(parents=True, exist_ok=True)
    for c in clips:
        src = varlamov if c["id"] == "varlamov_5min" else (first(c["src"]) if c["src"] else None)
        dst = out / "clips" / (c["id"] + ".wav")
        if dst.exists(): continue
        if not src:
            print(f"[prepare] {c['id']}: source not found - skipped"); continue
        print(f"[prepare] {c['id']} <- {src}")
        subprocess.run([ff, "-v", "error", "-y", "-ss", str(c["start"]), "-t", str(c["dur"]), "-i", src,
                        "-vn", "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(dst)], check=True)


# ---------------------------------------------------------------- models
class GpuWatch:
    """Peak GPU memory via nvidia-smi polling."""
    def __init__(self):
        self.peak, self.base, self._stop = 0, self.read(), False
    @staticmethod
    def read():
        try:
            o = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, timeout=5).stdout.strip().splitlines()[0]
            return int(o)
        except Exception:
            return 0
    def __enter__(self):
        def loop():
            while not self._stop:
                self.peak = max(self.peak, self.read()); time.sleep(0.5)
        self._t = threading.Thread(target=loop, daemon=True); self._t.start(); return self
    def __exit__(self, *a):
        self._stop = True; self._t.join(2)
    @property
    def used_mb(self): return max(0, self.peak - self.base)

def add_cuda_dlls():
    """faster-whisper (ctranslate2) needs cuBLAS 12 / cuDNN 9 DLLs: pip nvidia-* wheels ship them."""
    if os.name != "nt": return
    import site
    for sp in site.getsitepackages() + [site.getusersitepackages()]:
        for d in glob.glob(os.path.join(sp, "nvidia", "*", "bin")):
            try: os.add_dll_directory(d); os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]
            except Exception: pass

def load_model(name):
    """-> (transcribe(wav_path) -> [(word, start, end)], device_note)"""
    if name in WHISPER:
        add_cuda_dlls()
        from faster_whisper import WhisperModel
        repos, vad = WHISPER[name]; m = None; dev = "cuda/float16"; err = None
        for repo in repos:
            try: m = WhisperModel(repo, device="cuda", compute_type="float16"); break
            except Exception as e:
                err = e; print(f"  ! {repo}: {str(e)[:160]}")
        if m is None:
            raise RuntimeError(f"cannot load any of {repos}: {err}")
        def run(path):
            kw = dict(language="ru", word_timestamps=True, vad_filter=vad, condition_on_previous_text=False)
            if not vad:   # keep everything the model hears: retakes, whispers, commands
                kw.update(no_speech_threshold=None, log_prob_threshold=None, compression_ratio_threshold=None)
            segs, _ = m.transcribe(path, **kw)
            return [(w.word.strip(), w.start, w.end) for s in segs for w in (s.words or []) if w.word.strip()]
        return run, dev
    add_cuda_dlls()
    import onnx_asr, onnxruntime as ort
    try: ort.preload_dlls()
    except Exception: pass
    mid = ONNX_IDS[name]
    prov = ["CUDAExecutionProvider", "CPUExecutionProvider"] if "CUDAExecutionProvider" in ort.get_available_providers() else ["CPUExecutionProvider"]
    m = onnx_asr.load_model(mid, providers=prov).with_timestamps()
    dev = "onnx (GPU if VRAM>0, else CPU)"
    def run(path):
        x = read_wav(path); cuts = split_points(x, SR); out = []
        for a, b in zip(cuts, cuts[1:]):
            try: r = m.recognize(x[a:b], sample_rate=SR, language="ru")   # multilingual models (Canary) want the language
            except TypeError: r = m.recognize(x[a:b], sample_rate=SR)
            if r.tokens:
                ws = tokens_to_words(r.tokens, r.timestamps, (b - a) / SR)
                out += [(w, s + a / SR, e + a / SR) for w, s, e in ws]
        return out
    return run, dev

def run_all(out, models, clips, redo_cpu=True, force=False):
    (out / "hyp").mkdir(parents=True, exist_ok=True)
    for name in models:
        def done(c):
            p = out / "hyp" / f"{name}__{c['id']}.json"
            if force or not p.exists(): return False
            return json.load(open(p, encoding="utf-8")).get("device", "").startswith("cuda")   # redo anything that ran on CPU
        todo = [c for c in clips if (out / "clips" / (c["id"] + ".wav")).exists() and not done(c)]
        if not todo: continue
        print(f"\n=== {name}: loading")
        t0 = time.time()
        with GpuWatch() as gl:
            try: run, dev = load_model(name)
            except Exception as e: run = None; load_err = e
        if run is None:
            e = load_err
            print(f"  ! {name} cannot load: {e}"); (out / "hyp" / f"{name}__LOADERROR.txt").write_text(str(e), encoding="utf-8"); continue
        load_s = time.time() - t0
        on_gpu = gl.used_mb > 50   # model weights landed in GPU memory during load
        if name not in WHISPER:    # memory delta lies when the previous model left its memory reserved: ask onnxruntime directly
            try:
                import gc, onnxruntime as _ort
                ss = [o for o in gc.get_objects() if isinstance(o, _ort.InferenceSession)]
                if ss: on_gpu = all("CUDAExecutionProvider" in o.get_providers() for o in ss)
            except Exception: pass
        for c in todo:
            wav = str(out / "clips" / (c["id"] + ".wav")); dur = c["dur"]
            print(f"  {c['id']} ...", end="", flush=True)
            with GpuWatch() as g:
                t1 = time.time()
                try: words = run(wav)
                except Exception as e:
                    import traceback; print(" ERROR", str(e)[:200])
                    (out / "hyp" / f"{name}__{c['id']}__ERROR.txt").write_text(traceback.format_exc(), encoding="utf-8"); continue
                el = time.time() - t1
            if name not in WHISPER: dev_used = "cuda" if on_gpu else "CPU"
            else: dev_used = dev
            json.dump(dict(model=name, clip=c["id"], device=dev_used, load_s=round(load_s, 1), infer_s=round(el, 1),
                           audio_s=dur, rtfx=round(dur / el, 1), vram_mb=g.used_mb, words=[[w, round(s, 3), round(e, 3)] for w, s, e in words]),
                      open(out / "hyp" / f"{name}__{c['id']}.json", "w", encoding="utf-8"), ensure_ascii=False)
            print(f" {len(words)} words, {el:.0f}s ({dur/el:.1f}x realtime), VRAM +{g.used_mb} MB [{dev_used}]")
        del run
        import gc; gc.collect()


# ---------------------------------------------------------------- report
def load_ref(c, wavlen):
    """-> list of (start,end,text) blocks in clip time, or None."""
    if not c.get("ref"): return None
    p = first(c["ref"])
    if not p: return None
    a, b = c["start"], c["start"] + wavlen
    if c["ref_kind"] == "premiere_json":
        d = json.load(open(p, encoding="utf-8")); blocks = []
        for s in d["segments"]:
            for w in s["words"]:
                t = w["start"]   # absolute file time
                if a <= t < b: blocks.append((t - a, t - a + w["duration"], w["text"]))
        return blocks
    if c["ref_kind"] == "timed_txt":
        txt = open(p, encoding="utf-8-sig").read(); blocks = []
        for m in re.finditer(r"(\d+):(\d+):(\d+):(\d+)\s*-\s*(\d+):(\d+):(\d+):(\d+)\s*\n[^\n]*\n(.*?)(?=\n\d+:\d+:\d+:\d+\s*-|\Z)", txt, re.S):
            g = list(map(int, m.groups()[:8]))
            s = g[0]*3600 + g[1]*60 + g[2] + g[3]/25; e = g[4]*3600 + g[5]*60 + g[6] + g[7]/25
            if s >= a and e <= b: blocks.append((s - a, e - a, m.group(9).strip()))
        return blocks
    return None

def boundary_stats(words, samples):
    """Share of word boundaries that fall on loud audio (a cut there would clip live speech)."""
    import numpy as np
    if not words or len(samples) == 0: return None
    frame = int(0.02 * SR); n = len(samples) // frame
    env = np.sqrt((samples[:n*frame].reshape(n, frame) ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(env + 1e-9); speech = np.percentile(db, 90); thr = speech - 20
    bad_s = bad_e = 0
    for _, s, e in words:
        i = min(n - 1, int(s / 0.02)); j = min(n - 1, int(e / 0.02))
        bad_s += db[i] > thr; bad_e += db[j] > thr
    return round(100 * bad_s / len(words), 1), round(100 * bad_e / len(words), 1)

def report(out, models, clips):
    rows, hyps = [], {}
    for c in clips:
        wavp = out / "clips" / (c["id"] + ".wav")
        if not wavp.exists(): continue
        x = read_wav(str(wavp)); ref = load_ref(c, len(x) / SR)
        for m in models:
            p = out / "hyp" / f"{m}__{c['id']}.json"
            if p.exists(): hyps[(m, c["id"])] = json.load(open(p, encoding="utf-8"))
        base = hyps.get(("whisper-turbo", c["id"]))
        for m in models:
            h = hyps.get((m, c["id"]))
            if not h: continue
            hw = [(w, s, e) for w, s, e in h["words"]]
            r = dict(clip=c["id"], model=m, dev=h["device"], rtfx=h["rtfx"], infer=h["infer_s"], vram=h["vram_mb"], words=len(hw))
            if ref:
                a0, b0 = ref[0][0], ref[-1][1]
                rt = norm_words(" ".join(t for _, _, t in ref))
                ht = norm_words(" ".join(w for w, s, e in hw if a0 - 0.5 <= s <= b0 + 0.5))
                ed, n = wer_counts(rt, ht); r["wer_ref"] = round(100 * ed / max(n, 1), 1)
            if base and m != "whisper-turbo":
                ed, n = wer_counts(norm_words(" ".join(w for w, _, _ in base["words"])), norm_words(" ".join(w for w, _, _ in hw)))
                r["diff_vs_whisper"] = round(100 * ed / max(n, 1), 1)
            bs = boundary_stats(hw, x)
            if bs: r["loud_start"], r["loud_end"] = bs
            rows.append(r)
    md = ["# ASR benchmark (stage 0.4)", "", f"Generated {time.strftime('%Y-%m-%d %H:%M')}. RTFx = seconds of audio per second of work (higher = faster).", "",
          "- **WER vs ref**: against Premiere speech-to-text (B0002) or the channel's own transcript (lives) - both are themselves imperfect, so treat as relative.",
          "- **diff vs whisper**: word difference from Whisper large-v3-turbo (no reference for that clip).",
          "- **loud start/end %**: share of word boundaries sitting on loud audio (lower = safer cuts).", "",
          "| clip | model | device | RTFx | VRAM MB | words | WER vs ref % | diff vs whisper % | loud start/end % |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['clip']} | {r['model']} | {r['dev']} | {r['rtfx']} | {r['vram']} | {r['words']} | {r.get('wer_ref','-')} | {r.get('diff_vs_whisper','-')} | {r.get('loud_start','-')}/{r.get('loud_end','-')} |")
    (out / "asr.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md)); print(f"\nSaved: {out / 'asr.md'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prepare", "run", "report", "all"])
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "bench_out"))
    ap.add_argument("--models", default=",".join(MODELS)); ap.add_argument("--clips", default="")
    ap.add_argument("--varlamov", default=""); ap.add_argument("--force", action="store_true")
    a = ap.parse_args(); out = Path(a.out); models = a.models.split(",")
    clips = [c for c in CLIPS if not a.clips or c["id"] in a.clips.split(",")]
    if a.cmd in ("prepare", "all"): prepare(out, clips, a.varlamov)
    if a.cmd in ("run", "all"): run_all(out, models, clips, force=a.force)
    if a.cmd in ("report", "all"): report(out, models, clips)

if __name__ == "__main__":
    main()
