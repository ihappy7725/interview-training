"""OpenAI 호출: 음성 전사, 실제 면접 질문 수집(웹 검색), 예상 질문 생성, 답변 평가, 종합 리포트.

기존 interview-coach/core/ai.py의 프롬프트를 그대로 옮기고, 호출 방식만 현재 공식 문서(2026-11-10 확인)에 맞췄다.
- 텍스트: Responses API + JSON 출력  client.responses.create(..., text={"format": {"type": "json_object"}})
- 웹 검색: Responses API tools=[{"type": "web_search"}], 출처는 annotations의 url_citation
- 전사: client.audio.transcriptions.create, gpt-transcribe는 languages(배열) 사용
- 변경점: '즉시 피드백'을 따로 스트리밍하지 않고, 상세 평가 응답의 coach_comment로 함께 받는다(호출 1회 절약).
"""
from __future__ import annotations

import json
import logging
import re
from contextlib import contextmanager
from urllib.parse import urlsplit, urlunsplit

import openai
from fastapi import HTTPException

import config
from text_metrics import TRANSCRIBE_PROMPTS

log = logging.getLogger("uvicorn.error")
_client: openai.OpenAI | None = None


def client() -> openai.OpenAI:
    global _client
    if _client is None:
        _client = openai.OpenAI(api_key=config.OPENAI_API_KEY, timeout=120, max_retries=1)
    return _client


@contextmanager
def openai_errors(what: str):
    """OpenAI 오류 → 화면에 보여줄 한국어 메시지. 키·요청 본문은 로그에 남기지 않는다."""
    try:
        yield
    except HTTPException:
        raise
    except openai.AuthenticationError:
        raise HTTPException(502, {"code": "openai_auth", "message": "OpenAI API 키가 올바르지 않아요. 서버의 OPENAI_API_KEY를 확인해 주세요."}) from None
    except openai.RateLimitError as e:
        if "insufficient_quota" in str(getattr(e, "code", "") or e):
            raise HTTPException(402, {"code": "openai_quota", "message": "OpenAI 크레딧(사용 한도)이 부족해요. OpenAI 결제·한도 설정을 확인해 주세요."}) from None
        raise HTTPException(429, {"code": "openai_rate_limit", "message": "OpenAI 요청이 너무 많아요. 잠시 뒤 다시 시도해 주세요."}) from None
    except openai.APITimeoutError:
        raise HTTPException(504, {"code": "openai_timeout", "message": f"{what} 응답이 너무 늦어요. 잠시 뒤 다시 시도해 주세요."}) from None
    except openai.APIConnectionError:
        raise HTTPException(502, {"code": "openai_unreachable", "message": "OpenAI 서버에 연결할 수 없어요. 인터넷 연결을 확인해 주세요."}) from None
    except openai.APIStatusError as e:
        log.warning("OpenAI 오류(%s): HTTP %s", what, e.status_code)
        raise HTTPException(502, {"code": "openai_error", "message": f"{what} 중 OpenAI 오류가 발생했어요(HTTP {e.status_code})."}) from None
    except (ValueError, KeyError) as e:
        log.warning("AI 응답 해석 실패(%s): %s", what, type(e).__name__)
        raise HTTPException(502, {"code": "ai_bad_output", "message": f"{what} 결과를 해석하지 못했어요. 다시 시도해 주세요."}) from None


def _reasoning() -> dict:
    return {"reasoning": {"effort": config.REASONING_EFFORT}} if config.REASONING_EFFORT else {}


def _parse_json(text: str):
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1)
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    return json.loads(text[min(starts):] if starts else text)


def chat_json(system: str, user: str) -> dict:
    # JSON 모드는 instructions가 아니라 input(사용자 메시지)에 'json'이라는 단어가 있어야 한다.
    # 실제 호출에서 400 "Response input messages must contain the word 'json'" 오류를 확인하고 추가함(2026-11-10).
    if "json" not in user.lower():
        user += "\n\n(응답은 위 형식의 JSON 객체로만)"
    resp = client().responses.create(
        model=config.CHAT_MODEL,
        instructions=system,
        input=user,
        text={"format": {"type": "json_object"}},
        **_reasoning(),
    )
    data = _parse_json(resp.output_text)
    if not isinstance(data, dict):
        raise ValueError("JSON 객체가 아님")
    return data


# ── 1. 음성 전사 ───────────────────────────────────────────────────────────
def transcribe(audio: bytes, filename: str, content_type: str, lang: str) -> str:
    kwargs: dict = {
        "model": config.TRANSCRIBE_MODEL,
        "file": (filename, audio, content_type),
        "prompt": TRANSCRIBE_PROMPTS.get(lang, ""),  # 간투사를 지우지 않도록 예시 문장 제공
    }
    if config.TRANSCRIBE_MODEL.startswith("gpt-transcribe"):
        kwargs["extra_body"] = {"languages": [lang]}  # gpt-transcribe는 language 대신 languages(배열)
    else:
        kwargs["language"] = lang
    try:
        res = client().audio.transcriptions.create(**kwargs)
    except openai.BadRequestError:
        # 언어 지정 방식이 모델과 맞지 않으면 언어 없이 한 번 더
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

    모델이 제시한 출처 URL이 실제 검색 인용(url_citation)에 있는지 대조해 verified를 표시한다.
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
    # include=web_search_call.action.sources: 검색 도구가 실제로 가져온 페이지 목록을 함께 받는다(공식 문서 옵션).
    # 모델이 JSON만 출력하면 본문 인용(url_citation)이 붙지 않는 경우가 있어서(실제 호출에서 0개 확인),
    # '실제 검색 결과에 있던 URL인지'를 이 목록과 인용 둘 다로 대조한다.
    resp = client().responses.create(
        model=config.SEARCH_MODEL,
        tools=[{"type": "web_search"}],
        include=["web_search_call.action.sources"],
        input=prompt,
    )
    cited: set[str] = set()
    for item in getattr(resp, "output", []) or []:
        kind = getattr(item, "type", "")
        if kind == "web_search_call":
            action = getattr(item, "action", None)
            for src in getattr(action, "sources", None) or []:
                url = getattr(src, "url", None) or (src.get("url") if isinstance(src, dict) else None)
                if url:
                    cited.add(_norm_url(url))
            if getattr(action, "url", None):  # open_page 동작이면 연 페이지 주소
                cited.add(_norm_url(action.url))
        elif kind == "message":
            for c in getattr(item, "content", []) or []:
                for a in getattr(c, "annotations", []) or []:
                    if getattr(a, "type", "") == "url_citation" and getattr(a, "url", None):
                        cited.add(_norm_url(a.url))
    try:
        data = _parse_json(resp.output_text)
    except ValueError:
        return {"questions": [], "note": "검색 결과를 해석하지 못했어요. 다시 시도해 주세요."}
    qs = data.get("questions", []) if isinstance(data, dict) else []
    qs = [q for q in qs if isinstance(q, dict) and str(q.get("question", "")).strip()]
    for q in qs:
        q["verified"] = bool(q.get("source_url")) and _norm_url(q["source_url"]) in cited
    return {"questions": qs, "note": data.get("note", "") if isinstance(data, dict) else "", "cited_count": len(cited)}


# ── 3. AI 예상 질문 생성 ─────────────────────────────────────────────────────
def generate_questions(profile: dict, real_questions: list[str], n: int, lang_label: str) -> list[dict]:
    system = (
        "너는 채용 면접관 출신 면접 코치다. 지원자의 회사·직무·채용공고·이력 정보를 바탕으로 "
        "실제 면접에서 나올 법한 질문을 만든다. 지원자 정보에 없는 경력을 가정하지 않는다. 결과는 JSON으로만 답한다."
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
- 각 질문에 면접관의 의도(intent)와 답변 팁(tip, 1문장)을 붙인다. intent와 tip은 한국어.
JSON: {{"questions":[{{"question":"","category":"","intent":"","tip":""}}]}}
"""
    data = chat_json(system, user)
    return [q for q in data.get("questions", []) if isinstance(q, dict) and str(q.get("question", "")).strip()][:n]


# ── 4. 답변 평가 (즉시 피드백 + 논리성·구체성·적합성·STAR) ───────────────────
EVAL_SYSTEM = """너는 대기업·외국계 채용 면접관 출신 코치다. 면접 답변 '내용'을 루브릭에 따라 엄격하고 일관되게 채점한다.
말하기 속도·습관어·음성·시선은 별도 지표로 측정되므로, 너는 내용 위주로 평가하되 제공된 지표를 코멘트에 참고만 한다.

채점 루브릭(각 0~100):
- logic(논리성): 결론 先제시, 주장-근거-결론 연결, 논리 비약 없음. 90+ 결론→근거 2~3개→마무리가 명확 / 60 흐름은 있으나 근거 연결 약함 / 30 이하 산만함
- specificity(구체성): 수치·기간·역할·행동·결과 등 구체 정보. 90+ 정량 결과와 본인 행동이 명확 / 60 사례는 있으나 모호 / 30 이하 일반론
- relevance(질문 적합성): 질문 의도에 직접 답함, 회사·직무와 연결.
- structure(구조): 경험 질문이면 STAR(상황·과제·행동·결과) 충족도, 그 외 질문이면 두괄식·마무리 구조.

coach_comment(즉시 피드백): 따뜻하지만 정확한 코치의 말투로 한국어 3~4문장, 200자 내외.
1) 가장 좋았던 점 1개 2) 가장 먼저 고칠 점 1개 3) 다시 답할 때 바로 써먹을 한 문장 팁.

규칙:
- 전사에 없는 사실을 지어내지 않는다. improved_answer에서 지원자가 말하지 않은 수치·사실이 필요하면 [구체적 수치], [본인 역할] 같은 빈칸으로 둔다.
- 피드백은 한국어로, improved_answer와 follow_up_question은 면접 언어로 작성한다.
- 답변이 매우 짧거나 질문과 무관하면 점수를 낮게 주고 이유를 밝힌다.

JSON만 출력:
{"coach_comment":"...",
 "scores":{"logic":0,"specificity":0,"relevance":0,"structure":0},
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
    sc = data.get("scores", {}) or {}

    def clamp(v) -> int:
        try:
            return int(max(0, min(100, float(v or 0))))
        except (TypeError, ValueError):
            return 0

    data["scores"] = {k: clamp(sc.get(k)) for k in ("logic", "specificity", "relevance", "structure")}
    for key in ("strengths", "improvements", "missing_evidence"):
        data[key] = [str(x) for x in (data.get(key) or []) if str(x).strip()]
    return data


# ── 5. 종합 리포트 ───────────────────────────────────────────────────────────
def overall_report(profile: dict, answers: list[dict]) -> dict:
    lines = []
    for i, a in enumerate(answers, 1):
        sc, tx = a.get("scores", {}), a.get("text", {})
        lines.append(
            f"Q{i}. {a.get('question', '')}\n- 종합 {sc.get('total')} / 내용 {sc.get('content')} / 전달 {sc.get('delivery')} / 비언어 {sc.get('nonverbal')}\n"
            f"- 총평: {a.get('summary', '')}\n- 개선점: {'; '.join((a.get('improvements') or [])[:3])}\n"
            f"- 속도 {tx.get('pace')} ({tx.get('pace_label')}), 간투사 분당 {tx.get('filler_per_min')}"
        )
    system = ("너는 면접 코치다. 여러 답변 결과를 종합해 반복되는 패턴을 찾고 우선순위가 분명한 연습 계획을 한국어로 제시한다. "
              "데이터에 없는 내용은 추정하지 않는다. 결과는 JSON으로만 답한다.")
    user = f"""[회사/직무] {profile.get('company') or '-'} / {profile.get('role') or '-'}
{chr(10).join(lines)}

JSON: {{"headline":"한 줄 진단","strengths":["반복적으로 보인 강점"],"patterns":["반복되는 약점 패턴(근거 포함)"],
"priorities":["가장 먼저 고칠 것 순서대로 최대 3개"],"practice_plan":["다음 연습 3회 각각의 구체 과제"]}}"""
    data = chat_json(system, user)
    return {k: data.get(k) for k in ("headline", "strengths", "patterns", "priorities", "practice_plan")}
