/**
 * 리포트·기록 계산 (interview-coach/core/scoring.py의 LABELS·grade, report.py, storage.py를 옮김)
 */
import { newId } from './storage'

export const LABELS = {
  logic: '논리성',
  specificity: '구체성',
  relevance: '질문 적합성',
  structure: '구조(STAR)',
  pace: '말하기 속도',
  filler: '습관어 절제',
  voice: '음성 자신감',
  eye: '시선 처리',
}

export function grade(total) {
  if (total >= 85) return '실전 준비 완료'
  if (total >= 70) return '좋음 · 다듬기'
  if (total >= 55) return '보통 · 연습 필요'
  return '기초 보강 필요'
}

/** 질문별 마지막 시도만 남긴다(순서 유지) */
export function latestAnswers(answers) {
  const map = new Map()
  for (const a of answers) {
    if (!a.evaluation) continue // AI 평가 없이 측정만 한 답변은 리포트에서 제외
    map.delete(a.question)
    map.set(a.question, a)
  }
  return [...map.values()]
}

export function summarize(answers) {
  const n = answers.length
  const avg = (key) => (n ? Math.round(answers.reduce((s, a) => s + (a.scores[key] || 0), 0) / n) : 0)
  const nv = answers.map((a) => a.scores.nonverbal).filter((v) => v != null)
  const radarKeys = Object.keys(LABELS)
  const radar = Object.fromEntries(radarKeys.map((k) => [k, n ? answers.reduce((s, a) => s + (a.scores.radar?.[k] || 0), 0) / n : 0]))
  if (!nv.length) delete radar.eye // 카메라를 쓰지 않았으면 시선 축은 빼기
  return {
    n,
    total: avg('total'),
    content: avg('content'),
    delivery: avg('delivery'),
    nonverbal: nv.length ? Math.round(nv.reduce((s, v) => s + v, 0) / nv.length) : null,
    fillerPerMin: n ? answers.reduce((s, a) => s + (a.text?.filler_per_min || 0), 0) / n : 0,
    radar,
  }
}

/** 성장 기록에 저장할 한 회차 (storage.py의 save_session과 같은 항목) */
export function makeHistoryRecord(profile, language, answers) {
  const s = summarize(answers)
  return {
    id: newId(),
    date: new Date().toISOString(),
    company: profile.company || '',
    role: profile.role || '',
    language,
    count: s.n,
    total: s.total,
    content: s.content,
    delivery: s.delivery,
    nonverbal: s.nonverbal,
    filler_per_min: Math.round(s.fillerPerMin * 100) / 100,
    answers: answers.map((a) => ({ question: a.question, transcript: a.transcript, scores: a.scores, summary: a.evaluation?.summary || '' })),
  }
}

export const formatDate = (iso) => {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const p = (v) => String(v).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

/** Markdown 리포트 (report.py의 build_markdown) */
export function buildMarkdown(profile, language, paceUnit, answers, overall) {
  const s = summarize(answers)
  const out = [
    `# 면접 연습 리포트 — ${profile.company || '회사 미입력'} / ${profile.role || '직무 미입력'}`,
    `- 일시: ${formatDate(new Date().toISOString())}`,
    `- 면접 언어: ${language}`,
    `- 답변 수: ${s.n}`,
    `- **종합 ${s.total}점 (${grade(s.total)})** · 내용 ${s.content} · 전달력 ${s.delivery}`,
    '',
    '> 점수는 연습용 지표입니다. 내용 점수는 AI 루브릭 평가, 전달력·비언어 점수는 음성/영상 신호 기반 휴리스틱입니다.',
    '',
  ]
  if (overall) {
    out.push('## 종합 진단', `**${overall.headline || ''}**`, '')
    for (const [title, key] of [['강점', 'strengths'], ['반복 패턴', 'patterns'], ['우선순위', 'priorities'], ['다음 연습 계획', 'practice_plan']]) {
      const items = overall[key] || []
      if (items.length) out.push(`### ${title}`, ...items.map((x, i) => `${i + 1}. ${x}`), '')
    }
  }
  answers.forEach((a, i) => {
    const ev = a.evaluation || {}
    const sc = a.scores
    const tx = a.text
    out.push(
      `## Q${i + 1}. ${a.question}`,
      `**종합 ${sc.total}점** · 내용 ${sc.content} · 전달력 ${sc.delivery} · 비언어 ${sc.nonverbal ?? '측정 안 함'}`,
      '',
      '| 항목 | 점수 |',
      '|---|---|',
      ...Object.entries(sc.radar || {}).map(([k, v]) => `| ${LABELS[k]} | ${v} |`),
      '',
      `- 답변 시간 ${a.audio?.duration_sec ?? '-'}초 · 속도 ${tx.pace} ${paceUnit} (${tx.pace_label})`,
      `- 간투사: ${Object.entries(tx.fillers || {}).map(([k, v]) => `${k}×${v}`).join(', ') || '없음'} (분당 ${tx.filler_per_min}) · 습관 표현 후보: ${Object.entries(tx.habits || {}).map(([k, v]) => `${k}×${v}`).join(', ') || '없음'}`,
      '',
      '**답변 전사**',
      '',
      `> ${a.transcript}`,
      '',
      `**총평** ${ev.summary || ''}`,
      '',
    )
    for (const [title, key] of [['잘한 점', 'strengths'], ['개선점', 'improvements'], ['보강할 근거', 'missing_evidence']]) {
      if (ev[key]?.length) out.push(`**${title}**`, ...ev[key].map((x) => `- ${x}`), '')
    }
    if (a.voice?.notes?.length) out.push('**음성 분석**', ...a.voice.notes.map((x) => `- ${x}`), '')
    if (ev.improved_answer) out.push('**개선 답안 예시** ([ ]는 본인 경험으로 채울 부분)', '', ev.improved_answer, '')
    if (ev.follow_up_question) out.push(`**예상 꼬리질문** ${ev.follow_up_question}`, '')
  })
  return out.join('\n')
}

export function downloadText(filename, text, type = 'text/markdown') {
  const url = URL.createObjectURL(new Blob([text], { type: `${type};charset=utf-8` }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
