"""전사 텍스트 기반 지표: 말하기 속도, 간투사(습관어) 검출."""
from __future__ import annotations

import re
from collections import Counter

# filler: 의미 없는 간투사(음, 어, um, uh …) → 점수에 반영
# habit : 의미가 있을 수도 있는 습관 표현(이제, 약간, like …) → '후보'로만 표시
FILLERS = {
    "ko": {
        "filler_re": r"^(음+|으+음+|어+|아+|에+|흠+|으+|저기)$",
        "habit": ["이제", "약간", "막", "그러니까", "뭐", "좀", "진짜", "사실", "그냥", "되게"],
    },
    "en": {
        "filler_re": r"\b(u+m+|u+h+|e+r+m*|a+h+|h+m+|mm+)\b",
        "habit": ["like", "you know", "basically", "actually", "i mean", "kind of", "sort of", "literally", "right"],
    },
    "zh": {
        "filler_chars": ["嗯", "呃", "额", "啊", "哦"],
        "habit": ["那个", "就是", "然后", "这个", "其实", "反正"],
    },
}

TRANSCRIBE_PROMPTS = {
    # 전사 모델이 간투사를 지우지 않도록 간투사가 포함된 예시 문장을 컨텍스트로 준다.
    "ko": "면접 답변 녹음입니다. 음, 어, 그러니까 저는... 음, 그 프로젝트에서 어, 데이터를 분석했고요. 아, 그리고 음...",
    "en": "Interview answer. Umm, let me think like, hmm... Okay, uh, here's what I'm, like, thinking.",
    "zh": "面试回答录音。嗯，那个，我觉得……呃，就是说，嗯，这个项目……",
}


def _tokens(text: str) -> list[str]:
    return [re.sub(r"[^\w가-힣]", "", t) for t in text.split() if re.sub(r"[^\w가-힣]", "", t)]


def speech_units(text: str, lang: str) -> int:
    """속도 계산 단위: 한국어=한글 음절, 영어=단어, 중국어=한자."""
    if lang == "ko":
        return len(re.findall(r"[가-힣]", text))
    if lang == "zh":
        return len(re.findall(r"[一-鿿]", text))
    return len(re.findall(r"[A-Za-z']+", text))


def detect_fillers(text: str, lang: str) -> dict:
    cfg = FILLERS[lang]
    fillers: Counter = Counter()
    habits: Counter = Counter()
    if lang == "ko":
        pat = re.compile(cfg["filler_re"])
        for t in _tokens(text):
            if pat.match(t):
                key = t[0] if t[0] in "음어아에흠으" else t
                fillers[key] += 1
            elif t in cfg["habit"]:
                habits[t] += 1
    elif lang == "en":
        low = text.lower()
        for m in re.finditer(cfg["filler_re"], low):
            fillers[re.sub(r"(.)\1+", r"\1", m.group(1))] += 1
        for h in cfg["habit"]:
            n = len(re.findall(rf"\b{re.escape(h)}\b", low))
            if n:
                habits[h] += n
    else:  # zh
        for ch in cfg["filler_chars"]:
            n = text.count(ch)
            if n:
                fillers[ch] += n
        for h in cfg["habit"]:
            n = text.count(h)
            if n:
                habits[h] += n
    return {
        "filler_total": sum(fillers.values()),
        "fillers": dict(fillers.most_common()),
        "habit_total": sum(habits.values()),
        "habits": dict(habits.most_common()),
    }


def text_metrics(text: str, lang: str, duration_sec: float, pace_range: tuple[int, int]) -> dict:
    minutes = max(duration_sec, 1e-6) / 60
    units = speech_units(text, lang)
    pace = units / minutes if duration_sec > 0 else 0.0
    f = detect_fillers(text, lang)
    lo, hi = pace_range
    if pace == 0:
        pace_label = "측정 불가"
    elif pace < lo:
        pace_label = "느림"
    elif pace > hi:
        pace_label = "빠름"
    else:
        pace_label = "적정"
    return {
        "units": units,
        "pace": round(pace, 1),
        "pace_label": pace_label,
        "filler_per_min": round(f["filler_total"] / minutes, 2) if duration_sec > 0 else 0.0,
        **f,
    }
