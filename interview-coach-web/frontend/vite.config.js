import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 브라우저가 /api/... 로 요청하면 Vite 개발 서버가 FastAPI(8000번)로 대신 전달한다.
    // 'localhost' 대신 127.0.0.1을 쓰는 이유: 최신 Node는 localhost를 IPv6(::1)로 먼저 찾을 수 있는데,
    // uvicorn은 기본적으로 IPv4(127.0.0.1)에서만 대기하므로 연결이 실패할 수 있다.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
