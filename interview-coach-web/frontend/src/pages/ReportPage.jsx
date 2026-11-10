// 리포트: 이번 세션의 질문별 마지막 답변을 모아 점수·레이더·AI 종합 진단·다운로드·성장 기록 저장
// 기존 app.py의 page_report를 옮김.
import { useState } from 'react'
import Icon from '../components/Icon'
import PageHeader from '../components/PageHeader'
import AnswerResult from '../components/AnswerResult'
import { BarLineChart, RadarChart } from '../components/Charts'
import { apiJson } from '../lib/api'
import { buildMarkdown, downloadText, grade, LABELS, latestAnswers, makeHistoryRecord, summarize } from '../lib/report'

function Kpi({ label, value, sub, accent }) {
  return (
    <div className={`kpi ${accent ? 'accent' : ''}`}>
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}</span>
      <span className="kpi-sub">{sub}</span>
    </div>
  )
}

export default function ReportPage({ lang, onNavigate, session, updateSession, aiState, onSaveHistory, onNewSession }) {
  const answers = latestAnswers(session.answers)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirmReset, setConfirmReset] = useState(false)

  if (!answers.length) {
    return (
      <>
        <PageHeader page="report" title="리포트" description="모의 면접에서 답변을 분석하면 여기에서 종합 결과를 볼 수 있어요." onNavigate={onNavigate} />
        <section className="card">
          <div className="empty big">
            <Icon name="report" size={34} />
            <p>아직 AI로 분석된 답변이 없어요.</p>
            <button className="btn btn-primary" onClick={() => onNavigate('practice')}>
              모의 면접 시작하기 <Icon name="arrowRight" size={16} />
            </button>
          </div>
        </section>
      </>
    )
  }

  const s = summarize(answers)
  const overall = session.overall
  const saved = Boolean(session.savedId)

  const makeOverall = async () => {
    setBusy(true)
    setError('')
    try {
      const res = await apiJson('/api/report/overall', {
        method: 'POST',
        json: {
          profile: { company: session.profile.company, role: session.profile.role },
          // 서버에는 요약만 보낸다(전사 원문은 보내지 않음)
          answers: answers.map((a) => ({
            question: a.question,
            scores: a.scores,
            text: { pace: a.text.pace, pace_label: a.text.pace_label, filler_per_min: a.text.filler_per_min },
            summary: a.evaluation?.summary || '',
            improvements: a.evaluation?.improvements || [],
          })),
        },
      })
      updateSession({ overall: res })
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const title = [session.profile.company, session.profile.role].filter(Boolean).join(' · ') || '이번 연습 리포트'
  const radarItems = Object.entries(s.radar).map(([k, v]) => ({ label: LABELS[k], value: v }))

  return (
    <>
      <PageHeader page="report" title={title} description={`답변 ${s.n}개 · 질문별 마지막 시도 기준`} onNavigate={onNavigate}>
        <button className="btn btn-ghost" onClick={() => downloadText('mockmate_report.md', buildMarkdown(session.profile, lang.name, lang.pace_unit, answers, overall))}>
          <Icon name="download" size={16} /> .md 다운로드
        </button>
        <button className="btn btn-primary" onClick={() => onSaveHistory(makeHistoryRecord(session.profile, lang.name, answers))} disabled={saved}>
          <Icon name={saved ? 'check' : 'save'} size={16} /> {saved ? '성장 기록에 저장됨' : '성장 기록에 저장'}
        </button>
      </PageHeader>

      <div className="kpi-grid">
        <Kpi label="종합 점수" value={s.total} sub={grade(s.total)} accent />
        <Kpi label="내용" value={s.content} sub="논리·구체·적합·구조 (AI 루브릭)" />
        <Kpi label="전달력" value={s.delivery} sub="속도·습관어·음성 신호" />
        <Kpi label="비언어" value={s.nonverbal ?? '-'} sub={s.nonverbal == null ? '카메라 미사용' : '시선·자세·표정 (MediaPipe)'} />
        <Kpi label="간투사" value={s.fillerPerMin.toFixed(1)} sub="분당 평균 횟수" />
      </div>

      <div className="report-grid">
        <section className="card">
          <div className="card-head">
            <h2 className="card-title">역량 레이더</h2>
          </div>
          <RadarChart items={radarItems} />
        </section>

        <section className="card">
          <div className="card-head">
            <h2 className="card-title">
              <Icon name="sparkles" size={18} /> AI 종합 진단
            </h2>
            <button className="btn btn-primary btn-small" onClick={makeOverall} disabled={busy || aiState !== 'ready'}>
              {busy ? <span className="spinner light" aria-hidden="true" /> : <Icon name={overall ? 'refresh' : 'sparkles'} size={15} />}
              {busy ? '분석 중…' : overall ? '다시 만들기' : '종합 진단 만들기'}
            </button>
          </div>
          {error && <div className="alert">{error}</div>}
          {overall ? (
            <div className="overall">
              {overall.headline && <p className="overall-headline">{overall.headline}</p>}
              {[
                ['강점', 'strengths', 'check'],
                ['반복되는 약점', 'patterns', 'alert'],
                ['우선순위', 'priorities', 'flag'],
                ['다음 연습 계획', 'practice_plan', 'list'],
              ].map(([t, k, icon]) =>
                overall[k]?.length ? (
                  <div key={k} className="result-list">
                    <h4>
                      <Icon name={icon} size={16} /> {t}
                    </h4>
                    <ol>
                      {overall[k].map((x, i) => (
                        <li key={i}>{x}</li>
                      ))}
                    </ol>
                  </div>
                ) : null,
              )}
            </div>
          ) : (
            <p className="card-desc">{aiState === 'ready' ? '답변 전체를 묶어 반복되는 패턴과 우선순위, 다음 연습 계획을 정리해요.' : 'AI 기능을 쓸 수 있을 때 만들 수 있어요.'}</p>
          )}
        </section>
      </div>

      <section className="card">
        <div className="card-head">
          <h2 className="card-title">질문별 점수</h2>
        </div>
        <BarLineChart
          labels={answers.map((_, i) => `Q${i + 1}`)}
          bars={[
            { name: '내용', color: 'var(--series-1)', values: answers.map((a) => a.scores.content) },
            { name: '전달력', color: 'var(--series-2)', values: answers.map((a) => a.scores.delivery) },
            { name: '비언어', color: 'var(--series-3)', values: answers.map((a) => a.scores.nonverbal ?? 0) },
          ]}
          line={{ name: '종합', color: 'var(--series-total)', values: answers.map((a) => a.scores.total) }}
        />
      </section>

      <section className="card">
        <div className="card-head">
          <h2 className="card-title">질문별 상세</h2>
        </div>
        <div className="accordion">
          {answers.map((a, i) => (
            <details key={a.id} className="accordion-item">
              <summary>
                <span className="acc-num">Q{i + 1}</span>
                <span className="acc-title">{a.question}</span>
                <span className={`acc-score ${a.scores.total >= 80 ? 'good' : a.scores.total >= 60 ? 'warn' : 'bad'}`}>{a.scores.total}</span>
                <Icon name="chevronDown" size={16} className="acc-chevron" />
              </summary>
              <div className="accordion-body">
                <AnswerResult answer={a} paceUnit={lang.pace_unit} />
              </div>
            </details>
          ))}
        </div>
      </section>

      <div className="page-foot">
        {confirmReset ? (
          <div className="confirm">
            <span>답변·리포트를 지우고 새 연습을 시작할까요? (지원 정보는 남아요)</span>
            <button className="btn btn-danger btn-small" onClick={() => { onNewSession(); onNavigate('prepare') }}>
              새로 시작
            </button>
            <button className="btn btn-ghost btn-small" onClick={() => setConfirmReset(false)}>
              취소
            </button>
          </div>
        ) : (
          <button className="btn btn-ghost" onClick={() => setConfirmReset(true)}>
            <Icon name="refresh" size={16} /> 새 연습 시작
          </button>
        )}
        <button className="btn" onClick={() => onNavigate('practice')}>
          연습 계속하기 <Icon name="arrowRight" size={16} />
        </button>
      </div>
    </>
  )
}
