/**
 * 녹음 파일 → 음성 신호 지표 (interview-coach/core/audio_analysis.py의 analyze_audio를 JS로 옮김)
 *
 * 왜 브라우저에서 하나: 원본은 librosa(+numba, scipy)를 썼는데 수백 MB라 Vercel 함수 용량에 부담이 크다.
 * 카메라 영상처럼 음성 신호도 브라우저에서 계산하고, 서버에는 숫자만 보낸다.
 *
 * 원본과 같은 값: 16kHz, 프레임 1024 / 홉 256, 무음 기준 최대 음량 대비 -35dB,
 * 0.12초 미만 구간 제거, 멈춤 0.3초 / 긴 멈춤 2초, 말끝 0.4초, 음높이 70~400Hz.
 * 다른 점: 음높이(YIN)는 계산량 때문에 소리 나는 프레임 중 최대 600개만 골라 계산한다(대표값 추정에는 충분).
 * 주의: 브라우저 마이크의 자동 음량 조절 때문에 절대 음량은 참고만 하고, 상대적인 변화에 무게를 둔다.
 */
const SR = 16000
const HOP = 256
const FRAME = 1024
const TOP_DB = 35

const mean = (a) => (a.length ? a.reduce((s, v) => s + v, 0) / a.length : 0)
const std = (a) => {
  if (!a.length) return 0
  const m = mean(a)
  return Math.sqrt(a.reduce((s, v) => s + (v - m) ** 2, 0) / a.length)
}
const median = (a) => {
  const s = [...a].sort((x, y) => x - y)
  const m = s.length >> 1
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}
const round = (v, d) => (v == null ? null : Math.round(v * 10 ** d) / 10 ** d)

/** Blob(webm/mp4) → 16kHz 모노 Float32Array */
async function decodeToMono16k(blob) {
  const buf = await blob.arrayBuffer()
  const AC = window.AudioContext || window.webkitAudioContext
  const ctx = new AC()
  try {
    const audio = await ctx.decodeAudioData(buf)
    const ch0 = audio.getChannelData(0)
    // 단순 평균 다운샘플링 (48kHz → 16kHz면 3개씩 평균)
    const ratio = audio.sampleRate / SR
    const out = new Float32Array(Math.floor(ch0.length / ratio))
    for (let i = 0; i < out.length; i++) {
      const start = Math.floor(i * ratio)
      const end = Math.min(ch0.length, Math.floor((i + 1) * ratio))
      let s = 0
      for (let j = start; j < end; j++) s += ch0[j]
      out[i] = s / Math.max(1, end - start)
    }
    return out
  } finally {
    ctx.close()
  }
}

/** YIN 음높이 추정 (한 프레임). 실패하면 null */
function yinPitch(y, start, win = 512, fmin = 70, fmax = 400) {
  const tauMin = Math.floor(SR / fmax)
  const tauMax = Math.min(Math.floor(SR / fmin), win - 1)
  if (start + win + tauMax >= y.length) return null
  const d = new Float32Array(tauMax + 1)
  for (let tau = 1; tau <= tauMax; tau++) {
    let s = 0
    for (let j = 0; j < win; j++) {
      const diff = y[start + j] - y[start + j + tau]
      s += diff * diff
    }
    d[tau] = s
  }
  // 누적 평균 정규화 차이 함수(CMND)
  let running = 0
  let best = -1
  let bestVal = Infinity
  for (let tau = 1; tau <= tauMax; tau++) {
    running += d[tau]
    const cmnd = running > 0 ? (d[tau] * tau) / running : 1
    if (tau < tauMin) continue
    if (cmnd < 0.1) {
      // 기준(0.1)보다 낮아지는 첫 지점 = 기본 주기
      best = tau
      bestVal = cmnd
      break
    }
    if (cmnd < bestVal) {
      bestVal = cmnd
      best = tau
    }
  }
  // 뚜렷한 주기가 없으면(무성음·잡음) 버린다
  if (best < 0 || bestVal > 0.35) return null
  return SR / best
}

/** 녹음 Blob → 지표 (화면에서 쓰는 함수) */
export async function analyzeAudio(blob) {
  return analyzeSamples(await decodeToMono16k(blob))
}

/** 16kHz 모노 샘플 → 지표 (원본 analyze_audio와 같은 계산. 테스트하기 쉽게 디코딩과 분리) */
export function analyzeSamples(y) {
  const duration = y.length / SR
  const base = { duration_sec: round(duration, 2), speech_sec: 0, has_speech: false }
  let peak = 0
  for (let i = 0; i < y.length; i++) peak = Math.max(peak, Math.abs(y[i]))
  if (duration < 0.8 || peak < 1e-3) return base

  // 프레임별 음량(dB). librosa.feature.rms 기본값(center=True)과 같게, 프레임 f는 샘플 f*HOP을
  // '가운데'로 하는 구간이다(앞뒤 바깥은 0으로 채움). 처음엔 시작점 기준으로 짰다가, 말끝 음량 변화가
  // 원본과 크게 달라서(-2.9 vs -9.2dB) 같은 합성 음성으로 비교한 뒤 이렇게 맞췄다.
  const nFrames = 1 + Math.floor(y.length / HOP)
  const db = new Float32Array(nFrames)
  let dbMax = -Infinity
  for (let f = 0; f < nFrames; f++) {
    let s = 0
    const from = f * HOP - FRAME / 2
    for (let j = Math.max(0, from); j < Math.min(y.length, from + FRAME); j++) s += y[j] ** 2
    const rms = Math.sqrt(s / FRAME)
    db[f] = 20 * Math.log10(rms + 1e-10)
    if (db[f] > dbMax) dbMax = db[f]
  }
  const voiced = Array.from(db, (v) => v > dbMax - TOP_DB)

  // 소리 나는 구간(librosa.effects.split과 같은 방식) → 샘플 단위 [start, end)
  // 시작 = 첫 소리 프레임 × HOP, 끝 = (마지막 소리 프레임 + 1) × HOP
  let intervals = []
  for (let f = 0; f < nFrames; f++) {
    if (voiced[f] && (f === 0 || !voiced[f - 1])) intervals.push([f * HOP, null])
    if (voiced[f] && (f === nFrames - 1 || !voiced[f + 1])) intervals[intervals.length - 1][1] = Math.min(y.length, (f + 1) * HOP)
  }
  intervals = intervals.filter(([s, e]) => (e - s) / SR >= 0.12) // 너무 짧은 잡음 제거
  if (!intervals.length) return base

  const speechSec = intervals.reduce((acc, [s, e]) => acc + (e - s), 0) / SR
  const activeSpan = (intervals[intervals.length - 1][1] - intervals[0][0]) / SR
  const gaps = intervals.slice(0, -1).map(([, e], i) => (intervals[i + 1][0] - e) / SR)
  const pauses = gaps.filter((g) => g >= 0.3)
  const longPauses = gaps.filter((g) => g >= 2.0)
  const leadSilence = intervals[0][0] / SR // 첫 마디까지 걸린 시간

  // 음높이: 소리 나는 프레임 중 균등하게 최대 600개
  const voicedFrames = []
  for (let f = 0; f < nFrames; f++) if (voiced[f]) voicedFrames.push(f)
  const step = Math.max(1, Math.floor(voicedFrames.length / 600))
  const f0 = []
  for (let i = 0; i < voicedFrames.length; i += step) {
    const p = yinPitch(y, voicedFrames[i] * HOP)
    if (p) f0.push(p)
  }
  let pitchMedian = null
  let pitchStStd = null
  if (f0.length > 20) {
    const med = median(f0)
    const semis = f0.map((v) => 12 * Math.log2(v / med)).filter((s) => Math.abs(s) < 12) // 옥타브 오검출 제거
    pitchMedian = med
    pitchStStd = semis.length > 10 ? std(semis) : null
  }

  const loud = Array.from(db).filter((_, i) => voiced[i])
  const loudnessDb = loud.length ? mean(loud) : null
  const loudnessStd = loud.length ? std(loud) : null

  // 말끝 흐림: 1초 이상 발화 구간에서 마지막 0.4초 음량 - 앞부분 음량
  const tailFrames = Math.floor((0.4 * SR) / HOP)
  const tailDrops = []
  for (const [s, e] of intervals) {
    const fs = Math.floor(s / HOP)
    const fe = Math.min(nFrames, Math.floor(e / HOP))
    if ((e - s) / SR >= 1.0 && fe - fs > tailFrames * 2) {
      const seg = Array.from(db.slice(fs, fe))
      tailDrops.push(mean(seg.slice(-tailFrames)) - mean(seg.slice(0, -tailFrames)))
    }
  }

  return {
    ...base,
    has_speech: speechSec >= 0.5,
    speech_sec: round(speechSec, 2),
    active_sec: round(activeSpan, 2),
    speech_ratio: activeSpan ? round(speechSec / activeSpan, 3) : 0,
    pause_count: pauses.length,
    long_pause_count: longPauses.length,
    longest_pause_sec: gaps.length ? round(Math.max(...gaps), 2) : 0,
    lead_silence_sec: round(leadSilence, 2),
    pitch_median_hz: round(pitchMedian, 1),
    pitch_variation_st: round(pitchStStd, 2),
    loudness_dbfs: round(loudnessDb, 1),
    loudness_std_db: round(loudnessStd, 1),
    tail_drop_db: tailDrops.length ? round(mean(tailDrops), 1) : null,
  }
}
