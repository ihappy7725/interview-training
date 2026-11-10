// 직접 그린 SVG 차트 3종 (레이더, 묶은 막대 + 선, 선). 차트 라이브러리 없이 가볍게.
// viewBox를 쓰면 SVG 안의 좌표는 고정이고, 화면 크기에 맞춰 자동으로 늘었다 줄었다 한다.

const GRID = 'var(--chart-grid)'
const AXIS_TEXT = 'var(--muted)'

/** 레이더 차트. items: [{ label, value(0~100) }] */
export function RadarChart({ items, size = 320 }) {
  const c = size / 2
  const r = c - 62 // 바깥 글자 자리
  const n = items.length
  if (n < 3) return null
  const angle = (i) => -Math.PI / 2 + (i * 2 * Math.PI) / n
  const point = (i, v) => [c + Math.cos(angle(i)) * r * (v / 100), c + Math.sin(angle(i)) * r * (v / 100)]
  const ring = (v) => items.map((_, i) => point(i, v).join(',')).join(' ')
  const shape = items.map((it, i) => point(i, Math.max(0, Math.min(100, it.value))).join(',')).join(' ')

  return (
    <svg className="chart" viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`역량 레이더: ${items.map((i) => `${i.label} ${Math.round(i.value)}`).join(', ')}`}>
      {[25, 50, 75, 100].map((v) => (
        <polygon key={v} points={ring(v)} fill="none" stroke={GRID} strokeWidth="1" />
      ))}
      {items.map((_, i) => {
        const [x, y] = point(i, 100)
        return <line key={i} x1={c} y1={c} x2={x} y2={y} stroke={GRID} strokeWidth="1" />
      })}
      <polygon points={shape} fill="var(--primary)" fillOpacity="0.16" stroke="var(--primary)" strokeWidth="2" strokeLinejoin="round" />
      {items.map((it, i) => {
        const [x, y] = point(i, Math.max(0, Math.min(100, it.value)))
        return <circle key={i} cx={x} cy={y} r="3.5" fill="var(--surface)" stroke="var(--primary)" strokeWidth="2" />
      })}
      {items.map((it, i) => {
        const [x, y] = point(i, 118)
        const cos = Math.cos(angle(i))
        const anchor = Math.abs(cos) < 0.2 ? 'middle' : cos > 0 ? 'start' : 'end'
        return (
          <text key={it.label} x={x} y={y} textAnchor={anchor} dominantBaseline="middle" fontSize="11.5" fill={AXIS_TEXT}>
            <tspan>{it.label}</tspan>
            <tspan x={x} dy="14" fontWeight="700" fill="var(--text)">{Math.round(it.value)}</tspan>
          </text>
        )
      })}
    </svg>
  )
}

/**
 * 묶은 막대 + 선. labels: ['Q1', ...], bars: [{ name, color, values }], line: { name, color, values }
 */
export function BarLineChart({ labels, bars, line, height = 240 }) {
  const W = 640
  const H = height
  const pad = { l: 34, r: 12, t: 12, b: 28 }
  const iw = W - pad.l - pad.r
  const ih = H - pad.t - pad.b
  const groupW = iw / Math.max(labels.length, 1)
  const barW = Math.min(22, (groupW * 0.72) / bars.length)
  const y = (v) => pad.t + ih * (1 - Math.max(0, Math.min(100, v || 0)) / 100)
  const gx = (i) => pad.l + groupW * i + groupW / 2

  return (
    <figure className="chart-figure">
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="질문별 점수">
        {[0, 25, 50, 75, 100].map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke={GRID} strokeWidth="1" />
            <text x={pad.l - 8} y={y(v)} textAnchor="end" dominantBaseline="middle" fontSize="11" fill={AXIS_TEXT}>{v}</text>
          </g>
        ))}
        {labels.map((lab, i) => (
          <g key={lab}>
            {bars.map((b, j) => {
              const v = b.values[i] ?? 0
              const x = gx(i) - (barW * bars.length) / 2 + j * barW + 1
              return (
                <rect key={b.name} x={x} y={y(v)} width={barW - 2} height={Math.max(0, pad.t + ih - y(v))} rx="3" fill={b.color}>
                  <title>{`${lab} ${b.name} ${v ?? '-'}`}</title>
                </rect>
              )
            })}
            <text x={gx(i)} y={H - 8} textAnchor="middle" fontSize="11.5" fill={AXIS_TEXT}>{lab}</text>
          </g>
        ))}
        {line && (
          <>
            <polyline points={line.values.map((v, i) => `${gx(i)},${y(v)}`).join(' ')} fill="none" stroke={line.color} strokeWidth="2.2" strokeLinejoin="round" />
            {line.values.map((v, i) => (
              <circle key={i} cx={gx(i)} cy={y(v)} r="4" fill="var(--surface)" stroke={line.color} strokeWidth="2">
                <title>{`${labels[i]} ${line.name} ${v}`}</title>
              </circle>
            ))}
          </>
        )}
      </svg>
      <Legend items={[...bars, ...(line ? [line] : [])]} />
    </figure>
  )
}

/** 선 그래프. labels: x축 글자, series: [{ name, color, values(null 허용) }] */
export function LineChart({ labels, series, height = 260 }) {
  const W = 640
  const H = height
  const pad = { l: 34, r: 16, t: 14, b: 30 }
  const iw = W - pad.l - pad.r
  const ih = H - pad.t - pad.b
  const x = (i) => pad.l + (labels.length <= 1 ? iw / 2 : (iw * i) / (labels.length - 1))
  const y = (v) => pad.t + ih * (1 - Math.max(0, Math.min(100, v)) / 100)
  const every = Math.max(1, Math.ceil(labels.length / 7)) // x축 글자가 겹치지 않게 일부만

  return (
    <figure className="chart-figure">
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="점수 추이">
        {[0, 25, 50, 75, 100].map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke={GRID} strokeWidth="1" />
            <text x={pad.l - 8} y={y(v)} textAnchor="end" dominantBaseline="middle" fontSize="11" fill={AXIS_TEXT}>{v}</text>
          </g>
        ))}
        {labels.map((lab, i) =>
          i % every === 0 || i === labels.length - 1 ? (
            <text key={i} x={x(i)} y={H - 10} textAnchor="middle" fontSize="11" fill={AXIS_TEXT}>{lab}</text>
          ) : null,
        )}
        {series.map((s) => {
          const pts = s.values.map((v, i) => (v == null ? null : [x(i), y(v)])).filter(Boolean)
          return (
            <g key={s.name}>
              {pts.length > 1 && <polyline points={pts.map((p) => p.join(',')).join(' ')} fill="none" stroke={s.color} strokeWidth={s.strong ? 2.6 : 1.8} strokeLinejoin="round" />}
              {s.values.map((v, i) =>
                v == null ? null : (
                  <circle key={i} cx={x(i)} cy={y(v)} r={s.strong ? 4 : 3} fill="var(--surface)" stroke={s.color} strokeWidth="2">
                    <title>{`${labels[i]} ${s.name} ${v}`}</title>
                  </circle>
                ),
              )}
            </g>
          )
        })}
      </svg>
      <Legend items={series} />
    </figure>
  )
}

function Legend({ items }) {
  return (
    <figcaption className="legend">
      {items.map((it) => (
        <span key={it.name}>
          <i style={{ background: it.color }} />
          {it.name}
        </span>
      ))}
    </figcaption>
  )
}
