"""연습 기록 저장/불러오기 (로컬 JSON)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from core.config import DATA_DIR, HISTORY_PATH


def load_history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_session(profile: dict, answers: list[dict]) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    hist = load_history()
    n = len(answers)
    avg = lambda key: round(sum(a["scores"][key] or 0 for a in answers) / n) if n else 0  # noqa: E731
    nv = [a["scores"]["nonverbal"] for a in answers if a["scores"].get("nonverbal") is not None]
    record = {
        "id": uuid.uuid4().hex[:8],
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "company": profile.get("company", ""),
        "role": profile.get("role", ""),
        "language": profile.get("language", ""),
        "count": n,
        "total": avg("total"),
        "content": avg("content"),
        "delivery": avg("delivery"),
        "nonverbal": round(sum(nv) / len(nv)) if nv else None,
        "filler_per_min": round(sum(a["text"]["filler_per_min"] for a in answers) / n, 2) if n else 0,
        "answers": [
            {"question": a["question"], "transcript": a["transcript"], "scores": a["scores"],
             "summary": a.get("evaluation", {}).get("summary", "")}
            for a in answers
        ],
    }
    hist.append(record)
    HISTORY_PATH.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")
    return record
