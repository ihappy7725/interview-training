"""Markdown 리포트 생성 (다운로드용)."""
from __future__ import annotations

from datetime import datetime

from core.scoring import LABELS, grade


def build_markdown(profile: dict, answers: list[dict], overall: dict | None, pace_unit: str) -> str:
    n = len(answers)
    avg = lambda k: round(sum((a["scores"][k] or 0) for a in answers) / n) if n else 0  # noqa: E731
    out = [
        f"# 면접 연습 리포트 — {profile.get('company') or '회사 미입력'} / {profile.get('role') or '직무 미입력'}",
        f"- 일시: {datetime.now():%Y-%m-%d %H:%M}",
        f"- 면접 언어: {profile.get('language', '')}",
        f"- 답변 수: {n}",
        f"- **종합 {avg('total')}점 ({grade(avg('total'))})** · 내용 {avg('content')} · 전달력 {avg('delivery')}",
        "",
        "> 점수는 연습용 지표입니다. 내용 점수는 GPT 루브릭 평가, 전달력·비언어 점수는 음성/영상 신호 기반 휴리스틱입니다.",
        "",
    ]
    if overall:
        out += ["## 종합 진단", f"**{overall.get('headline', '')}**", ""]
        for title, key in [("강점", "strengths"), ("반복 패턴", "patterns"), ("우선순위", "priorities"), ("다음 연습 계획", "practice_plan")]:
            items = overall.get(key) or []
            if items:
                out.append(f"### {title}")
                out += [f"{i}. {x}" for i, x in enumerate(items, 1)] + [""]

    for i, a in enumerate(answers, 1):
        ev, sc, tx, au = a.get("evaluation", {}), a["scores"], a["text"], a["audio"]
        out += [
            f"## Q{i}. {a['question']}",
            f"**종합 {sc['total']}점** · 내용 {sc['content']} · 전달력 {sc['delivery']} · 비언어 {sc['nonverbal'] if sc['nonverbal'] is not None else '측정 안 함'}",
            "",
            "| 항목 | 점수 |", "|---|---|",
        ]
        out += [f"| {LABELS[k]} | {v} |" for k, v in sc["radar"].items()]
        fillers = ", ".join(f"{k}×{v}" for k, v in tx["fillers"].items()) or "없음"
        habits = ", ".join(f"{k}×{v}" for k, v in tx["habits"].items()) or "없음"
        out += [
            "",
            f"- 답변 시간 {au.get('duration_sec')}초 · 속도 {tx['pace']} {pace_unit} ({tx['pace_label']})",
            f"- 간투사: {fillers} (분당 {tx['filler_per_min']}) · 습관 표현 후보: {habits}",
            "",
            "**답변 전사**", "", f"> {a['transcript']}", "",
            f"**총평** {ev.get('summary', '')}", "",
        ]
        for title, key in [("잘한 점", "strengths"), ("개선점", "improvements"), ("보강할 근거", "missing_evidence")]:
            if ev.get(key):
                out += [f"**{title}**"] + [f"- {x}" for x in ev[key]] + [""]
        if a.get("voice", {}).get("notes"):
            out += ["**음성 분석**"] + [f"- {x}" for x in a["voice"]["notes"]] + [""]
        if ev.get("improved_answer"):
            out += ["**개선 답안 예시** ([ ]는 본인 경험으로 채울 부분)", "", ev["improved_answer"], ""]
        if ev.get("follow_up_question"):
            out += [f"**예상 꼬리질문** {ev['follow_up_question']}", ""]
    return "\n".join(out)
