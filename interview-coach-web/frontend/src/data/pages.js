// 사이드바 메뉴 목록. App(제목 표시)과 Sidebar(메뉴 버튼)가 함께 쓰므로 별도 파일로 둔다.
// (컴포넌트 파일에서 상수를 같이 export하면 Vite의 빠른 새로고침이 동작하지 않는다)
export const PAGES = [
  { id: 'prepare', icon: '📝', label: '질문 준비' },
  { id: 'practice', icon: '🎥', label: '모의 면접' },
  { id: 'report', icon: '📊', label: '리포트' },
  { id: 'history', icon: '📈', label: '성장 기록' },
]
