# 🎙️ MockMate: AI 면접 연습기 (React + FastAPI)

**MockMate**는 카메라 앞에서 실제 면접처럼 답변을 연습하는 웹 앱입니다.
시선·자세를 실시간으로 코칭하고, 면접관 질문은 ElevenLabs 음성으로 읽어 줍니다.
기존 Streamlit 버전(`../interview-coach`)을 **React 화면 + Python FastAPI 서버** 구조로 다시 만들고 있습니다.
카메라 영상은 **브라우저 안에서 MediaPipe로만 분석**하며 서버로 보내지 않습니다.

| 단계 | 내용 | 상태 |
|---|---|---|
| 1단계 | 프로젝트 뼈대, 레이아웃, 모의 면접 화면(카메라 + 실시간 얼굴 분석 + 질문·타이머) | ✅ |
| 1단계 보완 | MockMate 이름·파비콘, 개발자 확인 패널, ElevenLabs 질문 음성(브라우저 음성 예비) | ✅ |
| 2·3단계 | 질문 준비(AI 예상 질문), 녹음·AI 평가, 리포트, 성장 기록 | 예정 |

```
interview-coach-web/
├─ backend/                FastAPI 서버
│  ├─ main.py              /api/health, /api/config, /api/tts, /api/tts/status
│  ├─ requirements.txt     서버 실행용 패키지
│  ├─ requirements-dev.txt 개발 도구용(Pillow, 파비콘 생성에만 사용)
│  ├─ .env.example         .env 견본 (실제 .env는 git에 올라가지 않음)
│  └─ cache/tts/           ElevenLabs 음성 캐시(mp3, 자동 생성, git 제외)
├─ frontend/               Vite + React(JavaScript) 화면
│  ├─ public/              파비콘, brand/(원본·정리본·단순화 아이콘)
│  └─ src/
│     ├─ App.jsx                    현재 페이지·설정, 5초 서버 확인, 개발자 모드
│     ├─ components/                Sidebar, DevPanel, CoachingPanel, PlaceholderPage
│     ├─ pages/PracticePage.jsx     모의 면접 화면
│     ├─ hooks/useFaceCamera.js     카메라 + MediaPipe 분석 반복
│     ├─ hooks/useQuestionVoice.js  질문 듣기(ElevenLabs → 브라우저 음성 예비)
│     ├─ lib/faceAnalysis.js        vision.py를 옮긴 계산 로직
│     ├─ data/                      기본 질문, 메뉴 목록
│     └─ styles.css                 색상 CSS 변수와 전체 스타일
└─ tools/
   ├─ make_favicons.py     아이콘 정리 + 파비콘 생성 일회용 스크립트
   └─ favicon-compare.png  파비콘 비교 이미지
```

---

## 1. 사전 준비 (Mac)

- **Node.js LTS**: [nodejs.org](https://nodejs.org)에서 설치. 확인: `node -v`, `npm -v`
- **Python 3.13**(또는 3.12): [python.org](https://www.python.org/downloads/macos/)에서 설치. 확인: `python3.13 --version`
  - Mac 기본 `python3`는 3.9일 수 있습니다. 그래서 venv를 만들 때는 꼭 버전을 붙여(`python3.13`) 실행합니다.
- **Chrome**(권장) 또는 Edge, Safari 최신 버전과 웹캠

## 2. backend 설치·실행 (터미널 1)

```bash
cd interview-coach-web/backend

# 가상환경 만들기 (처음 한 번)
python3.13 -m venv venv
source venv/bin/activate          # 프롬프트 앞에 (venv)가 보이면 성공
pip install -r requirements.txt

# .env 만들기 (처음 한 번)
cp .env.example .env              # 그다음 아래 3번을 보고 키를 넣으세요

# 서버 실행
uvicorn main:app --reload --port 8000
```

확인: <http://127.0.0.1:8000/api/health> → `{"status":"ok"}`, API 문서는 <http://127.0.0.1:8000/docs>.

> `.env`를 고친 뒤에는 서버를 `Ctrl + C`로 껐다가 다시 실행하세요(`--reload`는 .py 파일 변경만 감지합니다).
> 그다음 브라우저도 새로고침하면 사이드바와 개발자 패널에 새 설정이 반영됩니다.

## 3. ElevenLabs 음성 설정 (선택)

키가 없어도 앱은 정상 동작하며, 이때 질문 듣기는 **브라우저 기본 음성**을 씁니다.

1. [elevenlabs.io](https://elevenlabs.io)에 가입하고 **Settings > API Keys**에서 키를 만듭니다.
2. `backend/.env`에 넣습니다. 키는 따옴표 없이 `=` 뒤에 바로 붙여 씁니다.
   ```env
   ELEVENLABS_API_KEY=여기에_발급받은_키
   # 아래는 비워 두면 기본값을 사용합니다
   ELEVENLABS_MODEL_ID=            # 기본: eleven_flash_v2_5
   ELEVENLABS_VOICE_ID_KO=         # 한국어 질문 음성
   ELEVENLABS_VOICE_ID_EN=         # 영어 질문 음성
   ELEVENLABS_VOICE_ID_ZH=         # 중국어 질문 음성
   ```
3. 서버를 다시 시작합니다. 사이드바의 **개발자 확인** 패널에서 `TTS: ElevenLabs · eleven_flash_v2_5`가 보이면 연결된 것입니다.

**기본 모델이 `eleven_flash_v2_5`인 이유**
- 한국어·영어·중국어를 지원하고 응답이 빠릅니다(공식 문서 기준 약 100ms).
- API 가격이 `eleven_multilingual_v2`의 절반입니다(공식 가격표 $0.04 대 $0.08 / 1천 자).
- 언어 코드를 지정할 수 있습니다.

**안전장치**
- 한 번에 300자 이하만 허용합니다(넘으면 400 오류). 질문 하나에는 충분하고, 실수로 긴 글을 보내 크레딧이 빠지는 것을 막습니다.
- 키 값은 화면·API 응답·로그 어디에도 나오지 않습니다. `/api/tts/status`는 키가 있는지(`enabled`)만 알려 줍니다.

### 무료 요금제 조건 (2026-11 공식 문서 기준, 바뀔 수 있음)
- **월 10,000 크레딧**이고, 남은 크레딧은 다음 달로 이월되지 않습니다. Flash 모델은 API 사용 시 글자당 0.5~1 크레딧입니다. 질문 하나가 약 20~60자라서 캐시를 쓰면 한 달 연습에 충분합니다.
- **상업적 사용 불가**: 무료 요금제로 만든 음성은 비상업적 용도로만 쓸 수 있습니다.
- **출처 표기 필수**: 공개할 때 "elevenlabs.io"를 함께 적어야 합니다. 그래서 ElevenLabs 음성을 쓰는 동안 화면 하단에 **"Voice by ElevenLabs (elevenlabs.io)"**를 표시합니다.
- 출처: [요금제](https://elevenlabs.io/pricing), [생성물 공개 규정](https://elevenlabs.io/docs/help-center/legal/can-i-publish-the-content-i-generate-on-the-platform)

### 음성 캐시 폴더: `backend/cache/tts/`
- 같은 질문을 다시 들을 때 ElevenLabs를 또 부르지 않도록 mp3를 저장해 둡니다. 크레딧도 아끼고 응답도 즉시 옵니다.
- 파일 이름은 `(문장 + 음성 ID + 모델 ID)`의 SHA-256 해시입니다. 음성이나 모델을 바꾸면 자동으로 새 파일이 만들어집니다.
- 지워도 됩니다(다음 재생 때 다시 만들어집니다). `.gitignore`에 포함되어 GitHub에는 올라가지 않습니다.
- 응답 헤더 `X-TTS-Source`가 `cache`면 캐시에서, `elevenlabs`면 새로 만든 음성입니다.

## 4. frontend 설치·실행 (터미널 2)

```bash
cd interview-coach-web/frontend
npm install        # 처음 한 번
npm run dev        # 개발 서버 실행
```

## 5. 접속

- 화면: **<http://localhost:5173>**
- 브라우저는 5173(Vite)에만 접속합니다. `/api/...` 요청은 Vite가 8000(FastAPI)으로 대신 전달합니다(`vite.config.js`의 proxy).
- 사이드바의 서버 표시는 **5초마다** 자동으로 확인합니다. 서버를 껐다 켜면 몇 초 안에 `연결 안 됨` ↔ `연결됨`으로 바뀌고, 다시 연결되면 언어 설정과 TTS 상태도 자동으로 다시 불러옵니다.

## 6. 카메라 권한

1. `🎥 모의 면접` → **📷 카메라 켜기** → 브라우저 권한 창에서 **허용**
2. Mac에서는 **시스템 설정 > 개인정보 보호 및 보안 > 카메라**에서 사용하는 브라우저를 켜세요. 바꾼 뒤 브라우저를 완전히 종료(⌘Q)했다가 다시 여세요.
3. 처음 카메라를 켜면 얼굴 분석 모델(약 4MB)과 wasm 파일을 내려받습니다. 두 번째부터는 브라우저 캐시를 씁니다.

## 7. 개발자 확인 패널

사이드바 맨 아래 **개발자 확인** 스위치를 켜면 아래 값이 보입니다. 켠 상태는 브라우저에 기억됩니다(localStorage).

| 구역 | 항목 | 설명 |
|---|---|---|
| 서버 | 상태 / 마지막 확인 / 응답 시간 | 5초마다 `/api/health` 결과. 응답 시간은 브라우저 → Vite → FastAPI 왕복 ms |
| | 언어 설정 / TTS | `/api/config`를 불러왔는지, ElevenLabs 사용 여부와 모델 ID |
| 머리 각도 | yaw / pitch / roll | 소수점 1자리. **yaw + : 화면 기준 오른쪽**, **pitch + : 아래를 봄**, **roll + : 화면 기준 왼쪽으로 기울임**(수식 기준이므로 직접 고개를 돌려 확인 권장) |
| 성능 | 분석 FPS / 1회 분석 평균 / 실행 방식 | 초당 분석 횟수, `detectForVideo` 1회 시간(ms), MediaPipe가 GPU와 CPU 중 무엇으로 도는지 |

숫자는 카메라 분석과 같은 주기(초당 4회)로만 갱신해서 분석 성능에 영향을 주지 않도록 했습니다.

## 8. 파비콘 다시 만들기

원본(`frontend/public/brand/mockmate-icon-original.png`)을 바꿨다면:

```bash
cd interview-coach-web
backend/venv/bin/pip install -r backend/requirements-dev.txt   # Pillow, 처음 한 번
backend/venv/bin/python tools/make_favicons.py
```

- 원본은 덮어쓰지 않고 정리본(`brand/mockmate-icon-clean.png`)을 따로 만듭니다.
- 16·32px는 작은 크기에서 잘 보이도록 단순화한 그림(`brand/mockmate-icon-simple.png`)을 씁니다. 그물망은 흰 면으로 바꾸고, 빛 효과는 빼고, 선은 굵게 했습니다.
- 결과는 `tools/favicon-compare.png`에서 비교할 수 있습니다.

## 9. 자주 나는 오류와 해결 방법

| 증상 | 원인·해결 |
|---|---|
| `zsh: command not found: python3.13` | Python 미설치 → python.org에서 설치 후 터미널 재시작 |
| `No module named fastapi` | 가상환경이 꺼져 있음 → `source venv/bin/activate` 후 다시 실행 |
| `[Errno 48] Address already in use` | 8000번 포트를 이미 쓰는 중 → 이전 서버를 `Ctrl + C`로 끄거나 `lsof -i :8000`으로 확인 |
| 사이드바에 **● 서버 연결 안 됨** | backend가 꺼져 있음 → 터미널 1에서 uvicorn 실행. 5초 안에 자동 복구(즉시 확인은 **다시 연결**) |
| 질문 듣기에서 "기본 음성으로 재생 중" | ElevenLabs를 쓸 수 없는 상태입니다. 안내 문구 뒤에 이유가 표시됩니다(키 없음, 키 오류, 크레딧 부족, 요청 과다 등) |
| "ElevenLabs API 키가 올바르지 않아요" | `.env`의 키 확인(앞뒤 공백·따옴표 없이) → 서버 재시작 |
| "크레딧이 부족해요" | 이번 달 무료 크레딧 소진 → 다음 달 초기화까지 기본 음성 사용, 또는 캐시된 질문만 사용 |
| "음성 ID가 설정되지 않았어요" / "음성 ID를 찾을 수 없어요" | `.env`의 `ELEVENLABS_VOICE_ID_*` 확인. 무료 요금제는 Voice Library의 일부 음성을 API로 쓸 수 없을 수 있음 |
| "카메라 권한이 거부되었어요" | 주소창 왼쪽 아이콘 → 카메라 허용, 그리고 6번의 Mac 시스템 설정 확인 |
| "카메라를 열 수 없어요" | Zoom·FaceTime·다른 탭이 카메라 사용 중 → 그 앱 종료 |
| "얼굴 분석 모델을 불러오지 못했어요" | 인터넷 연결 확인. 회사망·광고 차단기가 `cdn.jsdelivr.net`, `storage.googleapis.com`을 막는지 확인 |
| "이 주소에서는 카메라를 쓸 수 없어요" | IP 주소로 접속한 경우 → `http://localhost:5173`으로 접속 |
| 브라우저 탭 아이콘이 안 바뀜 | 파비콘은 브라우저가 오래 캐시합니다 → 강력 새로고침(⌘⇧R) 또는 탭을 닫았다 다시 열기 |

## 10. 개인정보

- 카메라 영상은 브라우저 안에서만 분석되며 서버로 전송되지 않습니다.
- 질문 듣기를 누르면 **질문 문장**만 ElevenLabs로 전송됩니다(사용자 음성·영상은 전송하지 않음).
- `.env`(API 키)와 음성 캐시는 `.gitignore`에 포함되어 GitHub에 올라가지 않습니다.
- 화면의 수치는 MediaPipe 표정 계수로 **추정한 연습용 지표**이며, 카메라 위치·조명·안경에 따라 오차가 있습니다.
