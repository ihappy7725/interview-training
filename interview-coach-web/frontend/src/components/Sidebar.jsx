import { useState } from 'react'
import { PAGES } from '../data/pages'
import DevPanel from './DevPanel'
import Icon from './Icon'

// [React 개념] props
//   부모(App)가 자식(Sidebar)에게 넘겨주는 값. 함수의 매개변수처럼 { page, onChangePage, ... }로 받는다.
//   Sidebar는 화면용 작은 상태(입력 중인 접근 코드)만 갖고, 진짜 데이터는 App이 들고 있다.

const SERVER_BADGE = {
  checking: { cls: 'gray', text: '서버 확인 중' },
  ok: { cls: 'good', text: '서버 연결됨' },
  error: { cls: 'bad', text: '서버 연결 안 됨' },
}

function AccessSection({ ai }) {
  const [code, setCode] = useState('')
  if (ai.state === 'offline') return null
  if (ai.state === 'disabled') {
    return (
      <p className="side-note">
        <Icon name="info" size={14} /> 서버에 OpenAI 키가 없어 AI 평가는 꺼져 있어요. 카메라 코칭과 녹음 지표는 쓸 수 있어요.
      </p>
    )
  }
  if (!ai.required) return null
  if (ai.state === 'ready') {
    return (
      <div className="access ok">
        <span>
          <Icon name="unlock" size={15} /> AI 기능 사용 중
        </span>
        <button className="link-btn" onClick={ai.onClear}>
          잠그기
        </button>
      </div>
    )
  }
  return (
    <form
      className="access"
      onSubmit={(e) => {
        e.preventDefault() // 폼 제출 시 페이지가 새로고침되는 기본 동작 막기
        if (code.trim()) ai.onSubmit(code)
      }}
    >
      <label htmlFor="access-code" className="field-label">
        <Icon name="lock" size={14} /> AI 접근 코드
      </label>
      <div className="access-row">
        <input id="access-code" type="password" value={code} onChange={(e) => setCode(e.target.value)} placeholder="코드 입력" autoComplete="off" />
        <button className="btn btn-small btn-primary" disabled={!code.trim() || ai.access === 'checking'}>
          확인
        </button>
      </div>
      {ai.access === 'denied' && <p className="field-error">코드가 맞지 않아요.</p>}
      <p className="side-note">질문 생성·답변 평가 등 AI 기능에 필요해요.</p>
    </form>
  )
}

export default function Sidebar({
  page,
  onChangePage,
  languages,
  settings,
  onChangeSettings,
  serverStatus,
  onRetryServer,
  ai,
  answerCount,
  devMode,
  onChangeDevMode,
  devInfo,
}) {
  const current = languages.find((l) => l.name === settings.language) ?? languages[0]
  const [lo, hi] = current.pace_range
  const badge = SERVER_BADGE[serverStatus]

  return (
    <aside className="sidebar">
      <div className="brand">
        {/* public 폴더의 파일은 "/파일이름"으로 바로 쓸 수 있다. 옆에 이름이 있어 alt=""(장식용) */}
        <img className="brand-logo" src="/icon-192.png" alt="" width="36" height="36" />
        <div>
          <div className="brand-name">MockMate</div>
          <div className="brand-sub">AI 면접 연습</div>
        </div>
      </div>

      <nav className="nav" aria-label="메뉴">
        {/* 배열.map()으로 같은 모양의 버튼을 반복해서 만든다. key는 React가 항목을 구분하는 이름표 */}
        {PAGES.map((p) => (
          <button
            key={p.id}
            className={`nav-item ${page === p.id ? 'active' : ''}`}
            onClick={() => onChangePage(p.id)}
            aria-current={page === p.id ? 'page' : undefined}
          >
            <Icon name={p.icon} size={19} />
            <span>{p.label}</span>
            {p.id === 'report' && answerCount > 0 && <span className="nav-count">{answerCount}</span>}
          </button>
        ))}
      </nav>

      <details className="side-section" open>
        <summary>
          <Icon name="settings" size={16} /> 면접 설정 <Icon name="chevronDown" size={14} className="side-chevron" />
        </summary>
        <div className="settings">
          <label className="field">
            <span className="field-label">면접 언어</span>
            <select value={current.name} onChange={(e) => onChangeSettings({ language: e.target.value })} disabled={serverStatus !== 'ok'}>
              {languages.map((l) => (
                <option key={l.code} value={l.name}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span className="field-label">
              답변 제한 시간 <b>{settings.timeLimit}초</b>
            </span>
            <input
              type="range"
              min={30}
              max={180}
              step={10}
              value={settings.timeLimit}
              onChange={(e) => onChangeSettings({ timeLimit: Number(e.target.value) })}
            />
          </label>

          <label className="toggle">
            <input type="checkbox" checked={settings.useCamera} onChange={(e) => onChangeSettings({ useCamera: e.target.checked })} />
            <span className="toggle-track" />
            카메라 비언어 분석
          </label>

          <p className="side-note">
            말하기 속도 참고: {lo}–{hi} {current.pace_unit}
          </p>
        </div>
      </details>

      <AccessSection ai={ai} />

      <div className="side-footer">
        <div className="server">
          <span className={`status-dot ${badge.cls}`} aria-hidden="true" />
          <span>{badge.text}</span>
          {serverStatus === 'error' && (
            <button className="link-btn" onClick={onRetryServer}>
              다시 연결
            </button>
          )}
        </div>
        {serverStatus === 'error' && <p className="side-note">backend 서버를 실행했는지 확인하세요. 기본 질문·카메라 코칭은 서버 없이도 돼요.</p>}
        <p className="side-note">
          <Icon name="lock" size={13} /> 카메라 영상은 브라우저 안에서만 분석돼요.
        </p>

        <label className="toggle toggle-small">
          <input type="checkbox" checked={devMode} onChange={(e) => onChangeDevMode(e.target.checked)} />
          <span className="toggle-track" />
          개발자 확인
        </label>
        {devMode && <DevPanel info={devInfo} />}
      </div>
    </aside>
  )
}
