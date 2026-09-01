#!/usr/bin/env python3
"""Validate Supabase credentials before orchestrator run."""

import os
import sys

from supabase_client import verify_supabase_connection


def main() -> int:
    try:
        verify_supabase_connection(
            os.environ.get("SUPABASE_URL"),
            os.environ.get("SUPABASE_ANON_KEY"),
        )
        print("✅ Supabase connection OK")
        return 0
    except Exception as exc:
        print(f"❌ Supabase validation failed: {exc}")
        print(
            "Проверьте GitHub Secrets:\n"
            "  SUPABASE_URL — https://xxxx.supabase.co\n"
            "  SUPABASE_ANON_KEY — anon JWT (eyJ...) или publishable (sb_publishable_...)\n"
            "Без лишних пробелов и кавычек."
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
