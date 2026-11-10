// 개발자 확인 패널: 서버 상태, 머리 각도, 분석 성능을 숫자로 보여준다.
// 값은 모두 props로 받기만 한다. 각도·성능 값은 카메라 분석과 같은 250ms 주기(초당 4회)로만 바뀐다.

const fmtTime = (d) => (d ? d.toLocaleTimeString('ko-KR', { hour12: false }) : '—')
const fix1 = (v) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}°`

// 방향 라벨: 분석은 거울 반전된 화면 기준이고, MediaPipe 3D 좌표계(x 오른쪽, y 위쪽, 카메라는 -z 방향을 봄)로 계산했다.
// 수식으로 정한 방향이라 실제 카메라로 한 번 확인이 필요하다(README 체크리스트).
const POSE_ROWS = [
  { key: 'yaw', label: 'yaw (좌우 회전)', hint: '+ : 화면 기준 오른쪽으로 고개 돌림' },
  { key: 'pitch', label: 'pitch (상하 회전)', hint: '+ : 아래를 내려다봄' },
  { key: 'roll', label: 'roll (기울기)', hint: '+ : 화면 기준 왼쪽으로 기울임(반시계)' },
]

function Item({ label, value, hint }) {
  return (
    <div className="dev-item">
      <span>{label}</span>
      <b>{value}</b>
      {hint && <small>{hint}</small>}
    </div>
  )
}

export default function DevPanel({ info }) {
  const { serverStatus, checkedAt, latencyMs, configLoaded, tts, ai, stats } = info
  const pose = stats?.pose
  const perf = stats?.perf

  return (
    <div className="dev-panel">
      <p className="dev-title">서버</p>
      <Item label="상태" value={{ ok: '연결됨', error: '연결 안 됨', checking: '확인 중' }[serverStatus]} />
      <Item label="마지막 확인" value={fmtTime(checkedAt)} hint="5초마다 /api/health" />
      <Item label="응답 시간" value={latencyMs != null ? `${latencyMs} ms` : '—'} />
      <Item label="언어 설정" value={configLoaded ? '불러옴' : '기본값 사용'} />
      <Item label="TTS" value={tts ? (tts.enabled ? `ElevenLabs · ${tts.model_id}` : '키 없음 → 기본 음성') : '—'} />
      <Item label="AI" value={ai ? (ai.enabled ? `${ai.model} · ${ai.access_required ? '코드 필요' : '코드 없음'}` : '키 없음') : '—'} />

      <p className="dev-title">머리 각도</p>
      {pose ? (
        POSE_ROWS.map((r) => <Item key={r.key} label={r.label} value={fix1(pose[r.key])} hint={r.hint} />)
      ) : (
        <p className="muted small">모의 면접에서 카메라 분석 중이고 얼굴이 보일 때 표시됩니다.</p>
      )}

      <p className="dev-title">성능</p>
      {perf ? (
        <>
          <Item label="분석 FPS" value={perf.analysisFps.toFixed(1)} hint="초당 분석 횟수(카메라 fps 이하)" />
          <Item label="1회 분석 평균" value={`${perf.avgAnalysisMs.toFixed(1)} ms`} />
          <Item label="실행 방식" value={perf.delegate ?? '—'} />
        </>
      ) : (
        <p className="muted small">카메라 분석이 시작되면 표시됩니다.</p>
      )}
    </div>
  )
}
