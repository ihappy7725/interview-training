// 오른쪽 '실시간 코칭' 카드. 값은 모두 props로 받아서 보여주기만 한다.
// 판정 기준은 기존 app.py의 live_panel()과 동일하다.
import Icon from './Icon'

const level = (v, good, warn) => (v >= good ? 'good' : v >= warn ? 'warn' : 'bad')
const pct = (v) => `${Math.round(v * 100)}%`
const deg = (v) => `${v >= 0 ? '+' : ''}${Math.round(v)}°`

function Row({ label, value, lvl }) {
  return (
    <div className="live-row">
      <span>{label}</span>
      <span className={`badge ${lvl}`}>{value}</span>
    </div>
  )
}

export default function CoachingPanel({ enabled, cameraOn, status, snapshot }) {
  let body
  if (!enabled) {
    body = <p className="muted">카메라 분석이 꺼져 있어요. 사이드바에서 켤 수 있습니다.</p>
  } else if (!cameraOn) {
    body = <p className="muted">카메라를 켜면 시선·자세 실시간 코칭이 시작됩니다.</p>
  } else if (status === 'camera-only') {
    body = <p className="muted">얼굴 분석 모델이 없어 지표를 계산할 수 없어요.</p>
  } else if (!snapshot) {
    body = <p className="muted">{status === 'loading-model' ? '얼굴 분석 모델을 불러오는 중…' : '카메라 준비 중…'}</p>
  } else {
    const s = snapshot
    const pose = s.pose
    body = (
      <>
        {s.coach && <div className={`coach-msg ${s.coach.level}`}>{s.coach.ko}</div>}
        <Row label="얼굴 인식률" value={pct(s.facePresence)} lvl={level(s.facePresence, 0.9, 0.7)} />
        <Row label="정면 응시 (최근 1.5초)" value={pct(s.recentEyeContact)} lvl={level(s.recentEyeContact, 0.7, 0.4)} />
        <Row label="정면 응시 (누적)" value={pct(s.eyeContact)} lvl={level(s.eyeContact, 0.7, 0.5)} />
        <Row
          label="미소 비율"
          value={pct(s.smileRatio)}
          lvl={s.smileRatio >= 0.1 && s.smileRatio <= 0.6 ? 'good' : 'warn'}
        />
        <Row
          label="눈 깜빡임"
          value={`${Math.round(s.blinksPerMin)}회/분`}
          lvl={s.blinksPerMin <= 30 ? 'good' : 'warn'}
        />
        <Row label="머리 움직임" value={s.headMovement.toFixed(2)} lvl={s.headMovement <= 0.3 ? 'good' : 'warn'} />
        <Row
          label="머리 각도 (좌우·상하·기울기)"
          value={pose ? `${deg(pose.yaw)} · ${deg(pose.pitch)} · ${deg(pose.roll)}` : '—'}
          lvl={pose ? (pose.headOk && Math.abs(pose.roll) <= 15 ? 'good' : 'warn') : 'gray'}
        />
      </>
    )
  }

  return (
    <section className="card coaching">
      <div className="card-head">
        <h2 className="card-title">
          <Icon name="camera" size={18} /> 실시간 코칭
        </h2>
        {enabled && cameraOn && status === 'running' && (
          <span className="badge good">
            <span className="live-dot" /> 분석 중
          </span>
        )}
      </div>
      {body}
      <p className="footnote">MediaPipe 표정 계수로 추정한 연습용 지표입니다.</p>
    </section>
  )
}
