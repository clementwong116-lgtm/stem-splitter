#!/usr/bin/env python3
"""Minimal vocal/instrumental stem splitter — stdlib HTTP + StemSplit / Demucs / ffmpeg."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import traceback
import uuid
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from stemsplit_client import StemSplitClient, StemSplitError

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"
STATIC_DIR = BASE_DIR / "static"
TEMPLATE = BASE_DIR / "templates" / "index.html"
JOBS_FILE = DATA_DIR / "jobs.json"

ALLOWED_EXT = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma"}
MAX_DURATION_SEC = 5 * 60
MAX_BYTES = 80 * 1024 * 1024
MODEL_NAME = os.environ.get("DEMUCS_MODEL", "htdemucs")
DEVICE = os.environ.get("DEMUCS_DEVICE", "cpu")
SEGMENT = os.environ.get("DEMUCS_SEGMENT", "7")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8765"))

# StemSplit / provider
STEMSPLIT_API_KEY = (os.environ.get("STEMSPLIT_API_KEY") or "").strip()
STEMSPLIT_BASE_URL = (
    os.environ.get("STEMSPLIT_BASE_URL") or "https://stemsplit.io"
).rstrip("/")
STEMSPLIT_QUALITY = os.environ.get("STEMSPLIT_QUALITY", "BALANCED").upper()
STEMSPLIT_OUTPUT_FORMAT = os.environ.get("STEMSPLIT_OUTPUT_FORMAT", "WAV").upper()
# stemsplit | demucs | ffmpeg | auto
STEM_PROVIDER = (os.environ.get("STEM_PROVIDER") or "auto").strip().lower()

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_jobs_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_jobs() -> None:
    if JOBS_FILE.exists():
        try:
            raw = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                _jobs.update(raw)
        except Exception:
            pass


def _save_jobs() -> None:
    with _jobs_lock:
        JOBS_FILE.write_text(
            json.dumps(_jobs, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _set_job(job_id: str, **fields: Any) -> None:
    with _jobs_lock:
        job = _jobs.setdefault(job_id, {"id": job_id})
        job.update(fields)
        job["updated_at"] = _now()
    _save_jobs()


def _demucs_available() -> bool:
    try:
        import importlib.util

        return (
            importlib.util.find_spec("demucs") is not None
            and importlib.util.find_spec("torch") is not None
        )
    except Exception:
        return False


def _stemsplit_configured() -> bool:
    return bool(STEMSPLIT_API_KEY)


def _resolve_provider() -> str:
    """Pick active separation backend.

    - STEM_PROVIDER=stemsplit|demucs|ffmpeg forces that path (stemsplit needs key).
    - STEM_PROVIDER=auto (default): prefer StemSplit when STEMSPLIT_API_KEY is set,
      else Demucs if installed, else ffmpeg mid/side.
    """
    forced = STEM_PROVIDER
    if forced in ("stemsplit", "demucs", "ffmpeg"):
        if forced == "stemsplit" and not _stemsplit_configured():
            # Fall back rather than hard-fail every upload at boot.
            return "demucs" if _demucs_available() else "ffmpeg"
        if forced == "demucs" and not _demucs_available():
            return "ffmpeg"
        return forced
    # auto
    if _stemsplit_configured():
        return "stemsplit"
    if _demucs_available():
        return "demucs"
    return "ffmpeg"


def _engine_name() -> str:
    p = _resolve_provider()
    if p == "ffmpeg":
        return "ffmpeg-midside"
    return p


def _stem_output_ext() -> str:
    """File extension used for downloaded stems under data/outputs/<id>/."""
    if _resolve_provider() == "stemsplit":
        fmt = STEMSPLIT_OUTPUT_FORMAT.lower()
        if fmt in ("mp3", "wav", "flac"):
            return f".{fmt}"
    return ".wav"


def _parse_multipart(body: bytes, content_type: str) -> dict[str, dict[str, Any]]:
    """Minimal multipart/form-data parser (stdlib only; cgi removed in 3.13)."""
    m = re.search(r"boundary=([^;]+)", content_type, flags=re.I)
    if not m:
        raise ValueError("missing boundary")
    boundary = m.group(1).strip().strip('"').encode("ascii", "ignore")
    if not boundary:
        raise ValueError("empty boundary")
    parts = body.split(b"--" + boundary)
    out: dict[str, dict[str, Any]] = {}
    for part in parts:
        if not part or part in (b"--", b"--\r\n", b"\r\n"):
            continue
        if part.startswith(b"--"):
            continue
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        header_blob, sep, data = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        headers = {}
        for line in header_blob.split(b"\r\n"):
            if b":" in line:
                k, v = line.split(b":", 1)
                headers[k.decode("latin-1").strip().lower()] = v.decode("latin-1").strip()
        disp = headers.get("content-disposition", "")
        name_m = re.search(r'name="([^"]+)"', disp)
        if not name_m:
            continue
        name = name_m.group(1)
        fn_m = re.search(r'filename="([^"]*)"', disp)
        filename = fn_m.group(1) if fn_m else None
        out[name] = {"filename": filename, "data": data}
    return out


def _probe_duration(path: Path) -> float | None:
    try:
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if r.returncode == 0 and r.stdout.strip():
            return float(r.stdout.strip())
    except Exception:
        return None
    return None


def _run_ffmpeg_midside(job_id: str, input_path: Path, out_root: Path) -> None:
    """Stereo mid/side: center≈vocals, sides≈instrumental. Crude but real split."""
    _set_job(
        job_id,
        status="processing",
        progress=20,
        message="使用 ffmpeg 中置／側邊分離（Demucs 未安裝時的後備方案）…",
        engine="ffmpeg-midside",
        provider="ffmpeg",
    )
    wav_in = out_root / "input_converted.wav"
    vocals = out_root / "vocals.wav"
    instr = out_root / "instrumental.wav"

    r0 = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-ac",
            "2",
            "-ar",
            "44100",
            str(wav_in),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if r0.returncode != 0:
        raise RuntimeError(r0.stderr[-1200:] or "ffmpeg convert failed")

    _set_job(job_id, progress=50, message="萃取人聲（中置）…")
    r1 = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(wav_in),
            "-af",
            "pan=mono|c0=0.5*c0+0.5*c1",
            str(vocals),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if r1.returncode != 0:
        raise RuntimeError(r1.stderr[-1200:] or "vocals extract failed")

    _set_job(job_id, progress=75, message="萃取伴奏（側邊）…")
    r2 = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(wav_in),
            "-af",
            "pan=stereo|c0=0.5*c0+-0.5*c1|c1=-0.5*c0+0.5*c1",
            str(instr),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if r2.returncode != 0:
        raise RuntimeError(r2.stderr[-1200:] or "instrumental extract failed")

    wav_in.unlink(missing_ok=True)


def _run_demucs(job_id: str, input_path: Path, out_root: Path) -> None:
    _set_job(
        job_id,
        status="processing",
        progress=5,
        message="Demucs 載入模型並分離中…",
        engine="demucs",
        provider="demucs",
    )
    cmd = [
        sys.executable,
        "-m",
        "demucs",
        "--two-stems=vocals",
        "-n",
        MODEL_NAME,
        "-d",
        DEVICE,
        "--segment",
        str(SEGMENT),
        "-o",
        str(out_root),
        str(input_path),
    ]
    if DEVICE == "cpu":
        cmd.extend(["--shifts", "0"])

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    lines: list[str] = []
    for line in proc.stdout:
        lines.append(line.rstrip())
        if any(k in line for k in ("% ", "Separating", "Downloading", "Torch")):
            prev = _jobs.get(job_id, {}).get("progress") or 10
            _set_job(
                job_id,
                progress=min(90, int(prev) + 5),
                message=(line.strip()[:200] or "處理中…"),
            )
    rc = proc.wait()
    (out_root / "demucs.log").write_text("\n".join(lines), encoding="utf-8")
    if rc != 0:
        raise RuntimeError("\n".join(lines[-40:]) or f"demucs exit {rc}")

    found = list(out_root.rglob("vocals.wav"))
    if not found:
        raise RuntimeError("demucs produced no vocals.wav")
    stem_dir = found[0].parent
    no_voc = stem_dir / "no_vocals.wav"
    if not no_voc.exists():
        raise RuntimeError("demucs produced no no_vocals.wav")
    shutil.copy2(found[0], out_root / "vocals.wav")
    shutil.copy2(no_voc, out_root / "instrumental.wav")


def _run_stemsplit(
    job_id: str,
    input_path: Path,
    out_root: Path,
    filename: str,
    *,
    mode: str = "split",
) -> None:
    if not _stemsplit_configured():
        raise StemSplitError(
            "STEMSPLIT_API_KEY 未設定", code="MISSING_API_KEY"
        )
    ext = _stem_output_ext()
    vocals = out_root / f"vocals{ext}"
    instr = out_root / f"instrumental{ext}"
    # Vocal remover: INSTRUMENTAL primary. Split mode: BOTH.
    output_type = "INSTRUMENTAL" if mode == "vocal_remover" else "BOTH"

    msg = (
        "透過 StemSplit API 消除人聲中…"
        if mode == "vocal_remover"
        else "透過 StemSplit API 分離中…"
    )
    _set_job(
        job_id,
        status="processing",
        progress=5,
        message=msg,
        engine="stemsplit",
        provider="stemsplit",
        stem_ext=ext,
        mode=mode,
        stemsplit_output_type=output_type,
    )

    client = StemSplitClient(STEMSPLIT_API_KEY, base_url=STEMSPLIT_BASE_URL)

    def on_progress(pct: int, msg: str) -> None:
        _set_job(job_id, progress=min(99, max(5, pct)), message=msg)

    remote = client.separate_file(
        input_path,
        filename=filename,
        out_vocals=vocals if output_type != "INSTRUMENTAL" else None,
        out_instrumental=instr,
        quality=STEMSPLIT_QUALITY,
        output_format=STEMSPLIT_OUTPUT_FORMAT,
        output_type=output_type,
        on_progress=on_progress,
    )
    _set_job(
        job_id,
        stemsplit_job_id=remote.get("id"),
        stem_ext=ext,
    )


def _find_stem_file(out_root: Path, stem: str) -> Path | None:
    for ext in (".wav", ".mp3", ".flac"):
        p = out_root / f"{stem}{ext}"
        if p.is_file():
            return p
    return None


def _audio_mime(path: Path) -> str:
    return {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".flac": "audio/flac",
    }.get(path.suffix.lower(), "application/octet-stream")


def _normalize_mode(raw: str | None) -> str:
    """UI modes: split (人聲／伴奏) | vocal_remover (人聲消除)."""
    m = (raw or "split").strip().lower().replace("-", "_")
    if m in ("vocal_remover", "vocalremover", "remover", "karaoke", "instrumental"):
        return "vocal_remover"
    return "split"


def _process_job(
    job_id: str, input_path: Path, filename: str, *, mode: str = "split"
) -> None:
    out_root = OUTPUT_DIR / job_id
    out_root.mkdir(parents=True, exist_ok=True)
    mode = _normalize_mode(mode)
    provider = _resolve_provider()
    try:
        if provider == "stemsplit":
            _run_stemsplit(job_id, input_path, out_root, filename, mode=mode)
        elif provider == "demucs":
            _run_demucs(job_id, input_path, out_root)
        else:
            _run_ffmpeg_midside(job_id, input_path, out_root)

        vocals = _find_stem_file(out_root, "vocals")
        instr = _find_stem_file(out_root, "instrumental")
        if mode == "vocal_remover":
            if not instr:
                raise RuntimeError("instrumental output missing")
        elif not vocals or not instr:
            raise RuntimeError("output stems missing")

        done_msg = (
            "人聲已消除，可下載伴奏／卡拉OK"
            if mode == "vocal_remover"
            else "完成"
        )
        stem_ext = (instr or vocals).suffix
        result: dict[str, Any] = {
            "status": "done",
            "progress": 100,
            "message": done_msg,
            "provider": provider,
            "engine": _engine_name(),
            "mode": mode,
            "stem_ext": stem_ext,
            "instrumental_url": f"/api/jobs/{job_id}/download/instrumental",
            "instrumental_stream": f"/api/jobs/{job_id}/stream/instrumental",
        }
        if vocals:
            result["vocals_url"] = f"/api/jobs/{job_id}/download/vocals"
            result["vocals_stream"] = f"/api/jobs/{job_id}/stream/vocals"
        _set_job(job_id, **result)
    except Exception as e:
        fail_msg = "人聲消除失敗" if mode == "vocal_remover" else "分離失敗"
        _set_job(
            job_id,
            status="error",
            progress=0,
            message=fail_msg,
            mode=mode,
            error=f"{e}\n{traceback.format_exc()[-800:]}",
        )


_load_jobs()


MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml",
}


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send_json(self, code: int, obj: Any) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(
        self,
        code: int,
        data: bytes,
        content_type: str,
        *,
        filename: str | None = None,
        cache: str = "no-store",
    ) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        if filename:
            self.send_header(
                "Content-Disposition", f'attachment; filename="{filename}"'
            )
        self.end_headers()
        self.wfile.write(data)

    def _send_file(
        self,
        path: Path,
        content_type: str | None = None,
        *,
        download_name: str | None = None,
        cache: str = "public, max-age=3600",
    ) -> None:
        if not path.is_file():
            self._send_json(404, {"detail": "not found"})
            return
        ctype = content_type or MIME.get(path.suffix.lower(), "application/octet-stream")
        data = path.read_bytes()
        self._send_bytes(
            200,
            data,
            ctype,
            filename=download_name,
            cache="no-store" if download_name else cache,
        )

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == "/" or path == "/index.html":
            self._send_file(TEMPLATE, "text/html; charset=utf-8", cache="no-cache")
            return

        if path.startswith("/static/"):
            rel = path[len("/static/") :]
            target = (STATIC_DIR / rel).resolve()
            if not str(target).startswith(str(STATIC_DIR.resolve())):
                self._send_json(400, {"detail": "bad path"})
                return
            self._send_file(target, MIME.get(target.suffix.lower()))
            return

        if path == "/api/health":
            provider = _resolve_provider()
            self._send_json(
                200,
                {
                    "ok": True,
                    "engine": _engine_name(),
                    "provider": provider,
                    "stemsplit_configured": _stemsplit_configured(),
                    "stemsplit_base_url": STEMSPLIT_BASE_URL,
                    "stemsplit_quality": STEMSPLIT_QUALITY if _stemsplit_configured() else None,
                    "model": MODEL_NAME if provider == "demucs" else None,
                    "device": (
                        DEVICE
                        if provider == "demucs"
                        else ("stemsplit" if provider == "stemsplit" else "ffmpeg")
                    ),
                    "segment": SEGMENT,
                    "max_duration_sec": MAX_DURATION_SEC,
                    "demucs_available": _demucs_available(),
                    "stem_provider_env": STEM_PROVIDER,
                    "modes": ["split", "vocal_remover"],
                    "pwa": True,
                },
            )
            return

        if path.startswith("/api/jobs/") and path.count("/") >= 3:
            parts = path.strip("/").split("/")
            if len(parts) == 3:
                job = _jobs.get(parts[2])
                if not job:
                    self._send_json(404, {"detail": "找不到此任務"})
                    return
                self._send_json(200, job)
                return
            if len(parts) == 5 and parts[3] in ("download", "stream"):
                job_id, action, which = parts[2], parts[3], parts[4]
                if which not in ("vocals", "instrumental", "no_vocals"):
                    self._send_json(400, {"detail": "unknown stem"})
                    return
                stem = "instrumental" if which in ("instrumental", "no_vocals") else "vocals"
                fp = _find_stem_file(OUTPUT_DIR / job_id, stem)
                if not fp:
                    self._send_json(404, {"detail": "not found"})
                    return
                if action == "download":
                    self._send_file(
                        fp,
                        _audio_mime(fp),
                        download_name=f"{job_id}_{stem}{fp.suffix}",
                    )
                else:
                    self._send_file(fp, _audio_mime(fp), cache="no-store")
                return

        self._send_json(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/upload":
            self._send_json(404, {"detail": "not found"})
            return

        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype:
            self._send_json(400, {"detail": "需要 multipart/form-data"})
            return

        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            self._send_json(400, {"detail": "空請求"})
            return
        if length > MAX_BYTES + 1024 * 1024:
            self._send_json(400, {"detail": "檔案過大（上限約 80 MB）"})
            return

        body = self.rfile.read(length)
        try:
            form = _parse_multipart(body, ctype)
        except Exception as e:
            self._send_json(400, {"detail": f"無法解析上傳：{e}"})
            return
        if "file" not in form:
            self._send_json(400, {"detail": "缺少 file 欄位"})
            return
        fileitem = form["file"]
        filename = Path(fileitem.get("filename") or "").name
        if not filename:
            self._send_json(400, {"detail": "缺少檔名"})
            return
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXT:
            self._send_json(
                400,
                {
                    "detail": f"不支援的格式：{ext or '(無副檔名)'}。請使用 mp3 / wav / flac / m4a / ogg"
                },
            )
            return

        job_id = uuid.uuid4().hex
        job_upload = UPLOAD_DIR / job_id
        job_upload.mkdir(parents=True, exist_ok=True)
        dest = job_upload / f"input{ext}"

        try:
            data = fileitem["data"]
            if len(data) > MAX_BYTES:
                self._send_json(400, {"detail": "檔案過大（上限約 80 MB）"})
                return
            dest.write_bytes(data)
            size = len(data)
        except Exception as e:
            self._send_json(500, {"detail": f"儲存失敗：{e}"})
            return

        duration = _probe_duration(dest)
        warning = None
        if duration is not None and duration > MAX_DURATION_SEC:
            warning = (
                f"音檔約 {duration/60:.1f} 分鐘，超過建議上限 "
                f"{MAX_DURATION_SEC // 60} 分鐘；分離可能很慢或記憶體不足。"
            )
        mode_field = form.get("mode") or {}
        mode_raw = ""
        if isinstance(mode_field, dict):
            raw_bytes = mode_field.get("data") or b""
            if isinstance(raw_bytes, bytes):
                mode_raw = raw_bytes.decode("utf-8", errors="ignore").strip()
            else:
                mode_raw = str(raw_bytes).strip()
        mode = _normalize_mode(mode_raw)

        provider = _resolve_provider()
        if provider == "ffmpeg":
            extra = (
                "目前使用 ffmpeg 中置／側邊後備分離。"
                "設定 STEMSPLIT_API_KEY 或安裝 torch+demucs 後重啟即可升級品質。"
            )
            warning = f"{warning + ' ' if warning else ''}{extra}"
        elif provider == "stemsplit":
            extra = "使用 StemSplit 雲端 API（金鑰僅存於伺服器）。"
            warning = f"{warning + ' ' if warning else ''}{extra}"

        engine = _engine_name()
        queued_msg = (
            "排隊中（人聲消除）…" if mode == "vocal_remover" else "排隊中…"
        )
        _set_job(
            job_id,
            status="queued",
            progress=0,
            message=queued_msg,
            filename=filename,
            size=size,
            duration=duration,
            warning=warning,
            engine=engine,
            provider=provider,
            mode=mode,
            created_at=_now(),
        )
        threading.Thread(
            target=_process_job,
            args=(job_id, dest, filename),
            kwargs={"mode": mode},
            daemon=True,
        ).start()

        self._send_json(
            200,
            {
                "job_id": job_id,
                "filename": filename,
                "duration": duration,
                "warning": warning,
                "engine": engine,
                "provider": provider,
                "mode": mode,
            },
        )


def main() -> None:
    engine = _engine_name()
    provider = _resolve_provider()
    print(
        f"[stem-splitter] http://127.0.0.1:{PORT}/  provider={provider} engine={engine}"
        f" stemsplit_configured={_stemsplit_configured()}",
        flush=True,
    )
    if provider == "demucs":
        print(f"[stem-splitter] demucs model={MODEL_NAME} device={DEVICE}", flush=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[stem-splitter] shutting down", flush=True)
        server.shutdown()


if __name__ == "__main__":
    main()
