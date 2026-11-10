/**
 * useFaceCamera — 카메라 켜기/끄기 + MediaPipe 얼굴 분석을 한곳에 모은 "커스텀 훅"
 *
 * [React 개념] 커스텀 훅
 *   이름이 use로 시작하는 함수 안에서 useState/useEffect/useRef를 묶어 둔 것.
 *   화면(JSX) 코드와 카메라 로직을 분리해서, PracticePage는 "카메라를 켠다/값을 읽는다"만 신경 쓰면 된다.
 *
 * 처리 흐름 (vision.py의 InterviewVideoProcessor.recv와 같은 순서)
 *   video 프레임 → 거울 반전 + 가로 640px 이하로 축소 → detectForVideo → analyzeFace
 *   → 누적 통계 갱신 → 코칭 메시지 → canvas에 테두리·메시지 그리기
 */
import { useEffect, useRef, useState } from 'react'
import { FaceLandmarker, FilesetResolver } from '@mediapipe/tasks-vision'
import { analyzeFace, coachingMessage, createStats, takeSnapshot, updateStats } from '../lib/faceAnalysis'

// wasm 버전은 package.json의 @mediapipe/tasks-vision 버전과 반드시 같아야 한다(다르면 로딩 오류).
const WASM_URL = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.2.2/wasm'
// 기존 config.py의 FACE_MODEL_URL과 같은 공식 모델 (약 4MB, 브라우저가 캐시함)
const MODEL_URL =
  'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task'

const ANALYSIS_MAX_WIDTH = 640 // vision.py와 동일: 가로 640px 넘으면 줄여서 분석
const UI_UPDATE_MS = 250 // 화면 갱신 주기(초당 4회)
const COLORS = { good: '#22A06B', warn: '#F08C00', bad: '#E5372B' }

/** getUserMedia 오류 → 한국어 안내 문구 */
function cameraErrorMessage(err) {
  switch (err?.name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return '카메라 권한이 거부되었어요. 주소창 왼쪽 아이콘에서 카메라를 "허용"으로 바꾸고, Mac이라면 시스템 설정 > 개인정보 보호 및 보안 > 카메라에서 브라우저를 켠 뒤 다시 시도해 주세요.'
    case 'NotFoundError':
    case 'OverconstrainedError':
      return '사용할 수 있는 카메라를 찾지 못했어요. 웹캠이 연결되어 있는지 확인해 주세요.'
    case 'NotReadableError':
      return '카메라를 열 수 없어요. 다른 앱(Zoom, FaceTime 등)이 카메라를 쓰고 있는지 확인해 주세요.'
    default:
      return `카메라를 켜지 못했어요. (${err?.name ?? '알 수 없는 오류'})`
  }
}

/**
 * FaceLandmarker 생성. GPU가 안 되는 환경이면 CPU로 한 번 더 시도한다.
 * @returns {Promise<{ landmarker: FaceLandmarker, delegate: 'GPU' | 'CPU' }>} 실제로 쓰인 실행 방식도 함께 돌려준다
 */
async function createLandmarker() {
  const fileset = await FilesetResolver.forVisionTasks(WASM_URL)
  const options = (delegate) => ({
    baseOptions: { modelAssetPath: MODEL_URL, delegate },
    runningMode: 'VIDEO',
    numFaces: 1,
    outputFaceBlendshapes: true,
    outputFacialTransformationMatrixes: true,
  })
  try {
    return { landmarker: await FaceLandmarker.createFromOptions(fileset, options('GPU')), delegate: 'GPU' }
  } catch {
    return { landmarker: await FaceLandmarker.createFromOptions(fileset, options('CPU')), delegate: 'CPU' }
  }
}

/** canvas에 얼굴 테두리 모서리 4개와 왼쪽 위 상태 메시지 그리기 (vision.py의 _draw, _put_label) */
function drawOverlay(ctx, w, h, a, coach) {
  ctx.clearRect(0, 0, w, h)
  const color = COLORS[coach.level]
  if (a) {
    const x1 = a.bbox.x1 * w, y1 = a.bbox.y1 * h
    const x2 = a.bbox.x2 * w, y2 = a.bbox.y2 * h
    const L = Math.max(12, (x2 - x1) / 6)
    ctx.strokeStyle = color
    ctx.lineWidth = 3
    ctx.lineCap = 'round'
    for (const [x, y, sx, sy] of [[x1, y1, 1, 1], [x2, y1, -1, 1], [x1, y2, 1, -1], [x2, y2, -1, -1]]) {
      ctx.beginPath()
      ctx.moveTo(x + sx * L, y)
      ctx.lineTo(x, y)
      ctx.lineTo(x, y + sy * L)
      ctx.stroke()
    }
  }
  // Python은 OpenCV가 한글을 못 그려서 영어를 썼지만, canvas는 한글이 되므로 한국어 메시지를 쓴다.
  ctx.font = '600 15px Pretendard, -apple-system, sans-serif'
  const tw = ctx.measureText(coach.ko).width
  ctx.fillStyle = 'rgba(30, 30, 30, 0.55)'
  ctx.beginPath()
  ctx.roundRect(14, 14, tw + 40, 32, 10)
  ctx.fill()
  ctx.fillStyle = color
  ctx.beginPath()
  ctx.arc(30, 30, 5, 0, Math.PI * 2)
  ctx.fill()
  ctx.fillStyle = '#fff'
  ctx.textBaseline = 'middle'
  ctx.fillText(coach.ko, 42, 31)
}

/**
 * @param {boolean} enabled  사이드바의 '카메라 분석' 설정. false면 카메라를 쓰지 않는다.
 */
export function useFaceCamera(enabled) {
  // [React 개념] useRef
  //   값이 바뀌어도 화면을 다시 그리지 않는 "보관함". .current로 읽고 쓴다.
  //   ① <video>, <canvas> 같은 실제 DOM 요소를 가리킬 때  ② 매 프레임 바뀌는 누적값을 담을 때 쓴다.
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const statsRef = useRef(createStats())
  const recentRef = useRef([])
  const liveRef = useRef(null) // 가장 최근 프레임의 { coach, pose }

  const [cameraOn, setCameraOn] = useState(false)
  // 'off' | 'starting'(카메라 여는 중) | 'loading-model' | 'running' | 'camera-only'(모델 실패)
  const [status, setStatus] = useState('off')
  const [error, setError] = useState('')
  const [snapshot, setSnapshot] = useState(null)

  // 사이드바에서 카메라 분석을 끄면 카메라 상태도 끈다.
  // (렌더 중에 state를 맞추는 React 공식 패턴. 다시 켰을 때 카메라가 저절로 켜지는 것을 막는다)
  if (!enabled && cameraOn) setCameraOn(false)

  // [React 개념] useEffect
  //   화면이 그려진 "뒤에" 실행할 부수 작업(카메라 열기, 타이머 등)을 넣는 곳.
  //   두 번째 인자 [enabled, cameraOn]가 바뀔 때마다 이전 것을 정리하고 다시 실행된다.
  //   return 하는 함수가 "정리 함수(cleanup)"로, 카메라를 끄거나 페이지를 떠나(컴포넌트가 사라질 때)
  //   반드시 실행된다. 여기서 카메라 트랙을 stop() 하지 않으면 카메라 초록불이 계속 켜져 있다.
  useEffect(() => {
    if (!enabled || !cameraOn) return

    let cancelled = false // 정리된 뒤에 늦게 끝난 await 결과를 무시하기 위한 표시
    let stream = null
    let landmarker = null
    let rafId = 0
    let timerId = 0
    const video = videoRef.current
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    // 분석용 보이지 않는 canvas: 여기에 거울 반전 + 축소한 프레임을 그려서 MediaPipe에 넘긴다.
    // vision.py도 cv2.flip(img, 1)로 먼저 뒤집은 뒤 분석했기 때문에, 똑같이 뒤집어야
    // 좌표(cx)와 각도(yaw, roll)의 부호가 Python 버전과 같아진다.
    const work = document.createElement('canvas')
    const wctx = work.getContext('2d')
    let lastVideoTime = -1
    let lastTs = -1
    let delegate = null // 'GPU' | 'CPU'
    // 성능 측정(개발자 확인 패널용): 화면 갱신 사이(250ms) 동안의 분석 횟수와 걸린 시간 합계
    const perf = { count: 0, sumMs: 0, since: performance.now() }

    // 매 화면 주사(보통 60Hz)마다 호출되는 분석 루프
    const loop = () => {
      rafId = requestAnimationFrame(loop)
      // 카메라는 보통 30fps라서, 새 프레임이 왔을 때만 분석한다(같은 프레임 중복 분석 방지).
      if (video.readyState < 2 || video.currentTime === lastVideoTime) return
      lastVideoTime = video.currentTime

      const scale = Math.min(1, ANALYSIS_MAX_WIDTH / video.videoWidth)
      const w = Math.round(video.videoWidth * scale)
      const h = Math.round(video.videoHeight * scale)
      if (work.width !== w || work.height !== h) {
        work.width = canvas.width = w
        work.height = canvas.height = h
      }
      wctx.setTransform(-1, 0, 0, 1, w, 0) // 좌우 반전
      wctx.drawImage(video, 0, 0, w, h)

      // detectForVideo의 타임스탬프는 반드시 계속 증가해야 한다(vision.py와 같은 처리).
      let ts = performance.now()
      if (ts <= lastTs) ts = lastTs + 1
      lastTs = ts

      let analysis = null
      const t0 = performance.now()
      try {
        const res = landmarker.detectForVideo(work, ts)
        if (res.faceLandmarks?.length) {
          analysis = analyzeFace(
            res.faceBlendshapes?.[0]?.categories,
            res.facialTransformationMatrixes?.[0]?.data ?? null,
            res.faceLandmarks[0],
          )
        }
      } catch (e) {
        console.warn('프레임 분석 오류(이 프레임만 건너뜀):', e) // vision.py처럼 프레임 하나 실패는 무시
      }
      perf.count += 1
      perf.sumMs += performance.now() - t0 // detectForVideo + analyzeFace 1회에 걸린 시간

      // ── 성능 설계 ──────────────────────────────────────────────────────
      // 이 루프는 초당 약 30번 돈다. 여기서 setState를 부르면 React가 초당 30번 화면 전체를
      // 다시 계산해서 분석과 렌더링이 서로 CPU를 뺏고 화면이 버벅인다.
      // 그래서 누적값은 화면과 상관없는 useRef 보관함에만 쌓고(=렌더링 없음),
      // 사람이 읽는 숫자는 아래 setInterval이 250ms마다(초당 4회) 한 번씩만 state로 옮긴다.
      // canvas 오버레이는 React를 거치지 않고 직접 그리므로 매 프레임 그려도 가볍다.
      const now = performance.now()
      updateStats(statsRef.current, recentRef.current, analysis, now)
      const coach = coachingMessage(analysis)
      liveRef.current = {
        coach,
        pose: analysis && { yaw: analysis.yaw, pitch: analysis.pitch, roll: analysis.roll, headOk: analysis.headOk },
      }
      drawOverlay(ctx, w, h, analysis, coach)
    }

    async function start() {
      setStatus('starting')
      if (!navigator.mediaDevices?.getUserMedia) {
        setError('이 주소에서는 카메라를 쓸 수 없어요. http://localhost:5173 처럼 localhost 또는 HTTPS 주소로 접속해 주세요.')
        setCameraOn(false)
        return
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 960 }, height: { ideal: 540 } },
          audio: false,
        })
      } catch (e) {
        if (cancelled) return
        setError(cameraErrorMessage(e))
        setCameraOn(false)
        return
      }
      if (cancelled) {
        // 권한 창이 떠 있는 사이에 페이지를 떠났다면, 늦게 받은 카메라도 바로 끈다.
        stream.getTracks().forEach((t) => t.stop())
        return
      }
      video.srcObject = stream
      await video.play().catch(() => {})
      if (cancelled) return

      setStatus('loading-model')
      try {
        ;({ landmarker, delegate } = await createLandmarker())
      } catch (e) {
        if (cancelled) return
        console.error(e)
        setError('얼굴 분석 모델을 불러오지 못했어요. 인터넷 연결을 확인하고 카메라를 껐다가 다시 켜 주세요. (카메라 화면은 그대로 볼 수 있어요)')
        setStatus('camera-only')
        return
      }
      if (cancelled) {
        landmarker.close()
        return
      }

      // 카메라를 새로 켤 때마다 통계를 0부터 (vision.py도 카메라 시작 때 처리기를 새로 만든다)
      statsRef.current = createStats()
      recentRef.current = []
      setStatus('running')
      rafId = requestAnimationFrame(loop)
      perf.since = performance.now()
      timerId = setInterval(() => {
        const now = performance.now()
        const perfInfo = {
          analysisFps: (perf.count * 1000) / Math.max(now - perf.since, 1),
          avgAnalysisMs: perf.count ? perf.sumMs / perf.count : 0,
          delegate,
        }
        perf.count = 0
        perf.sumMs = 0
        perf.since = now
        setSnapshot({
          ...takeSnapshot(statsRef.current, recentRef.current, now),
          ...liveRef.current, // { coach, pose }: 가장 최근 프레임의 메시지와 머리 각도
          perf: perfInfo, // 개발자 확인 패널용. 같은 250ms 주기로 함께 갱신되므로 렌더링이 추가로 늘지 않는다
        })
      }, UI_UPDATE_MS)
    }

    start()

    // 정리 함수: 카메라 끄기 버튼, 설정 끄기, 다른 페이지로 이동할 때 모두 여기로 온다.
    return () => {
      cancelled = true
      cancelAnimationFrame(rafId)
      clearInterval(timerId)
      stream?.getTracks().forEach((t) => t.stop()) // 카메라 하드웨어 해제(초록불 꺼짐)
      if (video) video.srcObject = null
      landmarker?.close()
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      liveRef.current = null
      setStatus('off')
      setSnapshot(null)
    }
  }, [enabled, cameraOn])

  const turnOn = () => {
    setError('')
    setCameraOn(true)
  }
  const turnOff = () => setCameraOn(false)
  /** '답변 시작' 때 누적 지표를 0으로 (vision.py의 reset) */
  const resetStats = () => {
    statsRef.current = createStats()
  }

  return { videoRef, canvasRef, cameraOn, status, error, snapshot, turnOn, turnOff, resetStats }
}
