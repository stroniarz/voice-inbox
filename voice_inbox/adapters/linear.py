import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Iterable

import requests

from .base import Event
from ..config import SourceConfig
from ..dedup import DedupStore
from ..i18n import t

log = logging.getLogger(__name__)

LINEAR_API = "https://api.linear.app/graphql"

ISSUES_QUERY = """
query RecentIssues($since: DateTimeOrDuration!, $teamKeys: [String!]) {
  issues(
    filter: {
      updatedAt: { gt: $since }
      team: { key: { in: $teamKeys } }
    }
    orderBy: updatedAt
    first: 50
  ) {
    nodes {
      id
      identifier
      title
      description
      priority
      createdAt
      updatedAt
      creator { name }
      assignee { name }
      state { name }
      team { key name }
    }
  }
}
"""

ISSUES_QUERY_ALL = """
query RecentIssues($since: DateTimeOrDuration!) {
  issues(
    filter: { updatedAt: { gt: $since } }
    orderBy: updatedAt
    first: 50
  ) {
    nodes {
      id
      identifier
      title
      description
      priority
      createdAt
      updatedAt
      creator { name }
      assignee { name }
      state { name }
      team { key name }
    }
  }
}
"""

COMMENTS_QUERY = """
query RecentComments($since: DateTimeOrDuration!) {
  comments(
    filter: { createdAt: { gt: $since } }
    orderBy: createdAt
    first: 50
  ) {
    nodes {
      id
      body
      createdAt
      user { name }
      issue { identifier title priority }
    }
  }
}
"""


class LinearAdapter:
    name = "linear"

    def __init__(self, cfg: SourceConfig, store: DedupStore, language: str = "pl"):
        env_name = cfg.options.get("api_key_env", "LINEAR_API_KEY")
        api_key = os.environ.get(env_name)
        if not api_key:
            raise RuntimeError(f"Linear: env {env_name} not set")
        self.api_key = api_key
        self.team_keys = cfg.options.get("team_keys") or []
        self.store = store
        self.language = language

    def _gql(self, query: str, variables: dict) -> dict:
        r = requests.post(
            LINEAR_API,
            headers={"Authorization": self.api_key},
            json={"query": query, "variables": variables},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        if "errors" in data:
            raise RuntimeError(f"Linear GraphQL errors: {data['errors']}")
        return data["data"]

    def _since(self) -> str:
        cursor = self.store.get_cursor(self.name)
        if cursor:
            return cursor
        now = datetime.now(timezone.utc).isoformat()
        self.store.set_cursor(self.name, now)
        return now

    def poll(self) -> Iterable[Event]:
        since = self._since()
        latest = since

        if self.team_keys:
            data = self._gql(ISSUES_QUERY, {"since": since, "teamKeys": self.team_keys})
        else:
            data = self._gql(ISSUES_QUERY_ALL, {"since": since})

        for issue in data["issues"]["nodes"]:
            ext_id = f"issue:{issue['id']}:{issue['updatedAt']}"
            if self.store.is_seen(self.name, ext_id):
                continue
            self.store.mark_seen(self.name, ext_id)
            is_new = issue["createdAt"] == issue["updatedAt"]
            author = (issue.get("creator") or {}).get("name") or "unknown"
            ident = issue["identifier"]
            issue_title = issue["title"]
            priority = int(issue.get("priority") or 3)
            is_urgent = priority in (1, 2)
            prefix = t(self.language, "urgent_prefix") if is_urgent else ""
            if is_new:
                body_text = t(self.language, "linear_new_task", title=issue_title)
            else:
                body_text = t(self.language, "linear_update",
                              title=issue_title, state=issue["state"]["name"])
            short = f"{prefix}{body_text}"
            team_key = (issue.get("team") or {}).get("key")
            yield Event(
                source=self.name,
                external_id=ext_id,
                author=author,
                short=short,
                title=f"[{ident}] {issue_title}",
                body=issue.get("description") or "",
                priority=priority,
                project=team_key,
            )
            if issue["updatedAt"] > latest:
                latest = issue["updatedAt"]

        try:
            comments_data = self._gql(COMMENTS_QUERY, {"since": since})
            for c in comments_data["comments"]["nodes"]:
                ext_id = f"comment:{c['id']}"
                if self.store.is_seen(self.name, ext_id):
                    continue
                self.store.mark_seen(self.name, ext_id)
                author = (c.get("user") or {}).get("name") or "unknown"
                issue = c.get("issue") or {}
                ident = issue.get("identifier", "?")
                issue_title = issue.get("title", "")
                priority = int(issue.get("priority") or 3)
                prefix = t(self.language, "urgent_prefix") if priority in (1, 2) else ""
                short = f"{prefix}{t(self.language, 'linear_comment', title=issue_title)}"
                team_key = ident.split("-")[0] if "-" in ident else None
                yield Event(
                    source=self.name,
                    external_id=ext_id,
                    author=author,
                    short=short,
                    title=f"[{ident}] {issue_title}",
                    body=c.get("body") or "",
                    priority=priority,
                    project=team_key,
                )
                if c["createdAt"] > latest:
                    latest = c["createdAt"]
        except Exception as e:
            log.warning("Linear comments poll failed: %s", e)

        self.store.set_cursor(self.name, latest)
