import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import { PAGES } from './data/pages'
import PlaceholderPage from './components/PlaceholderPage'
import PracticePage from './pages/PracticePage'

// 서버에 연결하지 못했을 때도 연습은 할 수 있도록 쓰는 기본 언어(서버의 '한국어' 설정과 같은 값)
const FALLBACK_LANGUAGES = [
  { name: '한국어', code: 'ko', tts: 'ko-KR', pace_unit: '음절/분', pace_range: [250, 350], label: 'Korean' },
]

const PLACEHOLDERS = {
  prepare: '회사·직무·채용공고를 입력해 예상 질문을 만들고, 웹에서 기출 질문을 찾는 기능이 들어갈 자리입니다.',
  report: '답변별 AI 평가 점수, 비언어 지표 요약, 개선 포인트를 정리한 리포트가 들어갈 자리입니다.',
  history: '연습 기록을 저장하고 점수 변화를 그래프로 보여주는 기능이 들어갈 자리입니다.',
}

const HEALTH_INTERVAL_MS = 5000
const HEALTH_TIMEOUT_MS = 3000
const DEV_MODE_KEY = 'mockmate.devMode'

// localStorage는 사생활 보호 모드 등에서 막혀 있을 수 있어서 try/catch로 감싼다.
function readDevMode() {
  try {
    return localStorage.getItem(DEV_MODE_KEY) === 'on'
  } catch {
    return false
  }
}

// [React 개념] 컴포넌트 나누기
//   App은 "전체 상태를 들고 있는 부모"다. 화면 조각(Sidebar, PracticePage …)은 각각 파일로 나누고,
//   필요한 값과 함수를 props로 내려준다. 데이터는 위(App)에서 아래(자식)로만 흐른다.
export default function App() {
  // [React 개념] useState
  //   const [값, 값을바꾸는함수] = useState(초기값)
  //   setPage('report')처럼 바꾸는 함수를 부르면 React가 이 컴포넌트를 다시 그린다.
  //   react-router 없이, page 값에 따라 어떤 화면을 보여줄지 고르는 방식으로 페이지를 이동한다.
  const [page, setPage] = useState('practice')
  const [language, setLanguage] = useState('한국어')
  const [timeLimit, setTimeLimit] = useState(90)
  const [useCamera, setUseCamera] = useState(true)

  // 서버 상태
  // online은 true/false 같은 단순 값으로 따로 둔다. 같은 값으로 setOnline을 다시 불러도
  // React는 "바뀐 게 없다"고 보고 화면을 다시 그리지 않으므로, 5초 확인이 계속 성공하는 동안에는 렌더링 비용이 없다.
  const [online, setOnline] = useState(null) // null: 첫 확인 중
  const [healthInfo, setHealthInfo] = useState({ checkedAt: null, latencyMs: null })
  const [config, setConfig] = useState({ languages: [], tts: null })
  const [checkTick, setCheckTick] = useState(0) // '다시 연결' 버튼으로 즉시 다시 확인

  // 개발자 확인 패널
  const [devMode, setDevMode] = useState(readDevMode) // 함수를 넘기면 처음 한 번만 실행된다
  const [devStats, setDevStats] = useState(null) // PracticePage가 올려 보내는 머리 각도·성능 값

  useEffect(() => {
    try {
      localStorage.setItem(DEV_MODE_KEY, devMode ? 'on' : 'off')
    } catch {
      /* 저장할 수 없어도 동작에는 문제없음 */
    }
  }, [devMode])

  // [React 개념] useEffect + setInterval
  //   화면이 처음 그려진 뒤 /api/health를 바로 한 번, 그다음 5초마다 확인한다.
  //   정리 함수에서 clearInterval을 해야 타이머가 중복으로 쌓이지 않는다.
  useEffect(() => {
    let stopped = false
    async function check() {
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS) // 서버가 멈춰 있어도 3초 뒤 포기
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
      // 5초에 한 번이라 화면 부담은 무시할 수준. 패널이 꺼져 있어도 기록해 두면 켜는 즉시 값이 보인다.
      setHealthInfo({ checkedAt: new Date(), latencyMs: ok ? Math.round(performance.now() - t0) : null })
    }
    check()
    const id = setInterval(check, HEALTH_INTERVAL_MS)
    return () => {
      stopped = true
      clearInterval(id)
    }
  }, [checkTick])

  // 서버가 "연결됨"이 될 때마다(처음 연결, 끊겼다가 복구) 설정과 TTS 상태를 다시 불러온다.
  useEffect(() => {
    if (!online) return
    let ignore = false
    async function load() {
      try {
        const [configRes, ttsRes] = await Promise.all([fetch('/api/config'), fetch('/api/tts/status')])
        const cfg = configRes.ok ? await configRes.json() : null
        const tts = ttsRes.ok ? await ttsRes.json() : null
        if (!ignore) setConfig({ languages: cfg?.languages ?? [], tts })
      } catch {
        /* 다음 health 확인 때 다시 시도됨 */
      }
    }
    load()
    return () => {
      ignore = true
    }
  }, [online])

  const serverStatus = online == null ? 'checking' : online ? 'ok' : 'error'
  const ttsEnabled = Boolean(online && config.tts?.enabled)
  const languages = config.languages.length ? config.languages : FALLBACK_LANGUAGES
  const lang = languages.find((l) => l.name === language) ?? languages[0]
  const pageInfo = PAGES.find((p) => p.id === page)

  return (
    <div className="app">
      <Sidebar
        page={page}
        onChangePage={setPage}
        languages={languages}
        language={lang.name}
        onChangeLanguage={setLanguage}
        timeLimit={timeLimit}
        onChangeTimeLimit={setTimeLimit}
        useCamera={useCamera}
        onChangeUseCamera={setUseCamera}
        serverStatus={serverStatus}
        onRetryServer={() => setCheckTick((k) => k + 1)}
        devMode={devMode}
        onChangeDevMode={setDevMode}
        devInfo={{ serverStatus, ...healthInfo, configLoaded: config.languages.length > 0, tts: config.tts, stats: devStats }}
      />

      <main className="main">
        <header className="page-header">
          <div className="hdr-sub">
            MockMate <span className="badge">{lang.name}</span>
          </div>
          <h1 className="hdr-title">
            {pageInfo.icon} {pageInfo.label}
          </h1>
        </header>

        {/* page 값에 맞는 화면 하나만 그린다. PracticePage가 화면에서 사라지면(다른 메뉴 클릭)
            그 안의 useEffect 정리 함수가 실행되어 카메라와 질문 음성이 꺼진다. */}
        {page === 'practice' ? (
          <PracticePage
            lang={lang}
            timeLimit={timeLimit}
            useCamera={useCamera}
            ttsEnabled={ttsEnabled}
            devMode={devMode}
            onDevStats={setDevStats}
            onEnd={() => setPage('report')}
          />
        ) : (
          <PlaceholderPage title={pageInfo.label} description={PLACEHOLDERS[page]} />
        )}
      </main>
    </div>
  )
}
