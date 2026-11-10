// 질문 준비: 지원 정보 → (웹 기출 질문 찾기 / 직접 붙여넣기 / AI 예상 질문) → 질문 세트 편집 → 모의 면접 시작
// 기존 app.py의 page_prepare를 옮김.
import { useState } from 'react'
import Icon from '../components/Icon'
import PageHeader from '../components/PageHeader'
import AiNotice from '../components/AiNotice'
import { apiJson } from '../lib/api'
import { newId } from '../lib/storage'

const manualLines = (text) =>
  text
    .split('\n')
    .map((l) => l.replace(/^[\s\-•\d.)]+/, '').trim())
    .filter(Boolean)

export default function PreparePage({ lang, onNavigate, session, updateSession, aiState, questionTypes, defaultQuestions }) {
  const { profile, real, manual, aiQuestions, draft } = session
  const [busy, setBusy] = useState('') // 'search' | 'generate' | ''
  const [error, setError] = useState({ search: '', generate: '' })
  const types = questionTypes.length ? questionTypes : ['인성', '직무 역량', '경험(STAR)', '상황 대처', '압박', '지원 동기', '외국어']
  const aiReady = aiState === 'ready'

  const setProfile = (patch) => updateSession((s) => ({ profile: { ...s.profile, ...patch } }))

  const search = async () => {
    setBusy('search')
    setError((e) => ({ ...e, search: '' }))
    try {
      const res = await apiJson('/api/questions/search', { method: 'POST', json: { company: profile.company, role: profile.role, lang: lang.code } })
      updateSession({ real: { items: res.questions.map((q) => ({ ...q, id: newId(), selected: Boolean(q.verified) })), note: res.note || '' } })
    } catch (e) {
      setError((x) => ({ ...x, search: e.message }))
    } finally {
      setBusy('')
    }
  }

  const generate = async () => {
    setBusy('generate')
    setError((e) => ({ ...e, generate: '' }))
    try {
      const realQs = [...real.items.filter((q) => q.selected).map((q) => q.question), ...manualLines(manual)]
      const res = await apiJson('/api/questions/generate', {
        method: 'POST',
        json: { profile: { company: profile.company, role: profile.role, types: profile.types, jd: profile.jd, resume: profile.resume }, real_questions: realQs, n: profile.n, lang: lang.code },
      })
      updateSession({ aiQuestions: res.questions.map((q) => ({ ...q, id: newId(), selected: true })) })
    } catch (e) {
      setError((x) => ({ ...x, generate: e.message }))
    } finally {
      setBusy('')
    }
  }

  // 선택한 질문들로 '질문 세트' 초안 만들기
  const row = (question, extra) => ({ id: newId(), question, signedText: extra.sig ? question : null, use: true, lang: lang.code, category: '', tip: '', ...extra })
  const compose = () => {
    const rows = [
      ...real.items.filter((q) => q.selected).map((q) => row(q.spoken || q.question, { sig: q.sig, source: '기출(웹)', category: q.category || '' })),
      ...manualLines(manual).map((q) => row(q, { source: '직접 입력' })),
      ...aiQuestions.filter((q) => q.selected).map((q) => row(q.question, { sig: q.sig, source: 'AI 예상', category: q.category || '', tip: q.tip || '' })),
    ]
    updateSession({ draft: rows.length ? rows : defaultQuestions.map((q) => row(q.question, { sig: q.sig, source: '기본 질문', category: '공통' })) })
  }
  const loadDefaults = () => updateSession({ draft: defaultQuestions.map((q) => row(q.question, { sig: q.sig, source: '기본 질문', category: '공통' })) })

  const setDraft = (fn) => updateSession((s) => ({ draft: fn(s.draft) }))
  const editRow = (id, patch) =>
    setDraft((d) =>
      d.map((r) => {
        if (r.id !== id) return r
        const next = { ...r, ...patch }
        // 질문을 고치면 서버 서명이 맞지 않게 되므로 ElevenLabs 대신 기본 음성으로 읽힌다
        if ('question' in patch) next.sig = patch.question === r.signedText ? r.sig ?? next.sig : undefined
        return next
      }),
    )
  const moveRow = (i, dir) =>
    setDraft((d) => {
      const j = i + dir
      if (j < 0 || j >= d.length) return d
      const copy = [...d]
      ;[copy[i], copy[j]] = [copy[j], copy[i]]
      return copy
    })

  const usable = draft.filter((r) => r.use && r.question.trim())
  const start = () => {
    updateSession({
      questions: usable.map(({ id, question, sig, source, category, tip, lang: l }) => ({ id, question: question.trim(), sig, source, category, tip, lang: l })),
      qIdx: 0,
      overall: null,
    })
    onNavigate('practice')
  }

  return (
    <>
      <PageHeader page="prepare" title="질문 준비" description="지원 정보를 넣고 실제 기출 질문과 AI 예상 질문으로 나만의 질문 세트를 만드세요." onNavigate={onNavigate}>
        <button className="btn btn-ghost" onClick={() => onNavigate('practice')}>
          기본 질문으로 바로 연습 <Icon name="arrowRight" size={16} />
        </button>
      </PageHeader>

      <AiNotice state={aiState} />

      <div className="prepare-grid">
        {/* ── 1. 지원 정보 ── */}
        <section className="card">
          <div className="card-head">
            <h2 className="card-title">
              <span className="card-num">1</span> 지원 정보
            </h2>
          </div>
          <div className="form-grid">
            <label className="field">
              <span className="field-label">회사명</span>
              <input value={profile.company} onChange={(e) => setProfile({ company: e.target.value })} placeholder="예: 태웅로직스" maxLength={80} />
            </label>
            <label className="field">
              <span className="field-label">직무</span>
              <input value={profile.role} onChange={(e) => setProfile({ role: e.target.value })} placeholder="예: 해상 수출 영업" maxLength={80} />
            </label>
          </div>
          <fieldset className="field">
            <legend className="field-label">면접 유형</legend>
            <div className="chip-select">
              {types.map((t) => {
                const on = profile.types.includes(t)
                return (
                  <button
                    key={t}
                    type="button"
                    className={`chip-toggle ${on ? 'on' : ''}`}
                    aria-pressed={on}
                    onClick={() => setProfile({ types: on ? profile.types.filter((x) => x !== t) : [...profile.types, t] })}
                  >
                    {on && <Icon name="check" size={13} strokeWidth={2.4} />} {t}
                  </button>
                )
              })}
            </div>
          </fieldset>
          <label className="field">
            <span className="field-label">
              생성할 예상 질문 수 <b>{profile.n}개</b>
            </span>
            <input type="range" min={3} max={12} value={profile.n} onChange={(e) => setProfile({ n: Number(e.target.value) })} />
          </label>
          <label className="field">
            <span className="field-label">채용공고 / 직무기술서(JD)</span>
            <textarea rows={5} value={profile.jd} onChange={(e) => setProfile({ jd: e.target.value })} maxLength={6000} placeholder="주요 업무, 자격 요건, 우대 사항을 붙여넣으면 질문이 더 정확해져요." />
          </label>
          <label className="field">
            <span className="field-label">이력서·자기소개서 핵심 (선택)</span>
            <textarea rows={5} value={profile.resume} onChange={(e) => setProfile({ resume: e.target.value })} maxLength={6000} placeholder="경험·프로젝트·성과를 붙여넣으면 경험을 파고드는 질문이 생성돼요." />
          </label>
        </section>

        <div className="stack">
          {/* ── 2. 실제 기출 질문 ── */}
          <section className="card">
            <div className="card-head">
              <h2 className="card-title">
                <span className="card-num">2</span> 실제 기출 질문 찾기
              </h2>
              <button className="btn btn-primary" onClick={search} disabled={!aiReady || !profile.company.trim() || busy !== ''}>
                {busy === 'search' ? <span className="spinner" aria-hidden="true" /> : <Icon name="search" size={16} />}
                {busy === 'search' ? '검색 중… (30초~1분)' : '웹에서 찾기'}
              </button>
            </div>
            <p className="card-desc">
              공개된 면접 후기·채용 페이지·기사를 검색합니다. <b>출처 확인</b>은 그 링크가 실제 검색 인용에 있다는 뜻이니, 질문 내용은 링크에서 한 번 더 확인하세요.
              {!profile.company.trim() && ' 회사명을 입력하면 검색할 수 있어요.'}
            </p>
            {error.search && <div className="alert">{error.search}</div>}
            {real.note && <div className="notice">{real.note}</div>}
            {real.items.length > 0 && (
              <ul className="pick-list">
                {real.items.map((q) => (
                  <li key={q.id}>
                    <label className="pick">
                      <input
                        type="checkbox"
                        checked={q.selected}
                        onChange={(e) => updateSession((s) => ({ real: { ...s.real, items: s.real.items.map((x) => (x.id === q.id ? { ...x, selected: e.target.checked } : x)) } }))}
                      />
                      <span className="pick-body">
                        <span className="pick-meta">
                          <span className={`badge ${q.verified ? 'good' : 'warn'}`}>{q.verified ? '출처 확인' : '출처 미확인'}</span>
                          {[q.role_match, q.category, q.year].filter(Boolean).map((m) => (
                            <span key={m} className="badge gray">
                              {m}
                            </span>
                          ))}
                        </span>
                        <span className="pick-text">{q.question}</span>
                        {q.question_translated && q.question_translated !== q.question && <span className="pick-sub">{q.question_translated}</span>}
                        {q.source_url && (
                          <a className="pick-link" href={q.source_url} target="_blank" rel="noreferrer">
                            <Icon name="external" size={13} /> {q.source_title || '출처'}
                          </a>
                        )}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
            <label className="field">
              <span className="field-label">직접 수집한 기출 질문 (한 줄에 하나)</span>
              <textarea rows={3} value={manual} onChange={(e) => updateSession({ manual: e.target.value })} placeholder="로그인이 필요한 후기 사이트의 질문은 직접 붙여넣어 주세요." />
            </label>
          </section>

          {/* ── 3. AI 예상 질문 ── */}
          <section className="card">
            <div className="card-head">
              <h2 className="card-title">
                <span className="card-num">3</span> AI 예상 질문
              </h2>
              <button className="btn btn-primary" onClick={generate} disabled={!aiReady || busy !== ''}>
                {busy === 'generate' ? <span className="spinner" aria-hidden="true" /> : <Icon name="sparkles" size={16} />}
                {busy === 'generate' ? '만드는 중…' : '예상 질문 생성'}
              </button>
            </div>
            <p className="card-desc">지원 정보와 선택한 기출 질문을 참고해 만든 &lsquo;예상&rsquo; 질문이에요. 실제 출제 여부와는 무관합니다.</p>
            {error.generate && <div className="alert">{error.generate}</div>}
            {aiQuestions.length > 0 && (
              <ul className="pick-list">
                {aiQuestions.map((q) => (
                  <li key={q.id}>
                    <label className="pick">
                      <input
                        type="checkbox"
                        checked={q.selected}
                        onChange={(e) => updateSession((s) => ({ aiQuestions: s.aiQuestions.map((x) => (x.id === q.id ? { ...x, selected: e.target.checked } : x)) }))}
                      />
                      <span className="pick-body">
                        {q.category && (
                          <span className="pick-meta">
                            <span className="badge">{q.category}</span>
                          </span>
                        )}
                        <span className="pick-text">{q.question}</span>
                        {q.intent && (
                          <span className="pick-sub">
                            <b>의도</b> {q.intent}
                          </span>
                        )}
                        {q.tip && (
                          <span className="pick-sub">
                            <b>팁</b> {q.tip}
                          </span>
                        )}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>

      {/* ── 4. 질문 세트 ── */}
      <section className="card">
        <div className="card-head">
          <h2 className="card-title">
            <span className="card-num">4</span> 모의 면접 질문 세트
          </h2>
          <div className="btn-row">
            <button className="btn" onClick={compose}>
              <Icon name="list" size={16} /> 선택한 질문으로 세트 만들기
            </button>
            <button className="btn btn-ghost" onClick={loadDefaults}>
              기본 질문 불러오기
            </button>
          </div>
        </div>
        {draft.length === 0 ? (
          <div className="empty">
            <Icon name="list" size={28} />
            <p>위에서 질문을 고른 뒤 &lsquo;선택한 질문으로 세트 만들기&rsquo;를 누르세요. 질문을 고르지 않으면 기본 질문 6개로 만들어져요.</p>
          </div>
        ) : (
          <ol className="qset">
            {draft.map((r, i) => (
              <li key={r.id} className={r.use ? '' : 'off'}>
                <input type="checkbox" checked={r.use} onChange={(e) => editRow(r.id, { use: e.target.checked })} aria-label={`${i + 1}번 질문 사용`} />
                <span className="qset-num">{i + 1}</span>
                <div className="qset-main">
                  <input className="qset-input" value={r.question} onChange={(e) => editRow(r.id, { question: e.target.value })} placeholder="질문을 입력하세요" aria-label={`${i + 1}번 질문`} />
                  <div className="qset-meta">
                    <span className="badge gray">{r.source}</span>
                    {r.category && <span className="badge gray">{r.category}</span>}
                    {!r.sig && <span className="muted small">기본 음성으로 읽어요</span>}
                  </div>
                </div>
                <div className="qset-actions">
                  <button className="icon-btn" onClick={() => moveRow(i, -1)} disabled={i === 0} aria-label="위로">
                    <Icon name="arrowUp" size={16} />
                  </button>
                  <button className="icon-btn" onClick={() => moveRow(i, 1)} disabled={i === draft.length - 1} aria-label="아래로">
                    <Icon name="arrowDown" size={16} />
                  </button>
                  <button className="icon-btn danger" onClick={() => setDraft((d) => d.filter((x) => x.id !== r.id))} aria-label="삭제">
                    <Icon name="trash" size={16} />
                  </button>
                </div>
              </li>
            ))}
          </ol>
        )}
        <div className="card-foot">
          <button className="btn btn-ghost" onClick={() => setDraft((d) => [...d, row('', { source: '직접 입력' })])}>
            <Icon name="plus" size={16} /> 질문 추가
          </button>
          <button className="btn btn-primary btn-lg" onClick={start} disabled={!usable.length}>
            이 질문 {usable.length}개로 모의 면접 시작 <Icon name="arrowRight" size={17} />
          </button>
        </div>
      </section>
    </>
  )
}
