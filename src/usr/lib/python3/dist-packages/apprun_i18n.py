"""
apprun_i18n.py - small JSON-backed translation helper for AppRun tools.
"""

from __future__ import annotations

import json
import locale
import os
from pathlib import Path


LANG_DIRS = [
    Path(__file__).resolve().parents[3] / "share" / "apprun" / "lang",
    Path("/usr/share/apprun/lang"),
]
DEFAULT_LANG = "en"

_cache: dict[str, dict[str, str]] = {}


def _candidate_langs() -> list[str]:
    raw = (
        os.environ.get("APPRUN_LANG")
        or os.environ.get("LANGUAGE", "").split(":")[0]
        or os.environ.get("LC_ALL")
        or os.environ.get("LC_MESSAGES")
        or os.environ.get("LANG")
        or locale.getlocale()[0]
        or DEFAULT_LANG
    )
    raw = raw.split(".", 1)[0].split("@", 1)[0].replace("-", "_").lower()
    primary = raw.split("_", 1)[0]

    langs: list[str] = []
    for lang in (raw, primary, DEFAULT_LANG):
        if lang and lang not in langs:
            langs.append(lang)
    return langs


def _load_lang(lang: str) -> dict[str, str]:
    if lang in _cache:
        return _cache[lang]

    data: dict[str, str] = {}
    for lang_dir in LANG_DIRS:
        path = lang_dir / f"{lang}.json"
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, dict):
            data = {str(k): str(v) for k, v in raw.items()}
            break

    _cache[lang] = data
    return data


def tr(key: str, **kwargs) -> str:
    template = None
    for lang in _candidate_langs():
        template = _load_lang(lang).get(key)
        if template is not None:
            break
    if template is None:
        template = key

    try:
        return template.format(**kwargs)
    except Exception:
        return template
