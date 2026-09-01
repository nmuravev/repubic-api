#!/usr/bin/env python3
"""Build static site with Supabase credentials injected into index.html."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def get_env(*names: str) -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def main() -> int:
    url = get_env("SUPABASE_URL", "SUPABASE_URL_VAL")
    key = get_env("SUPABASE_ANON_KEY", "SUPABASE_ANON_VAL")

    if not url.startswith(("http://", "https://")):
        print(f"❌ SUPABASE_URL must be a valid HTTP(S) URL, got: {url!r}")
        return 1
    if not key:
        print("❌ SUPABASE_ANON_KEY is empty")
        return 1

    template_path = Path("index.html")
    if not template_path.exists():
        print("❌ index.html not found")
        return 1

    template = template_path.read_text(encoding="utf-8")
    if "__SUPABASE_URL__" not in template or "__SUPABASE_ANON_KEY__" not in template:
        print("❌ index.html is missing Supabase placeholders")
        return 1

    built = (
        template.replace("__SUPABASE_URL__", url).replace("__SUPABASE_ANON_KEY__", key)
    )
    if "__SUPABASE_URL__" in built or "__SUPABASE_ANON_KEY__" in built:
        print("❌ Placeholders remain after injection")
        return 1

    out = Path("_site")
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(built, encoding="utf-8")

    cname = Path("CNAME")
    if cname.exists():
        (out / "CNAME").write_text(cname.read_text(encoding="utf-8"), encoding="utf-8")

    (out / ".nojekyll").write_text("", encoding="utf-8")
    print("✅ Site built in _site/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
