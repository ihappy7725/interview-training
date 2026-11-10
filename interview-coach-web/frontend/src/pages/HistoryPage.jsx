// 성장 기록: 리포트에서 저장한 회차들의 점수 추이와 상세 (기존 app.py의 page_history)
// 기록은 이 브라우저(localStorage)에만 저장된다.
import { useState } from 'react'
import Icon from '../components/Icon'
import PageHeader from '../components/PageHeader'
import { LineChart } from '../components/Charts'
import { downloadText, formatDate } from '../lib/report'

export default function HistoryPage({ history, setHistory, onNavigate }) {
  const [confirm, setConfirm] = useState(null) // 삭제 확인 중인 기록 id 또는 'all'

  if (!history.length) {
    return (
      <>
        <PageHeader page="history" title="성장 기록" description="리포트에서 '성장 기록에 저장'을 누르면 회차별 점수 변화를 볼 수 있어요." onNavigate={onNavigate} />
        <section className="card">
          <div className="empty big">
            <Icon name="history" size={34} />
            <p>저장된 기록이 없어요.</p>
            <button className="btn btn-primary" onClick={() => onNavigate('report')}>
              리포트로 가기 <Icon name="arrowRight" size={16} />
            </button>
          </div>
        </section>
      </>
    )
  }

  const first = history[0]
  const last = history[history.length - 1]
  const diff = last.total - first.total
  const best = Math.max(...history.map((h) => h.total))
  const labels = history.map((h) => formatDate(h.date).slice(5, 10)) // MM-DD

  return (
    <>
      <PageHeader page="history" title="성장 기록" description="이 브라우저에 저장된 연습 기록이에요. 다른 기기와는 공유되지 않아요." onNavigate={onNavigate}>
        <button className="btn btn-ghost" onClick={() => downloadText('mockmate_history.json', JSON.stringify(history, null, 2), 'application/json')}>
          <Icon name="download" size={16} /> JSON 내보내기
        </button>
      </PageHeader>

      <div className="kpi-grid three">
        <div className="kpi accent">
          <span className="kpi-label">최근 종합 점수</span>
          <span className="kpi-value">{last.total}</span>
          <span className="kpi-sub">{formatDate(last.date)}</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">첫 기록 대비</span>
          <span className={`kpi-value ${diff > 0 ? 'up' : diff < 0 ? 'down' : ''}`}>
            {diff > 0 ? '+' : ''}
            {diff}
          </span>
          <span className="kpi-sub">{history.length}회 연습</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">최고 점수</span>
          <span className="kpi-value">{best}</span>
          <span className="kpi-sub">종합 기준</span>
        </div>
      </div>

      <section className="card">
        <div className="card-head">
          <h2 className="card-title">점수 추이</h2>
        </div>
        <LineChart
          labels={labels}
          series={[
            { name: '종합', color: 'var(--series-total)', values: history.map((h) => h.total), strong: true },
            { name: '내용', color: 'var(--series-1)', values: history.map((h) => h.content) },
            { name: '전달력', color: 'var(--series-2)', values: history.map((h) => h.delivery) },
            { name: '비언어', color: 'var(--series-3)', values: history.map((h) => h.nonverbal) },
          ]}
        />
      </section>

      <section className="card">
        <div className="card-head">
          <h2 className="card-title">회차별 기록</h2>
          {confirm === 'all' ? (
            <div className="confirm">
              <span>기록을 모두 지울까요?</span>
              <button className="btn btn-danger btn-small" onClick={() => { setHistory([]); setConfirm(null) }}>
                모두 삭제
              </button>
              <button className="btn btn-ghost btn-small" onClick={() => setConfirm(null)}>
                취소
              </button>
            </div>
          ) : (
            <button className="btn btn-ghost btn-small" onClick={() => setConfirm('all')}>
              <Icon name="trash" size={15} /> 전체 삭제
            </button>
          )}
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>일시</th>
                <th>회사 / 직무</th>
                <th>언어</th>
                <th className="num">답변</th>
                <th className="num">종합</th>
                <th className="num">내용</th>
                <th className="num">전달력</th>
                <th className="num">비언어</th>
                <th className="num">간투사/분</th>
              </tr>
            </thead>
            <tbody>
              {[...history].reverse().map((h) => (
                <tr key={h.id}>
                  <td>{formatDate(h.date)}</td>
                  <td>{[h.company, h.role].filter(Boolean).join(' / ') || '-'}</td>
                  <td>{h.language}</td>
                  <td className="num">{h.count}</td>
                  <td className="num strong">{h.total}</td>
                  <td className="num">{h.content}</td>
                  <td className="num">{h.delivery}</td>
                  <td className="num">{h.nonverbal ?? '-'}</td>
                  <td className="num">{h.filler_per_min}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="accordion">
          {[...history].reverse().map((h) => (
            <details key={h.id} className="accordion-item">
              <summary>
                <span className="acc-num">{formatDate(h.date).slice(5)}</span>
                <span className="acc-title">{[h.company, h.role].filter(Boolean).join(' / ') || '회사 미입력'} · 답변 {h.count}개</span>
                <span className={`acc-score ${h.total >= 80 ? 'good' : h.total >= 60 ? 'warn' : 'bad'}`}>{h.total}</span>
                <Icon name="chevronDown" size={16} className="acc-chevron" />
              </summary>
              <div className="accordion-body">
                <ul className="history-answers">
                  {h.answers.map((a, i) => (
                    <li key={i}>
                      <div className="ha-head">
                        <b>{a.question}</b>
                        <span className="badge">{a.scores.total}점</span>
                      </div>
                      {a.summary && <p className="muted">{a.summary}</p>}
                    </li>
                  ))}
                </ul>
                {confirm === h.id ? (
                  <div className="confirm">
                    <span>이 기록을 지울까요?</span>
                    <button className="btn btn-danger btn-small" onClick={() => { setHistory((list) => list.filter((x) => x.id !== h.id)); setConfirm(null) }}>
                      삭제
                    </button>
                    <button className="btn btn-ghost btn-small" onClick={() => setConfirm(null)}>
                      취소
                    </button>
                  </div>
                ) : (
                  <button className="btn btn-ghost btn-small" onClick={() => setConfirm(h.id)}>
                    <Icon name="trash" size={15} /> 이 기록 삭제
                  </button>
                )}
              </div>
            </details>
          ))}
        </div>
      </section>
    </>
  )
}
