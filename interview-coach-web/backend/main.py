"""MockMate API 서버 (FastAPI)

로컬 실행: uvicorn main:app --reload --port 8000   (backend 폴더에서)
Vercel: vercel.json의 services 설정으로 이 파일의 app이 /api/* 요청을 처리한다(경로에 /api가 그대로 붙어 들어옴).

| 경로 | 설명 | 보호 |
|---|---|---|
| GET  /api/health              | 서버 확인 | - |
| GET  /api/config              | 언어 설정, 기본 질문(서명 포함), AI·TTS 사용 가능 여부 | - |
| POST /api/access/check        | 접근 코드 확인 | - |
| GET  /api/tts/status          | ElevenLabs 사용 여부(키 값은 절대 포함하지 않음) | - |
| POST /api/tts                 | 서명된 질문만 음성(mp3)으로 | 질문 서명 |
| POST /api/questions/search    | 웹에서 실제 기출 질문 찾기 | 접근 코드 |
| POST /api/questions/generate  | AI 예상 질문 생성 | 접근 코드 |
| POST /api/answers/analyze     | 녹음 → 전사 → 지표 → AI 평가 → 점수 | 접근 코드 |
| POST /api/report/overall      | 여러 답변 종합 진단 | 접근 코드 |
"""
from __future__ import annotations

import json
import logging

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

import ai
import config
import security
import tts
from questions import DEFAULT_QUESTIONS
from scoring import compute_scores, voice_confidence
from text_metrics import text_metrics

log = logging.getLogger("uvicorn.error")
app = FastAPI(title="MockMate API", version="1.0.0")

MAX_AUDIO_BYTES = 4 * 1024 * 1024  # Vercel 함수 요청 본문 한도 4.5MB보다 작게


def bad_request(code: str, message: str) -> HTTPException:
    return HTTPException(400, {"code": code, "message": message})


def lang_cfg(lang: str) -> dict:
    if lang not in config.LANG_BY_CODE:
        raise bad_request("unsupported_lang", "지원하지 않는 언어예요(ko, en, zh만 가능).")
    return config.LANG_BY_CODE[lang]


# ── 기본 ──────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/config")
def get_config() -> dict:
    return {
        # JSON 객체 대신 순서가 유지되는 리스트로 보낸다(선택 상자 순서 고정).
        "languages": [{"name": name, **cfg, "pace_range": list(cfg["pace_range"])} for name, cfg in config.LANGUAGES.items()],
        "question_types": config.QUESTION_TYPES,
        # 기본 질문에도 서명을 붙여 둔다 → ElevenLabs로 읽을 수 있는 문장
        "default_questions": {lang: [security.signed(q, lang) for q in qs] for lang, qs in DEFAULT_QUESTIONS.items()},
        "ai": {
            "enabled": config.openai_ready(),
            "access_required": security.access_required(),
            "model": config.CHAT_MODEL,
            "transcribe_model": config.TRANSCRIBE_MODEL,
        },
    }


@app.post("/api/access/check")
def access_check(x_access_code: str | None = Header(default=None)) -> dict:
    return {"ok": security.check_access_code(x_access_code), "required": security.access_required()}


# ── TTS ───────────────────────────────────────────────────────────────────
class TTSRequest(BaseModel):
    text: str
    lang: str
    sig: str | None = None


@app.get("/api/tts/status")
def tts_status() -> dict:
    return {"enabled": tts.enabled(), "provider": "elevenlabs", "model_id": tts.MODEL_ID}


# 일반 def(async 아님): 외부 API를 기다리는 동안 FastAPI가 별도 스레드에서 실행해 다른 요청을 막지 않는다.
@app.post("/api/tts")
def text_to_speech(req: TTSRequest):
    text = req.text.strip()
    if not text:
        raise bad_request("empty_text", "읽을 문장이 비어 있어요.")
    if len(text) > tts.MAX_CHARS:
        raise bad_request("text_too_long", f"문장이 너무 길어요({len(text)}자). {tts.MAX_CHARS}자 이하만 읽을 수 있어요.")
    lang_cfg(req.lang)
    if not tts.enabled():
        raise tts.error(503, "tts_disabled", "ElevenLabs 키가 설정되지 않아 기본 음성을 사용해요.")
    if not security.verify_question(text, req.lang, req.sig):
        # 직접 입력·수정한 질문이나 외부에서 보낸 문장 → 크레딧 보호를 위해 거절(화면은 브라우저 음성으로 전환)
        raise tts.error(403, "unsigned_text", "직접 입력하거나 수정한 질문은 기본 음성으로 읽어요.")
    result, source = tts.synthesize(text, req.lang)
    headers = {"X-TTS-Source": source}
    if source == "cache":
        return FileResponse(result, media_type="audio/mpeg", headers=headers)
    return Response(content=result, media_type="audio/mpeg", headers=headers)


# ── 질문 준비 ─────────────────────────────────────────────────────────────
class SearchRequest(BaseModel):
    company: str = Field(min_length=1, max_length=80)
    role: str = Field(default="", max_length=80)
    lang: str


@app.post("/api/questions/search", dependencies=[Depends(security.require_ai)])
def search_questions(req: SearchRequest) -> dict:
    cfg = lang_cfg(req.lang)
    with ai.openai_errors("기출 질문 검색"):
        res = ai.collect_real_questions(req.company.strip(), req.role.strip() or "전체 직무", cfg["label"])
    for q in res["questions"]:
        # 면접 언어로 읽을 문장(번역이 있으면 번역)에 서명
        spoken = (q.get("question_translated") or q["question"]).strip()
        q["sig"] = security.sign_question(spoken, req.lang)
        q["spoken"] = spoken
    return res


class Profile(BaseModel):
    company: str = Field(default="", max_length=80)
    role: str = Field(default="", max_length=80)
    types: list[str] = Field(default_factory=list, max_length=10)
    jd: str = Field(default="", max_length=6000)
    resume: str = Field(default="", max_length=6000)


class GenerateRequest(BaseModel):
    profile: Profile
    real_questions: list[str] = Field(default_factory=list, max_length=40)
    n: int = Field(default=6, ge=3, le=12)
    lang: str


@app.post("/api/questions/generate", dependencies=[Depends(security.require_ai)])
def generate_questions(req: GenerateRequest) -> dict:
    cfg = lang_cfg(req.lang)
    real = [q.strip()[:300] for q in req.real_questions if q.strip()]
    with ai.openai_errors("예상 질문 생성"):
        qs = ai.generate_questions(req.profile.model_dump(), real, req.n, cfg["label"])
    for q in qs:
        q["question"] = str(q["question"]).strip()
        q["sig"] = security.sign_question(q["question"], req.lang)
    return {"questions": qs}


# ── 답변 분석 ─────────────────────────────────────────────────────────────
def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def metrics_brief(audio: dict, text: dict, vision: dict | None, cfg: dict, time_limit: int) -> str:
    """AI에게 참고로 주는 측정 지표 요약 (interview-coach/app.py의 metrics_brief와 동일)."""
    lo, hi = cfg["pace_range"]
    fill = ", ".join(f"{k}×{v}" for k, v in text["fillers"].items()) or "없음"
    habit = ", ".join(f"{k}×{v}" for k, v in text["habits"].items()) or "없음"
    lines = [
        f"- 답변 시간 {audio.get('duration_sec')}초 (제한 {time_limit}초)",
        f"- 말하기 속도 {text['pace']} {cfg['pace_unit']} → {text['pace_label']} (참고 범위 {lo}-{hi})",
        f"- 간투사 {text['filler_total']}회, 분당 {text['filler_per_min']}회: {fill}",
        f"- 습관 표현 후보: {habit}",
        f"- 2초 이상 멈춤 {audio.get('long_pause_count', 0)}회, 첫 마디까지 {audio.get('lead_silence_sec')}초",
        f"- 억양 변화 {audio.get('pitch_variation_st')}반음, 말끝 음량 변화 {audio.get('tail_drop_db')}dB",
    ]
    if vision:
        lines.append(f"- 카메라 정면 응시(추정) {vision['eye_contact'] * 100:.0f}%, 미소 {vision['smile_ratio'] * 100:.0f}%")
    return "\n".join(lines)


def _clean_vision(raw: str) -> dict | None:
    """브라우저가 보낸 얼굴 분석 요약. 15프레임 미만이면 비언어 점수를 매기지 않는다(원본과 동일)."""
    if not raw:
        return None
    try:
        v = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(v, dict) or _num(v.get("frames")) < 15:
        return None
    keys = ("frames", "face_presence", "eye_contact", "smile_ratio", "blinks_per_min", "head_movement")
    return {k: _num(v.get(k)) for k in keys}


@app.post("/api/answers/analyze", dependencies=[Depends(security.require_ai)])
def analyze_answer(
    audio: UploadFile = File(...),
    question: str = Form(..., max_length=500),
    lang: str = Form(...),
    time_limit: int = Form(90, ge=10, le=600),
    audio_metrics: str = Form("{}"),
    vision: str = Form(""),
    profile: str = Form("{}"),
) -> dict:
    cfg = lang_cfg(lang)
    data = audio.file.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, {"code": "audio_too_large", "message": "녹음 파일이 너무 커요(4MB 이하). 답변을 3분 안으로 해 주세요."})
    if len(data) < 1000:
        raise bad_request("audio_empty", "녹음된 소리가 거의 없어요. 마이크를 확인해 주세요.")
    try:
        am = json.loads(audio_metrics or "{}")
        prof = json.loads(profile or "{}")
    except ValueError:
        raise bad_request("bad_metrics", "분석 데이터 형식이 올바르지 않아요.") from None
    vis = _clean_vision(vision)

    with ai.openai_errors("음성 전사"):
        transcript = ai.transcribe(data, audio.filename or "answer.webm", audio.content_type or "audio/webm", lang)
    if not transcript:
        raise HTTPException(422, {"code": "no_speech", "message": "말소리를 알아듣지 못했어요. 마이크 가까이에서 다시 답해 주세요."})

    duration = _num(am.get("duration_sec"))
    text = text_metrics(transcript, lang, duration, cfg["pace_range"])
    voice = voice_confidence(am, text["filler_per_min"])
    brief = metrics_brief(am, text, vis, cfg, time_limit)
    with ai.openai_errors("답변 평가"):
        evaluation = ai.evaluate_answer(question, transcript, brief, prof if isinstance(prof, dict) else {}, cfg["label"])
    scores = compute_scores(evaluation, text, voice, vis, cfg["pace_range"])
    follow_up = str(evaluation.get("follow_up_question") or "").strip()
    return {
        "transcript": transcript,
        "text": text,
        "voice": voice,
        "vision": vis,
        "evaluation": evaluation,
        "scores": scores,
        "over_time": max(0, round(duration - time_limit)),
        "follow_up": security.signed(follow_up, lang) if follow_up else None,
    }


# ── 리포트 ────────────────────────────────────────────────────────────────
class OverallRequest(BaseModel):
    profile: Profile
    answers: list[dict] = Field(min_length=1, max_length=30)


@app.post("/api/report/overall", dependencies=[Depends(security.require_ai)])
def overall_report(req: OverallRequest) -> dict:
    with ai.openai_errors("종합 리포트"):
        return ai.overall_report(req.profile.model_dump(), req.answers)
