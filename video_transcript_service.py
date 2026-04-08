from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlparse

from config import (
    DOCUMENT_MAX_TEXT_CHARS,
    YOUTUBE_TRANSCRIPT_COMPUTE_TYPE,
    YOUTUBE_TRANSCRIPT_DEFAULT_LANGUAGE,
    YOUTUBE_TRANSCRIPT_DEVICE,
    YOUTUBE_TRANSCRIPT_MODEL_SIZE,
    YOUTUBE_TRANSCRIPTS_DISABLED_FEATURE_ERROR,
    YOUTUBE_TRANSCRIPTS_ENABLED,
)

_YOUTUBE_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}
_WHISPER_MODEL = None
_WHISPER_MODEL_KEY: tuple[str, str, str] | None = None
_WHISPER_MODEL_LOCK = Lock()


def _normalize_youtube_host(hostname: str | None) -> str:
    return str(hostname or "").strip().lower()


def extract_youtube_video_id(url: str) -> str | None:
    parsed = urlparse(str(url or "").strip())
    host = _normalize_youtube_host(parsed.hostname)
    if host not in _YOUTUBE_ALLOWED_HOSTS:
        return None

    if host in {"youtu.be", "www.youtu.be"}:
        candidate = parsed.path.strip("/").split("/", 1)[0]
        return candidate if _YOUTUBE_VIDEO_ID_RE.match(candidate) else None

    if parsed.path == "/watch":
        candidate = parse_qs(parsed.query).get("v", [""])[0].strip()
        return candidate if _YOUTUBE_VIDEO_ID_RE.match(candidate) else None

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) >= 2 and path_parts[0] in {"shorts", "embed", "live"}:
        candidate = path_parts[1].strip()
        return candidate if _YOUTUBE_VIDEO_ID_RE.match(candidate) else None

    return None


def normalize_youtube_url(url: str) -> str:
    video_id = extract_youtube_video_id(url)
    if not video_id:
        raise ValueError("Geçerli bir YouTube URL girin.")
    return f"https://www.youtube.com/watch?v={video_id}"


def read_youtube_video_reference(raw_url: str) -> tuple[str, str]:
    if not YOUTUBE_TRANSCRIPTS_ENABLED:
        raise RuntimeError(YOUTUBE_TRANSCRIPTS_DISABLED_FEATURE_ERROR)

    normalized_url = normalize_youtube_url(raw_url)
    video_id = extract_youtube_video_id(normalized_url)
    if not video_id:
        raise ValueError("Geçerli bir YouTube video kimliği bulunamadı.")
    return normalized_url, video_id


def _require_transcript_runtime() -> tuple[object, object]:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("YouTube transkripsiyonu için ffmpeg kurulu olmalıdır.")
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("YouTube transkripsiyonu için `yt-dlp` paketi kurulu olmalıdır.") from exc
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Yerel transkripsiyon için `faster-whisper` paketi kurulu olmalıdır.") from exc
    return yt_dlp, WhisperModel


def _get_whisper_model():
    global _WHISPER_MODEL, _WHISPER_MODEL_KEY

    _require_transcript_runtime()
    model_key = (
        YOUTUBE_TRANSCRIPT_MODEL_SIZE,
        YOUTUBE_TRANSCRIPT_DEVICE,
        YOUTUBE_TRANSCRIPT_COMPUTE_TYPE,
    )
    if _WHISPER_MODEL is not None and _WHISPER_MODEL_KEY == model_key:
        return _WHISPER_MODEL

    _yt_dlp, WhisperModel = _require_transcript_runtime()
    with _WHISPER_MODEL_LOCK:
        if _WHISPER_MODEL is not None and _WHISPER_MODEL_KEY == model_key:
            return _WHISPER_MODEL
        _WHISPER_MODEL = WhisperModel(
            YOUTUBE_TRANSCRIPT_MODEL_SIZE,
            device=YOUTUBE_TRANSCRIPT_DEVICE,
            compute_type=YOUTUBE_TRANSCRIPT_COMPUTE_TYPE,
        )
        _WHISPER_MODEL_KEY = model_key
    return _WHISPER_MODEL


def _resolve_downloaded_media_path(info: dict, temp_dir: str) -> str:
    requested_downloads = info.get("requested_downloads") if isinstance(info.get("requested_downloads"), list) else []
    for entry in requested_downloads:
        filepath = str((entry or {}).get("filepath") or "").strip()
        if filepath and Path(filepath).is_file():
            return filepath

    filepath = str(info.get("filepath") or "").strip()
    if filepath and Path(filepath).is_file():
        return filepath

    downloaded_files = [path for path in Path(temp_dir).glob("*") if path.is_file()]
    if not downloaded_files:
        raise RuntimeError("İndirilen video sesi bulunamadı.")
    downloaded_files.sort(key=lambda path: path.stat().st_size, reverse=True)
    return str(downloaded_files[0])


def _format_duration(duration_seconds: int | None) -> str:
    if not isinstance(duration_seconds, int) or duration_seconds <= 0:
        return ""
    minutes, seconds = divmod(duration_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:d}:{seconds:02d}"


def build_video_transcript_context_block(
    title: str,
    transcript_text: str,
    *,
    source_url: str = "",
    transcript_language: str = "",
    duration_seconds: int | None = None,
) -> tuple[str, bool]:
    normalized_title = str(title or "").strip() or "YouTube video"
    normalized_text = str(transcript_text or "").strip()
    if not normalized_text:
        raise ValueError("Video transcript is empty.")

    truncated = len(normalized_text) > DOCUMENT_MAX_TEXT_CHARS
    clipped_text = normalized_text[:DOCUMENT_MAX_TEXT_CHARS] if truncated else normalized_text
    header = f"[YouTube video transcript: {normalized_title}]"
    if truncated:
        header += " (truncated to first 50,000 characters)"

    detail_lines = []
    if source_url:
        detail_lines.append(f"Source: {source_url}")
    if transcript_language:
        detail_lines.append(f"Detected language: {transcript_language}")
    formatted_duration = _format_duration(duration_seconds)
    if formatted_duration:
        detail_lines.append(f"Duration: {formatted_duration}")

    parts = [header]
    if detail_lines:
        parts.append("\n".join(detail_lines))
    parts.append(clipped_text)
    return "\n\n".join(part for part in parts if part).strip(), truncated


def transcribe_youtube_video(source_url: str) -> dict:
    normalized_url, video_id = read_youtube_video_reference(source_url)
    yt_dlp, _WhisperModel = _require_transcript_runtime()
    whisper_model = _get_whisper_model()

    with tempfile.TemporaryDirectory(prefix="yt-transcript-") as temp_dir:
        download_options = {
            "format": "bestaudio/best",
            "outtmpl": str(Path(temp_dir) / "%(id)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": False,
            "cachedir": False,
        }
        with yt_dlp.YoutubeDL(download_options) as downloader:
            info = downloader.extract_info(normalized_url, download=True)

        media_path = _resolve_downloaded_media_path(info, temp_dir)
        segments, transcript_info = whisper_model.transcribe(
            media_path,
            language=YOUTUBE_TRANSCRIPT_DEFAULT_LANGUAGE or None,
            vad_filter=True,
            word_timestamps=False,
            condition_on_previous_text=False,
        )

        transcript_lines: list[str] = []
        for segment in segments:
            segment_text = str(getattr(segment, "text", "") or "").strip()
            if segment_text:
                transcript_lines.append(segment_text)

        transcript_text = "\n".join(transcript_lines).strip()
        if not transcript_text:
            raise ValueError("Videodan çözümlenebilir bir konuşma metni çıkarılamadı.")

        title = str(info.get("title") or "").strip() or f"YouTube video {video_id}"
        duration_value = info.get("duration")
        try:
            duration_seconds = max(0, int(duration_value)) if duration_value is not None else None
        except (TypeError, ValueError):
            duration_seconds = None

        detected_language = str(getattr(transcript_info, "language", "") or YOUTUBE_TRANSCRIPT_DEFAULT_LANGUAGE or "").strip()
        return {
            "platform": "youtube",
            "source_url": normalized_url,
            "source_video_id": video_id,
            "title": title,
            "duration_seconds": duration_seconds,
            "transcript_text": transcript_text,
            "transcript_language": detected_language,
        }