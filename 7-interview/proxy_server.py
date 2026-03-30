#!/usr/bin/env python3
"""
Local proxy server for YouTube Meeting Analyzer.
Runs on http://localhost:8888  —  uses yt-dlp + SQLite for persistent storage.

Usage:  python3 proxy_server.py
"""
import json, os, re, sqlite3, subprocess, sys, tempfile, threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT      = 8888
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.join(BASE_DIR, "videos.db")
CACHE_DIR = os.path.join(BASE_DIR, ".audio_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

_lock = threading.Lock()


# ── Database ──────────────────────────────────────────────────────

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id          TEXT PRIMARY KEY,
                url         TEXT,
                title       TEXT,
                analyzed_at TEXT,
                cues        TEXT
            )
        """)
        conn.commit()

def db_get(video_id: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT id, url, title, analyzed_at, cues FROM videos WHERE id=?", (video_id,)
        ).fetchone()

def db_save(video_id: str, url: str, title: str, cues: list):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO videos (id, url, title, analyzed_at, cues) VALUES (?,?,?,?,?)",
            (video_id, url, title, datetime.now().isoformat(), json.dumps(cues))
        )
        conn.commit()

def db_history():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, url, title, analyzed_at, json_array_length(cues) AS cue_count "
            "FROM videos ORDER BY analyzed_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

def db_delete(video_id: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM videos WHERE id=?", (video_id,))
        conn.commit()


# ── Transcript ────────────────────────────────────────────────────

def _is_chinese(lang_code: str) -> bool:
    return lang_code.startswith('zh') or lang_code in ('cmn', 'yue', 'zh')


def fetch_transcript_and_title(video_id: str) -> tuple[list[dict], str]:
    """Fetch transcript keeping original text; add bilingual subtitle translation."""
    from youtube_transcript_api import YouTubeTranscriptApi
    url = f"https://www.youtube.com/watch?v={video_id}"

    # ── Title ──
    title = video_id
    try:
        r = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--print", "title",
             "--no-download", "--no-warnings", url],
            capture_output=True, text=True, timeout=30
        )
        title = r.stdout.strip() or video_id
    except Exception:
        pass

    # ── Captions via youtube-transcript-api ──
    cues = None
    lang = 'en'
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        try:
            transcript = transcript_list.find_transcript(
                ['en', 'en-US', 'en-GB', 'en-AU', 'en-CA']
            )
        except Exception:
            transcript = next(iter(transcript_list))

        lang = transcript.language_code
        print(f"[yt]    captions    {video_id}  lang={lang}")
        fetched = transcript.fetch()
        cues = []
        for entry in fetched:
            text = str(entry.text).replace('\n', ' ').strip()
            if text:
                cues.append({"start": float(entry.start), "text": text})
        if not cues:
            cues = None
    except Exception as e:
        print(f"[yt]    transcript-api failed: {e} — trying yt-dlp subtitles…")

    # ── Fallback 1: yt-dlp auto-generated subtitles ──
    if not cues:
        cues = _fetch_subtitles_ytdlp(video_id, url)

    # ── Fallback 2: Whisper speech-to-text ──
    if not cues:
        print(f"[yt]    no captions — transcribing with Whisper…")
        cues, lang = _transcribe_whisper(video_id)

    if not cues:
        raise RuntimeError("No captions found and Whisper transcription failed.")

    # ── Add bilingual subtitle translations ──
    # Chinese → English subtitle; everything else → Chinese subtitle
    if _is_chinese(lang):
        trans_target, trans_source = 'en', lang
        print(f"[tr]    adding EN subtitles for {video_id}  ({lang}→en)…")
    else:
        trans_target, trans_source = 'zh-CN', lang
        print(f"[tr]    adding ZH subtitles for {video_id}  ({lang}→zh-CN)…")

    cues = _add_subtitle_translations(cues, source=trans_source, target=trans_target)
    print(f"[tr]    subtitles done")

    return cues, title


def _fetch_subtitles_ytdlp(video_id: str, url: str) -> list[dict] | None:
    """Fallback: download auto-generated subtitles via yt-dlp and parse VTT."""
    import re as _re, tempfile as _tmp
    print(f"[yt]    yt-dlp subs  {video_id}  …")
    with _tmp.TemporaryDirectory() as tmpdir:
        out_tmpl = os.path.join(tmpdir, "%(id)s.%(ext)s")
        result = subprocess.run([
            sys.executable, "-m", "yt_dlp",
            "--write-auto-sub", "--sub-lang", "en",
            "--skip-download", "--no-warnings",
            "-o", out_tmpl, url
        ], capture_output=True, text=True, timeout=60)

        # Find the downloaded subtitle file
        vtt_path = None
        for fname in os.listdir(tmpdir):
            if fname.endswith(".vtt") or fname.endswith(".srv3") or fname.endswith(".ttml"):
                vtt_path = os.path.join(tmpdir, fname)
                break

        if not vtt_path:
            print(f"[yt]    no subtitle file found. stderr: {result.stderr[:200]}")
            return None

        print(f"[yt]    parsing     {os.path.basename(vtt_path)}")
        return _parse_vtt(open(vtt_path, encoding="utf-8").read())


def _parse_vtt(content: str) -> list[dict] | None:
    """Parse WebVTT subtitle file into cues list."""
    import re as _re
    TIME_RE = _re.compile(
        r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[.,](\d{3})"
    )
    cues = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        m = TIME_RE.match(lines[i].strip())
        if m:
            h, mn, s, ms = int(m[1]), int(m[2]), int(m[3]), int(m[4])
            start = h * 3600 + mn * 60 + s + ms / 1000
            i += 1
            text_lines = []
            while i < len(lines) and lines[i].strip():
                # Strip VTT tags like <00:00:00.000><c>word</c>
                clean = _re.sub(r"<[^>]+>", "", lines[i]).strip()
                if clean:
                    text_lines.append(clean)
                i += 1
            text = " ".join(text_lines).strip()
            if text:
                cues.append({"start": start, "text": text})
        else:
            i += 1
    # Deduplicate consecutive identical cues (VTT often has overlapping entries)
    deduped = []
    for cue in cues:
        if not deduped or cue["text"] != deduped[-1]["text"]:
            deduped.append(cue)
    return deduped or None


def _transcribe_whisper(video_id: str) -> tuple[list[dict] | None, str]:
    """Download audio and transcribe with Whisper, keeping original language text."""
    try:
        import whisper
        audio_path, _ = get_audio_path(video_id)
        print(f"[whisper] loading model 'base'…")
        model = whisper.load_model("base")
        print(f"[whisper] transcribing {audio_path}…")
        result = model.transcribe(audio_path, verbose=False, fp16=False, task="transcribe")
        lang = result.get("language", "en")
        print(f"[whisper] detected lang={lang}")
        cues = []
        for seg in result.get("segments", []):
            text = seg.get("text", "").strip()
            if text:
                cues.append({"start": float(seg["start"]), "text": text})
        print(f"[whisper] done  {len(cues)} segments")
        return (cues or None), lang
    except Exception as e:
        print(f"[whisper] failed: {e}")
        return None, "en"


def _add_subtitle_translations(cues: list[dict], source: str, target: str) -> list[dict]:
    """Add a 'subtitle' field to each cue with translation in the target language."""
    from deep_translator import GoogleTranslator
    CHAR_LIMIT = 2000
    chunks: list[tuple[int, int, str]] = []
    start, buf, buf_len = 0, [], 0
    for i, cue in enumerate(cues):
        line = cue["text"]
        if buf and buf_len + len(line) + 1 > CHAR_LIMIT:
            chunks.append((start, i, "\n".join(buf)))
            start, buf, buf_len = i, [], 0
        buf.append(line)
        buf_len += len(line) + 1
    if buf:
        chunks.append((start, len(cues), "\n".join(buf)))

    result = [dict(c) for c in cues]  # copy
    for ci, (s, e, text) in enumerate(chunks):
        try:
            translated = GoogleTranslator(source=source, target=target).translate(text)
            lines = translated.split("\n")
            for j in range(e - s):
                result[s + j]["subtitle"] = lines[j].strip() if j < len(lines) else ""
            print(f"[tr]    subtitle chunk {ci+1}/{len(chunks)} done  ({e-s} cues)")
        except Exception as ex:
            print(f"[tr]    subtitle chunk {ci+1} failed: {ex}")
            for j in range(e - s):
                result[s + j]["subtitle"] = ""
    return result


def _translate_cues(cues: list[dict], source: str = 'auto') -> list[dict]:
    """
    Translate cues to English efficiently.
    Join texts with newlines (Google Translate preserves them),
    split chunks by char count to stay under the 4500-char limit.
    """
    from deep_translator import GoogleTranslator

    CHAR_LIMIT = 2000

    # Build chunks: list of (start_idx, end_idx, joined_text)
    chunks: list[tuple[int, int, str]] = []
    start = 0
    buf   = []
    buf_len = 0

    for i, cue in enumerate(cues):
        line = cue["text"]
        if buf and buf_len + len(line) + 1 > CHAR_LIMIT:
            chunks.append((start, i, "\n".join(buf)))
            start, buf, buf_len = i, [], 0
        buf.append(line)
        buf_len += len(line) + 1

    if buf:
        chunks.append((start, len(cues), "\n".join(buf)))

    print(f"[tr]    {len(cues)} cues → {len(chunks)} chunks")

    translated = list(cues)  # copy

    for ci, (s, e, text) in enumerate(chunks):
        try:
            result = GoogleTranslator(source=source, target='en').translate(text)
            lines  = result.split("\n")
            batch  = cues[s:e]
            # Align: if line count matches, map 1-to-1; else join remainder into last
            for j, cue in enumerate(batch):
                translated_text = lines[j].strip() if j < len(lines) else cue["text"]
                translated[s + j] = {"start": cue["start"], "text": translated_text or cue["text"]}
            print(f"[tr]    chunk {ci+1}/{len(chunks)} done  ({e-s} cues)")
        except Exception as ex:
            print(f"[tr]    chunk {ci+1} failed: {ex} — keeping originals")

    return translated


# ── TTS dubbing ───────────────────────────────────────────────────

TTS_DIR = os.path.join(BASE_DIR, ".tts_cache")
os.makedirs(TTS_DIR, exist_ok=True)

def get_tts_path(video_id: str) -> str:
    return os.path.join(TTS_DIR, f"{video_id}_en.mp3")

async def _generate_tts_async(video_id: str, cues: list[dict]) -> str:
    """Generate time-aligned English TTS audio from translated cues."""
    import asyncio, tempfile
    import edge_tts
    from pydub import AudioSegment

    out_path = get_tts_path(video_id)
    total_duration_ms = int((cues[-1]["start"] + 5) * 1000)  # +5s buffer at end

    print(f"[tts]   building {len(cues)} cues, ~{total_duration_ms//1000}s total")
    timeline = AudioSegment.silent(duration=total_duration_ms)

    # Generate TTS for each cue and place at correct timestamp
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, cue in enumerate(cues):
            text = cue["text"].strip()
            if not text:
                continue
            start_ms = int(cue["start"] * 1000)
            seg_path = os.path.join(tmpdir, f"seg_{i:04d}.mp3")
            try:
                communicate = edge_tts.Communicate(text, voice="en-US-AriaNeural")
                await communicate.save(seg_path)
                seg = AudioSegment.from_mp3(seg_path)
                # Speed up if segment overruns the next cue's start time
                if i + 1 < len(cues):
                    slot_ms = int((cues[i+1]["start"] - cue["start"]) * 1000)
                    if len(seg) > slot_ms and slot_ms > 100:
                        speed = len(seg) / slot_ms
                        speed = min(speed, 2.0)  # cap at 2x
                        # Use ffmpeg to speed up
                        fast_path = seg_path + "_fast.mp3"
                        subprocess.run([
                            "ffmpeg", "-y", "-i", seg_path,
                            "-filter:a", f"atempo={speed:.3f}",
                            fast_path
                        ], capture_output=True)
                        if os.path.exists(fast_path):
                            seg = AudioSegment.from_mp3(fast_path)
                timeline = timeline.overlay(seg, position=start_ms)
            except Exception as e:
                print(f"[tts]   cue {i} failed: {e}")
            if (i + 1) % 50 == 0:
                print(f"[tts]   {i+1}/{len(cues)} cues processed")

    timeline.export(out_path, format="mp3")
    size_mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"[tts]   done → {out_path} ({size_mb:.1f} MB)")
    return out_path

def generate_tts(video_id: str, cues: list[dict]) -> str:
    import asyncio
    return asyncio.run(_generate_tts_async(video_id, cues))


# ── Audio ─────────────────────────────────────────────────────────

def get_audio_path(video_id: str) -> tuple[str, str]:
    for ext in ("m4a", "webm", "mp3", "ogg"):
        cached = os.path.join(CACHE_DIR, f"{video_id}.{ext}")
        if os.path.exists(cached):
            return cached, ext

    out_tmpl = os.path.join(CACHE_DIR, f"{video_id}.%(ext)s")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bestaudio[ext=m4a]/bestaudio",
        "--no-warnings", "-o", out_tmpl,
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    for ext in ("m4a", "webm", "mp3", "ogg"):
        path = os.path.join(CACHE_DIR, f"{video_id}.{ext}")
        if os.path.exists(path):
            return path, ext
    raise RuntimeError(
        f"yt-dlp audio download failed.\n{(result.stderr + result.stdout)[:400]}"
    )


# ── HTTP handler ──────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/push-audio":
            video_id = self._require_video_id(params)
            if not video_id: return
            ext = params.get("ext", ["m4a"])[0]
            if ext not in ("m4a", "webm", "mp3", "ogg"):
                self._json(400, {"error": "Invalid ext"}); return
            length = int(self.headers.get("Content-Length", 0))
            data   = self.rfile.read(length)
            path   = os.path.join(CACHE_DIR, f"{video_id}.{ext}")
            with open(path, "wb") as f:
                f.write(data)
            print(f"[sync]  audio saved  {video_id}.{ext}  {len(data)//1024}KB")
            self._json(200, {"ok": True})
            return

        if parsed.path == "/push":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            try:
                data   = json.loads(body)
                videos = data.get("videos", [])
                count  = 0
                for v in videos:
                    if v.get("id") and v.get("cues"):
                        db_save(v["id"], v.get("url",""), v.get("title", v["id"]),
                                v["cues"] if isinstance(v["cues"], list) else json.loads(v["cues"]))
                        count += 1
                print(f"[sync]  pushed {count} videos")
                self._json(200, {"synced": count})
            except Exception as e:
                self._json(500, {"error": str(e)})
        else:
            self._json(404, {"error": "Not found"})

    def do_HEAD(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if parsed.path == "/audio":
            video_id = self._require_video_id(params)
            if not video_id: return
            try:
                path, ext = get_audio_path(video_id)
            except Exception as e:
                self._json(500, {"error": str(e)}); return
            size = os.path.getsize(path)
            self.send_response(200)
            self.send_header("Content-Type",   self._audio_mime(ext))
            self.send_header("Content-Length", str(size))
            self.send_header("Accept-Ranges",  "bytes")
            self._cors()
            self.end_headers()
        else:
            self.send_response(200); self._cors(); self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        p = parsed.path

        if p in ("/", "/index"):
            self._serve_file("youtube-analyzer.html", "text/html"); return
        if p == "/health":
            self._json(200, {"status": "ok"}); return
        if p == "/transcript":
            self._handle_transcript(params); return
        if p == "/history":
            self._handle_history(); return
        if p == "/delete":
            self._handle_delete(params); return
        if p == "/audio":
            self._handle_audio(params); return
        if p == "/tts":
            self._handle_tts(params); return

        self._json(404, {"error": "Not found"})

    # ── /transcript ──────────────────────────────────────────────

    def _handle_transcript(self, params):
        video_id = self._require_video_id(params)
        if not video_id: return

        # 1. DB cache
        row = db_get(video_id)
        if row:
            print(f"[db]    transcript  {video_id}  → '{row['title']}'")
            self._json(200, {
                "cues":        json.loads(row["cues"]),
                "title":       row["title"],
                "analyzed_at": row["analyzed_at"],
                "from_cache":  True,
            })
            return

        # 2. Fetch from YouTube
        print(f"[yt]    transcript  {video_id}  …")
        try:
            cues, title = fetch_transcript_and_title(video_id)
        except Exception as e:
            print(f"[err]   {e}")
            self._json(500, {"error": str(e)}); return

        url = f"https://www.youtube.com/watch?v={video_id}"
        db_save(video_id, url, title, cues)
        print(f"[db]    saved       {video_id}  '{title}'  ({len(cues)} cues)")
        self._json(200, {"cues": cues, "title": title, "analyzed_at": datetime.now().isoformat()})

    # ── /history ─────────────────────────────────────────────────

    def _handle_history(self):
        self._json(200, {"videos": db_history()})

    # ── /delete ──────────────────────────────────────────────────

    def _handle_delete(self, params):
        video_id = self._require_video_id(params)
        if not video_id: return
        db_delete(video_id)
        print(f"[db]    deleted     {video_id}")
        self._json(200, {"ok": True})

    # ── /audio ───────────────────────────────────────────────────

    def _handle_audio(self, params):
        video_id = self._require_video_id(params)
        if not video_id: return

        print(f"[yt]    audio       {video_id}  …")
        try:
            path, ext = get_audio_path(video_id)
        except Exception as e:
            print(f"[err]   {e}")
            self._json(500, {"error": str(e)}); return

        size     = os.path.getsize(path)
        mime     = self._audio_mime(ext)
        filename = f"audio_{video_id}.{ext}"
        print(f"[ok]    audio       {video_id}  {size/1024/1024:.1f} MB")

        range_header = self.headers.get("Range", "")
        if range_header.startswith("bytes="):
            spec  = range_header[6:]
            s_str, _, e_str = spec.partition("-")
            start  = int(s_str) if s_str else 0
            end    = int(e_str) if e_str else size - 1
            end    = min(end, size - 1)
            length = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type",   mime)
            self.send_header("Content-Range",  f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges",  "bytes")
            self.send_header("Content-Disposition", f'inline; filename="{filename}"')
            self.send_header("X-Filename", filename)
            self._cors(); self.end_headers()
            with open(path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk: break
                    try: self.wfile.write(chunk); remaining -= len(chunk)
                    except (BrokenPipeError, ConnectionResetError): break
        else:
            self.send_response(200)
            self.send_header("Content-Type",   mime)
            self.send_header("Content-Length", str(size))
            self.send_header("Accept-Ranges",  "bytes")
            self.send_header("Content-Disposition", f'inline; filename="{filename}"')
            self.send_header("X-Filename", filename)
            self._cors(); self.end_headers()
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk: break
                    try: self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError): break

    # ── /tts ─────────────────────────────────────────────────────

    def _handle_tts(self, params):
        video_id = self._require_video_id(params)
        if not video_id: return

        # Check cache
        tts_path = get_tts_path(video_id)
        if not os.path.exists(tts_path):
            row = db_get(video_id)
            if not row:
                self._json(404, {"error": "Video not found in DB — analyze first"}); return
            cues = json.loads(row["cues"])
            print(f"[tts]   generating TTS for {video_id} ({len(cues)} cues)…")
            try:
                with _lock:
                    if not os.path.exists(tts_path):
                        generate_tts(video_id, cues)
            except Exception as e:
                print(f"[err]   TTS: {e}")
                self._json(500, {"error": str(e)}); return

        size = os.path.getsize(tts_path)
        filename = f"tts_{video_id}_en.mp3"
        print(f"[ok]    tts  {video_id}  {size/1024/1024:.1f} MB")

        range_header = self.headers.get("Range", "")
        if range_header.startswith("bytes="):
            spec = range_header[6:]
            s_str, _, e_str = spec.partition("-")
            start = int(s_str) if s_str else 0
            end   = int(e_str) if e_str else size - 1
            end   = min(end, size - 1)
            length = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type",   "audio/mpeg")
            self.send_header("Content-Range",  f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges",  "bytes")
            self.send_header("Content-Disposition", f'inline; filename="{filename}"')
            self._cors(); self.end_headers()
            with open(tts_path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk: break
                    try: self.wfile.write(chunk); remaining -= len(chunk)
                    except (BrokenPipeError, ConnectionResetError): break
        else:
            self.send_response(200)
            self.send_header("Content-Type",   "audio/mpeg")
            self.send_header("Content-Length", str(size))
            self.send_header("Accept-Ranges",  "bytes")
            self.send_header("Content-Disposition", f'inline; filename="{filename}"')
            self._cors(); self.end_headers()
            with open(tts_path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk: break
                    try: self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError): break

    # ── helpers ──────────────────────────────────────────────────

    def _serve_file(self, filename: str, mime: str):
        path = os.path.join(BASE_DIR, filename)
        if not os.path.exists(path):
            self._json(404, {"error": f"{filename} not found"}); return
        with open(path, "rb") as f: data = f.read()
        self.send_response(200)
        self.send_header("Content-Type",   mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _require_video_id(self, params) -> str | None:
        vid_ids = params.get("v", [])
        if not vid_ids:
            self._json(400, {"error": "Missing ?v= parameter"}); return None
        video_id = vid_ids[0]
        if not re.fullmatch(r"[A-Za-z0-9_\-]{11}", video_id):
            self._json(400, {"error": "Invalid video ID"}); return None
        return video_id

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type",   "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors(); self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")
        self.send_header("Access-Control-Expose-Headers","Content-Range, Accept-Ranges, X-Filename")

    def _audio_mime(self, ext):
        return {"m4a":"audio/mp4","webm":"audio/webm","mp3":"audio/mpeg","ogg":"audio/ogg"}.get(ext,"audio/octet-stream")

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    init_db()
    server = HTTPServer(("localhost", PORT), Handler)
    print(f"✅  http://localhost:{PORT}")
    print(f"    /transcript?v=ID  — fetch & cache transcript")
    print(f"    /history          — list all saved videos")
    print(f"    /delete?v=ID      — remove from DB")
    print(f"    /audio?v=ID       — stream audio")
    print("    Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
