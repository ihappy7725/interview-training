// 모의 면접: 카메라 코칭 + 질문 듣기 + 답변 녹음 → 분석(전사·지표·AI 평가) → 결과
// 기존 app.py의 page_practice / process_answer를 옮김.
import { useEffect, useRef, useState } from 'react'
import Icon from '../components/Icon'
import PageHeader from '../components/PageHeader'
import AiNotice from '../components/AiNotice'
import CoachingPanel from '../components/CoachingPanel'
import AnswerResult from '../components/AnswerResult'
import { useFaceCamera } from '../hooks/useFaceCamera'
import { useQuestionVoice } from '../hooks/useQuestionVoice'
import { audioFilename, useRecorder } from '../hooks/useRecorder'
import { analyzeAudio } from '../lib/audioAnalysis'
import { apiJson } from '../lib/api'
import { newId } from '../lib/storage'

const MAX_RECORD_SEC = 600 // 안전장치: 10분이 지나면 자동으로 답변 완료

const mmss = (sec) => {
  const s = Math.max(0, Math.floor(sec))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

export default function PracticePage({
  lang,
  onNavigate,
  session,
  updateSession,
  aiState,
  ttsEnabled,
  defaultQuestions,
  timeLimit,
  useCamera,
  devMode,
  onDevStats,
}) {
  const questions = session.questions.length ? session.questions : defaultQuestions
  const qIdx = Math.min(session.qIdx, questions.length - 1)
  const q = questions[qIdx]

  const [answerStartedAt, setAnswerStartedAt] = useState(null)
  const [now, setNow] = useState(() => Date.now())
  const [phase, setPhase] = useState('ready') // 'ready' | 'recording' | 'analyzing'
  const [step, setStep] = useState('') // 분석 단계 안내
  const [error, setError] = useState('')
  const [localResult, setLocalResult] = useState(null) // AI 없이 측정만 한 결과
  const [hideResult, setHideResult] = useState(false) // '다시 답하기'를 누르면 이전 결과 숨김
  const aliveRef = useRef(true)

  // 훅이 돌려준 객체를 구조 분해로 꺼내 쓴다. (videoRef/canvasRef는 JSX의 ref={}에만 넘기고 .current는 읽지 않는다)
  const { videoRef, canvasRef, cameraOn, status, error: camError, snapshot, turnOn, turnOff, resetStats } = useFaceCamera(useCamera)
  const voice = useQuestionVoice(ttsEnabled)
  const stopVoice = voice.stop
  const recorder = useRecorder()

  useEffect(() => {
    aliveRef.current = true
    return () => {
      aliveRef.current = false // 분석 도중 페이지를 떠나면 늦게 온 결과로 화면을 바꾸지 않음
    }
  }, [])

  // 답변 중일 때만 250ms마다 현재 시각을 갱신해 타이머를 다시 그린다.
  useEffect(() => {
    if (answerStartedAt == null) return
    const id = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(id)
  }, [answerStartedAt])

  // 개발자 확인 패널에 머리 각도·성능 값 전달 (패널이 켜져 있을 때만)
  useEffect(() => {
    if (devMode) onDevStats(snapshot ? { pose: snapshot.pose, perf: snapshot.perf } : null)
  }, [devMode, snapshot, onDevStats])
  useEffect(() => () => onDevStats(null), [onDevStats])

  const elapsed = answerStartedAt == null ? 0 : (now - answerStartedAt) / 1000
  const timerLevel = elapsed > timeLimit ? 'bad' : elapsed >= timeLimit * 0.8 ? 'warn' : 'good'

  const attempts = session.answers.filter((a) => a.question === q.question)
  const latest = attempts[attempts.length - 1]

  const goTo = (i) => {
    if (phase === 'analyzing') return
    recorder.cancel()
    stopVoice()
    setAnswerStartedAt(null)
    setPhase('ready')
    setError('')
    setLocalResult(null)
    setHideResult(false)
    updateSession({ qIdx: i })
  }

  const startAnswer = async () => {
    stopVoice() // 답변을 시작하면 질문 음성 정지
    setError('')
    setLocalResult(null)
    const ok = await recorder.start()
    if (!ok) return
    const t = Date.now()
    setAnswerStartedAt(t)
    setNow(t)
    resetStats()
    setHideResult(true)
    setPhase('recording')
  }

  const finishAnswer = async () => {
    setPhase('analyzing') // 버튼 중복 클릭 방지를 위해 먼저 바꿈
    const blob = await recorder.stop()
    setAnswerStartedAt(null)
    // 녹음 종료 시점의 얼굴 분석 요약 (서버 점수 계산용, 원본 vision.py snapshot과 같은 이름)
    const vision =
      useCamera && status === 'running' && snapshot
        ? {
            frames: snapshot.frames,
            face_presence: snapshot.facePresence,
            eye_contact: snapshot.eyeContact,
            smile_ratio: snapshot.smileRatio,
            blinks_per_min: snapshot.blinksPerMin,
            head_movement: snapshot.headMovement,
          }
        : null
    if (!blob || blob.size < 1000) {
      setPhase('ready')
      setError('녹음된 내용이 없어요. 다시 시도해 주세요.')
      return
    }
    setStep('음성 신호 분석 중 (속도·침묵·억양)')
    try {
      const audio = await analyzeAudio(blob)
      if (!audio.has_speech) throw new Error('음성이 거의 감지되지 않았어요. 마이크를 확인하고 다시 답해 주세요.')
      if (aiState !== 'ready') {
        // AI 없이 측정만 (접근 코드가 없는 방문자도 체험 가능)
        if (aliveRef.current) setLocalResult({ audio, evaluation: null })
        return
      }
      setStep('음성을 텍스트로 바꾸고 AI 코치가 평가하는 중 (10~30초)')
      const form = new FormData()
      form.append('audio', blob, audioFilename(blob))
      form.append('question', q.question)
      form.append('lang', lang.code)
      form.append('time_limit', String(timeLimit))
      form.append('audio_metrics', JSON.stringify(audio))
      if (vision) form.append('vision', JSON.stringify(vision))
      form.append('profile', JSON.stringify({ company: session.profile.company, role: session.profile.role }))
      const res = await apiJson('/api/answers/analyze', { method: 'POST', form })
      if (!aliveRef.current) return
      const record = {
        id: newId(),
        qid: q.id,
        question: q.question,
        category: q.category || '',
        attempt: attempts.length + 1,
        prev_total: latest ? latest.scores.total : null,
        createdAt: new Date().toISOString(),
        lang: lang.code,
        audio,
        ...res,
      }
      updateSession((s) => ({ answers: [...s.answers, record], overall: null, savedId: null }))
      setHideResult(false)
      resetStats()
    } catch (e) {
      if (aliveRef.current) setError(e.message || '분석 중 오류가 발생했어요.')
    } finally {
      if (aliveRef.current) {
        setPhase('ready')
        setStep('')
      }
    }
  }

  // 안전장치: 너무 오래 녹음하면 자동 완료
  const tooLong = phase === 'recording' && elapsed > MAX_RECORD_SEC
  useEffect(() => {
    if (tooLong) finishAnswer()
    // finishAnswer는 매번 새로 만들어지는 함수라 의존성에서 뺀다(tooLong이 true가 되는 순간 한 번만 실행)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tooLong])

  const practiceFollowUp = () => {
    const fu = latest?.follow_up
    if (!fu) return
    updateSession((s) => {
      const base = s.questions.length ? s.questions : defaultQuestions
      const next = [...base]
      next.splice(qIdx + 1, 0, { id: newId(), question: fu.question, sig: fu.sig, source: '꼬리질문', category: '꼬리질문', tip: '', lang: lang.code })
      return { questions: next, qIdx: qIdx + 1 }
    })
    setHideResult(false)
    setLocalResult(null)
  }

  const title = [session.profile.company, session.profile.role].filter(Boolean).join(' · ') || '모의 면접'
  const showResult = latest && !hideResult && phase !== 'recording'

  return (
    <>
      <PageHeader page="practice" title={title} description="질문을 듣고 '답변 시작'을 누른 뒤 말하세요. 다 말했으면 '답변 완료'를 누르면 바로 분석합니다." onNavigate={onNavigate}>
        <button className="btn btn-ghost" onClick={() => onNavigate('report')} disabled={phase !== 'ready'}>
          <Icon name="report" size={16} /> 리포트 보기
        </button>
      </PageHeader>

      <AiNotice state={aiState} />

      <div className="practice-grid">
        <section className="card stage">
          <div className="stage-top">
            <div className="q-progress" aria-label={`${questions.length}개 중 ${qIdx + 1}번째 질문`}>
              <span className="q-count">
                Q {qIdx + 1}
                <small> / {questions.length}</small>
              </span>
              <div className="q-dots" aria-hidden="true">
                {questions.map((x, i) => (
                  <span key={x.id ?? i} className={`${i === qIdx ? 'now' : ''} ${session.answers.some((a) => a.question === x.question) ? 'done' : ''}`} />
                ))}
              </div>
            </div>
            <div className="stage-badges">
              <span className="badge gray">{q.source || '기본 질문'}</span>
              {q.category && q.category !== q.source && <span className="badge gray">{q.category}</span>}
              {phase === 'recording' && (
                <span className="badge bad">
                  <span className="rec-dot" /> 녹음 중
                </span>
              )}
            </div>
          </div>

          {useCamera ? (
            <div className="video-wrap">
              {/* 영상은 CSS로 좌우 반전(거울 모드). canvas는 이미 반전된 좌표로 그리므로 뒤집지 않는다 */}
              <video ref={videoRef} className="video" playsInline muted />
              <canvas ref={canvasRef} className="overlay" />
              {!cameraOn && (
                <div className="video-placeholder">
                  <Icon name="camera" size={34} strokeWidth={1.5} />
                  <p>카메라를 켜면 시선·자세를 실시간으로 코칭해요.</p>
                  <button className="btn btn-light" onClick={turnOn}>
                    카메라 켜기
                  </button>
                </div>
              )}
              {cameraOn && status !== 'running' && status !== 'camera-only' && (
                <div className="video-loading">
                  <span className="spinner light" aria-hidden="true" />
                  {status === 'loading-model' ? '얼굴 분석 모델 불러오는 중…' : '카메라 여는 중…'}
                </div>
              )}
            </div>
          ) : (
            <div className="notice">카메라 분석이 꺼져 있어요. 사이드바 &lsquo;면접 설정&rsquo;에서 켤 수 있어요.</div>
          )}

          {useCamera && camError && <div className="alert">{camError}</div>}
          {recorder.error && <div className="alert">{recorder.error}</div>}

          <div className="q-card">
            <div className="q-meta">
              <Icon name="bot" size={15} /> 면접관 질문
            </div>
            <p className="q-text">{q.question}</p>
            {q.tip && (
              <p className="q-tip">
                <Icon name="sparkles" size={14} /> {q.tip}
              </p>
            )}
          </div>

          <div className="timer">
            <div className="timer-head">
              <span>
                <Icon name="timer" size={16} /> 답변 시간
              </span>
              <span className={`timer-value ${answerStartedAt == null ? '' : timerLevel}`}>
                {mmss(elapsed)} <small>/ {mmss(timeLimit)}</small>
              </span>
            </div>
            <div className="progress">
              <div className={`progress-bar ${timerLevel}`} style={{ width: `${Math.min(elapsed / timeLimit, 1) * 100}%` }} />
            </div>
          </div>

          <div className="controls">
            {useCamera && (
              <button className={`ctrl ${cameraOn ? 'on' : ''}`} onClick={cameraOn ? turnOff : turnOn}>
                <span className="ctrl-icon">
                  <Icon name={cameraOn ? 'camera' : 'cameraOff'} size={20} />
                </span>
                {cameraOn ? '카메라 끄기' : '카메라 켜기'}
              </button>
            )}
            <button className={`ctrl ${voice.state !== 'idle' ? 'on' : ''}`} onClick={() => voice.toggle(q, lang)} disabled={phase === 'recording'} aria-busy={voice.state === 'loading'}>
              <span className="ctrl-icon">
                {voice.state === 'loading' ? <span className="spinner" aria-hidden="true" /> : <Icon name={voice.state === 'playing' ? 'stop' : 'volume'} size={20} />}
              </span>
              {voice.state === 'loading' ? '불러오는 중' : voice.state === 'playing' ? '정지' : '질문 듣기'}
            </button>
            {phase === 'recording' ? (
              <button className="ctrl rec" onClick={finishAnswer}>
                <span className="ctrl-icon">
                  <Icon name="stop" size={20} />
                </span>
                답변 완료
              </button>
            ) : (
              <button className="ctrl primary" onClick={startAnswer} disabled={phase === 'analyzing'} title="녹음과 타이머를 시작합니다">
                <span className="ctrl-icon">{phase === 'analyzing' ? <span className="spinner light" aria-hidden="true" /> : <Icon name="mic" size={20} />}</span>
                {phase === 'analyzing' ? '분석 중' : '답변 시작'}
              </button>
            )}
            <button className="ctrl" onClick={() => goTo(qIdx - 1)} disabled={qIdx === 0 || phase !== 'ready'}>
              <span className="ctrl-icon">
                <Icon name="chevronLeft" size={20} />
              </span>
              이전
            </button>
            <button className="ctrl" onClick={() => goTo(qIdx + 1)} disabled={qIdx >= questions.length - 1 || phase !== 'ready'}>
              <span className="ctrl-icon">
                <Icon name="chevronRight" size={20} />
              </span>
              다음
            </button>
            <span className="spacer" />
            <button
              className="ctrl danger"
              onClick={() => {
                recorder.cancel()
                onNavigate('report')
              }}
              disabled={phase === 'analyzing'}
            >
              <span className="ctrl-icon">
                <Icon name="flag" size={20} />
              </span>
              면접 종료
            </button>
          </div>

          {voice.notice && (
            <p className="voice-notice">
              <Icon name="volume" size={14} /> {voice.notice}
            </p>
          )}
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

        <div className="stack">
          <CoachingPanel enabled={useCamera} cameraOn={cameraOn} status={status} snapshot={snapshot} />

          <section className="card feedback" aria-live="polite">
            <div className="card-head">
              <h2 className="card-title">
                <Icon name="bot" size={18} /> AI 피드백
              </h2>
              {latest && <span className="badge gray">{attempts.length}회 답변</span>}
            </div>
            {phase === 'analyzing' && (
              <div className="analyzing">
                <span className="spinner" aria-hidden="true" />
                <span>{step || '녹음을 마무리하는 중…'}</span>
              </div>
            )}
            {error && <div className="alert">{error}</div>}
            {phase !== 'analyzing' && localResult && <AnswerResult answer={localResult} paceUnit={lang.pace_unit} />}
            {phase !== 'analyzing' && !localResult && showResult && (
              <AnswerResult
                answer={latest}
                paceUnit={lang.pace_unit}
                onFollowUp={latest.follow_up ? practiceFollowUp : undefined}
                onRetry={() => {
                  setHideResult(true)
                  setError('')
                }}
              />
            )}
            {phase === 'ready' && !error && !localResult && !showResult && (
              <div className="empty">
                <Icon name="mic" size={28} />
                <p>{latest ? "'답변 시작'을 눌러 다시 답해 보세요." : '답변을 녹음하면 점수와 피드백이 여기에 나와요.'}</p>
              </div>
            )}
            {phase === 'recording' && (
              <div className="empty">
                <span className="rec-dot big" aria-hidden="true" />
                <p>답변을 녹음하고 있어요. 다 말했으면 &lsquo;답변 완료&rsquo;를 누르세요.</p>
              </div>
            )}
          </section>
        </div>
      </div>
    </>
  )
}
