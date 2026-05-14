# ==============================================================================
# Creator: Anshul Vashist
# Email: vashistanshul.7@gmail.com
# LinkedIn: https://www.linkedin.com/in/av-0001/
# ==============================================================================
from __future__ import annotations

import threading
import time
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class AgentJobState:
    job_id: str
    kind: str
    status: str = "queued"
    started_at: float = 0.0
    finished_at: float = 0.0
    latest_substate: str = ""
    progress_log: list[str] = field(default_factory=list)
    stream_log: list[str] = field(default_factory=list)
    checkpoints: list[str] = field(default_factory=list)
    result: str = ""
    error: str = ""
    meta: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "latest_substate": self.latest_substate,
            "progress_log": list(self.progress_log),
            "stream_log": list(self.stream_log),
            "checkpoints": list(self.checkpoints),
            "result": self.result,
            "error": self.error,
            "meta": dict(self.meta),
        }


class AsyncJobManager:
    def __init__(self, max_progress_entries: int = 80, max_stream_entries: int = 1200):
        self._max_progress_entries = max(10, int(max_progress_entries))
        self._max_stream_entries = max(50, int(max_stream_entries))
        self._jobs: dict[str, AgentJobState] = {}
        self._stream_subscribers: dict[str, dict[str, Callable[[str], None]]] = {}
        self._done_subscribers: dict[str, dict[str, Callable[[str], None]]] = {}
        self._lock = threading.Lock()

    def submit(
        self,
        kind: str,
        runner: Callable[[Callable[[str], None], Callable[[dict], None]], str],
        stream_callback: Callable[[str], None] | None = None,
        done_callback: Callable[[str], None] | None = None,
        meta: dict | None = None,
    ) -> str:
        job_id = uuid.uuid4().hex[:12]
        job = AgentJobState(job_id=job_id, kind=kind)
        if meta:
            job.meta.update(dict(meta))
        with self._lock:
            self._jobs[job_id] = job
        if stream_callback or done_callback:
            self.subscribe(job_id, stream_callback=stream_callback, done_callback=done_callback)

        def _record_progress(chunk: str):
            text = str(chunk or "")
            self._record_stream(job_id, text)
            message = text.replace("\x00AGENT_PROGRESS\x00", "").replace("\u200b", "").strip()
            if message:
                self._record_substate(job_id, message)
            self._dispatch_stream(job_id, text)

        def _record_status(payload: dict):
            payload = dict(payload or {})
            self._record_runtime_status(job_id, payload)

        def _worker():
            self._set_status(job_id, "running")
            try:
                result = runner(_record_progress, _record_status)
                self._finish(job_id, status="completed", result=result)
                self._dispatch_done(job_id, result)
            except Exception as exc:
                error_text = f"⚠️ Agent Error: {exc}"
                traceback.print_exc()
                self._finish(job_id, status="failed", error=error_text)
                self._record_stream(job_id, f"\n\n{error_text}")
                self._dispatch_stream(job_id, f"\n\n{error_text}")
                self._dispatch_done(job_id, error_text)

        # ALWAYS use threading.Thread instead of QThreadPool/QRunnable.
        # Running hdefereval from a locked QRunnable blocks PySide's event loop on Mac,
        # leading to the "Houdini main-thread call timed out after 30s" deadlock.
        threading.Thread(target=_worker, daemon=True, name=f"houdinimind-job-{job_id}").start()

        return job_id

    def subscribe(
        self,
        job_id: str,
        stream_callback: Callable[[str], None] | None = None,
        done_callback: Callable[[str], None] | None = None,
    ) -> str:
        token = uuid.uuid4().hex[:12]
        with self._lock:
            if stream_callback:
                self._stream_subscribers.setdefault(job_id, {})[token] = stream_callback
            if done_callback:
                self._done_subscribers.setdefault(job_id, {})[token] = done_callback
        return token

    def unsubscribe(self, job_id: str, token: str) -> None:
        with self._lock:
            self._stream_subscribers.get(job_id, {}).pop(token, None)
            self._done_subscribers.get(job_id, {}).pop(token, None)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.to_dict() if job else None

    def latest_active(self) -> dict | None:
        with self._lock:
            active = [
                job
                for job in self._jobs.values()
                if job.status in {"queued", "running"} and not job.finished_at
            ]
            if not active:
                return None
            return max(active, key=lambda job: job.started_at or 0.0).to_dict()

    def _record_stream(self, job_id: str, chunk: str) -> None:
        if not chunk:
            return
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.stream_log.append(str(chunk))
            if len(job.stream_log) > self._max_stream_entries:
                job.stream_log = job.stream_log[-self._max_stream_entries :]

    def _dispatch_stream(self, job_id: str, chunk: str) -> None:
        with self._lock:
            callbacks = list(self._stream_subscribers.get(job_id, {}).items())
        dead = []
        for token, callback in callbacks:
            try:
                callback(chunk)
            except Exception:
                dead.append(token)
        for token in dead:
            self.unsubscribe(job_id, token)

    def _dispatch_done(self, job_id: str, result: str) -> None:
        with self._lock:
            callbacks = list(self._done_subscribers.get(job_id, {}).items())
        dead = []
        for token, callback in callbacks:
            try:
                callback(result)
            except Exception:
                dead.append(token)
        for token in dead:
            self.unsubscribe(job_id, token)

    def _set_status(self, job_id: str, status: str):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.status = status
            if status == "running" and not job.started_at:
                job.started_at = time.time()
            if status in {"completed", "failed", "cancelled"}:
                job.finished_at = time.time()

    def _record_substate(self, job_id: str, message: str):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.latest_substate = message
            if not job.progress_log or job.progress_log[-1] != message:
                job.progress_log.append(message)
                if len(job.progress_log) > self._max_progress_entries:
                    job.progress_log = job.progress_log[-self._max_progress_entries :]

    def _record_runtime_status(self, job_id: str, payload: dict):
        kind = str(payload.get("kind", "") or "").lower()
        if kind in {"substate", "progress"}:
            self._record_substate(job_id, str(payload.get("message", "") or ""))
            return
        if kind == "checkpoint":
            checkpoint = str(payload.get("path", "") or "").strip()
            if not checkpoint:
                return
            with self._lock:
                job = self._jobs.get(job_id)
                if not job:
                    return
                if checkpoint not in job.checkpoints:
                    job.checkpoints.append(checkpoint)
                job.meta["checkpoint_path"] = checkpoint
            return
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.meta.update(payload)

    def _finish(
        self,
        job_id: str,
        status: str,
        result: str = "",
        error: str = "",
    ):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.status = status
            job.finished_at = time.time()
            if not job.started_at:
                job.started_at = job.finished_at
            job.result = result or ""
            job.error = error or ""
