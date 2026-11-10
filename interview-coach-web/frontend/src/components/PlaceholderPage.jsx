// 아직 만들지 않은 페이지(질문 준비 / 리포트 / 성장 기록)에 공통으로 쓰는 빈 카드.
// 같은 모양을 세 번 쓰니까 컴포넌트 하나로 만들고, 다른 부분(제목·설명)만 props로 받는다.
export default function PlaceholderPage({ title, description }) {
  return (
    <section className="card placeholder">
      <span className="badge gray">2·3단계에서 구현 예정</span>
      <h2 className="sec-title">{title}</h2>
      <p className="muted">{description}</p>
    </section>
  )
}
