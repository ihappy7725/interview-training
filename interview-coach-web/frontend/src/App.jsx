import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import { PAGES } from './data/pages'
import { DEFAULT_QUESTIONS } from './data/questions'
import PreparePage from './pages/PreparePage'
import PracticePage from './pages/PracticePage'
import ReportPage from './pages/ReportPage'
import HistoryPage from './pages/HistoryPage'
import { apiJson, getAccessCode, setAccessCode } from './lib/api'
import { loadJSON, saveJSON, usePersistentState } from './lib/storage'
import { EMPTY_SESSION } from './data/session'

// 서버에 연결하지 못했을 때도 연습은 할 수 있도록 쓰는 기본 언어(서버의 '한국어' 설정과 같은 값)
const FALLBACK_LANGUAGES = [
  { name: '한국어', code: 'ko', tts: 'ko-KR', pace_unit: '음절/분', pace_range: [250, 350], label: 'Korean' },
]

const HEALTH_INTERVAL_MS = 5000
const HEALTH_TIMEOUT_MS = 3000
const DEV_MODE_KEY = 'mockmate.devMode'

// [React 개념] 컴포넌트 나누기
//   App은 "전체 상태를 들고 있는 부모"다. 화면 조각(Sidebar, 각 페이지)은 각각 파일로 나누고,
//   필요한 값과 함수를 props로 내려준다. 데이터는 위(App)에서 아래(자식)로만 흐른다.
export default function App() {
  // [React 개념] useState
  //   const [값, 값을바꾸는함수] = useState(초기값). 바꾸는 함수를 부르면 React가 화면을 다시 그린다.
  //   react-router 없이, page 값에 따라 어떤 화면을 보여줄지 고르는 방식으로 페이지를 이동한다.
  const [page, setPage] = useState(() => loadJSON('mockmate.page', 'prepare'))
  const [settings, setSettings] = usePersistentState('mockmate.settings', { language: '한국어', timeLimit: 90, useCamera: true })
  const [session, setSession] = usePersistentState('mockmate.session', EMPTY_SESSION)
  const [history, setHistory] = usePersistentState('mockmate.history', [])

  // 서버 상태: online은 단순 값이라, 같은 값으로 다시 set해도 React가 다시 그리지 않는다.
  const [online, setOnline] = useState(null) // null: 첫 확인 중
  const [healthInfo, setHealthInfo] = useState({ checkedAt: null, latencyMs: null })
  const [config, setConfig] = useState({ languages: [], tts: null, defaultQuestions: null, questionTypes: [], ai: null })
  const [checkTick, setCheckTick] = useState(0)
  const [access, setAccess] = useState('unknown') // 'unknown' | 'checking' | 'ok' | 'denied'

  const [devMode, setDevMode] = useState(() => loadJSON(DEV_MODE_KEY, false) === true)
  const [devStats, setDevStats] = useState(null)

  // 주의: useEffect 안의 함수가 무언가를 return하면 React는 그것을 '정리 함수'로 보고 나중에 호출한다.
  // `() => saveJSON(...)`처럼 중괄호 없이 쓰면 saveJSON의 결과(true)가 반환되어 화면 전체가 멈추므로 중괄호로 감싼다.
  useEffect(() => {
    saveJSON(DEV_MODE_KEY, devMode)
  }, [devMode])
  useEffect(() => {
    saveJSON('mockmate.page', page)
  }, [page])

  // 5초마다 /api/health 확인 (정리 함수에서 clearInterval → 타이머가 중복으로 쌓이지 않음)
  useEffect(() => {
    let stopped = false
    async function check() {
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS)
      const t0 = performance.now()
      let ok = false
      try {
        const res = await fetch('/api/health', { signal: controller.signal, cache: 'no-store' })
        ok = res.ok && (await res.json()).status === 'ok'
      } catch {
        ok = false
      }
      clearTimeout(timer)
      if (stopped) return
      setOnline(ok)
      setHealthInfo({ checkedAt: new Date(), latencyMs: ok ? Math.round(performance.now() - t0) : null })
    }
    check()
    const id = setInterval(check, HEALTH_INTERVAL_MS)
    return () => {
      stopped = true
      clearInterval(id)
    }
  }, [checkTick])

  // 서버가 "연결됨"이 될 때마다 설정·TTS 상태를 다시 불러오고, 저장된 접근 코드가 있으면 확인한다.
  useEffect(() => {
    if (!online) return
    let ignore = false
    async function load() {
      try {
        const [cfg, tts] = await Promise.all([apiJson('/api/config'), apiJson('/api/tts/status').catch(() => null)])
        if (ignore) return
        setConfig({
          languages: cfg.languages ?? [],
          tts,
          defaultQuestions: cfg.default_questions ?? null,
          questionTypes: cfg.question_types ?? [],
          ai: cfg.ai ?? null,
        })
        if (cfg.ai?.access_required && getAccessCode()) {
          const res = await apiJson('/api/access/check', { method: 'POST' })
          if (!ignore) setAccess(res.ok ? 'ok' : 'denied')
        }
      } catch {
        /* 다음 health 확인 때 다시 시도 */
      }
    }
    load()
    return () => {
      ignore = true
    }
  }, [online])

  const languages = config.languages.length ? config.languages : FALLBACK_LANGUAGES
  const lang = languages.find((l) => l.name === settings.language) ?? languages[0]
  const ttsEnabled = Boolean(online && config.tts?.enabled)

  // AI 사용 가능 상태: 'offline' | 'disabled'(서버 키 없음) | 'locked'(접근 코드 필요) | 'ready'
  const aiState = !online || !config.ai ? 'offline' : !config.ai.enabled ? 'disabled' : config.ai.access_required && access !== 'ok' ? 'locked' : 'ready'

  const submitAccessCode = async (code) => {
    setAccessCode(code.trim())
    setAccess('checking')
    try {
      const res = await apiJson('/api/access/check', { method: 'POST' })
      setAccess(res.ok ? 'ok' : 'denied')
      if (!res.ok) setAccessCode('')
    } catch {
      setAccess('denied')
      setAccessCode('')
    }
  }
  const clearAccessCode = () => {
    setAccessCode('')
    setAccess('unknown')
  }

  // 기본 질문(서버가 서명한 것 우선, 서버가 꺼져 있으면 화면에 들어 있는 예비 목록)
  const defaultQuestions = (config.defaultQuestions?.[lang.code] ?? DEFAULT_QUESTIONS[lang.code].map((q) => ({ question: q }))).map((q, i) => ({
    id: `default-${lang.code}-${i}`,
    question: q.question,
    sig: q.sig,
    source: '기본 질문',
    category: '공통',
    tip: '',
    lang: lang.code,
  }))

  const updateSession = (patch) => setSession((s) => ({ ...s, ...(typeof patch === 'function' ? patch(s) : patch) }))
  const resetSession = () => setSession((s) => ({ ...EMPTY_SESSION, profile: s.profile })) // 지원 정보는 남기고 새로 시작

  const pageInfo = PAGES.find((p) => p.id === page) ?? PAGES[0]
  const common = { lang, onNavigate: setPage, session, updateSession, aiState, ttsEnabled }

  return (
    <div className="app">
      <Sidebar
        page={page}
        onChangePage={setPage}
        languages={languages}
        settings={settings}
        onChangeSettings={(patch) => setSettings((s) => ({ ...s, ...patch }))}
        serverStatus={online == null ? 'checking' : online ? 'ok' : 'error'}
        onRetryServer={() => setCheckTick((k) => k + 1)}
        ai={{ state: aiState, required: Boolean(config.ai?.access_required), access, onSubmit: submitAccessCode, onClear: clearAccessCode }}
        answerCount={session.answers.length}
        devMode={devMode}
        onChangeDevMode={setDevMode}
        devInfo={{
          serverStatus: online == null ? 'checking' : online ? 'ok' : 'error',
          ...healthInfo,
          configLoaded: config.languages.length > 0,
          tts: config.tts,
          ai: config.ai,
          stats: devStats,
        }}
      />

      <main className="main" id="main">
        {/* page 값에 맞는 화면 하나만 그린다. 다른 메뉴로 가면 이전 페이지의 정리 함수가 실행되어
            카메라·마이크·질문 음성이 꺼진다. */}
        {pageInfo.id === 'prepare' && (
          <PreparePage {...common} questionTypes={config.questionTypes} defaultQuestions={defaultQuestions} />
        )}
        {pageInfo.id === 'practice' && (
          <PracticePage
            {...common}
            defaultQuestions={defaultQuestions}
            timeLimit={settings.timeLimit}
            useCamera={settings.useCamera}
            devMode={devMode}
            onDevStats={setDevStats}
          />
        )}
        {pageInfo.id === 'report' && (
          <ReportPage
            {...common}
            history={history}
            onSaveHistory={(record) => {
              setHistory((h) => [...h, record])
              updateSession({ savedId: record.id })
            }}
            onNewSession={resetSession}
          />
        )}
        {pageInfo.id === 'history' && <HistoryPage history={history} setHistory={setHistory} onNavigate={setPage} />}
      </main>
    </div>
  )
}
