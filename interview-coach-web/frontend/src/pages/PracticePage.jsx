import { useEffect, useState } from 'react'
import { DEFAULT_QUESTIONS } from '../data/questions'
import { useFaceCamera } from '../hooks/useFaceCamera'
import { useQuestionVoice } from '../hooks/useQuestionVoice'
import CoachingPanel from '../components/CoachingPanel'

const mmss = (sec) => {
  const s = Math.max(0, Math.floor(sec))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

export default function PracticePage({ lang, timeLimit, useCamera, ttsEnabled, devMode, onDevStats, onEnd }) {
  const questions = DEFAULT_QUESTIONS[lang.code] ?? DEFAULT_QUESTIONS.ko
  const [qIdx, setQIdx] = useState(0)
  const [answerStartedAt, setAnswerStartedAt] = useState(null) // 답변 시작 시각(ms) 또는 null
  const [now, setNow] = useState(() => Date.now())
  // 훅이 돌려준 객체를 구조 분해로 꺼내 쓴다. (videoRef/canvasRef는 JSX의 ref={}에만 넘기고 .current는 읽지 않는다)
  const { videoRef, canvasRef, cameraOn, status, error, snapshot, turnOn, turnOff, resetStats } =
    useFaceCamera(useCamera)
  const voice = useQuestionVoice(ttsEnabled)
  const stopVoice = voice.stop

  // 답변 중일 때만 250ms마다 현재 시각을 갱신해 타이머를 다시 그린다.
  useEffect(() => {
    if (answerStartedAt == null) return
    const id = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(id) // 질문을 넘기거나 페이지를 떠나면 타이머 정지
  }, [answerStartedAt])

  // 개발자 확인 패널(사이드바)에 머리 각도·성능 값을 올려 보낸다.
  // 패널이 켜져 있을 때만 보내므로, 꺼져 있으면 App이 추가로 다시 그려지지 않는다.
  useEffect(() => {
    if (devMode) onDevStats(snapshot ? { pose: snapshot.pose, perf: snapshot.perf } : null)
  }, [devMode, snapshot, onDevStats])
  useEffect(() => () => onDevStats(null), [onDevStats]) // 페이지를 떠나면 패널 값 비우기

  const startAnswer = () => {
    const t = Date.now()
    setAnswerStartedAt(t)
    setNow(t)
    resetStats()
    stopVoice() // 답변을 시작하면 질문 음성 정지
  }
  const goTo = (i) => {
    setQIdx(i)
    setAnswerStartedAt(null) // app.py처럼 질문을 바꾸면 타이머 초기화
    stopVoice() // 질문을 넘기면 음성 정지 (페이지 이동 시 정지는 useQuestionVoice 안의 정리 함수가 처리)
  }

  const elapsed = answerStartedAt == null ? 0 : (now - answerStartedAt) / 1000
  const timerLevel = elapsed > timeLimit ? 'bad' : elapsed >= timeLimit * 0.8 ? 'warn' : 'good'
  const question = questions[Math.min(qIdx, questions.length - 1)]

  return (
    <div className="practice-grid">
      <section className="card stage">
        <div className="stage-top">
          <span className="hdr-sub">
            Q {qIdx + 1} / {questions.length} <span className="badge">기본 질문</span>
          </span>
          {useCamera && status === 'running' && <span className="badge good">● 카메라 분석 중</span>}
        </div>

        {useCamera ? (
          <div className="video-wrap">
            {/* 영상은 CSS로 좌우 반전(거울 모드). canvas는 이미 반전된 좌표로 그리므로 뒤집지 않는다 */}
            <video ref={videoRef} className="video" playsInline muted />
            <canvas ref={canvasRef} className="overlay" />
            {!cameraOn && (
              <div className="video-placeholder">
                <div className="video-placeholder-icon">📷</div>
                <p>아래 ‘카메라 켜기’를 누르고 브라우저의 카메라 권한을 허용하세요.</p>
              </div>
            )}
            {cameraOn && status !== 'running' && status !== 'camera-only' && (
              <div className="video-loading">
                {status === 'loading-model' ? '얼굴 분석 모델 불러오는 중…' : '카메라 여는 중…'}
              </div>
            )}
          </div>
        ) : (
          <div className="notice">카메라 분석이 꺼져 있습니다. 사이드바에서 켤 수 있어요.</div>
        )}

        {useCamera && error && <div className="alert">{error}</div>}

        <div className="q-card">
          <div className="q-meta">면접관 질문</div>
          <div className="q-text">{question}</div>
        </div>

        <div className="timer">
          <div className="timer-head">
            <span>⏱ 답변 시간</span>
            <span className={`badge ${answerStartedAt == null ? 'gray' : timerLevel}`}>
              {mmss(elapsed)} / {mmss(timeLimit)}
            </span>
          </div>
          <div className="progress">
            <div
              className={`progress-bar ${timerLevel}`}
              style={{ width: `${Math.min(elapsed / timeLimit, 1) * 100}%` }}
            />
          </div>
        </div>

        <div className="controls">
          {useCamera && (
            <button className={`ctrl ${cameraOn ? 'on' : ''}`} onClick={cameraOn ? turnOff : turnOn}>
              <span className="ctrl-icon">📷</span>
              {cameraOn ? '카메라 끄기' : '카메라 켜기'}
            </button>
          )}
          <button
            className={`ctrl ${voice.state !== 'idle' ? 'on' : ''}`}
            onClick={() => voice.toggle(question, lang)}
            aria-busy={voice.state === 'loading'}
          >
            <span className="ctrl-icon">
              {voice.state === 'loading' ? <span className="spinner" aria-hidden="true" /> : voice.state === 'playing' ? '⏹' : '🔊'}
            </span>
            {voice.state === 'loading' ? '불러오는 중' : voice.state === 'playing' ? '정지' : '질문 듣기'}
          </button>
          <button className="ctrl primary" onClick={startAnswer} title="타이머와 비언어 지표를 0부터 다시 잽니다">
            <span className="ctrl-icon">▶</span>답변 시작
          </button>
          <button className="ctrl" onClick={() => goTo(qIdx - 1)} disabled={qIdx === 0}>
            <span className="ctrl-icon">◀</span>이전
          </button>
          <button className="ctrl" onClick={() => goTo(qIdx + 1)} disabled={qIdx >= questions.length - 1}>
            <span className="ctrl-icon">▶</span>다음
          </button>
          <span className="spacer" />
          <button className="ctrl danger" onClick={onEnd}>
            <span className="ctrl-icon">⏹</span>면접 종료
          </button>
        </div>

        {voice.notice && <p className="muted small voice-notice">🔈 {voice.notice}</p>}
        {/* ElevenLabs 무료 요금제 출처 표기 (elevenlabs.io를 함께 적어야 함) */}
        {ttsEnabled && (
          <p className="attribution">
            Voice by{' '}
            <a href="https://elevenlabs.io" target="_blank" rel="noreferrer">
              ElevenLabs (elevenlabs.io)
            </a>
          </p>
        )}
      </section>

      <CoachingPanel enabled={useCamera} cameraOn={cameraOn} status={status} snapshot={snapshot} />
    </div>
  )
}
