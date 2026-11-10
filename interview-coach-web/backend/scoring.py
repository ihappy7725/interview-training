"""점수 산출 (interview-coach/core/scoring.py + audio_analysis.py의 voice_confidence를 그대로 옮김).

가중치와 기준은 연습용 휴리스틱이며 채용 결과로 검증된 값이 아니다.
음성 신호 수치(억양·말끝·침묵)는 브라우저(frontend/src/lib/audioAnalysis.js)에서 계산해 보내 준다.
"""
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


def voice_confidence(a: dict, filler_per_min: float) -> dict:
    """음성 자신감 '추정' 점수(0~100)와 근거. 연습용 휴리스틱."""
    if not a.get("has_speech"):
        return {"score": None, "notes": ["음성이 충분히 감지되지 않았습니다."]}
    score, notes = 100.0, []

    pv = a.get("pitch_variation_st")
    if pv is not None:
        if pv < 1.5:
            score -= 18
            notes.append(f"억양 변화가 작아 단조롭게 들릴 수 있어요 (음높이 변화 {pv}반음).")
        elif pv > 6:
            score -= 8
            notes.append(f"억양 변화가 커서 다소 불안정하게 들릴 수 있어요 ({pv}반음).")
        else:
            notes.append(f"억양 변화가 적당합니다 ({pv}반음).")

    td = a.get("tail_drop_db")
    if td is not None:
        if td < -8:
            score -= 18
            notes.append(f"말끝이 많이 작아집니다 (평균 {td}dB). 문장 끝까지 힘을 유지해 보세요.")
        elif td < -5:
            score -= 8
            notes.append(f"말끝이 약간 흐려지는 경향이 있어요 (평균 {td}dB).")
        else:
            notes.append("문장 끝까지 음량이 비교적 잘 유지됩니다.")

    lp = a.get("long_pause_count", 0)
    if lp:
        score -= min(20, lp * 7)
        notes.append(f"2초 이상 멈춤이 {lp}회 있었어요.")

    lead = a.get("lead_silence_sec", 0)
    if lead and lead > 4:
        score -= 6
        notes.append(f"첫 마디까지 {lead}초가 걸렸어요. 핵심 문장으로 바로 시작해 보세요.")

    if filler_per_min > 4:
        score -= min(20, (filler_per_min - 4) * 3)
        notes.append(f"간투사가 분당 {filler_per_min:.1f}회로 잦아 자신감이 낮아 보일 수 있어요.")

    ls = a.get("loudness_std_db")
    if ls is not None and ls > 12:
        score -= 6
        notes.append("음량 편차가 큰 편입니다. 일정한 크기로 말해 보세요.")

    return {"score": int(max(0, min(100, round(score)))), "notes": notes}
