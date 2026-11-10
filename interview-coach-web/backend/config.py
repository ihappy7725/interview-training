"""서버 전역 설정: .env 로드, 언어별 설정, 모델 이름.

.env는 서버가 시작될 때 한 번만 읽는다. 값을 바꾸면 서버를 껐다 켜야 반영된다.
Vercel에서는 .env 파일 대신 프로젝트의 Environment Variables에 같은 이름으로 넣는다.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str = "") -> str:
    return (os.getenv(name) or "").strip() or default


def real_key(value: str) -> bool:
    """.env.example의 자리표시자(sk-your-key-here 등)를 그대로 둔 경우는 '키 없음'으로 본다."""
    return bool(value) and "your" not in value.lower()


ON_VERCEL = bool(os.getenv("VERCEL"))  # Vercel이 자동으로 넣어 주는 환경 변수

# ── OpenAI ────────────────────────────────────────────────────────────────
# 2026-11-10 OpenAI 공식 문서 확인:
# - gpt-6-luna: 현재 카탈로그의 저비용 모델($0.10/$0.50 per 1M), Responses API·JSON 출력·web_search 지원
# - gpt-transcribe: 녹음 파일 전사 권장 모델, languages(배열) 파라미터 지원
OPENAI_API_KEY = env("OPENAI_API_KEY")
CHAT_MODEL = env("OPENAI_CHAT_MODEL", "gpt-6-luna")
SEARCH_MODEL = env("OPENAI_SEARCH_MODEL", CHAT_MODEL)
TRANSCRIBE_MODEL = env("OPENAI_TRANSCRIBE_MODEL", "gpt-transcribe")
REASONING_EFFORT = env("OPENAI_REASONING_EFFORT")  # 비우면 모델 기본값


def openai_ready() -> bool:
    return real_key(OPENAI_API_KEY)


# ── 접근 코드 (공개 배포 시 OpenAI 비용 보호) ───────────────────────────────
APP_ACCESS_CODE = env("APP_ACCESS_CODE")

# ── 언어별 설정 (interview-coach/core/config.py와 동일) ─────────────────────
# pace_range: 말하기 속도 '참고 범위'. 검증된 표준이 아니라 연습용 휴리스틱이다.
LANGUAGES: dict[str, dict] = {
    "한국어": {"code": "ko", "tts": "ko-KR", "pace_unit": "음절/분", "pace_range": (250, 350), "label": "Korean"},
    "English": {"code": "en", "tts": "en-US", "pace_unit": "words/min", "pace_range": (120, 160), "label": "English"},
    "中文": {"code": "zh", "tts": "zh-CN", "pace_unit": "字/分", "pace_range": (180, 260), "label": "Mandarin Chinese"},
}
LANG_BY_CODE = {cfg["code"]: cfg for cfg in LANGUAGES.values()}

QUESTION_TYPES = ["인성", "직무 역량", "경험(STAR)", "상황 대처", "압박", "지원 동기", "외국어"]
