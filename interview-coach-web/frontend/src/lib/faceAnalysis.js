/**
 * MediaPipe Face Landmarker 결과 → 비언어 지표 계산 (순수 JS, React와 무관)
 *
 * 기존 interview-coach/core/vision.py를 그대로 옮긴 파일이다.
 * 함수 이름도 Python 쪽과 대응되게 지었으니 두 파일을 나란히 놓고 비교하며 읽으면 된다.
 *   head_pose_from_matrix → headPoseFromMatrix
 *   analyze_face          → analyzeFace
 *   coaching_message      → coachingMessage
 *   _update_stats         → updateStats
 *   snapshot              → takeSnapshot
 *
 * 수치는 블렌드셰이프(표정 계수)와 머리 회전각으로 '추정'한 연습용 지표이며,
 * 카메라 위치·조명·안경에 따라 오차가 있다.
 */

// ── 판정 기준(휴리스틱) — vision.py와 동일 ─────────────────────────────────
export const YAW_LIMIT = 18.0 // 좌우 고개 회전 허용 각도(도)
export const PITCH_LIMIT = 18.0 // 상하 고개 회전 허용 각도(도)
export const GAZE_SIDE_LIMIT = 0.45 // 눈동자 좌우 치우침 계수 한계
export const GAZE_UP_LIMIT = 0.45
export const GAZE_DOWN_LIMIT = 0.6 // 카메라가 화면 위에 있어 약간 아래를 보는 것은 허용
export const BLINK_ON = 0.5
export const SMILE_ON = 0.35

// '정면 응시(최근)' 계산 구간.
// vision.py는 최근 45프레임(30fps 기준 약 1.5초)을 썼다. 브라우저는 카메라·기기마다 fps가 달라서
// 프레임 개수 대신 "최근 1500ms"라는 시간 기준으로 바꿨다(의도는 동일: 약 1.5초).
export const RECENT_WINDOW_MS = 1500

const toDeg = (rad) => (rad * 180) / Math.PI

/** ±180° 근처 표현을 ±90° 범위로 정규화 (vision.py의 _wrap) */
function wrap(angle) {
  if (angle > 90) return angle - 180
  if (angle < -90) return angle + 180
  return angle
}

/**
 * 4x4 변환 행렬의 data(길이 16 배열)에서 m(행, 열) 값을 꺼내는 함수를 만든다.
 *
 * ── 저장 순서(행 우선/열 우선) 판단 근거 ──────────────────────────────────
 * 1) Python (mediapipe 1.2.2, tasks/python/components/containers/matrix_c.py의 to_numpy):
 *    C 쪽 데이터를 "열 우선(column-major)"으로 보고 (cols, rows) 모양으로 읽은 뒤 .T(전치)한다.
 *    → vision.py의 r[2, 1]은 수학적 의미 그대로 "2행 1열"이다.
 * 2) JS (@mediapipe/tasks-vision 1.2.2, vision_bundle.mjs):
 *    MatrixData proto의 packed_data를 아무 변환 없이 그대로 result.data에 복사한다.
 *    proto의 layout 필드는 읽지 않으며, MatrixData의 기본 layout은 COLUMN_MAJOR다.
 *    → Python과 같은 원본 데이터이므로 JS data도 열 우선: m(i, j) = data[j * 4 + i]
 * 3) 안전장치(버전이 바뀌어 순서가 달라질 경우 대비):
 *    얼굴 변환 행렬의 이동량(translation)은 4번째 열에 있고, 얼굴은 카메라 앞 수십 cm에 있으므로
 *    z 이동량의 절댓값이 크다(보통 수십). 열 우선이면 data[14]에, 행 우선이면 data[11]에 들어가고
 *    반대쪽 칸은 0이다. 그래서 둘 중 큰 쪽을 보고 저장 순서를 판정한다.
 */
function matrixReader(data) {
  const columnMajor = Math.abs(data[14]) >= Math.abs(data[11])
  return columnMajor ? (i, j) => data[j * 4 + i] : (i, j) => data[i * 4 + j]
}

/** 4x4 얼굴 변환 행렬 → { yaw, pitch, roll } 도 단위 (vision.py의 head_pose_from_matrix와 같은 식) */
export function headPoseFromMatrix(data) {
  const r = matrixReader(data)
  const sy = Math.sqrt(r(0, 0) ** 2 + r(1, 0) ** 2)
  const pitch = toDeg(Math.atan2(r(2, 1), r(2, 2)))
  const yaw = toDeg(Math.atan2(-r(2, 0), sy))
  const roll = toDeg(Math.atan2(r(1, 0), r(0, 0)))
  return { yaw: wrap(yaw), pitch: wrap(pitch), roll: wrap(roll) }
}

/**
 * 한 프레임의 얼굴 결과 → 판정값 (vision.py의 analyze_face)
 * @param {Array<{categoryName: string, score: number}>} categories  faceBlendshapes[0].categories
 * @param {number[] | null} matrixData  facialTransformationMatrixes[0].data
 * @param {Array<{x: number, y: number}>} landmarks  faceLandmarks[0] (0~1 정규화 좌표)
 */
export function analyzeFace(categories, matrixData, landmarks) {
  const blend = {}
  for (const c of categories ?? []) blend[c.categoryName] = c.score
  const b = (name) => blend[name] ?? 0

  const { yaw, pitch, roll } = matrixData ? headPoseFromMatrix(matrixData) : { yaw: 0, pitch: 0, roll: 0 }
  // 눈동자 방향(좌우 눈의 대응 계수 평균)
  const lookSide = Math.max(
    (b('eyeLookOutLeft') + b('eyeLookInRight')) / 2,
    (b('eyeLookInLeft') + b('eyeLookOutRight')) / 2,
  )
  const lookUp = (b('eyeLookUpLeft') + b('eyeLookUpRight')) / 2
  const lookDown = (b('eyeLookDownLeft') + b('eyeLookDownRight')) / 2
  const blink = (b('eyeBlinkLeft') + b('eyeBlinkRight')) / 2
  const smile = (b('mouthSmileLeft') + b('mouthSmileRight')) / 2

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const p of landmarks) {
    if (p.x < minX) minX = p.x
    if (p.x > maxX) maxX = p.x
    if (p.y < minY) minY = p.y
    if (p.y > maxY) maxY = p.y
  }
  const nose = landmarks[1]

  const headOk = Math.abs(yaw) < YAW_LIMIT && Math.abs(pitch) < PITCH_LIMIT
  const gazeOk = lookSide < GAZE_SIDE_LIMIT && lookUp < GAZE_UP_LIMIT && lookDown < GAZE_DOWN_LIMIT
  return {
    yaw, pitch, roll,
    lookSide, lookUp, lookDown,
    blink, smile,
    faceW: maxX - minX,
    cx: (maxX + minX) / 2,
    cy: (maxY + minY) / 2,
    nose: { x: nose.x, y: nose.y },
    eyeContact: headOk && gazeOk && blink < BLINK_ON,
    headOk,
    bbox: { x1: minX, y1: minY, x2: maxX, y2: maxY },
  }
}

/**
 * 코칭 메시지 (vision.py의 coaching_message). 위에서부터 먼저 걸리는 문제 하나만 보여준다.
 * @returns {{ en: string, ko: string, level: 'good' | 'warn' | 'bad' }}
 */
export function coachingMessage(a) {
  if (a == null) return { en: 'Face not detected', ko: '얼굴이 화면에 보이지 않아요', level: 'bad' }
  if (a.faceW < 0.18) return { en: 'Move closer', ko: '카메라에 조금 더 가까이 앉아 주세요', level: 'warn' }
  if (Math.abs(a.cx - 0.5) > 0.22 || Math.abs(a.cy - 0.5) > 0.25)
    return { en: 'Center your face', ko: '얼굴을 화면 중앙에 맞춰 주세요', level: 'warn' }
  if (Math.abs(a.roll) > 15) return { en: 'Keep your head level', ko: '고개가 기울어져 있어요', level: 'warn' }
  if (!a.headOk) return { en: 'Face the camera', ko: '고개를 정면으로 돌려 주세요', level: 'warn' }
  if (!a.eyeContact) return { en: 'Look at the camera', ko: '카메라 렌즈를 바라봐 주세요', level: 'warn' }
  return { en: 'Good posture', ko: '좋아요! 시선과 자세가 안정적이에요', level: 'good' }
}

// ── 누적 통계 (vision.py의 FaceStats) ──────────────────────────────────────
export function createStats(now = performance.now()) {
  return {
    started: now,
    frames: 0,
    faceFrames: 0,
    eyeContactFrames: 0,
    smileFrames: 0,
    blinks: 0,
    moveSum: 0,
    moveN: 0,
    eyeClosed: false,
    lastNose: null,
  }
}

/**
 * 프레임 하나의 분석 결과를 누적 통계에 반영 (vision.py의 _update_stats)
 * stats는 "그 자리에서 수정"한다. React state가 아니라 useRef에 들어 있는 객체라서 괜찮다.
 * recent는 [{ t, ok }] 배열로, 최근 RECENT_WINDOW_MS 동안의 정면 응시 여부를 담는다.
 */
export function updateStats(stats, recent, a, now) {
  stats.frames += 1
  if (a == null) {
    stats.lastNose = null
    pushRecent(recent, false, now)
    return
  }
  stats.faceFrames += 1
  stats.eyeContactFrames += a.eyeContact ? 1 : 0
  stats.smileFrames += a.smile > SMILE_ON ? 1 : 0
  // 눈을 "뜬 상태 → 감은 상태"로 바뀌는 순간만 깜빡임 1회로 센다
  const closed = a.blink > BLINK_ON
  if (closed && !stats.eyeClosed) stats.blinks += 1
  stats.eyeClosed = closed
  if (stats.lastNose) {
    stats.moveSum += Math.hypot(a.nose.x - stats.lastNose.x, a.nose.y - stats.lastNose.y)
    stats.moveN += 1
  }
  stats.lastNose = a.nose
  pushRecent(recent, a.eyeContact, now)
}

function pushRecent(recent, ok, now) {
  recent.push({ t: now, ok })
  while (recent.length && now - recent[0].t > RECENT_WINDOW_MS) recent.shift()
}

/** 화면 표시용 요약값 (vision.py의 snapshot) */
export function takeSnapshot(stats, recent, now) {
  const s = stats
  const elapsedSec = Math.max((now - s.started) / 1000, 1e-6)
  const recentEyeContact = recent.length ? recent.filter((r) => r.ok).length / recent.length : 0
  return {
    frames: s.frames,
    elapsedSec,
    facePresence: s.frames ? s.faceFrames / s.frames : 0,
    eyeContact: s.faceFrames ? s.eyeContactFrames / s.faceFrames : 0,
    smileRatio: s.faceFrames ? s.smileFrames / s.faceFrames : 0,
    blinksPerMin: s.frames ? s.blinks / (elapsedSec / 60) : 0,
    // 프레임 간 코끝 이동량(화면 폭 대비 %). 클수록 자주 움직임.
    headMovement: s.moveN ? (s.moveSum / s.moveN) * 100 : 0,
    recentEyeContact,
  }
}
