"""Journal persistence: save/list/detail/delete + temp sweep (DATABASE.md section 4).

Transaction order (files first, then row) and sweep rules implement the doc
verbatim. Temp validity = file present under uploads/tmp (unclaimed means
not yet promoted away). No invented data: titles/dates are server-generated
timestamps, labeled as such in the UI.
"""

import datetime
import json
import os
import re
import secrets
import shutil
import sqlite3
import time

from app import schemas
from app.db import connect
from app.errors import ApiError
from app.services import images

ID_RE_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
TEMP_TTL_S = 3600  # DATABASE.md: temp rows/files older than 1 hour are swept

ID_RE = re.compile(ID_RE_PATTERN)


def new_entry_id() -> str:
    return "entry_" + secrets.token_hex(13)


def utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _tmp_candidates(upload_dir: str, temp_id: str) -> str | None:
    """Locate the unclaimed temp file. None when missing/claimed/invalid."""
    if not isinstance(temp_id, str) or ID_RE.match(temp_id) is None:
        return None
    tmp_dir = os.path.join(upload_dir, "tmp")
    try:
        names = os.listdir(tmp_dir)
    except OSError:
        return None
    for name in sorted(names):
        base, dot, ext = name.partition(".")
        if base == temp_id and dot and ext in ("jpg", "png", "webp"):
            return os.path.join(tmp_dir, name)
    return None


def _entry_to_dict(row: sqlite3.Row, upload_dir: str) -> dict:
    entry_id = row["id"]
    analysis = json.loads(row["ai_analysis_json"]) if row["ai_analysis_json"] else None
    # Find the stored original (extension varies by upload).
    image_url = ""
    entry_dir = os.path.join(upload_dir, entry_id)
    try:
        for name in sorted(os.listdir(entry_dir)):
            if name.startswith("original."):
                image_url = "/media/%s/%s" % (entry_id, name)
                break
    except OSError:
        pass
    return {
        "id": entry_id,
        "title": row["title"],
        "created_at": row["created_at"],
        "image_url": image_url,
        "thumbnail_url": "/media/%s/thumb_512.jpg" % entry_id,
        "analysis": analysis,
        "user_notes": row["user_notes"],
        "experiment_done": bool(row["experiment_done"]),
        "experiment_result": row["experiment_result"],
    }


def create_entry(settings, model_id: str, payload: dict) -> dict:
    """Validate (documented codes) then promote + insert atomically."""
    temp_image_id = payload.get("temp_image_id")
    user_notes = normalize_text(payload.get("user_notes"))
    if user_notes is None or len(user_notes.strip()) == 0 or len(user_notes) > 2000:
        raise ApiError(400, "notes_required",
                       "Write at least a sentence about what you saw.", {})
    experiment_done = payload.get("experiment_done", False)
    if not isinstance(experiment_done, bool):
        raise ApiError(400, "bad_request",
                       "That request was malformed. Check your input and retry.", {})
    experiment_result = payload.get("experiment_result")
    if experiment_result is not None:
        experiment_result = normalize_text(experiment_result)
        if experiment_result is None or len(experiment_result) > 2000:
            raise ApiError(400, "bad_request",
                           "That request was malformed. Check your input and retry.", {})
        if experiment_result == "":
            experiment_result = None

    ai_analysis = payload.get("ai_analysis")
    frozen = None
    if ai_analysis is not None:
        if not isinstance(ai_analysis, dict):
            raise ApiError(400, "ai_model_mismatch",
                           "That AI result doesn't match this service. Retry the analysis.", {})
        try:
            validated = schemas.AIAnalysis.model_validate(ai_analysis)
        except Exception:
            raise ApiError(400, "ai_model_mismatch",
                           "That AI result doesn't match this service. Retry the analysis.", {})
        if validated.model_id != model_id:
            raise ApiError(400, "ai_model_mismatch",
                           "That AI result doesn't match this service. Retry the analysis.", {})
        frozen = validated.model_dump()

    src = _tmp_candidates(settings.upload_dir, temp_image_id)
    if src is None:
        raise ApiError(404, "temp_image_expired",
                       "That photo expired before saving. Upload it again.", {})

    entry_id = new_entry_id()
    entry_dir = os.path.join(settings.upload_dir, entry_id)
    ext = src.rsplit(".", 1)[1]
    with open(src, "rb") as fh:
        original_bytes = fh.read()
    os.makedirs(entry_dir, exist_ok=True)
    try:
        with open(os.path.join(entry_dir, "original." + ext), "wb") as fh:
            fh.write(original_bytes)
        with open(os.path.join(entry_dir, "thumb_512.jpg"), "wb") as fh:
            fh.write(images.make_thumbnail(original_bytes))
    except Exception:
        raise ApiError(500, "internal_error",
                       "Something went wrong. Please retry.", {})

    title = "Outdoor note · %s" % datetime.date.today().isoformat()
    created_at = utcnow()
    conn = connect(settings.database_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO journal_entries (id, title, created_at, image_path,"
            " thumbnail_path, ai_analysis_json, ai_model_id, ai_analyzed_at,"
            " user_notes, experiment_done, experiment_result)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entry_id, title, created_at,
             os.path.join("uploads", entry_id, "original." + ext),
             os.path.join("uploads", entry_id, "thumb_512.jpg"),
             json.dumps(frozen) if frozen is not None else None,
             frozen["model_id"] if frozen is not None else None,
             frozen.get("analyzed_at") if frozen is not None else None,
             user_notes, 1 if experiment_done else 0, experiment_result))
        conn.execute("UPDATE ai_analyses SET entry_id = ?, saved = 1 WHERE id = ?",
                     (entry_id, temp_image_id))
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        finally:
            pass
        shutil.rmtree(entry_dir, ignore_errors=True)
        raise ApiError(503, "db_busy",
                       "The journal store is busy right now. Please retry.", {})
    finally:
        conn.close()
    # Claimed: remove the temp file only after commit.
    try:
        os.remove(src)
    except OSError:
        pass
    return get_entry(settings, entry_id)


def get_entry(settings, entry_id: str) -> dict:
    if not isinstance(entry_id, str) or ID_RE.match(entry_id) is None:
        raise ApiError(404, "entry_not_found", "This entry no longer exists.", {})
    conn = connect(settings.database_path)
    try:
        row = conn.execute("SELECT * FROM journal_entries WHERE id = ?",
                           (entry_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ApiError(404, "entry_not_found", "This entry no longer exists.", {})
    return _entry_to_dict(row, settings.upload_dir)


def list_entries(settings) -> dict:
    conn = connect(settings.database_path)
    try:
        rows = conn.execute(
            "SELECT * FROM journal_entries ORDER BY created_at DESC, rowid DESC").fetchall()
    finally:
        conn.close()
    items = []
    for row in rows:
        full = _entry_to_dict(row, settings.upload_dir)
        items.append({"id": full["id"], "title": full["title"],
                      "created_at": full["created_at"],
                      "thumbnail_url": full["thumbnail_url"],
                      "has_ai": full["analysis"] is not None,
                      "experiment_done": full["experiment_done"]})
    return {"entries": items, "total": len(items)}


def delete_entry(settings, entry_id: str) -> None:
    if not isinstance(entry_id, str) or ID_RE.match(entry_id) is None:
        raise ApiError(404, "entry_not_found", "This entry no longer exists.", {})
    conn = connect(settings.database_path)
    try:
        row = conn.execute("SELECT id FROM journal_entries WHERE id = ?",
                           (entry_id,)).fetchone()
        if row is None:
            raise ApiError(404, "entry_not_found", "This entry no longer exists.", {})
        conn.execute("DELETE FROM journal_entries WHERE id = ?", (entry_id,))
        conn.commit()
    finally:
        conn.close()
    # Files go after commit; leftovers are found by the orphan query (DATABASE.md).
    shutil.rmtree(os.path.join(settings.upload_dir, entry_id), ignore_errors=True)


def sweep_temp(upload_dir: str, db_path: str, now: float | None = None) -> dict:
    """Delete expired unsaved temp rows/files (DATABASE.md section 4).

    Never raises: called from request/startup paths. Never touches entry dirs.
    """
    swept = {"rows": 0, "files": 0}
    try:
        cutoff = datetime.datetime.fromtimestamp(
            (now if now is not None else time.time()) - TEMP_TTL_S,
            tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = connect(db_path)
        try:
            stale = conn.execute(
                "SELECT id, image_tmp_path FROM ai_analyses"
                " WHERE saved = 0 AND analyzed_at < ?", (cutoff,)).fetchall()
            for row in stale:
                rel = row["image_tmp_path"] or ""
                if rel:
                    _safe_unlink(upload_dir, rel)
                    swept["files"] += 1
            conn.execute("DELETE FROM ai_analyses WHERE saved = 0 AND analyzed_at < ?",
                         (cutoff,))
            swept["rows"] = len(stale)
            conn.commit()
        finally:
            conn.close()
        tmp_dir = os.path.join(upload_dir, "tmp")
        try:
            names = os.listdir(tmp_dir)
        except OSError:
            return swept
        live_rows: set[str] = set()
        try:
            conn = connect(db_path)
            try:
                for (relpath,) in conn.execute(
                        "SELECT image_tmp_path FROM ai_analyses WHERE image_tmp_path IS NOT NULL"):
                    live_rows.add(os.path.basename(relpath))
            finally:
                conn.close()
        except Exception:
            pass
        now_s = now if now is not None else time.time()
        for name in names:
            base, dot, ext = name.partition(".")
            if not dot or ext not in ("jpg", "png", "webp"):
                continue
            full = os.path.join(tmp_dir, name)
            try:
                old = now_s - os.path.getmtime(full) > TEMP_TTL_S
            except OSError:
                continue
            if old and name not in live_rows:
                _safe_unlink(upload_dir, os.path.join("tmp", name))
                swept["files"] += 1
    except Exception:
        pass
    return swept


def _safe_unlink(upload_dir: str, rel: str) -> None:
    # Confine deletions to uploads/tmp (never entry dirs, never absolute paths).
    parts = rel.replace("\\", "/").split("/")
    if len(parts) != 2 or parts[0] != "tmp":
        return
    base, dot, ext = parts[1].partition(".")
    if not dot or ext not in ("jpg", "png", "webp") or ID_RE.match(base) is None:
        return
    try:
        os.remove(os.path.join(upload_dir, "tmp", parts[1]))
    except OSError:
        pass
