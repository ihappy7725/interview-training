"""공개 배포 시 비용 보호.

1) 접근 코드: OpenAI를 쓰는 API(질문 생성·검색·답변 평가·종합 리포트)는 요청 헤더 X-Access-Code가
   APP_ACCESS_CODE와 같아야 한다.
   - 로컬(Vercel 밖)에서 APP_ACCESS_CODE를 비워 두면 코드 없이 허용(개발 편의).
   - Vercel에서 비워 두면 AI 기능을 막는다(설정 실수로 공개되는 것 방지).
2) 질문 서명: 서버가 만든 질문(기본·AI 생성·웹 수집·꼬리질문)에만 서명을 붙이고,
   /api/tts는 서명이 맞는 문장만 ElevenLabs로 읽는다. 서버에 저장할 것이 없어 서버리스에서도 동작한다.
"""
from __future__ import annotations

import hashlib
import hmac

from fastapi import Header, HTTPException

import config


def _secret() -> bytes:
    explicit = config.env("TTS_SIGNING_SECRET")
    if explicit:
        return explicit.encode()
    # 따로 정하지 않으면 서버만 아는 값(ElevenLabs 키)에서 만든다. 키 자체는 밖으로 나가지 않는다.
    base = config.env("ELEVENLABS_API_KEY") or config.APP_ACCESS_CODE or "mockmate-local-dev"
    return hashlib.sha256(("mockmate-question-signature|" + base).encode()).digest()


def sign_question(text: str, lang: str) -> str:
    msg = f"{lang}\n{text.strip()}".encode()
    return hmac.new(_secret(), msg, hashlib.sha256).hexdigest()[:32]


def verify_question(text: str, lang: str, sig: str | None) -> bool:
    return bool(sig) and hmac.compare_digest(sign_question(text, lang), sig)


def signed(text: str, lang: str) -> dict:
    return {"question": text, "sig": sign_question(text, lang)}


def access_required() -> bool:
    return bool(config.APP_ACCESS_CODE) or config.ON_VERCEL


def check_access_code(code: str | None) -> bool:
    if not access_required():
        return True
    if not config.APP_ACCESS_CODE:  # Vercel인데 코드를 설정하지 않음
        return False
    return bool(code) and hmac.compare_digest(code.strip().encode(), config.APP_ACCESS_CODE.encode())


def require_ai(x_access_code: str | None = Header(default=None)) -> None:
    """FastAPI 의존성: AI 엔드포인트 앞에서 키·접근 코드를 확인한다."""
    if not config.openai_ready():
        raise HTTPException(503, {"code": "ai_disabled", "message": "서버에 OPENAI_API_KEY가 설정되지 않아 AI 기능을 쓸 수 없어요."})
    if config.ON_VERCEL and not config.APP_ACCESS_CODE:
        raise HTTPException(503, {"code": "access_code_not_set", "message": "배포 서버에 APP_ACCESS_CODE가 설정되지 않아 AI 기능을 잠가 두었어요."})
    if not check_access_code(x_access_code):
        raise HTTPException(401, {"code": "access_denied", "message": "접근 코드가 맞지 않아요. 사이드바에서 접근 코드를 입력해 주세요."})
