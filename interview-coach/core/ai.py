"""OpenAI 호출: 음성 전사, 실제 면접 질문 수집(웹 검색), 예상 질문 생성, 답변 평가."""
from __future__ import annotations

import json
import re
from typing import Iterator
from urllib.parse import urlsplit, urlunsplit

from openai import BadRequestError, OpenAI

from core import config
from core.text_metrics import TRANSCRIBE_PROMPTS

_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        if not config.api_key_ready():
            raise RuntimeError(".env 파일에 OPENAI_API_KEY를 설정해 주세요.")
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


def _extra() -> dict:
    return {"reasoning_effort": config.REASONING_EFFORT} if config.REASONING_EFFORT else {}


def _parse_json(text: str):
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=0)
    return json.loads(text[start:])


def chat_json(system: str, user: str) -> dict:
    resp = client().chat.completions.create(
        model=config.CHAT_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
        **_extra(),
    )
    return _parse_json(resp.choices[0].message.content or "{}")


# ── 1. 음성 전사 ───────────────────────────────────────────────────────────
def transcribe(wav_bytes: bytes, lang: str) -> str:
    kwargs = {
        "model": config.TRANSCRIBE_MODEL,
        "file": ("answer.wav", wav_bytes, "audio/wav"),
        "prompt": TRANSCRIBE_PROMPTS.get(lang, ""),
    }
    if config.TRANSCRIBE_MODEL.startswith("gpt-transcribe"):
        kwargs["extra_body"] = {"languages": [lang]}  # gpt-transcribe는 languages(복수) 사용
    else:
        kwargs["language"] = lang
    try:
        res = client().audio.transcriptions.create(**kwargs)
    except BadRequestError:
        kwargs.pop("extra_body", None)
        kwargs.pop("language", None)
        res = client().audio.transcriptions.create(**kwargs)
    return (getattr(res, "text", None) or str(res)).strip()


# ── 2. 실제 면접 질문 수집 (웹 검색) ─────────────────────────────────────────
def _norm_url(u: str) -> str:
    p = urlsplit(u.strip())
    return urlunsplit((p.scheme, p.netloc.lower().removeprefix("www."), p.path.rstrip("/"), "", ""))


def collect_real_questions(company: str, role: str, lang_label: str) -> dict:
    """공개된 면접 후기/기사에서 실제 질문을 찾는다.

    모델이 제시한 출처 URL이 실제 검색 인용(url_citation)에 있는지 대조해
    verified 여부를 표시한다. 인용에 없는 항목은 '출처 미확인'으로 남긴다.
    """
    prompt = f"""
웹 검색으로 '{company}' '{role}' (또는 유사 직무) 면접에서 실제로 나왔다고 공개된 질문을 찾아라.
대상: 면접 후기 사이트(잡플래닛, 캐치, 링커리어, 코멘토, Glassdoor 등의 공개 페이지),
기업 채용 블로그·공식 채용 페이지, 언론 인터뷰 기사.

규칙:
- 출처 페이지에 실제로 적혀 있는 질문만 포함한다. 추측하거나 지어내지 않는다.
- 질문마다 근거가 된 페이지의 URL과 제목을 적는다.
- 직무가 정확히 일치하지 않으면 role_match를 "유사 직무" 또는 "회사 공통"으로 표시한다.
- 찾지 못하면 questions를 빈 배열로 두고 note에 이유를 적는다.
- 질문은 원문 언어 그대로, 면접 언어가 {lang_label}이면 해당 언어 번역을 question_translated에 추가한다.

반드시 아래 JSON만 출력:
{{"questions":[{{"question":"","question_translated":"","category":"인성|직무|경험|상황|압박|기타",
"role_match":"동일 직무|유사 직무|회사 공통","year":"알 수 없으면 빈 문자열",
"source_title":"","source_url":""}}],"note":""}}
"""
    resp = client().responses.create(
        model=config.SEARCH_MODEL,
        tools=[{"type": "web_search"}],
        input=prompt,
    )
    cited: set[str] = set()
    for item in getattr(resp, "output", []) or []:
        if getattr(item, "type", "") == "message":
            for c in getattr(item, "content", []) or []:
                for a in getattr(c, "annotations", []) or []:
                    if getattr(a, "type", "") == "url_citation" and getattr(a, "url", None):
                        cited.add(_norm_url(a.url))
    try:
        data = _parse_json(resp.output_text)
    except Exception:
        return {"questions": [], "note": "검색 결과를 해석하지 못했습니다. 다시 시도해 주세요.", "raw": resp.output_text}
    qs = data.get("questions", []) if isinstance(data, dict) else []
    for q in qs:
        q["verified"] = bool(q.get("source_url")) and _norm_url(q["source_url"]) in cited
    return {"questions": qs, "note": data.get("note", "") if isinstance(data, dict) else "", "cited_count": len(cited)}


# ── 3. AI 예상 질문 생성 ─────────────────────────────────────────────────────
def generate_questions(profile: dict, real_questions: list[str], n: int, lang_label: str) -> list[dict]:
    system = (
        "너는 채용 면접관 출신 면접 코치다. 지원자의 회사·직무·채용공고·이력 정보를 바탕으로 "
        "실제 면접에서 나올 법한 질문을 만든다. 지원자 정보에 없는 경력을 가정하지 않는다."
    )
    user = f"""
[면접 언어] {lang_label}  (질문은 이 언어로 작성)
[회사] {profile.get('company')}
[직무] {profile.get('role')}
[면접 유형] {', '.join(profile.get('types', []))}
[채용공고/JD]
{profile.get('jd') or '(없음)'}
[이력서·자기소개서 핵심]
{profile.get('resume') or '(없음)'}
[수집된 실제 기출 질문(참고, 중복 금지)]
{chr(10).join('- ' + q for q in real_questions) or '(없음)'}

요구사항:
- {n}개 생성. 면접 유형을 고르게 섞되, 이력서 내용이 있으면 그 경험을 파고드는 질문을 2개 이상 포함.
- 각 질문에 면접관의 의도(intent)와 답변 팁(tip, 1문장)을 붙인다.
JSON: {{"questions":[{{"question":"","category":"","intent":"","tip":""}}]}}
"""
    data = chat_json(system, user)
    return data.get("questions", [])


# ── 4. 실시간(스트리밍) 짧은 피드백 ──────────────────────────────────────────
def stream_quick_feedback(question: str, transcript: str, metrics_brief: str, lang_label: str) -> Iterator[str]:
    system = (
        "너는 따뜻하지만 정확한 면접 코치다. 한국어로 3~4문장, 200자 내외로 즉시 피드백한다. "
        "1) 가장 좋았던 점 1개 2) 가장 먼저 고칠 점 1개 3) 다시 답할 때 바로 써먹을 한 문장 팁. "
        "답변에 없는 내용을 칭찬하거나 지어내지 않는다."
    )
    user = f"[면접 언어] {lang_label}\n[질문] {question}\n[답변 전사]\n{transcript}\n\n[측정 지표]\n{metrics_brief}"
    stream = client().chat.completions.create(
        model=config.CHAT_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        stream=True,
        **_extra(),
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


# ── 5. 상세 평가 (논리성·구체성·적합성·STAR) ─────────────────────────────────
EVAL_SYSTEM = """너는 대기업·외국계 채용 면접관 출신 코치다. 면접 답변 '내용'을 루브릭에 따라 엄격하고 일관되게 채점한다.
말하기 속도·습관어·음성·시선은 별도 지표로 측정되므로, 너는 내용 위주로 평가하되 제공된 지표를 코멘트에 참고만 한다.

채점 루브릭(각 0~100):
- logic(논리성): 결론 先제시, 주장-근거-결론 연결, 논리 비약 없음. 90+ 결론→근거 2~3개→마무리가 명확 / 60 흐름은 있으나 근거 연결 약함 / 30 이하 산만함
- specificity(구체성): 수치·기간·역할·행동·결과 등 구체 정보. 90+ 정량 결과와 본인 행동이 명확 / 60 사례는 있으나 모호 / 30 이하 일반론
- relevance(질문 적합성): 질문 의도에 직접 답함, 회사·직무와 연결.
- structure(구조): 경험 질문이면 STAR(상황·과제·행동·결과) 충족도, 그 외 질문이면 두괄식·마무리 구조.

규칙:
- 전사에 없는 사실을 지어내지 않는다. improved_answer에서 지원자가 말하지 않은 수치·사실이 필요하면 [구체적 수치], [본인 역할] 같은 빈칸으로 둔다.
- 피드백은 한국어로, improved_answer와 follow_up_question은 면접 언어로 작성한다.
- 답변이 매우 짧거나 질문과 무관하면 점수를 낮게 주고 이유를 밝힌다.

JSON만 출력:
{"scores":{"logic":0,"specificity":0,"relevance":0,"structure":0},
 "star":{"situation":false,"task":false,"action":false,"result":false,"applicable":true},
 "summary":"한 줄 총평",
 "strengths":["..."],
 "improvements":["구체적 개선점(무엇을 어떻게)"],
 "missing_evidence":["보강하면 좋을 근거/정보"],
 "improved_answer":"...",
 "follow_up_question":"이 답변에 면접관이 이어서 물을 꼬리질문"}"""


def evaluate_answer(question: str, transcript: str, metrics_brief: str, profile: dict, lang_label: str) -> dict:
    user = f"""[면접 언어] {lang_label}
[회사/직무] {profile.get('company') or '-'} / {profile.get('role') or '-'}
[질문] {question}
[답변 전사(간투사 포함)]
{transcript}

[측정 지표]
{metrics_brief}"""
    data = chat_json(EVAL_SYSTEM, user)
    sc = data.get("scores", {})
    data["scores"] = {k: int(max(0, min(100, float(sc.get(k, 0) or 0)))) for k in ("logic", "specificity", "relevance", "structure")}
    return data


# ── 6. 종합 리포트 ───────────────────────────────────────────────────────────
def overall_report(profile: dict, answers: list[dict]) -> dict:
    lines = []
    for i, a in enumerate(answers, 1):
        ev = a.get("evaluation", {})
        lines.append(
            f"Q{i}. {a['question']}\n- 종합 {a['scores']['total']} / 내용 {a['scores']['content']} / 전달 {a['scores']['delivery']} / 비언어 {a['scores'].get('nonverbal')}\n"
            f"- 총평: {ev.get('summary', '')}\n- 개선점: {'; '.join(ev.get('improvements', [])[:3])}\n"
            f"- 속도 {a['text']['pace']} ({a['text']['pace_label']}), 간투사 분당 {a['text']['filler_per_min']}"
        )
    system = "너는 면접 코치다. 여러 답변 결과를 종합해 반복되는 패턴을 찾고 우선순위가 분명한 연습 계획을 한국어로 제시한다. 데이터에 없는 내용은 추정하지 않는다."
    user = f"""[회사/직무] {profile.get('company')} / {profile.get('role')}
{chr(10).join(lines)}

JSON: {{"headline":"한 줄 진단","strengths":["반복적으로 보인 강점"],"patterns":["반복되는 약점 패턴(근거 포함)"],
"priorities":["가장 먼저 고칠 것 순서대로 최대 3개"],"practice_plan":["다음 연습 3회 각각의 구체 과제"]}}"""
    return chat_json(system, user)
