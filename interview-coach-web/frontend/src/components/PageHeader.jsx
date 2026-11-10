// 모든 페이지 상단 공통: 단계 표시 + 제목 + 설명 + 오른쪽 버튼 영역(children)
const STEPS = [
  { id: 'prepare', label: '질문 준비' },
  { id: 'practice', label: '모의 면접' },
  { id: 'report', label: '리포트' },
]

export default function PageHeader({ page, title, description, onNavigate, children }) {
  const current = STEPS.findIndex((s) => s.id === page)
  return (
    <header className="page-header">
      <div className="page-header-text">
        {current >= 0 && (
          <ol className="steps" aria-label="연습 단계">
            {STEPS.map((s, i) => (
              <li key={s.id} className={i === current ? 'is-current' : i < current ? 'is-done' : ''}>
                <button type="button" onClick={() => onNavigate(s.id)} aria-current={i === current ? 'step' : undefined}>
                  <span className="step-num">{i + 1}</span>
                  {s.label}
                </button>
              </li>
            ))}
          </ol>
        )}
        <h1 className="page-title">{title}</h1>
        {description && <p className="page-desc">{description}</p>}
      </div>
      {children && <div className="page-actions">{children}</div>}
    </header>
  )
}
