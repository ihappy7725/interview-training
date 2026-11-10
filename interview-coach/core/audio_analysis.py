"""음성 신호 분석: 길이, 침묵, 음높이 변화, 말끝 흐림, 음량.

주의: 브라우저 마이크는 자동 음량 조절(AGC)이 켜져 있는 경우가 많아
절대 음량(dBFS)은 참고만 하고, 상대적인 변화(억양 변화·말끝 처짐·침묵)에 무게를 둔다.
"""
from __future__ import annotations

import io

import librosa
import numpy as np

SR = 16000
HOP = 256
FRAME = 1024


def analyze_audio(wav_bytes: bytes) -> dict:
    y, sr = librosa.load(io.BytesIO(wav_bytes), sr=SR, mono=True)
    duration = len(y) / sr if sr else 0.0
    base = {"duration_sec": round(duration, 2), "speech_sec": 0.0, "has_speech": False}
    if duration < 0.8 or np.max(np.abs(y)) < 1e-3:
        return base

    intervals = librosa.effects.split(y, top_db=35, frame_length=FRAME, hop_length=HOP)
    # 너무 짧은 잡음 구간 제거
    intervals = [iv for iv in intervals if (iv[1] - iv[0]) / sr >= 0.12]
    if not intervals:
        return base

    speech_sec = sum((e - s) for s, e in intervals) / sr
    active_span = (intervals[-1][1] - intervals[0][0]) / sr
    gaps = [(intervals[i + 1][0] - intervals[i][1]) / sr for i in range(len(intervals) - 1)]
    pauses = [g for g in gaps if g >= 0.3]
    long_pauses = [g for g in gaps if g >= 2.0]
    lead_silence = intervals[0][0] / sr  # 질문 후 첫 마디까지 걸린 시간

    rms = librosa.feature.rms(y=y, frame_length=FRAME, hop_length=HOP)[0]
    db = 20 * np.log10(rms + 1e-10)
    voiced = db > (db.max() - 35)

    f0 = librosa.yin(y, fmin=70, fmax=400, sr=sr, frame_length=FRAME, hop_length=HOP)
    n = min(len(f0), len(voiced))
    f0v = f0[:n][voiced[:n]]
    pitch_median = pitch_st_std = None
    if len(f0v) > 20:
        med = float(np.median(f0v))
        semis = 12 * np.log2(f0v / med)
        semis = semis[np.abs(semis) < 12]  # 옥타브 오검출 제거
        pitch_median = med
        pitch_st_std = float(np.std(semis)) if len(semis) > 10 else None

    loud = db[voiced]
    loudness_db = float(np.mean(loud)) if len(loud) else None
    loudness_std = float(np.std(loud)) if len(loud) else None

    # 말끝 흐림: 1초 이상 발화 구간에서 마지막 0.4초 음량 - 앞부분 음량
    tail_drops = []
    tail_frames = int(0.4 * sr / HOP)
    for s, e in intervals:
        fs, fe = s // HOP, e // HOP
        if (e - s) / sr >= 1.0 and fe - fs > tail_frames * 2:
            seg = db[fs:fe]
            tail_drops.append(float(np.mean(seg[-tail_frames:]) - np.mean(seg[:-tail_frames])))
    tail_drop_db = float(np.mean(tail_drops)) if tail_drops else None

    return {
        **base,
        "has_speech": bool(speech_sec >= 0.5),
        "speech_sec": round(float(speech_sec), 2),
        "active_sec": round(float(active_span), 2),
        "speech_ratio": round(float(speech_sec / active_span), 3) if active_span else 0.0,
        "pause_count": len(pauses),
        "long_pause_count": len(long_pauses),
        "longest_pause_sec": round(float(max(gaps)), 2) if gaps else 0.0,
        "lead_silence_sec": round(float(lead_silence), 2),
        "pitch_median_hz": round(pitch_median, 1) if pitch_median else None,
        "pitch_variation_st": round(pitch_st_std, 2) if pitch_st_std is not None else None,
        "loudness_dbfs": round(loudness_db, 1) if loudness_db is not None else None,
        "loudness_std_db": round(loudness_std, 1) if loudness_std is not None else None,
        "tail_drop_db": round(tail_drop_db, 1) if tail_drop_db is not None else None,
    }


def voice_confidence(a: dict, filler_per_min: float) -> dict:
    """음성 자신감 '추정' 점수(0~100)와 근거. 연습용 휴리스틱."""
    if not a.get("has_speech"):
        return {"score": None, "notes": ["음성이 충분히 감지되지 않았습니다."]}
    score, notes = 100.0, []

    pv = a.get("pitch_variation_st")
    if pv is not None:
        if pv < 1.5:
            score -= 18
            notes.append(f"억양 변화가 작아 단조롭게 들릴 수 있어요 (음높이 변화 {pv}반음).")
        elif pv > 6:
            score -= 8
            notes.append(f"억양 변화가 커서 다소 불안정하게 들릴 수 있어요 ({pv}반음).")
        else:
            notes.append(f"억양 변화가 적당합니다 ({pv}반음).")

    td = a.get("tail_drop_db")
    if td is not None:
        if td < -8:
            score -= 18
            notes.append(f"말끝이 많이 작아집니다 (평균 {td}dB). 문장 끝까지 힘을 유지해 보세요.")
        elif td < -5:
            score -= 8
            notes.append(f"말끝이 약간 흐려지는 경향이 있어요 (평균 {td}dB).")
        else:
            notes.append("문장 끝까지 음량이 비교적 잘 유지됩니다.")

    lp = a.get("long_pause_count", 0)
    if lp:
        score -= min(20, lp * 7)
        notes.append(f"2초 이상 멈춤이 {lp}회 있었어요.")

    lead = a.get("lead_silence_sec", 0)
    if lead and lead > 4:
        score -= 6
        notes.append(f"첫 마디까지 {lead}초가 걸렸어요. 핵심 문장으로 바로 시작해 보세요.")

    if filler_per_min > 4:
        score -= min(20, (filler_per_min - 4) * 3)
        notes.append(f"간투사가 분당 {filler_per_min:.1f}회로 잦아 자신감이 낮아 보일 수 있어요.")

    ls = a.get("loudness_std_db")
    if ls is not None and ls > 12:
        score -= 6
        notes.append("음량 편차가 큰 편입니다. 일정한 크기로 말해 보세요.")

    return {"score": int(max(0, min(100, round(score)))), "notes": notes}
