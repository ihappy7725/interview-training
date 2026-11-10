/**
 * useRecorder — 마이크 녹음 (MediaRecorder)
 *
 * - 낮은 비트레이트(32kbps)로 녹음한다. 3분 ≈ 0.7MB → Vercel 함수 요청 한도(4.5MB) 안에 여유 있게 들어간다.
 * - 브라우저마다 지원 형식이 달라서(Chrome: webm/opus, Safari: mp4) 되는 형식을 골라 쓴다.
 *   OpenAI 전사 API는 webm·mp4·m4a 모두 받는다(공식 문서 확인).
 * - 녹음을 멈추거나 페이지를 떠나면 마이크 트랙을 완전히 종료한다.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

const MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']

function pickMime() {
  if (typeof MediaRecorder === 'undefined') return null
  return MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported?.(m)) ?? ''
}

function micErrorMessage(err) {
  switch (err?.name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return '마이크 권한이 거부되었어요. 주소창 왼쪽 아이콘에서 마이크를 허용하고, Mac이라면 시스템 설정 > 개인정보 보호 및 보안 > 마이크에서 브라우저를 켜 주세요.'
    case 'NotFoundError':
      return '사용할 수 있는 마이크를 찾지 못했어요.'
    case 'NotReadableError':
      return '마이크를 열 수 없어요. 다른 앱이 마이크를 쓰고 있는지 확인해 주세요.'
    default:
      return `마이크를 켜지 못했어요. (${err?.name ?? '알 수 없는 오류'})`
  }
}

export function useRecorder() {
  const [recording, setRecording] = useState(false)
  const [error, setError] = useState('')
  const recRef = useRef(null)
  const streamRef = useRef(null)
  const chunksRef = useRef([])

  const releaseMic = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
  }, [])

  /** 녹음 시작. 성공하면 true */
  const start = async () => {
    setError('')
    const mime = pickMime()
    if (mime == null || !navigator.mediaDevices?.getUserMedia) {
      setError('이 브라우저에서는 녹음을 할 수 없어요. 최신 Chrome·Edge·Safari를 사용해 주세요.')
      return false
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
        video: false,
      })
      streamRef.current = stream
      const rec = new MediaRecorder(stream, { ...(mime ? { mimeType: mime } : {}), audioBitsPerSecond: 32000 })
      chunksRef.current = []
      rec.ondataavailable = (e) => {
        if (e.data.size) chunksRef.current.push(e.data)
      }
      rec.start(1000) // 1초마다 조각 저장(중간에 끊겨도 앞부분은 남음)
      recRef.current = rec
      setRecording(true)
      return true
    } catch (e) {
      releaseMic()
      setError(micErrorMessage(e))
      return false
    }
  }

  /** 녹음 종료 → Blob 반환 (녹음 중이 아니면 null) */
  const stop = () =>
    new Promise((resolve) => {
      const rec = recRef.current
      if (!rec || rec.state === 'inactive') {
        resolve(null)
        return
      }
      rec.onstop = () => {
        const type = rec.mimeType || chunksRef.current[0]?.type || 'audio/webm'
        resolve(new Blob(chunksRef.current, { type }))
        chunksRef.current = []
      }
      rec.stop()
      recRef.current = null
      releaseMic()
      setRecording(false)
    })

  /** 저장하지 않고 취소 */
  const cancel = useCallback(() => {
    const rec = recRef.current
    if (rec && rec.state !== 'inactive') {
      rec.onstop = null
      rec.stop()
    }
    recRef.current = null
    chunksRef.current = []
    releaseMic()
    setRecording(false)
  }, [releaseMic])

  useEffect(() => cancel, [cancel]) // 페이지를 떠나면 마이크 종료

  return { recording, error, start, stop, cancel }
}

/** 녹음 형식 → 서버로 보낼 파일 이름 확장자 */
export function audioFilename(blob) {
  const t = blob?.type || ''
  if (t.includes('mp4')) return 'answer.mp4'
  if (t.includes('ogg')) return 'answer.ogg'
  return 'answer.webm'
}
