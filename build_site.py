#!/usr/bin/env python3
"""Build static site with Supabase config.js for GitHub Pages."""

from __future__ import annotations

import json
import os
import shutil
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

    out = Path("_site")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()

    shutil.copy2(template_path, out / "index.html")

    config_js = (
        "window.RED_CAT_CONFIG = "
        + json.dumps({"supabaseUrl": url, "supabaseAnonKey": key}, ensure_ascii=False)
        + ";\n"
    )
    (out / "config.js").write_text(config_js, encoding="utf-8")

    cname = Path("CNAME")
    if cname.exists():
        (out / "CNAME").write_text(cname.read_text(encoding="utf-8"), encoding="utf-8")

    state_path = Path("STATE.md")
    if state_path.exists():
        shutil.copy2(state_path, out / "STATE.md")
    else:
        (out / "STATE.md").write_text(
            "# RedCat Republic — State of the Aquarium\n\n"
            "_Ожидает первого запуска workflow RedCat Chronicle._\n",
            encoding="utf-8",
        )

    (out / ".nojekyll").write_text("", encoding="utf-8")
    print("✅ Site built in _site/ (index.html + config.js + STATE.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
