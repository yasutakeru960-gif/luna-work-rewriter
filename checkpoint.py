"""Per-chunk checkpointing for long rewrites.

A 4-chunk rewrite takes several minutes. If the Streamlit session dies partway
through (websocket reconnect, script rerun, resource reboot) every finished
chunk used to be lost and the whole rewrite restarted from part 1. Here each
chunk is written to disk the moment Claude returns it, so a restart replays the
saved parts instantly and only re-runs the chunk that never finished.

Storage is a single JSON file per job under CHECKPOINT_DIR. /tmp survives a
script rerun and a websocket reconnect (the common failure); it does not
survive a container reboot or redeploy, which is why the UI also keeps the
draft-JSON download as the durable escape hatch.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

CHECKPOINT_DIR = Path(
    os.getenv(
        "REWRITE_CHECKPOINT_DIR",
        str(Path(tempfile.gettempdir()) / "luna_rewriter_ckpt"),
    )
)

# Checkpoints older than this are swept on the next job so /tmp cannot grow
# without bound across many articles.
MAX_AGE_SECONDS = 7 * 24 * 3600

# Bump when the on-disk chunk payload shape changes, so stale files are ignored
# instead of being replayed into a format the current code cannot read.
FORMAT_VERSION = 1


def make_job_id(article_text: str, chunk_char_limit: int, model: str) -> str:
    """Stable id for one (article, chunking, model) combination.

    Keyed on the source text so re-pasting the same article finds the same
    checkpoint, and editing the article (or changing the chunk size / model)
    produces a different id rather than replaying chunks that no longer match.
    """
    h = hashlib.sha256()
    h.update(article_text.encode("utf-8"))
    h.update(f"|{chunk_char_limit}|{model}|{FORMAT_VERSION}".encode("utf-8"))
    return h.hexdigest()[:16]


def _path(job_id: str) -> Path:
    return CHECKPOINT_DIR / f"{job_id}.json"


def _read(job_id: str) -> dict | None:
    p = _path(job_id)
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("format_version") != FORMAT_VERSION:
        return None
    return data


def _write(job_id: str, data: dict) -> None:
    """Atomic write — a crash mid-save must not leave a truncated JSON file
    that would make the whole checkpoint unreadable on the next run."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    p = _path(job_id)
    fd, tmp_name = tempfile.mkstemp(dir=str(CHECKPOINT_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, p)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _sweep_old() -> None:
    try:
        entries = list(CHECKPOINT_DIR.glob("*.json"))
    except OSError:
        return
    cutoff = time.time() - MAX_AGE_SECONDS
    for p in entries:
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass


def peek(job_id: str) -> dict | None:
    """Summary of a saved job for the UI, or None if there is nothing usable.

    Returns {"done": int, "total": int, "title": str, "updated_at": float}.
    """
    data = _read(job_id)
    if not data:
        return None
    chunks = data.get("chunks") or {}
    if not chunks:
        return None
    return {
        "done": len(chunks),
        "total": int(data.get("total_chunks") or 0),
        "title": data.get("source_title") or "",
        "updated_at": float(data.get("updated_at") or 0.0),
    }


def clear(job_id: str) -> None:
    try:
        _path(job_id).unlink()
    except OSError:
        pass


class RewriteCheckpoint:
    """Handle on one job's saved chunks. Every put() hits disk immediately."""

    def __init__(self, job_id: str, data: dict):
        self.job_id = job_id
        self._data = data

    @property
    def done_count(self) -> int:
        return len(self._data.get("chunks") or {})

    def get(self, idx: int) -> dict | None:
        """Saved payload for chunk idx: {"title","slug","meta","html",
        "prompts","styles"} — or None if that chunk was never finished."""
        return (self._data.get("chunks") or {}).get(str(idx))

    def put(self, idx: int, payload: dict) -> None:
        self._data.setdefault("chunks", {})[str(idx)] = payload
        self._data["updated_at"] = time.time()
        _write(self.job_id, self._data)

    def clear(self) -> None:
        clear(self.job_id)
        self._data["chunks"] = {}


def open_job(
    *,
    job_id: str,
    total_chunks: int,
    source_title: str,
    source_chars: int,
    resume: bool = True,
) -> RewriteCheckpoint:
    """Open (and resume, unless resume=False) the checkpoint for a job.

    A stored job whose total_chunks disagrees with the current split is
    discarded — replaying those chunks would stitch the article back together
    in the wrong proportions.
    """
    _sweep_old()
    data = _read(job_id) if resume else None
    if data and int(data.get("total_chunks") or 0) != total_chunks:
        data = None
    if not data:
        data = {
            "format_version": FORMAT_VERSION,
            "job_id": job_id,
            "total_chunks": total_chunks,
            "source_title": source_title,
            "source_chars": source_chars,
            "created_at": time.time(),
            "updated_at": time.time(),
            "chunks": {},
        }
    return RewriteCheckpoint(job_id, data)
