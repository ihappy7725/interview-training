# 🎙️ MockMate: AI 면접 연습기 (React + FastAPI)

**MockMate**는 카메라 앞에서 실제 면접처럼 답변하면 시선·자세를 실시간으로 코칭하고, 녹음한 답변을 AI가 평가해 주는 웹 앱입니다.

```
질문 준비(실제 기출 + AI 예상 질문) → 모의 면접(카메라·마이크) → 즉시 피드백 → 리포트 → 성장 기록
```

| 페이지 | 기능 |
|---|---|
| **질문 준비** | 지원 정보(회사·직무·면접 유형·JD·이력서), 🔎 웹에서 실제 기출 질문 찾기(출처 확인 표시), 직접 붙여넣기, ✨ AI 예상 질문(의도·팁), 질문 세트 편집(사용 여부, 수정, 추가, 삭제, 순서) |
| **모의 면접** | 카메라 시선·자세 실시간 코칭, 🔊 질문 듣기(ElevenLabs), 답변 녹음 → 전사 → 지표 → AI 평가, 점수(종합·내용·전달력·비언어), STAR 체크, 개선 답안, 꼬리질문 연습 |
| **리포트** | KPI, 역량 레이더, 질문별 점수, AI 종합 진단, 질문별 상세, `.md` 다운로드, 성장 기록 저장 |
| **성장 기록** | 회차별 점수 추이, 기록 표, 회차 상세, 삭제, JSON 내보내기 |

---

## 1. 구조

```
interview-coach-web/
├─ vercel.json             Vercel 설정 (frontend + backend를 한 프로젝트로)
├─ backend/                FastAPI 서버 (/api/*)
│  ├─ main.py              API 경로
│  ├─ ai.py                OpenAI: 전사·웹 검색·질문 생성·답변 평가·종합 리포트
│  ├─ tts.py               ElevenLabs 질문 음성 + 캐시
│  ├─ security.py          접근 코드, 질문 서명
│  ├─ scoring.py, text_metrics.py   점수·말하기 속도·간투사 (기존 버전 그대로)
│  ├─ config.py, questions.py       환경 변수·언어 설정, 기본 질문
│  └─ requirements.txt, requirements-dev.txt(Pillow, 파비콘 생성용)
├─ frontend/               Vite + React(JavaScript)
│  └─ src/
│     ├─ App.jsx           전체 상태(설정·세션·기록), 서버 확인, 페이지 전환
│     ├─ pages/            PreparePage, PracticePage, ReportPage, HistoryPage
│     ├─ components/       Sidebar, PageHeader, AnswerResult, Charts(SVG), CoachingPanel, DevPanel, Icon …
│     ├─ hooks/            useFaceCamera(카메라+MediaPipe), useRecorder(녹음), useQuestionVoice(질문 음성)
│     └─ lib/              faceAnalysis(얼굴), audioAnalysis(음성 신호), api, storage, report
└─ tools/make_favicons.py  파비콘 생성 스크립트
```

**어디서 무엇을 계산하나**

| 데이터 | 처리 위치 | 서버로 가는 것 |
|---|---|---|
| 카메라 영상 | 브라우저(MediaPipe) | 얼굴 지표 숫자만 (영상은 안 보냄) |
| 녹음 음성 신호(침묵·억양·말끝) | 브라우저(Web Audio, 기존 librosa 로직 이식) | 숫자 + 전사용 녹음 파일 |
| 전사, 속도·간투사, 점수, AI 평가 | 서버 | 결과 JSON |
| 연습 기록 | **브라우저 localStorage** | 저장하지 않음 |

> 기록은 **그 브라우저에만** 남습니다(다른 기기와 공유 안 됨, 브라우저 데이터를 지우면 사라짐). 녹음 파일은 저장하지 않습니다.

## 2. 로컬 실행 (Mac)

준비: Node.js LTS, Python 3.13(`python3.13 --version`), Chrome 권장

**터미널 1: backend**
```bash
cd interview-coach-web/backend
python3.13 -m venv venv            # 처음 한 번
source venv/bin/activate
pip install -r requirements.txt    # 패키지가 바뀌면 다시 실행
cp .env.example .env               # 처음 한 번, 그다음 3번을 보고 키 입력
uvicorn main:app --reload --port 8000
```

**터미널 2: frontend**
```bash
cd interview-coach-web/frontend
npm install                        # 처음 한 번
npm run dev
```

접속: **http://localhost:5173** (`/api` 요청은 Vite가 8000번 서버로 전달)

## 3. 환경 변수 (`backend/.env` 또는 Vercel Environment Variables)

| 이름 | 필수 | 설명 |
|---|---|---|
| `OPENAI_API_KEY` | AI 기능에 필요 | 없으면 AI 기능이 꺼지고 카메라 코칭·녹음 지표만 동작 |
| `OPENAI_CHAT_MODEL` | - | 기본 `gpt-6-luna` (2026-11 OpenAI 문서 기준 저비용 모델) |
| `OPENAI_TRANSCRIBE_MODEL` | - | 기본 `gpt-transcribe` (공식 권장 전사 모델) |
| `OPENAI_REASONING_EFFORT` | - | `low` 등. 응답이 느리면 `low` |
| `APP_ACCESS_CODE` | **배포 시 필수** | AI 기능 접근 코드. 아래 4번 참고 |
| `ELEVENLABS_API_KEY` | - | 질문 음성. 없으면 브라우저 기본 음성 |
| `ELEVENLABS_MODEL_ID` | - | 기본 `eleven_flash_v2_5` |
| `ELEVENLABS_VOICE_ID_KO` / `_EN` / `_ZH` | ElevenLabs 사용 시 | 언어별 음성 ID. 없는 언어는 기본 음성 |
| `TTS_SIGNING_SECRET` | - | 질문 서명 비밀값(비우면 자동) |

`.env`를 고친 뒤에는 서버를 껐다 켜고(`Ctrl + C` → 다시 실행) 브라우저를 새로고침하세요.

## 4. 비용 보호

배포하면 누구나 서버 API를 호출할 수 있어서 두 가지 장치를 두었습니다.

1. **접근 코드 (OpenAI):** 질문 생성·검색·답변 평가·종합 리포트는 화면 사이드바에 `APP_ACCESS_CODE`를 입력해야 동작합니다.
   - 코드는 브라우저에 기억됩니다.
   - 로컬에서 비워 두면 코드 없이 쓸 수 있습니다.
   - **Vercel에서 비워 두면 AI 기능이 잠깁니다**(실수로 공개되는 것 방지).
   - 코드 없는 방문자도 기본 질문, 카메라 코칭, 녹음 음성 지표는 체험할 수 있습니다.
   - 추가로 OpenAI 대시보드에서 월 사용 한도를 정해 두기를 권합니다.
2. **질문 서명 (ElevenLabs):** 서버가 만든 질문(기본·AI 생성·웹 수집·꼬리질문)에만 서명을 붙이고, `/api/tts`는 서명이 맞는 문장만 읽습니다.
   - 직접 입력하거나 수정한 질문은 브라우저 기본 음성으로 읽습니다.
   - 한 번에 300자까지만 허용합니다.

## 5. ElevenLabs 음성

- 키 권한: **Text to Speech**(필수), **Voices Read**(음성 목록 조회 시)
- 같은 질문은 `backend/cache/tts/`에 mp3로 저장해 다시 부르지 않습니다(Vercel에서는 `/tmp`에 저장되며 오래 유지되지 않음).
- **무료 요금제 조건** (2026-11 공식 문서 기준)
  - 월 10,000 크레딧, 이월 없음
  - **상업적 사용 불가**
  - 공개 시 **"elevenlabs.io" 표기 필수**. 그래서 화면에 "Voice by ElevenLabs (elevenlabs.io)"를 표시합니다.

## 6. Vercel 배포

`vercel.json`이 frontend와 backend를 한 프로젝트로 묶습니다(Vercel **Services** 기능, 2026-11 기준 베타).
- `/api/*` 요청은 `backend/main.py`의 `app`(FastAPI, Python 3.13 — `backend/.python-version`)이 처리합니다.
- 그 밖의 요청은 `frontend/`(Vite 빌드)가 처리합니다.

1. GitHub에 `interview-coach-web` 폴더를 저장소로 올립니다. 올리기 전에 `git status`로 **`.env`가 포함되지 않았는지 확인**하세요.
2. Vercel에서 저장소를 Import합니다. Root Directory는 저장소 최상위(`vercel.json`이 있는 곳)로 둡니다.
3. **Environment Variables**에 3번 표의 값을 넣습니다. 최소한 `OPENAI_API_KEY`, `APP_ACCESS_CODE`가 필요합니다.
4. Deploy를 누릅니다. 배포 주소는 HTTPS라서 카메라·마이크가 동작합니다.

**Vercel 제약 (공식 문서 기준)**
- 요청 본문은 4.5MB까지입니다. 녹음은 32kbps라 3분이면 약 0.7MB, 서버는 4MB에서 거절합니다.
- Hobby 요금제는 함수 실행 시간이 최대 300초이고, **비상업적 용도 전용**입니다.
- 서버에는 파일이 오래 남지 않습니다. 그래서 기록은 브라우저에 저장합니다.

> 이 저장소의 Vercel 설정은 공식 문서를 보고 작성했지만, 실제 Vercel 환경에서는 아직 테스트하지 않았습니다. 첫 배포 후 빌드 로그를 확인해 주세요.

## 7. 개발자 확인 패널

사이드바 맨 아래 **개발자 확인**을 켜면 다음이 보입니다(켠 상태는 브라우저에 기억).
- **서버:** 서버 상태(5초마다 확인), 응답 시간, TTS·AI 설정
- **머리 각도:** yaw +는 화면 기준 오른쪽, pitch +는 아래, roll +는 화면 기준 왼쪽 기울기
- **성능:** 분석 FPS, 1회 분석 시간, GPU/CPU

## 8. 자주 나는 오류

| 증상 | 해결 |
|---|---|
| 사이드바 **서버 연결 안 됨** | 터미널 1의 uvicorn이 켜져 있는지 확인. `--reload` 중 코드 오류로 멈췄다면 `Ctrl + C` 후 다시 실행 |
| `No module named openai` 등 | `source venv/bin/activate` 후 `pip install -r requirements.txt` |
| "OpenAI 키가 설정되지 않아…" | `backend/.env`에 `OPENAI_API_KEY` 입력 후 서버 재시작 |
| "접근 코드가 맞지 않아요" | 사이드바에 `APP_ACCESS_CODE`와 같은 값 입력 |
| "마이크 권한이 거부되었어요" / 카메라 권한 | 주소창 왼쪽 아이콘에서 허용 + Mac **시스템 설정 > 개인정보 보호 및 보안 > 마이크/카메라**에서 브라우저 켜기 → 브라우저 완전 종료 후 재실행 |
| "음성이 거의 감지되지 않았어요" | 마이크 입력 장치 확인(시스템 설정 > 사운드 > 입력), 마이크 가까이에서 답변 |
| 질문 듣기가 "기본 음성으로 재생 중" | 안내 뒤의 이유 확인(키 없음, 권한 부족, 음성 ID 없음, 직접 입력한 질문 등) |
| ElevenLabs "키에 필요한 권한이 없어요" | elevenlabs.io > Settings > API Keys에서 Text to Speech 권한 켜기 |
| `CERTIFICATE_VERIFY_FAILED` | Mac python.org 설치판의 인증서 문제. 서버는 certifi로 해결되어 있음. 다른 스크립트에서 나면 `/Applications/Python 3.13/Install Certificates.command` 실행 |
| 탭 아이콘이 안 바뀜 | 강력 새로고침(⌘⇧R) |

## 9. 개인정보

- 카메라 영상은 브라우저 안에서만 분석되며 서버로 전송되지 않습니다.
- 답변 녹음과 질문 문장은 전사·평가를 위해 서버를 거쳐 **OpenAI**로 전송됩니다. 질문 문장은 음성 생성을 위해 **ElevenLabs**로도 전송됩니다. 서버는 녹음을 저장하지 않습니다.
- 표시되는 점수는 **연습용 지표**입니다. 내용 점수는 AI 루브릭 평가, 전달력·비언어 점수는 신호 기반 휴리스틱이며 채용 결과로 검증된 값이 아닙니다.
