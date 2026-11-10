import { PAGES } from '../data/pages'
import DevPanel from './DevPanel'

// [React 개념] props
//   부모(App)가 자식(Sidebar)에게 넘겨주는 값. 함수의 매개변수처럼 { page, onChangePage, ... }로 받는다.
//   Sidebar는 상태를 직접 갖지 않고, 값은 props로 받아 보여주고, 바뀌면 onXxx 함수로 부모에게 알린다.
//   이렇게 하면 "현재 페이지·설정"이라는 진짜 데이터는 App 한 곳에만 있게 된다.

const SERVER_BADGE = {
  checking: { cls: 'gray', text: '● 서버 확인 중…' },
  ok: { cls: 'good', text: '● 서버 연결됨' },
  error: { cls: 'bad', text: '● 서버 연결 안 됨' },
}

export default function Sidebar({
  page,
  onChangePage,
  languages,
  language,
  onChangeLanguage,
  timeLimit,
  onChangeTimeLimit,
  useCamera,
  onChangeUseCamera,
  serverStatus,
  onRetryServer,
  devMode,
  onChangeDevMode,
  devInfo,
}) {
  const current = languages.find((l) => l.name === language) ?? languages[0]
  const [lo, hi] = current.pace_range
  const badge = SERVER_BADGE[serverStatus]

  return (
    <aside className="sidebar">
      <div className="brand">
        {/* public 폴더의 파일은 "/파일이름"으로 바로 쓸 수 있다. alt=""는 옆에 이름 글자가 있어서 장식용으로 처리 */}
        <img className="brand-logo" src="/icon-192.png" alt="" width="34" height="34" />
        MockMate
      </div>

      <nav className="nav">
        {/* 배열.map()으로 같은 모양의 버튼을 반복해서 만든다. key는 React가 항목을 구분하는 이름표 */}
        {PAGES.map((p) => (
          <button
            key={p.id}
            className={`nav-item ${page === p.id ? 'active' : ''}`}
            onClick={() => onChangePage(p.id)}
          >
            <span className="nav-icon">{p.icon}</span>
            {p.label}
          </button>
        ))}
      </nav>

      <div className="divider" />

      <div className="settings">
        <p className="settings-title">면접 설정</p>

        <label className="field">
          <span className="field-label">면접 언어</span>
          <select
            value={language}
            onChange={(e) => onChangeLanguage(e.target.value)}
            disabled={serverStatus !== 'ok'}
          >
            {languages.map((l) => (
              <option key={l.code} value={l.name}>
                {l.name}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span className="field-label">
            답변 제한 시간 <b>{timeLimit}초</b>
          </span>
          <input
            type="range"
            min={30}
            max={180}
            step={10}
            value={timeLimit}
            onChange={(e) => onChangeTimeLimit(Number(e.target.value))}
          />
        </label>

        <label className="toggle">
          <input type="checkbox" checked={useCamera} onChange={(e) => onChangeUseCamera(e.target.checked)} />
          <span className="toggle-track" />
          카메라 비언어 분석 (MediaPipe)
        </label>

        <p className="muted small">
          말하기 속도 참고 범위: {lo}–{hi} {current.pace_unit} (연습용 기준)
        </p>
      </div>

      <div className="divider" />

      <div className="server">
        <span className={`badge ${badge.cls}`}>{badge.text}</span>
        {serverStatus === 'error' && (
          <>
            <p className="muted small">
              backend 폴더에서 FastAPI 서버를 실행했는지 확인하세요. 서버 없이도 기본 질문(한국어)으로 연습할 수 있어요.
            </p>
            <button className="btn btn-small" onClick={onRetryServer}>
              다시 연결
            </button>
          </>
        )}
      </div>

      <p className="muted small privacy">🔒 카메라 영상은 이 브라우저 안에서만 분석되며 서버로 전송되지 않습니다.</p>

      <div className="dev">
        <label className="toggle">
          <input type="checkbox" checked={devMode} onChange={(e) => onChangeDevMode(e.target.checked)} />
          <span className="toggle-track" />
          개발자 확인
        </label>
        {devMode && <DevPanel info={devInfo} />}
      </div>
    </aside>
  )
}
