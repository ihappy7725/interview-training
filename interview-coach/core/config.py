"""앱 전역 설정: .env 로드, 모델 이름, 언어별 기준값."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ── OpenAI ────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
# 2026-11 기준 OpenAI 문서에서 확인한 모델명. 바뀌면 .env에서만 수정하면 된다.
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-5.4-mini").strip()
SEARCH_MODEL = os.getenv("OPENAI_SEARCH_MODEL", CHAT_MODEL).strip()
TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-transcribe").strip()
# 선택: low / medium / high. 비워두면 모델 기본값 사용(지원하지 않는 모델이면 비워둘 것)
REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "").strip()


def api_key_ready() -> bool:
    k = OPENAI_API_KEY
    return bool(k) and k.startswith("sk-") and "your" not in k.lower()


# ── MediaPipe ─────────────────────────────────────────────────────────────
MODELS_DIR = BASE_DIR / "models"
FACE_MODEL_PATH = MODELS_DIR / "face_landmarker.task"
FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/latest/face_landmarker.task"
)

# ── 데이터 저장 ────────────────────────────────────────────────────────────
DATA_DIR = BASE_DIR / "data"
HISTORY_PATH = DATA_DIR / "history.json"

# ── 언어별 설정 ────────────────────────────────────────────────────────────
# pace_range: 말하기 속도 '참고 범위'. 검증된 표준이 아니라 연습용 휴리스틱이므로
# 본인 기준에 맞게 조정해서 쓰면 된다.
LANGUAGES: dict[str, dict] = {
    "한국어": {
        "code": "ko",
        "tts": "ko-KR",
        "pace_unit": "음절/분",
        "pace_range": (250, 350),
        "label": "Korean",
    },
    "English": {
        "code": "en",
        "tts": "en-US",
        "pace_unit": "words/min",
        "pace_range": (120, 160),
        "label": "English",
    },
    "中文": {
        "code": "zh",
        "tts": "zh-CN",
        "pace_unit": "字/分",
        "pace_range": (180, 260),
        "label": "Mandarin Chinese",
    },
}

QUESTION_TYPES = ["인성", "직무 역량", "경험(STAR)", "상황 대처", "압박", "지원 동기", "외국어"]
