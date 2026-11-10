"""MockMate API 서버 (FastAPI)

실행: uvicorn main:app --reload --port 8000   (backend 폴더에서)

- GET  /api/health      → {"status": "ok"}
- GET  /api/config      → 언어별 설정 (기존 interview-coach/core/config.py의 LANGUAGES)
- GET  /api/tts/status  → {"enabled": 키 존재 여부, "provider": "elevenlabs", "model_id": ...}  (키 값은 절대 넣지 않음)
- POST /api/tts         → {"text", "lang"} 를 받아 질문 음성(audio/mpeg)을 돌려줌. 같은 요청은 캐시 파일 사용

CORS 설정이 없는 이유:
개발 중에는 브라우저가 Vite 개발 서버(5173)에만 요청하고, Vite가 /api 요청을
이 서버(8000)로 대신 전달(proxy)한다. 브라우저 입장에서는 같은 출처라서 CORS가 필요 없다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
# .env는 서버가 시작될 때 한 번만 읽는다. .env를 고친 뒤에는 서버를 껐다 켜야 반영된다.
load_dotenv(BASE_DIR / ".env")

log = logging.getLogger("uvicorn.error")  # uvicorn 터미널에 함께 찍히는 로거

app = FastAPI(title="MockMate API", version="0.2.0")

# ── 언어별 설정 (interview-coach/core/config.py에서 그대로 옮김) ─────────────
# pace_range: 말하기 속도 '참고 범위'. 검증된 표준이 아니라 연습용 휴리스틱이다.
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


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/config")
def get_config() -> dict:
    # JSON 객체 대신 순서가 유지되는 리스트로 보낸다(선택 상자 순서 고정).
    return {
        "languages": [
            {"name": name, **cfg, "pace_range": list(cfg["pace_range"])}
            for name, cfg in LANGUAGES.items()
        ]
    }


# ══════════════════════════════════════════════════════════════════════════
# ElevenLabs TTS
# 참고: https://elevenlabs.io/docs/api-reference/text-to-speech/convert (2026-11-10 확인)
#       POST /v1/text-to-speech/{voice_id}, 헤더 xi-api-key, 본문 {text, model_id, language_code}
# ══════════════════════════════════════════════════════════════════════════
ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
OUTPUT_FORMAT = "mp3_44100_128"  # 문서상 기본값. 192kbps는 유료(Creator 이상) 전용
MAX_CHARS = 300  # 크레딧 보호: 질문 하나 길이로 충분

# 기본 모델: eleven_flash_v2_5
# - 한국어·영어·중국어 지원, 지연 약 100ms
# - API 가격이 eleven_multilingual_v2의 절반($0.04 vs $0.08 / 1천 자, elevenlabs.io/pricing/api)
# - language_code 지정 가능(multilingual_v2는 이 값을 지원하지 않음)
DEFAULT_MODEL_ID = "eleven_flash_v2_5"

# 기본 음성: 계정의 음성 목록(GET /v2/voices)에서 고른 premade 음성. .env에서 바꿀 수 있다.
DEFAULT_VOICE_IDS = {"ko": "", "en": "", "zh": ""}


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or "").strip() or default


ELEVENLABS_API_KEY = _env("ELEVENLABS_API_KEY")
ELEVENLABS_MODEL_ID = _env("ELEVENLABS_MODEL_ID", DEFAULT_MODEL_ID)
VOICE_IDS = {
    lang: _env(f"ELEVENLABS_VOICE_ID_{lang.upper()}", default)
    for lang, default in DEFAULT_VOICE_IDS.items()
}

CACHE_DIR = BASE_DIR / "cache" / "tts"


def tts_enabled() -> bool:
    k = ELEVENLABS_API_KEY
    # .env.example의 자리표시자(your-...)를 그대로 둔 경우도 '키 없음'으로 본다
    return bool(k) and "your" not in k.lower()


def tts_error(status: int, code: str, message: str) -> HTTPException:
    """화면이 code로 구분하고 message(한국어)를 그대로 보여줄 수 있는 오류 형식."""
    return HTTPException(status_code=status, detail={"code": code, "message": message})


# ElevenLabs 오류 코드 → (우리 서버가 돌려줄 상태 코드, 코드, 한국어 메시지)
# 출처: https://elevenlabs.io/docs/eleven-api/resources/errors (detail.code 사용, status는 레거시)
UPSTREAM_ERRORS = {
    "invalid_api_key": (502, "elevenlabs_auth", "ElevenLabs API 키가 올바르지 않아요. backend/.env의 ELEVENLABS_API_KEY를 확인하고 서버를 다시 시작해 주세요."),
    "missing_api_key": (502, "elevenlabs_auth", "ElevenLabs API 키가 전달되지 않았어요. backend/.env를 확인해 주세요."),
    "insufficient_credits": (402, "insufficient_credits", "ElevenLabs 크레딧이 부족해요. 이번 달 사용량을 확인해 주세요(무료 요금제는 매월 초기화)."),
    "quota_exceeded": (402, "insufficient_credits", "ElevenLabs 크레딧이 부족해요. 이번 달 사용량을 확인해 주세요(무료 요금제는 매월 초기화)."),
    "rate_limit_exceeded": (429, "rate_limited", "ElevenLabs 요청이 너무 많아요. 잠시 뒤 다시 시도해 주세요."),
    "concurrent_limit_exceeded": (429, "rate_limited", "ElevenLabs 동시 요청 한도를 넘었어요. 잠시 뒤 다시 시도해 주세요."),
    "system_busy": (429, "elevenlabs_busy", "ElevenLabs 서버가 바빠요. 잠시 뒤 다시 시도해 주세요."),
    "voice_not_found": (502, "voice_not_found", "설정된 음성 ID를 찾을 수 없어요. backend/.env의 ELEVENLABS_VOICE_ID_* 값을 확인해 주세요."),
    "text_too_long": (400, "text_too_long", f"문장이 너무 길어요({MAX_CHARS}자 이하)."),
}


def _upstream_error(status: int, body: bytes) -> HTTPException:
    code = ""
    try:
        detail = json.loads(body.decode("utf-8", "replace")).get("detail")
        if isinstance(detail, dict):
            code = detail.get("code") or detail.get("status") or ""
    except (ValueError, AttributeError):
        pass
    log.warning("ElevenLabs 오류: HTTP %s, code=%s", status, code or "(없음)")  # 키·본문은 로그에 남기지 않음
    if code in UPSTREAM_ERRORS:
        return tts_error(*UPSTREAM_ERRORS[code])
    if status == 401:
        return tts_error(*UPSTREAM_ERRORS["invalid_api_key"])
    if status == 402:
        return tts_error(*UPSTREAM_ERRORS["insufficient_credits"])
    if status == 429:
        return tts_error(*UPSTREAM_ERRORS["rate_limit_exceeded"])
    if status == 403:
        return tts_error(502, "elevenlabs_forbidden", "현재 요금제에서 이 음성이나 기능을 쓸 수 없어요. 다른 음성 ID를 지정해 보세요.")
    return tts_error(502, "elevenlabs_error", f"ElevenLabs 요청이 실패했어요(HTTP {status}).")


def call_elevenlabs(text: str, lang: str, voice_id: str) -> bytes:
    url = ELEVENLABS_URL.format(voice_id=urllib.parse.quote(voice_id, safe=""))
    url += "?" + urllib.parse.urlencode({"output_format": OUTPUT_FORMAT})
    body: dict = {"text": text, "model_id": ELEVENLABS_MODEL_ID}
    if not ELEVENLABS_MODEL_ID.startswith("eleven_multilingual_v2"):
        body["language_code"] = lang  # 문서: multilingual_v2는 language_code 미지원
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"},
    )
    log.info("ElevenLabs 호출: lang=%s, %d자, model=%s", lang, len(text), ELEVENLABS_MODEL_ID)
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            return res.read()
    except urllib.error.HTTPError as e:
        raise _upstream_error(e.code, e.read()) from None
    except TimeoutError:
        raise tts_error(504, "elevenlabs_timeout", "ElevenLabs 응답이 늦어요. 잠시 뒤 다시 시도해 주세요.") from None
    except urllib.error.URLError:
        raise tts_error(502, "elevenlabs_unreachable", "ElevenLabs 서버에 연결할 수 없어요. 인터넷 연결을 확인해 주세요.") from None


class TTSRequest(BaseModel):
    text: str
    lang: str


@app.get("/api/tts/status")
def tts_status() -> dict:
    return {"enabled": tts_enabled(), "provider": "elevenlabs", "model_id": ELEVENLABS_MODEL_ID}


# 일반 def(async 아님)로 둔 이유: urllib는 응답을 기다리는 동안 멈춰 있는(블로킹) 방식이다.
# FastAPI는 일반 def 엔드포인트를 별도 스레드에서 실행하므로, 기다리는 동안에도 /api/health 같은 다른 요청이 처리된다.
@app.post("/api/tts")
def tts(req: TTSRequest):
    text = req.text.strip()
    if not text:
        raise tts_error(400, "empty_text", "읽을 문장이 비어 있어요.")
    if len(text) > MAX_CHARS:
        raise tts_error(400, "text_too_long", f"문장이 너무 길어요({len(text)}자). {MAX_CHARS}자 이하만 읽을 수 있어요.")
    if req.lang not in VOICE_IDS:
        raise tts_error(400, "unsupported_lang", "지원하지 않는 언어예요(ko, en, zh만 가능).")
    if not tts_enabled():
        raise tts_error(503, "tts_disabled", "ElevenLabs 키가 설정되지 않아 기본 음성을 사용해요.")
    voice_id = VOICE_IDS[req.lang]
    if not voice_id:
        raise tts_error(503, "voice_not_configured", f"{req.lang} 음성 ID가 설정되지 않았어요(ELEVENLABS_VOICE_ID_{req.lang.upper()}).")

    # 캐시: (텍스트 + 음성 ID + 모델 ID)의 해시를 파일 이름으로 쓴다. 셋 중 하나라도 바뀌면 다른 파일.
    key = hashlib.sha256(f"{text}\n{voice_id}\n{ELEVENLABS_MODEL_ID}".encode("utf-8")).hexdigest()
    path = CACHE_DIR / f"{key}.mp3"
    if path.is_file() and path.stat().st_size > 0:
        log.info("TTS 캐시 사용: %s…", key[:12])
        return FileResponse(path, media_type="audio/mpeg", headers={"X-TTS-Source": "cache"})

    audio = call_elevenlabs(text, req.lang, voice_id)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(audio)
    tmp.replace(path)  # 다 쓴 뒤에 이름을 바꿔서, 중간에 끊겨도 깨진 mp3가 캐시로 쓰이지 않게 함
    return Response(content=audio, media_type="audio/mpeg", headers={"X-TTS-Source": "elevenlabs"})
