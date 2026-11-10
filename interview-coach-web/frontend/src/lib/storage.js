/**
 * 브라우저 저장소(localStorage) 도우미 + 값이 바뀌면 자동 저장하는 usePersistentState 훅.
 *
 * 왜 localStorage인가: Vercel 같은 서버리스 환경에는 서버에 파일을 계속 저장할 곳이 없다.
 * 연습 기록은 이 브라우저에만 남는다(다른 기기·브라우저와 공유되지 않음, 브라우저 데이터 삭제 시 사라짐).
 * 녹음 파일은 저장하지 않는다(용량 한도 약 5MB, 개인정보).
 */
import { useEffect, useState } from 'react'

export function loadJSON(key, fallback) {
  try {
    const raw = localStorage.getItem(key)
    return raw == null ? fallback : JSON.parse(raw)
  } catch {
    return fallback
  }
}

export function saveJSON(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
    return true
  } catch {
    return false // 사생활 보호 모드이거나 용량 초과
  }
}

/** useState와 같지만, 값을 localStorage에도 저장해 새로고침 후에도 유지한다. */
export function usePersistentState(key, initial) {
  const [value, setValue] = useState(() => {
    const stored = loadJSON(key, null)
    // 저장된 값에 새로 생긴 항목이 없을 수 있어서 초기값과 합친다(객체일 때만)
    if (stored && typeof initial === 'object' && !Array.isArray(initial)) return { ...initial, ...stored }
    return stored ?? initial
  })
  useEffect(() => {
    saveJSON(key, value)
  }, [key, value])
  return [value, setValue]
}

export const newId = () => Math.random().toString(36).slice(2, 10)
