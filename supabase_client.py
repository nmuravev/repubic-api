"""Supabase client via PostgREST — works with JWT anon keys and sb_publishable_* keys."""

from __future__ import annotations

import re
from typing import Any, Optional

from postgrest import SyncPostgrestClient


class _TableProxy:
    def __init__(self, query: Any):
        self._q = query

    def select(self, *args: Any, **kwargs: Any) -> "_TableProxy":
        self._q = self._q.select(*args, **kwargs)
        return self

    def insert(self, *args: Any, **kwargs: Any) -> "_TableProxy":
        self._q = self._q.insert(*args, **kwargs)
        return self

    def update(self, *args: Any, **kwargs: Any) -> "_TableProxy":
        self._q = self._q.update(*args, **kwargs)
        return self

    def eq(self, *args: Any, **kwargs: Any) -> "_TableProxy":
        self._q = self._q.eq(*args, **kwargs)
        return self

    def gte(self, *args: Any, **kwargs: Any) -> "_TableProxy":
        self._q = self._q.gte(*args, **kwargs)
        return self

    def order(self, *args: Any, **kwargs: Any) -> "_TableProxy":
        self._q = self._q.order(*args, **kwargs)
        return self

    def limit(self, *args: Any, **kwargs: Any) -> "_TableProxy":
        self._q = self._q.limit(*args, **kwargs)
        return self

    def single(self) -> "_TableProxy":
        self._q = self._q.single()
        return self

    def execute(self) -> Any:
        return self._q.execute()


class SupabaseRestClient:
    def __init__(self, supabase_url: str, supabase_key: str):
        self.supabase_url = supabase_url.rstrip("/")
        self.supabase_key = supabase_key
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
        }
        self._rest = SyncPostgrestClient(f"{self.supabase_url}/rest/v1", headers=headers)

    def table(self, name: str) -> _TableProxy:
        return _TableProxy(self._rest.from_(name))


def normalize_supabase_credentials(url: Optional[str], key: Optional[str]) -> tuple[str, str]:
    clean_url = (url or "").strip().rstrip("/")
    clean_key = (key or "").strip()
    if not clean_url or not clean_key:
        raise ValueError("SUPABASE_URL и SUPABASE_ANON_KEY обязательны")
    if not re.match(r"^https?://", clean_url):
        raise ValueError("SUPABASE_URL должен начинаться с http:// или https://")
    return clean_url, clean_key


def create_supabase_client(url: Optional[str], key: Optional[str]) -> SupabaseRestClient:
    """Create Supabase client. Always uses PostgREST (no supabase-py create_client)."""
    clean_url, clean_key = normalize_supabase_credentials(url, key)
    return SupabaseRestClient(clean_url, clean_key)


def verify_supabase_connection(url: Optional[str], key: Optional[str]) -> None:
    client = create_supabase_client(url, key)
    client.table("citizens").select("id").limit(1).execute()
