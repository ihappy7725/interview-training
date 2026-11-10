"""MediaPipe Face Landmarker 기반 실시간 비언어 분석.

- 영상은 로컬에서만 처리하며 OpenAI 등 외부로 전송하지 않는다.
- 시선/표정 수치는 블렌드셰이프(표정 계수)와 머리 회전각으로 '추정'한 값이다.
  카메라 위치·조명·안경에 따라 오차가 있으므로 절대 평가가 아닌 연습용 지표로 본다.
"""
from __future__ import annotations

import math
import threading
import time
import urllib.request
from collections import deque
from dataclasses import dataclass, field

import av
import cv2
import numpy as np
from streamlit_webrtc import VideoProcessorBase

from core.config import FACE_MODEL_PATH, FACE_MODEL_URL

# 판정 기준(휴리스틱). 필요하면 조정.
YAW_LIMIT = 18.0      # 좌우 고개 회전 허용 각도(도)
PITCH_LIMIT = 18.0    # 상하 고개 회전 허용 각도(도)
GAZE_SIDE_LIMIT = 0.45  # 눈동자 좌우 치우침 계수 한계
GAZE_UP_LIMIT = 0.45
GAZE_DOWN_LIMIT = 0.60  # 카메라가 화면 위에 있어 약간 아래를 보는 것은 허용
BLINK_ON = 0.50
SMILE_ON = 0.35


def ensure_face_model() -> str:
    """face_landmarker.task가 없으면 내려받는다. 경로를 반환."""
    FACE_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not FACE_MODEL_PATH.exists() or FACE_MODEL_PATH.stat().st_size < 1_000_000:
        tmp = FACE_MODEL_PATH.with_suffix(".part")
        urllib.request.urlretrieve(FACE_MODEL_URL, tmp)
        tmp.replace(FACE_MODEL_PATH)
    return str(FACE_MODEL_PATH)


def create_landmarker():
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    options = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=ensure_face_model()),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
        output_face_blendshapes=True,
        output_facial_transformation_matrixes=True,
    )
    try:
        return vision.FaceLandmarker.create_from_options(options), mp
    except Exception as e:
        # 다운로드가 중간에 끊겨 손상된 파일이면 지워서 다음 실행 때 다시 받도록 한다.
        FACE_MODEL_PATH.unlink(missing_ok=True)
        raise RuntimeError(f"모델 파일이 손상되었을 수 있어 삭제했습니다. 앱을 재시작해 다시 받으세요. ({e})") from e


def _wrap(angle: float) -> float:
    """±180° 근처 표현을 ±90° 범위로 정규화."""
    if angle > 90:
        angle -= 180
    elif angle < -90:
        angle += 180
    return angle


def head_pose_from_matrix(m: np.ndarray) -> tuple[float, float, float]:
    """4x4 얼굴 변환 행렬 → (yaw, pitch, roll) 도 단위."""
    r = np.asarray(m)[:3, :3]
    sy = math.sqrt(r[0, 0] ** 2 + r[1, 0] ** 2)
    pitch = math.degrees(math.atan2(r[2, 1], r[2, 2]))
    yaw = math.degrees(math.atan2(-r[2, 0], sy))
    roll = math.degrees(math.atan2(r[1, 0], r[0, 0]))
    return _wrap(yaw), _wrap(pitch), _wrap(roll)


def analyze_face(blend: dict[str, float], matrix, landmarks) -> dict:
    """한 프레임의 얼굴 결과 → 판정값."""
    def b(name: str) -> float:
        return float(blend.get(name, 0.0))

    yaw, pitch, roll = head_pose_from_matrix(matrix) if matrix is not None else (0.0, 0.0, 0.0)
    # 눈동자 방향(좌우 눈의 대응 계수 평균)
    look_side = max((b("eyeLookOutLeft") + b("eyeLookInRight")) / 2,
                    (b("eyeLookInLeft") + b("eyeLookOutRight")) / 2)
    look_up = (b("eyeLookUpLeft") + b("eyeLookUpRight")) / 2
    look_down = (b("eyeLookDownLeft") + b("eyeLookDownRight")) / 2
    blink = (b("eyeBlinkLeft") + b("eyeBlinkRight")) / 2
    smile = (b("mouthSmileLeft") + b("mouthSmileRight")) / 2

    xs = [p.x for p in landmarks]
    ys = [p.y for p in landmarks]
    face_w = max(xs) - min(xs)
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    nose = landmarks[1]

    head_ok = abs(yaw) < YAW_LIMIT and abs(pitch) < PITCH_LIMIT
    gaze_ok = look_side < GAZE_SIDE_LIMIT and look_up < GAZE_UP_LIMIT and look_down < GAZE_DOWN_LIMIT
    return {
        "yaw": yaw, "pitch": pitch, "roll": roll,
        "look_side": look_side, "look_up": look_up, "look_down": look_down,
        "blink": blink, "smile": smile,
        "face_w": face_w, "cx": cx, "cy": cy,
        "nose": (nose.x, nose.y),
        "eye_contact": head_ok and gaze_ok and blink < BLINK_ON,
        "head_ok": head_ok,
        "bbox": (min(xs), min(ys), max(xs), max(ys)),
    }


def coaching_message(a: dict | None) -> tuple[str, str, str]:
    """(영문 오버레이, 한글 메시지, 상태색 good/warn/bad)"""
    if a is None:
        return "Face not detected", "얼굴이 화면에 보이지 않아요", "bad"
    if a["face_w"] < 0.18:
        return "Move closer", "카메라에 조금 더 가까이 앉아 주세요", "warn"
    if abs(a["cx"] - 0.5) > 0.22 or abs(a["cy"] - 0.5) > 0.25:
        return "Center your face", "얼굴을 화면 중앙에 맞춰 주세요", "warn"
    if abs(a["roll"]) > 15:
        return "Keep your head level", "고개가 기울어져 있어요", "warn"
    if not a["head_ok"]:
        return "Face the camera", "고개를 정면으로 돌려 주세요", "warn"
    if not a["eye_contact"]:
        return "Look at the camera", "카메라 렌즈를 바라봐 주세요", "warn"
    return "Good posture", "좋아요! 시선과 자세가 안정적이에요", "good"


@dataclass
class FaceStats:
    started: float = field(default_factory=time.time)
    frames: int = 0
    face_frames: int = 0
    eye_contact_frames: int = 0
    smile_frames: int = 0
    blinks: int = 0
    move_sum: float = 0.0
    move_n: int = 0
    _eye_closed: bool = False
    _last_nose: tuple[float, float] | None = None


class InterviewVideoProcessor(VideoProcessorBase):
    """streamlit-webrtc 영상 프레임 처리기 (별도 스레드에서 실행)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.error: str | None = None
        self.landmarker = None
        self._mp = None
        try:
            self.landmarker, self._mp = create_landmarker()
        except Exception as e:  # 모델 다운로드 실패 등
            self.error = f"MediaPipe 모델을 불러오지 못했습니다: {e}"
        self._t0 = time.monotonic()
        self._last_ts = -1
        self.stats = FaceStats()
        self.live: dict = {"msg_ko": "카메라 준비 중", "level": "warn", "analysis": None}
        self._recent_contact: deque[bool] = deque(maxlen=45)  # 약 1.5초

    # ── 외부(메인 스레드)에서 호출 ─────────────────────────────────────────
    def reset(self) -> None:
        with self._lock:
            self.stats = FaceStats()

    def snapshot(self) -> dict:
        with self._lock:
            s = self.stats
            elapsed = max(time.time() - s.started, 1e-6)
            live = dict(self.live)
            recent = (sum(self._recent_contact) / len(self._recent_contact)) if self._recent_contact else 0.0
        face_ratio = s.face_frames / s.frames if s.frames else 0.0
        return {
            "frames": s.frames,
            "elapsed_sec": elapsed,
            "face_presence": face_ratio,
            "eye_contact": s.eye_contact_frames / s.face_frames if s.face_frames else 0.0,
            "smile_ratio": s.smile_frames / s.face_frames if s.face_frames else 0.0,
            "blinks_per_min": s.blinks / (elapsed / 60) if s.frames else 0.0,
            # 프레임 간 코끝 이동량(화면 폭 대비 %). 클수록 자주 움직임.
            "head_movement": (s.move_sum / s.move_n * 100) if s.move_n else 0.0,
            "recent_eye_contact": recent,
            "live_msg": live.get("msg_ko", ""),
            "live_level": live.get("level", "warn"),
            "error": self.error,
        }

    # ── 프레임 처리 ────────────────────────────────────────────────────────
    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        img = cv2.flip(img, 1)  # 거울 모드
        if self.landmarker is None:
            self._put_label(img, "Face model not loaded", (60, 60, 230))
            return av.VideoFrame.from_ndarray(img, format="bgr24")

        h, w = img.shape[:2]
        scale = 640 / w if w > 640 else 1.0
        small = cv2.resize(img, (int(w * scale), int(h * scale))) if scale < 1 else img
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)

        ts = int((time.monotonic() - self._t0) * 1000)
        if ts <= self._last_ts:
            ts = self._last_ts + 1
        self._last_ts = ts

        analysis = None
        try:
            result = self.landmarker.detect_for_video(mp_image, ts)
            if result.face_landmarks:
                blend = {c.category_name: c.score for c in result.face_blendshapes[0]} if result.face_blendshapes else {}
                matrix = result.facial_transformation_matrixes[0] if result.facial_transformation_matrixes else None
                analysis = analyze_face(blend, matrix, result.face_landmarks[0])
        except Exception as e:  # 프레임 하나 실패는 무시
            self.error = f"프레임 분석 오류: {e}"

        self._update_stats(analysis)
        en, ko, level = coaching_message(analysis)
        with self._lock:
            self.live = {"msg_ko": ko, "level": level, "analysis": analysis}
        self._draw(img, analysis, en, level)
        return av.VideoFrame.from_ndarray(img, format="bgr24")

    def _update_stats(self, a: dict | None) -> None:
        with self._lock:
            s = self.stats
            s.frames += 1
            if a is None:
                s._last_nose = None
                self._recent_contact.append(False)
                return
            s.face_frames += 1
            s.eye_contact_frames += int(a["eye_contact"])
            s.smile_frames += int(a["smile"] > SMILE_ON)
            closed = a["blink"] > BLINK_ON
            if closed and not s._eye_closed:
                s.blinks += 1
            s._eye_closed = closed
            if s._last_nose is not None:
                dx = a["nose"][0] - s._last_nose[0]
                dy = a["nose"][1] - s._last_nose[1]
                s.move_sum += math.hypot(dx, dy)
                s.move_n += 1
            s._last_nose = a["nose"]
            self._recent_contact.append(bool(a["eye_contact"]))

    # ── 오버레이 ───────────────────────────────────────────────────────────
    COLORS = {"good": (96, 186, 46), "warn": (0, 165, 255), "bad": (60, 60, 230)}

    def _draw(self, img: np.ndarray, a: dict | None, text: str, level: str) -> None:
        color = self.COLORS[level]
        h, w = img.shape[:2]
        if a is not None:
            x1, y1, x2, y2 = a["bbox"]
            p1, p2 = (int(x1 * w), int(y1 * h)), (int(x2 * w), int(y2 * h))
            L = max(12, (p2[0] - p1[0]) // 6)
            for (x, y, sx, sy) in [(p1[0], p1[1], 1, 1), (p2[0], p1[1], -1, 1),
                                   (p1[0], p2[1], 1, -1), (p2[0], p2[1], -1, -1)]:
                cv2.line(img, (x, y), (x + sx * L, y), color, 3, cv2.LINE_AA)
                cv2.line(img, (x, y), (x, y + sy * L), color, 3, cv2.LINE_AA)
        self._put_label(img, text, color)

    @staticmethod
    def _put_label(img: np.ndarray, text: str, color) -> None:
        font, fs, th = cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
        (tw, tht), _ = cv2.getTextSize(text, font, fs, th)
        x, y = 16, 16
        overlay = img.copy()
        cv2.rectangle(overlay, (x, y), (x + tw + 36, y + tht + 18), (30, 30, 30), -1)
        cv2.addWeighted(overlay, 0.55, img, 0.45, 0, img)
        cv2.circle(img, (x + 14, y + (tht + 18) // 2), 5, color, -1, cv2.LINE_AA)
        cv2.putText(img, text, (x + 26, y + tht + 9), font, fs, (255, 255, 255), th, cv2.LINE_AA)
