from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


STATE_PATH = Path("casteriel_memory/registro_state.json")


@dataclass
class UserProfile:
    user_id: int
    first_seen_ts: float
    last_seen_ts: float
    warnings: int = 0
    reverence_count: int = 0
    last_reverence_ts: float = 0.0
    notes: str = ""


class Registro:
    """
    Memoria "fría":
    - actividad por canal (para lunes silencioso)
    - cooldown por canal
    - sesiones de menciones por canal
    - perfiles por usuario (advertencias, reverencia, etc.)
    """

    def __init__(self) -> None:
        self._channel_last_message_ts: dict[int, float] = {}
        self._channel_last_reply_ts: dict[int, float] = {}
        self._mention_sessions: dict[int, dict[str, Any]] = {}  # channel_id -> {"window_start": ts, "count": int}
        self.last_monday_noon_post_date_key: str | None = None

        self._users: dict[int, UserProfile] = {}

        self._load()

    # ---------------- persistence ----------------
    def _load(self) -> None:
        if not STATE_PATH.exists():
            return
        try:
            raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return

        self.last_monday_noon_post_date_key = raw.get("last_monday_noon_post_date_key")

        self._channel_last_message_ts = {int(k): float(v) for k, v in raw.get("channel_last_message_ts", {}).items()}
        self._channel_last_reply_ts = {int(k): float(v) for k, v in raw.get("channel_last_reply_ts", {}).items()}
        self._mention_sessions = {int(k): v for k, v in raw.get("mention_sessions", {}).items()}

        users_raw = raw.get("users", {})
        for k, v in users_raw.items():
            try:
                uid = int(k)
                self._users[uid] = UserProfile(
                    user_id=uid,
                    first_seen_ts=float(v.get("first_seen_ts", time.time())),
                    last_seen_ts=float(v.get("last_seen_ts", time.time())),
                    warnings=int(v.get("warnings", 0)),
                    reverence_count=int(v.get("reverence_count", 0)),
                    last_reverence_ts=float(v.get("last_reverence_ts", 0.0)),
                    notes=str(v.get("notes", "")),
                )
            except Exception:
                continue

    def _save(self) -> None:
        try:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "last_monday_noon_post_date_key": self.last_monday_noon_post_date_key,
                "channel_last_message_ts": self._channel_last_message_ts,
                "channel_last_reply_ts": self._channel_last_reply_ts,
                "mention_sessions": self._mention_sessions,
                "users": {str(uid): asdict(p) for uid, p in self._users.items()},
            }
            STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ---------------- channel activity ----------------
    def mark_message_seen(self, channel_id: int) -> None:
        self._channel_last_message_ts[channel_id] = time.time()
        self._save()

    def last_message_ts(self, channel_id: int) -> float:
        return float(self._channel_last_message_ts.get(channel_id, 0.0))

    def can_reply_channel(self, channel_id: int, cooldown_s: int) -> bool:
        now = time.time()
        last = float(self._channel_last_reply_ts.get(channel_id, 0.0))
        return (now - last) >= cooldown_s

    def mark_replied(self, channel_id: int) -> None:
        self._channel_last_reply_ts[channel_id] = time.time()
        self._save()

    # ---------------- mention session ----------------
    def increment_mention(self, channel_id: int, window_s: int) -> int:
        now = time.time()
        sess = self._mention_sessions.get(channel_id)
        if not sess:
            sess = {"window_start": now, "count": 0}
            self._mention_sessions[channel_id] = sess

        window_start = float(sess.get("window_start", now))
        if (now - window_start) > window_s:
            sess["window_start"] = now
            sess["count"] = 0

        sess["count"] = int(sess.get("count", 0)) + 1
        self._save()
        return int(sess["count"])

    # ---------------- user profiles ----------------
    def ensure_user(self, user_id: int) -> UserProfile:
        now = time.time()
        if user_id not in self._users:
            self._users[user_id] = UserProfile(user_id=user_id, first_seen_ts=now, last_seen_ts=now)
            self._save()
        return self._users[user_id]

    def mark_user_seen(self, user_id: int) -> None:
        p = self.ensure_user(user_id)
        p.last_seen_ts = time.time()
        self._save()

    def mark_reverence(self, user_id: int) -> None:
        p = self.ensure_user(user_id)
        p.reverence_count += 1
        p.last_reverence_ts = time.time()
        self._save()

    def add_warning(self, user_id: int, note: str = "") -> int:
        p = self.ensure_user(user_id)
        p.warnings += 1
        if note:
            # guarda solo lo último (simple)
            p.notes = note.strip()[:240]
        self._save()
        return p.warnings

    def reset_user(self, user_id: int) -> None:
        p = self.ensure_user(user_id)
        p.warnings = 0
        p.reverence_count = 0
        p.last_reverence_ts = 0.0
        p.notes = ""
        self._save()

    def get_profile(self, user_id: int) -> UserProfile:
        return self.ensure_user(user_id)

    def is_reverent_recent(self, user_id: int, within_days: int = 30) -> bool:
        p = self.ensure_user(user_id)
        if p.last_reverence_ts <= 0:
            return False
        return (time.time() - p.last_reverence_ts) <= within_days * 86400
