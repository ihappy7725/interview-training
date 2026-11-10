import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import App from './App.jsx'

// StrictMode: 개발 중에만 컴포넌트의 useEffect를 일부러 "실행 → 정리 → 다시 실행"한다.
// 정리 함수(cleanup)를 빠뜨리면 카메라가 두 번 켜지는 식의 버그가 바로 드러나서 학습에 도움이 된다.
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
