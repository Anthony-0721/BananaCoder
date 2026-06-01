"""Session persistence and management."""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiofiles


@dataclass
class Session:
    id: str
    project: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0

    def __post_init__(self):
        now = time.time()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now


class SessionManager:
    def __init__(self, storage_dir: Path, project_dir: Path):
        self._storage = storage_dir / "sessions"
        self._project_hash = hashlib.sha256(str(project_dir.resolve()).encode()).hexdigest()[:12]
        self._active_id = "default"

    def _project_dir(self) -> Path:
        return self._storage / self._project_hash

    def _session_path(self, session_id: str) -> Path:
        return self._project_dir() / session_id / "messages.json"

    def _meta_path(self, session_id: str) -> Path:
        return self._project_dir() / session_id / "meta.json"

    def _index_path(self) -> Path:
        return self._storage / "index.json"

    def _load_index(self) -> dict:
        path = self._index_path()
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {"sessions": {}, "active": "default"}

    def _save_index(self, index: dict):
        self._index_path().parent.mkdir(parents=True, exist_ok=True)
        tmp = str(self._index_path()) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._index_path())

    async def load(self, session_id: str | None = None) -> Session:
        sid = session_id or self._active_id
        msg_path = self._session_path(sid)
        meta_path = self._meta_path(sid)

        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        else:
            meta = {"id": sid, "project": str(self._project_hash),
                    "created_at": time.time(), "summary": "",
                    "prompt_tokens": 0, "completion_tokens": 0}

        if msg_path.exists():
            async with aiofiles.open(msg_path, "r", encoding="utf-8") as f:
                messages = json.loads(await f.read())
        else:
            messages = []

        return Session(
            id=sid, project=meta.get("project", ""),
            messages=messages, summary=meta.get("summary", ""),
            prompt_tokens=meta.get("prompt_tokens", 0),
            completion_tokens=meta.get("completion_tokens", 0),
            created_at=meta.get("created_at", time.time()),
            updated_at=meta.get("updated_at", time.time()),
        )

    async def save(self, session: Session):
        session.updated_at = time.time()
        dir_path = self._session_path(session.id).parent
        dir_path.mkdir(parents=True, exist_ok=True)

        tmp_msg = str(self._session_path(session.id)) + ".tmp"
        async with aiofiles.open(tmp_msg, "w", encoding="utf-8") as f:
            content = json.dumps(session.messages, ensure_ascii=False, indent=2)
            await f.write(content)
            await f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_msg, self._session_path(session.id))

        tmp_meta = str(self._meta_path(session.id)) + ".tmp"
        meta = {
            "id": session.id, "project": session.project,
            "created_at": session.created_at, "updated_at": session.updated_at,
            "summary": session.summary,
            "prompt_tokens": session.prompt_tokens,
            "completion_tokens": session.completion_tokens,
        }
        async with aiofiles.open(tmp_meta, "w", encoding="utf-8") as f:
            await f.write(json.dumps(meta, ensure_ascii=False, indent=2))
            await f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_meta, self._meta_path(session.id))

        index = self._load_index()
        index["sessions"][session.id] = {
            "id": session.id, "project": session.project,
            "created_at": session.created_at, "updated_at": session.updated_at,
            "message_count": len(session.messages), "summary": session.summary,
        }
        index["active"] = self._active_id
        self._save_index(index)

    async def switch(self, session_id: str) -> Session:
        self._active_id = session_id
        index = self._load_index()
        index["active"] = session_id
        self._save_index(index)
        return await self.load(session_id)

    async def new(self, session_id: str) -> Session:
        session = Session(id=session_id, project=str(self._project_hash))
        await self.save(session)
        return await self.switch(session_id)

    async def delete(self, session_id: str):
        import shutil
        dir_path = self._project_dir() / session_id
        if dir_path.exists():
            shutil.rmtree(dir_path)
        index = self._load_index()
        index["sessions"].pop(session_id, None)
        if index["active"] == session_id:
            index["active"] = "default"
        self._save_index(index)

    async def list_sessions(self) -> list[dict]:
        index = self._load_index()
        return list(index["sessions"].values())

    async def compact(self, session: Session, provider=None, keep_recent: int = 20):
        if len(session.messages) <= keep_recent:
            return

        old = session.messages[:-keep_recent]
        recent = session.messages[-keep_recent:]

        summary = session.summary or ""
        if provider and old:
            flat = "\n".join(
                f"[{m['role']}] {str(m.get('content', ''))[:200]}"
                for m in old
            )
            try:
                resp = await provider.chat(
                    messages=[
                        {"role": "system", "content": "Summarize this conversation in 2-3 sentences. Include: files edited, decisions made, errors encountered."},
                        {"role": "user", "content": flat[:8000]},
                    ],
                )
                summary = resp.content or summary
            except Exception:
                pass

        session.messages = [
            {"role": "user", "content": f"[History summary]\n{summary}"},
            {"role": "assistant", "content": "Got it. I have the context from our previous conversation."},
        ] + recent
        session.summary = summary
        await self.save(session)
