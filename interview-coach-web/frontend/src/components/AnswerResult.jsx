// 답변 한 개의 분석 결과 (기존 app.py의 render_result를 옮김)
// answer: PracticePage가 만든 기록, onFollowUp/onRetry가 있으면 아래에 버튼을 보여준다.
import Icon from './Icon'
import { LABELS } from '../lib/report'

const scoreLevel = (v) => (v == null ? 'gray' : v >= 80 ? 'good' : v >= 60 ? 'warn' : 'bad')

function Stat({ label, value, sub, level }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className={`stat-value ${level || ''}`}>{value}</span>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  )
}

function Meter({ label, value }) {
  return (
    <div className="meter">
      <div className="meter-head">
        <span>{label}</span>
        <b>{value}</b>
      </div>
      <div className="meter-track">
        <div className={`meter-fill ${scoreLevel(value)}`} style={{ width: `${value}%` }} />
      </div>
    </div>
  )
}

function List({ title, items, icon }) {
  if (!items?.length) return null
  return (
    <div className="result-list">
      <h4>
        <Icon name={icon} size={16} /> {title}
      </h4>
      <ul>
        {items.map((x, i) => (
          <li key={i}>{x}</li>
        ))}
      </ul>
    </div>
  )
}

export default function AnswerResult({ answer: a, paceUnit, onFollowUp, onRetry, defaultOpen = false }) {
  const ev = a.evaluation
  const sc = a.scores
  const tx = a.text
  const au = a.audio || {}

  // AI 평가 없이 측정만 한 답변(접근 코드 없음 등)
  if (!ev) {
    return (
      <div className="result">
        <p className="result-note">
          <Icon name="info" size={16} /> AI 평가 없이 측정한 음성 지표입니다.
        </p>
        <div className="stat-grid">
          <Stat label="답변 시간" value={`${Math.round(au.duration_sec || 0)}초`} />
          <Stat label="첫 마디까지" value={au.lead_silence_sec != null ? `${au.lead_silence_sec}초` : '-'} />
          <Stat label="2초 이상 멈춤" value={`${au.long_pause_count ?? 0}회`} />
          <Stat label="억양 변화" value={au.pitch_variation_st != null ? `${au.pitch_variation_st}반음` : '-'} />
        </div>
      </div>
    )
  }

  const delta = a.prev_total != null ? sc.total - a.prev_total : null
  const star = ev.star || {}

  return (
    <div className="result">
      <div className="stat-grid">
        <Stat
          label="종합"
          value={sc.total}
          level={scoreLevel(sc.total)}
          sub={delta != null ? `이전 대비 ${delta >= 0 ? '+' : ''}${delta}` : `${a.attempt}번째 시도`}
        />
        <Stat label="내용" value={sc.content} level={scoreLevel(sc.content)} />
        <Stat label="전달력" value={sc.delivery} level={scoreLevel(sc.delivery)} />
        <Stat label="비언어" value={sc.nonverbal ?? '-'} level={scoreLevel(sc.nonverbal)} sub={sc.nonverbal == null ? '카메라 미사용' : undefined} />
      </div>

      <div className="chips">
        <span className="chip">
          속도 <b>{Math.round(tx.pace)}</b> {paceUnit} · {tx.pace_label}
        </span>
        <span className="chip">
          간투사 <b>{tx.filler_total}</b>회
        </span>
        <span className="chip">
          시간 <b>{Math.round(au.duration_sec || 0)}</b>초
        </span>
        {a.over_time > 0 && <span className="badge bad">시간 초과 +{a.over_time}초</span>}
      </div>

      <div className="bubble me">
        <span className="bubble-name">
          <Icon name="user" size={14} /> 내 답변
        </span>
        <p>{a.transcript}</p>
      </div>
      {ev.coach_comment && (
        <div className="bubble coach">
          <span className="bubble-name">
            <Icon name="bot" size={14} /> AI 코치
          </span>
          <p>{ev.coach_comment}</p>
        </div>
      )}

      {/* <details>: 브라우저 기본 '접고 펼치기' 요소. JS 없이 동작한다 */}
      <details className="disclosure" open={defaultOpen}>
        <summary>
          상세 평가 보기 <Icon name="chevronDown" size={16} />
        </summary>
        <div className="disclosure-body">
          <div className="meters">
            {['logic', 'specificity', 'relevance', 'structure'].map((k) => (
              <Meter key={k} label={LABELS[k]} value={ev.scores?.[k] ?? 0} />
            ))}
          </div>
          {star.applicable !== false && (
            <div className="star">
              <span className="star-title">STAR 체크</span>
              {[['situation', '상황'], ['task', '과제'], ['action', '행동'], ['result', '결과']].map(([k, n]) => (
                <span key={k} className={`badge ${star[k] ? 'good' : 'gray'}`}>
                  {star[k] ? <Icon name="check" size={12} strokeWidth={2.4} /> : null} {n}
                </span>
              ))}
            </div>
          )}
          {ev.summary && (
            <p className="result-summary">
              <b>총평</b> {ev.summary}
            </p>
          )}
          <List title="잘한 점" items={ev.strengths} icon="check" />
          <List title="개선점" items={ev.improvements} icon="arrowRight" />
          <List title="보강하면 좋을 근거" items={ev.missing_evidence} icon="search" />
          {(Object.keys(tx.fillers || {}).length > 0 || Object.keys(tx.habits || {}).length > 0) && (
            <div className="result-list">
              <h4>
                <Icon name="mic" size={16} /> 습관어
              </h4>
              <div className="chips">
                {Object.entries(tx.fillers || {}).map(([k, v]) => (
                  <span key={k} className="chip">
                    {k} <b>×{v}</b>
                  </span>
                ))}
                {Object.entries(tx.habits || {}).map(([k, v]) => (
                  <span key={k} className="chip muted-chip" title="의미가 있을 수도 있는 습관 표현 후보">
                    {k} <b>×{v}</b>
                  </span>
                ))}
              </div>
            </div>
          )}
          {a.voice?.notes?.length > 0 && (
            <List title={`목소리·자신감 (추정 ${a.voice.score ?? '-'}점)`} items={a.voice.notes} icon="volume" />
          )}
          {ev.improved_answer && (
            <div className="improved">
              <h4>
                <Icon name="sparkles" size={16} /> 개선 답안 예시
              </h4>
              <p className="muted small">[ ] 는 본인 경험으로 채울 부분이에요.</p>
              <p className="improved-text">{ev.improved_answer}</p>
            </div>
          )}
        </div>
      </details>

      {a.follow_up?.question && (
        <div className="follow-up">
          <span className="bubble-name">예상 꼬리질문</span>
          <p>{a.follow_up.question}</p>
          {(onFollowUp || onRetry) && (
            <div className="btn-row">
              {onFollowUp && (
                <button className="btn" onClick={onFollowUp}>
                  <Icon name="reply" size={16} /> 꼬리질문 연습하기
                </button>
              )}
              {onRetry && (
                <button className="btn btn-ghost" onClick={onRetry}>
                  <Icon name="repeat" size={16} /> 같은 질문 다시 답하기
                </button>
              )}
            </div>
          )}
        </div>
      )}
      {!a.follow_up?.question && onRetry && (
        <div className="btn-row">
          <button className="btn btn-ghost" onClick={onRetry}>
            <Icon name="repeat" size={16} /> 같은 질문 다시 답하기
          </button>
        </div>
      )}
    </div>
  )
}
