import os
import time
import logging
from typing import Iterable

import requests

from .base import Event
from ..config import SourceConfig
from ..dedup import DedupStore
from ..i18n import t

log = logging.getLogger(__name__)

SLACK_API = "https://slack.com/api"


class SlackAdapter:
    name = "slack"

    def __init__(self, cfg: SourceConfig, store: DedupStore, language: str = "pl"):
        env_name = cfg.options.get("token_env", "SLACK_USER_TOKEN")
        token = os.environ.get(env_name)
        if not token:
            raise RuntimeError(f"Slack: env {env_name} not set")
        self.token = token
        self.dms_enabled = bool(cfg.options.get("dms", True))
        self.mentions_enabled = bool(cfg.options.get("mentions", True))
        self.store = store
        self.language = language
        self._user_cache: dict[str, str] = {}
        self._self_id: str | None = None

    def _call(self, method: str, params: dict | None = None) -> dict:
        r = requests.get(
            f"{SLACK_API}/{method}",
            headers={"Authorization": f"Bearer {self.token}"},
            params=params or {},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack {method} failed: {data.get('error')}")
        return data

    def _resolve_user(self, user_id: str | None) -> str:
        if not user_id:
            return "nieznany"
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        try:
            data = self._call("users.info", {"user": user_id})
            profile = data["user"].get("profile") or {}
            name = profile.get("real_name") or data["user"].get("name") or user_id
        except Exception:
            name = user_id
        self._user_cache[user_id] = name
        return name

    def _self(self) -> str:
        if self._self_id:
            return self._self_id
        data = self._call("auth.test")
        self._self_id = data["user_id"]
        return self._self_id

    def _since_ts(self) -> str:
        cursor = self.store.get_cursor(self.name)
        if cursor:
            return cursor
        return str(time.time() - 300)

    def poll(self) -> Iterable[Event]:
        since = self._since_ts()
        latest = float(since)

        if self.dms_enabled:
            yield from self._poll_dms(since)

        if self.mentions_enabled:
            for ev in self._poll_mentions(since):
                yield ev

        current = time.time()
        if current > latest:
            latest = current
        self.store.set_cursor(self.name, str(latest))

    def _poll_dms(self, since: str) -> Iterable[Event]:
        try:
            convs = self._call(
                "users.conversations",
                {"types": "im,mpim", "limit": 100},
            )
        except Exception as e:
            log.warning("Slack conversations list failed: %s", e)
            return

        self_id = self._self()

        for ch in convs.get("channels", []):
            ch_id = ch["id"]
            try:
                hist = self._call(
                    "conversations.history",
                    {"channel": ch_id, "oldest": since, "limit": 50},
                )
            except Exception as e:
                log.warning("Slack history %s failed: %s", ch_id, e)
                continue

            for msg in reversed(hist.get("messages", [])):
                if msg.get("subtype"):
                    continue
                if msg.get("user") == self_id:
                    continue
                ext_id = f"dm:{ch_id}:{msg['ts']}"
                if self.store.is_seen(self.name, ext_id):
                    continue
                self.store.mark_seen(self.name, ext_id)
                author = self._resolve_user(msg.get("user"))
                yield Event(
                    source=self.name,
                    external_id=ext_id,
                    author=author,
                    short=t(self.language, "slack_dm"),
                    title=f"DM / {author}",
                    body=msg.get("text") or "",
                    project=f"dm:{author}",
                )

    def _poll_mentions(self, since: str) -> Iterable[Event]:
        self_id = self._self()
        try:
            data = self._call(
                "search.messages",
                {"query": f"<@{self_id}>", "sort": "timestamp", "count": 20},
            )
        except Exception as e:
            log.warning("Slack mentions search failed: %s", e)
            return

        matches = ((data.get("messages") or {}).get("matches")) or []
        since_f = float(since)
        for m in matches:
            ts = float(m.get("ts", "0"))
            if ts <= since_f:
                continue
            if m.get("user") == self_id:
                continue
            ext_id = f"mention:{m.get('iid') or m['ts']}"
            if self.store.is_seen(self.name, ext_id):
                continue
            self.store.mark_seen(self.name, ext_id)
            author = self._resolve_user(m.get("user"))
            channel = ((m.get("channel") or {}).get("name")) or "kanał"
            yield Event(
                source=self.name,
                external_id=ext_id,
                author=author,
                short=t(self.language, "slack_mention", channel=channel),
                title=f"mention #{channel} / {author}",
                body=m.get("text") or "",
                project=f"#{channel}",
            )
