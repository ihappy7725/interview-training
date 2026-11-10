"""점수 산출. 가중치와 기준은 연습용 휴리스틱이며 채용 결과로 검증된 값이 아니다."""
from __future__ import annotations

WEIGHTS = {"content": 0.55, "delivery": 0.25, "nonverbal": 0.20}

LABELS = {
    "logic": "논리성",
    "specificity": "구체성",
    "relevance": "질문 적합성",
    "structure": "구조(STAR)",
    "pace": "말하기 속도",
    "filler": "습관어 절제",
    "voice": "음성 자신감",
    "eye": "시선 처리",
}


def pace_score(pace: float, rng: tuple[int, int]) -> int:
    lo, hi = rng
    if pace <= 0:
        return 0
    if lo <= pace <= hi:
        return 100
    dist = (lo - pace) / lo if pace < lo else (pace - hi) / hi
    return int(max(0, 100 - dist * 250))  # 범위에서 20% 벗어나면 50점


def filler_score(per_min: float) -> int:
    if per_min <= 2:
        return 100
    return int(max(0, 100 - (per_min - 2) * 8))


def nonverbal_score(v: dict | None) -> int | None:
    if not v or v.get("frames", 0) < 15:
        return None
    eye = v["eye_contact"] * 100
    presence = v["face_presence"] * 100
    mv = v["head_movement"]  # 프레임당 이동 %, 0.3 이하 안정
    stability = 100 if mv <= 0.3 else max(0, 100 - (mv - 0.3) * 120)
    smile = v["smile_ratio"]
    expression = 100 if 0.1 <= smile <= 0.6 else (70 if smile < 0.1 else 80)
    return int(round(eye * 0.5 + presence * 0.2 + stability * 0.15 + expression * 0.15))


def compute_scores(evaluation: dict, text: dict, voice: dict, vision: dict | None, pace_range) -> dict:
    s = evaluation.get("scores", {})
    content = round(sum(s.get(k, 0) for k in ("logic", "specificity", "relevance", "structure")) / 4)
    p = pace_score(text["pace"], pace_range)
    f = filler_score(text["filler_per_min"])
    v = voice.get("score")
    delivery_parts = [p, f] + ([v] if v is not None else [])
    delivery = round(sum(delivery_parts) / len(delivery_parts))
    nv = nonverbal_score(vision)

    parts = {"content": content, "delivery": delivery}
    if nv is not None:
        parts["nonverbal"] = nv
    wsum = sum(WEIGHTS[k] for k in parts)
    total = round(sum(parts[k] * WEIGHTS[k] for k in parts) / wsum)

    radar = {
        "logic": s.get("logic", 0),
        "specificity": s.get("specificity", 0),
        "relevance": s.get("relevance", 0),
        "structure": s.get("structure", 0),
        "pace": p,
        "filler": f,
        "voice": v if v is not None else 0,
        "eye": int(vision["eye_contact"] * 100) if nv is not None else 0,
    }
    return {"total": total, "content": content, "delivery": delivery, "nonverbal": nv, "radar": radar}


def grade(total: int) -> str:
    if total >= 85:
        return "실전 준비 완료"
    if total >= 70:
        return "좋음 · 다듬기"
    if total >= 55:
        return "보통 · 연습 필요"
    return "기초 보강 필요"
