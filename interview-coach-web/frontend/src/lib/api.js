/**
 * 서버 API 호출 도우미.
 * - 접근 코드가 있으면 X-Access-Code 헤더로 함께 보낸다.
 * - 서버 오류 형식 {"detail": {"code", "message"}} 를 ApiError로 바꿔서, 화면이 message를 그대로 보여줄 수 있게 한다.
 */
const CODE_KEY = 'mockmate.accessCode'

export function getAccessCode() {
  try {
    return localStorage.getItem(CODE_KEY) || ''
  } catch {
    return ''
  }
}

export function setAccessCode(code) {
  try {
    if (code) localStorage.setItem(CODE_KEY, code)
    else localStorage.removeItem(CODE_KEY)
  } catch {
    /* 저장할 수 없어도 이번 접속에서는 동작 */
  }
}

export class ApiError extends Error {
  constructor(message, code, status) {
    super(message)
    this.code = code
    this.status = status
  }
}

async function toApiError(res) {
  let data = null
  try {
    data = await res.json()
  } catch {
    /* JSON이 아닌 응답 */
  }
  const d = data?.detail
  if (d && typeof d === 'object' && !Array.isArray(d)) return new ApiError(d.message, d.code, res.status)
  if (Array.isArray(d)) return new ApiError('입력값이 올바르지 않아요. 길이나 형식을 확인해 주세요.', 'validation', res.status)
  if (res.status === 413) return new ApiError('보내는 데이터가 너무 커요.', 'too_large', 413)
  if (res.status >= 500 && res.status !== 503) return new ApiError('서버에 연결할 수 없어요. 서버가 켜져 있는지 확인해 주세요.', 'server', res.status)
  return new ApiError(`요청이 실패했어요(HTTP ${res.status}).`, `http_${res.status}`, res.status)
}

/** fetch + 공통 처리. 실패하면 ApiError를 던진다. */
export async function api(path, { method = 'GET', json, form, signal } = {}) {
  const headers = {}
  const code = getAccessCode()
  if (code) headers['X-Access-Code'] = code
  let body
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(json)
  } else if (form) {
    body = form // FormData: Content-Type은 브라우저가 자동으로 정함
  }
  let res
  try {
    res = await fetch(path, { method, headers, body, signal })
  } catch (e) {
    if (e.name === 'AbortError') throw e
    throw new ApiError('서버에 연결할 수 없어요. 서버가 켜져 있는지 확인해 주세요.', 'network', 0)
  }
  if (!res.ok) throw await toApiError(res)
  return res
}

export const apiJson = async (path, options) => (await api(path, options)).json()
