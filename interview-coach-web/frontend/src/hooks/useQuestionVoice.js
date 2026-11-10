/**
 * useQuestionVoice: '질문 듣기' 재생을 관리하는 커스텀 훅
 *
 * 1순위: 서버의 /api/tts (ElevenLabs 음성, 서버가 mp3를 캐시). 서버가 서명한 질문만 가능(크레딧 보호)
 * 예비: 브라우저 내장 speechSynthesis (서버 TTS가 꺼져 있거나 실패했을 때 자동 전환)
 *
 * state:  'idle' | 'loading' | 'playing'
 * source: 'elevenlabs' | 'browser' | null  (지금/마지막으로 재생한 음성의 출처)
 * notice: 기본 음성으로 바꿨을 때 보여줄 짧은 안내 문구
 */
import { useCallback, useEffect, useRef, useState } from 'react'

/** 브라우저 내장 음성으로 읽기 (1단계의 speak 함수와 같은 로직) */
function speakWithBrowser(text, langTag, onEnd) {
  const synth = window.speechSynthesis
  if (!synth) return false
  synth.cancel()
  const u = new SpeechSynthesisUtterance(text)
  u.lang = langTag
  u.rate = 1.0
  const voice = synth.getVoices().find((v) => v.lang && v.lang.replace('_', '-').startsWith(langTag.slice(0, 2)))
  if (voice) u.voice = voice
  u.onend = onEnd
  u.onerror = onEnd
  synth.speak(u)
  return true
}

export function useQuestionVoice(ttsEnabled) {
  const [state, setState] = useState('idle')
  const [source, setSource] = useState(null)
  const [notice, setNotice] = useState('')

  const audioRef = useRef(null)
  const abortRef = useRef(null)
  const urlRef = useRef(null)
  // 재생 요청마다 번호를 붙인다. 응답이 늦게 와도 "가장 최근 요청"이 아니면 무시하기 위해서다.
  // (예: 질문 듣기 → 바로 다음 질문으로 넘김 → 앞 질문 음성이 뒤늦게 재생되는 문제 방지)
  const tokenRef = useRef(0)

  // [React 개념] useCallback
  //   컴포넌트가 다시 그려질 때마다 함수가 새로 만들어지는데, useCallback으로 감싸면 같은 함수를 계속 쓴다.
  //   stop을 다른 useEffect의 의존성 배열에 넣어야 해서, 매번 바뀌지 않도록 고정했다.
  const stop = useCallback(() => {
    tokenRef.current += 1
    abortRef.current?.abort() // 아직 받는 중인 /api/tts 요청 취소
    abortRef.current = null
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.removeAttribute('src')
      audioRef.current = null
    }
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current) // 메모리에 올려 둔 mp3 해제
      urlRef.current = null
    }
    window.speechSynthesis?.cancel()
    setState('idle')
    setNotice('')
  }, [])

  // 페이지를 떠날 때(컴포넌트가 사라질 때) 재생 중인 음성 정지
  useEffect(() => stop, [stop])

  const playBrowser = (text, lang, token, reason) => {
    const ok = speakWithBrowser(text, lang.tts, () => {
      if (token !== tokenRef.current) return
      setState('idle')
      setNotice('') // 다 읽으면 "기본 음성으로 재생 중" 안내도 지움
    })
    if (!ok) {
      setNotice('이 브라우저는 음성 읽기를 지원하지 않아요.')
      setState('idle')
      return
    }
    setSource('browser')
    setNotice(reason ? `기본 음성으로 재생 중 · ${reason}` : '기본 음성으로 재생 중')
    setState('playing')
  }

  const play = async (text, sig, lang) => {
    stop()
    const token = tokenRef.current
    setNotice('')
    if (!ttsEnabled || !sig) {
      // 서명이 없는 질문(직접 입력·수정)은 서버가 읽어 주지 않으므로 바로 브라우저 음성
      playBrowser(text, lang, token, ttsEnabled ? '직접 입력한 질문' : '')
      return
    }

    // Safari 등은 "클릭 직후"가 아니면 소리 재생을 막을 수 있다. 그래서 Audio 객체는 클릭 순간에 먼저 만들어 둔다.
    const audio = new Audio()
    audioRef.current = audio
    const controller = new AbortController()
    abortRef.current = controller
    setState('loading')
    try {
      const res = await fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, lang: lang.code, sig }),
        signal: controller.signal,
      })
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new Error(body?.detail?.message ?? `서버 음성 오류(HTTP ${res.status})`)
      }
      const blob = await res.blob()
      if (token !== tokenRef.current) return // 기다리는 사이에 정지·다른 질문으로 바뀜
      const url = URL.createObjectURL(blob)
      urlRef.current = url
      audio.src = url
      audio.onended = () => {
        if (token === tokenRef.current) setState('idle')
      }
      await audio.play()
      if (token !== tokenRef.current) return
      setSource('elevenlabs')
      setState('playing')
    } catch (e) {
      if (e.name === 'AbortError' || token !== tokenRef.current) return // 사용자가 정지한 경우
      console.warn('ElevenLabs 음성 실패 → 브라우저 음성으로 전환:', e.message)
      audioRef.current = null
      playBrowser(text, lang, token, e.message)
    }
  }

  /** 버튼 하나로: 멈춰 있으면 재생, 재생/로딩 중이면 정지. q = { question, sig } */
  const toggle = (q, lang) => (state === 'idle' ? play(q.question, q.sig, lang) : stop())

  return { state, source, notice, toggle, stop }
}
