from __future__ import annotations

import json
from typing import Any, Optional
from datetime import datetime, timezone

from app.core.redis import get_redis


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobService:
    @staticmethod
    def _key(job_id: str) -> str:
        return f"job:{job_id}"

    @staticmethod
    def create(job_id: str, payload: dict[str, Any], ttl_sec: int = 60 * 60 * 6) -> None:
        r = get_redis()
        data = {
            "job_id": job_id,
            "status": "queued",          # queued | running | done | error | cancelled
            "stage": "created",
            "progress": 0,
            "total": payload.get("total"),
            "error": None,
            "result": None,
            "cancel_requested": False,
            "updated_at": _now_iso(),
            "payload": payload,
        }
        r.set(JobService._key(job_id), json.dumps(data), ex=ttl_sec)

    @staticmethod
    def get(job_id: str) -> Optional[dict[str, Any]]:
        r = get_redis()
        raw = r.get(JobService._key(job_id))
        if not raw:
            return None
        return json.loads(raw)

    @staticmethod
    def update(job_id: str, **updates) -> None:
        r = get_redis()
        data = JobService.get(job_id) or {"job_id": job_id}
        data.update(updates)
        data["updated_at"] = _now_iso()
        # keep existing TTL if present
        ttl = r.ttl(JobService._key(job_id))
        if ttl and ttl > 0:
            r.set(JobService._key(job_id), json.dumps(data), ex=ttl)
        else:
            r.set(JobService._key(job_id), json.dumps(data), ex=60 * 60 * 6)

    @staticmethod
    def request_cancel(job_id: str) -> None:
        JobService.update(job_id, cancel_requested=True, stage="cancel_requested")

    @staticmethod
    def is_cancel_requested(job_id: str) -> bool:
        data = JobService.get(job_id) or {}
        return bool(data.get("cancel_requested"))