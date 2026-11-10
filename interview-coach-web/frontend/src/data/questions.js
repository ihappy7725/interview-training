// 기존 interview-coach/app.py의 DEFAULT_QUESTIONS를 그대로 옮김.
// 키는 언어 코드(/api/config의 languages[].code)와 같다.
export const DEFAULT_QUESTIONS = {
  ko: [
    '1분 동안 자기소개를 해 주세요.',
    '이 회사와 직무에 지원한 이유는 무엇인가요?',
    '가장 성과를 냈던 경험을 구체적으로 말씀해 주세요.',
    '팀에서 갈등이 생겼을 때 어떻게 해결했나요?',
    '본인의 약점과 이를 보완하기 위한 노력을 말씀해 주세요.',
    '입사 후 3년 동안 이루고 싶은 목표는 무엇인가요?',
  ],
  en: [
    'Please introduce yourself in about one minute.',
    'Why are you applying for this company and role?',
    'Tell me about your most significant achievement.',
    'Describe a time you resolved a conflict within a team.',
    'What is your biggest weakness and how are you working on it?',
    'Where do you see yourself in three years?',
  ],
  zh: [
    '请用一分钟做一下自我介绍。',
    '你为什么申请我们公司和这个职位？',
    '请具体谈谈你最有成就感的一段经历。',
    '团队中出现矛盾时，你是如何解决的？',
    '你的缺点是什么？你是如何改进的？',
    '入职后三年内你想实现什么目标？',
  ],
}
