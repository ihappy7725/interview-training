"""ElevenLabs TTS (질문 듣기).

참고: https://elevenlabs.io/docs/api-reference/text-to-speech/convert (2026-11-10 확인)
POST /v1/text-to-speech/{voice_id}, 헤더 xi-api-key, 본문 {text, model_id, language_code}
"""
from __future__ import annotations

import hashlib
import json
import logging
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import certifi
from fastapi import HTTPException

import config

log = logging.getLogger("uvicorn.error")

ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
OUTPUT_FORMAT = "mp3_44100_128"  # 문서상 기본값. 192kbps는 유료(Creator 이상) 전용
MAX_CHARS = 300  # 크레딧 보호: 질문 하나 길이로 충분

# 기본 모델 eleven_flash_v2_5: 한국어·영어·중국어 지원, 지연 약 100ms,
# API 가격이 multilingual_v2의 절반($0.04 vs $0.08 / 1천 자), language_code 지정 가능
DEFAULT_MODEL_ID = "eleven_flash_v2_5"
# 기본 음성: 계정 음성 목록(GET /v2/voices)으로 고른 뒤 채울 자리. .env에서 바꿀 수 있다.
DEFAULT_VOICE_IDS = {"ko": "", "en": "", "zh": ""}

API_KEY = config.env("ELEVENLABS_API_KEY")
MODEL_ID = config.env("ELEVENLABS_MODEL_ID", DEFAULT_MODEL_ID)
VOICE_IDS = {lang: config.env(f"ELEVENLABS_VOICE_ID_{lang.upper()}", d) for lang, d in DEFAULT_VOICE_IDS.items()}

# Vercel은 /tmp만 쓸 수 있고 다른 요청(인스턴스)과 공유되지 않는다. 로컬은 backend/cache/tts.
CACHE_DIR = (Path(tempfile.gettempdir()) / "mockmate-tts") if config.ON_VERCEL else (config.BASE_DIR / "cache" / "tts")

# python.org에서 설치한 Mac용 Python은 HTTPS 인증서 묶음이 연결되어 있지 않아
# ElevenLabs 접속이 CERTIFICATE_VERIFY_FAILED로 실패한다. certifi의 인증서 묶음을 직접 지정한다.
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def enabled() -> bool:
    return config.real_key(API_KEY)


def error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


# ElevenLabs 오류 코드 → (우리 서버 상태 코드, 코드, 한국어 메시지)
# 출처: https://elevenlabs.io/docs/eleven-api/resources/errors (detail.code 사용, status는 레거시)
UPSTREAM_ERRORS = {
    "invalid_api_key": (502, "elevenlabs_auth", "ElevenLabs API 키가 올바르지 않아요. ELEVENLABS_API_KEY를 확인하고 서버를 다시 시작해 주세요."),
    "missing_api_key": (502, "elevenlabs_auth", "ElevenLabs API 키가 전달되지 않았어요. ELEVENLABS_API_KEY를 확인해 주세요."),
    "missing_permissions": (502, "elevenlabs_permission", "ElevenLabs 키에 필요한 권한이 없어요. elevenlabs.io > Settings > API Keys에서 'Text to Speech' 권한을 켜 주세요."),
    "insufficient_credits": (402, "insufficient_credits", "ElevenLabs 크레딧이 부족해요. 이번 달 사용량을 확인해 주세요(무료 요금제는 매월 초기화)."),
    "quota_exceeded": (402, "insufficient_credits", "ElevenLabs 크레딧이 부족해요. 이번 달 사용량을 확인해 주세요(무료 요금제는 매월 초기화)."),
    "rate_limit_exceeded": (429, "rate_limited", "ElevenLabs 요청이 너무 많아요. 잠시 뒤 다시 시도해 주세요."),
    "concurrent_limit_exceeded": (429, "rate_limited", "ElevenLabs 동시 요청 한도를 넘었어요. 잠시 뒤 다시 시도해 주세요."),
    "system_busy": (429, "elevenlabs_busy", "ElevenLabs 서버가 바빠요. 잠시 뒤 다시 시도해 주세요."),
    "voice_not_found": (502, "voice_not_found", "설정된 음성 ID를 찾을 수 없어요. ELEVENLABS_VOICE_ID_* 값을 확인해 주세요."),
    "text_too_long": (400, "text_too_long", f"문장이 너무 길어요({MAX_CHARS}자 이하)."),
}


def _upstream_error(status: int, body: bytes) -> HTTPException:
    code = ""
    try:
        detail = json.loads(body.decode("utf-8", "replace")).get("detail")
        if isinstance(detail, dict):
            # 권한 부족은 code가 'unauthorized', status가 'missing_permissions'로 온다(실제 응답에서 확인)
            code = detail.get("status") if detail.get("status") == "missing_permissions" else (detail.get("code") or detail.get("status") or "")
    except (ValueError, AttributeError):
        pass
    log.warning("ElevenLabs 오류: HTTP %s, code=%s", status, code or "(없음)")  # 키·본문은 로그에 남기지 않음
    if code in UPSTREAM_ERRORS:
        return error(*UPSTREAM_ERRORS[code])
    if status == 401:
        return error(*UPSTREAM_ERRORS["invalid_api_key"])
    if status == 402:
        return error(*UPSTREAM_ERRORS["insufficient_credits"])
    if status == 429:
        return error(*UPSTREAM_ERRORS["rate_limit_exceeded"])
    if status == 403:
        return error(502, "elevenlabs_forbidden", "현재 요금제에서 이 음성이나 기능을 쓸 수 없어요. 다른 음성 ID를 지정해 보세요.")
    return error(502, "elevenlabs_error", f"ElevenLabs 요청이 실패했어요(HTTP {status}).")


def _call_elevenlabs(text: str, lang: str, voice_id: str) -> bytes:
    url = ELEVENLABS_URL.format(voice_id=urllib.parse.quote(voice_id, safe=""))
    url += "?" + urllib.parse.urlencode({"output_format": OUTPUT_FORMAT})
    body: dict = {"text": text, "model_id": MODEL_ID}
    if not MODEL_ID.startswith("eleven_multilingual_v2"):
        body["language_code"] = lang  # 문서: multilingual_v2는 language_code 미지원
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"xi-api-key": API_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"},
    )
    log.info("ElevenLabs 호출: lang=%s, %d자, model=%s", lang, len(text), MODEL_ID)
    try:
        with urllib.request.urlopen(req, timeout=20, context=SSL_CONTEXT) as res:
            return res.read()
    except urllib.error.HTTPError as e:
        raise _upstream_error(e.code, e.read()) from None
    except TimeoutError:
        raise error(504, "elevenlabs_timeout", "ElevenLabs 응답이 늦어요. 잠시 뒤 다시 시도해 주세요.") from None
    except urllib.error.URLError:
        raise error(502, "elevenlabs_unreachable", "ElevenLabs 서버에 연결할 수 없어요. 인터넷 연결을 확인해 주세요.") from None


def synthesize(text: str, lang: str) -> tuple[bytes | Path, str]:
    """(mp3 바이트 또는 캐시 파일 경로, 출처 'cache'|'elevenlabs')."""
    voice_id = VOICE_IDS[lang]
    if not voice_id:
        raise error(503, "voice_not_configured", f"{lang} 음성 ID가 설정되지 않았어요(ELEVENLABS_VOICE_ID_{lang.upper()}).")
    # 캐시: (텍스트 + 음성 ID + 모델 ID)의 해시를 파일 이름으로. 셋 중 하나라도 바뀌면 다른 파일.
    key = hashlib.sha256(f"{text}\n{voice_id}\n{MODEL_ID}".encode("utf-8")).hexdigest()
    path = CACHE_DIR / f"{key}.mp3"
    if path.is_file() and path.stat().st_size > 0:
        log.info("TTS 캐시 사용: %s…", key[:12])
        return path, "cache"
    audio = _call_elevenlabs(text, lang, voice_id)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(audio)
        tmp.replace(path)  # 다 쓴 뒤 이름을 바꿔서, 중간에 끊겨도 깨진 mp3가 캐시로 쓰이지 않게 함
    except OSError as e:  # 캐시를 못 써도 음성은 돌려준다
        log.warning("TTS 캐시 저장 실패: %s", type(e).__name__)
    return audio, "elevenlabs"
