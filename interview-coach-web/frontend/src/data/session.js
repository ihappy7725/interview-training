// 한 번의 면접 연습(세션) 초기 상태. 브라우저에 저장되어 새로고침해도 이어서 할 수 있다.
export const EMPTY_SESSION = {
  profile: { company: '', role: '', types: ['인성', '직무 역량', '경험(STAR)'], n: 6, jd: '', resume: '' },
  real: { items: [], note: '' }, // 웹에서 찾은 기출 질문
  manual: '', // 직접 붙여넣은 기출 질문(한 줄에 하나)
  aiQuestions: [], // AI 예상 질문
  draft: [], // 질문 세트 편집 중인 목록
  questions: [], // 모의 면접에 쓸 확정 질문 세트(비어 있으면 기본 질문)
  qIdx: 0,
  answers: [],
  overall: null,
  savedId: null, // 성장 기록에 저장한 회차 id(중복 저장 방지)
}
