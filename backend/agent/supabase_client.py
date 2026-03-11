"""
FireReach — Supabase Client (singleton)

Used by:
  • agent loop — progress events for SSE streaming
  • outreach sender — idempotency + audit log
  • contact resolver — credit tracking
"""

from __future__ import annotations
import os
from functools import lru_cache

from supabase import create_client, Client


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)
