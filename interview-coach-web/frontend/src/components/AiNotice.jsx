// AI 기능을 쓸 수 없을 때 이유를 알려 주는 안내 띠
import Icon from './Icon'

const MESSAGES = {
  offline: '서버에 연결되지 않아 AI 기능을 쓸 수 없어요. 기본 질문과 카메라 코칭은 그대로 쓸 수 있어요.',
  disabled: '서버에 OpenAI 키가 설정되지 않아 AI 기능(질문 생성·답변 평가)이 꺼져 있어요.',
  locked: 'AI 기능을 쓰려면 사이드바에서 접근 코드를 입력해 주세요. 코드 없이도 기본 질문·카메라 코칭·녹음 지표는 쓸 수 있어요.',
}

export default function AiNotice({ state }) {
  if (state === 'ready' || !MESSAGES[state]) return null
  return (
    <div className="banner" role="status">
      <Icon name={state === 'locked' ? 'lock' : 'info'} size={18} />
      <span>{MESSAGES[state]}</span>
    </div>
  )
}
