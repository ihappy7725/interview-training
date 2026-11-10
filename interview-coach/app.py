"""AI 면접 연습기 — Streamlit + MediaPipe + OpenAI

실행: streamlit run app.py
"""
from __future__ import annotations

import hashlib
import json
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from core import ai, config
from core.audio_analysis import analyze_audio, voice_confidence
from core.report import build_markdown
from core.scoring import LABELS, compute_scores, grade
from core.storage import load_history, save_session
from core.text_metrics import text_metrics
from core.theme import CSS, PRIMARY, chip, esc, kpi, live_row

st.set_page_config(page_title="InterviewLab · AI 면접 연습기", page_icon="🎙️", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

PAGES = ["📝 질문 준비", "🎥 모의 면접", "📊 리포트", "📈 성장 기록"]
DEFAULT_QUESTIONS = {
    "ko": ["1분 동안 자기소개를 해 주세요.", "이 회사와 직무에 지원한 이유는 무엇인가요?",
           "가장 성과를 냈던 경험을 구체적으로 말씀해 주세요.", "팀에서 갈등이 생겼을 때 어떻게 해결했나요?",
           "본인의 약점과 이를 보완하기 위한 노력을 말씀해 주세요.", "입사 후 3년 동안 이루고 싶은 목표는 무엇인가요?"],
    "en": ["Please introduce yourself in about one minute.", "Why are you applying for this company and role?",
           "Tell me about your most significant achievement.", "Describe a time you resolved a conflict within a team.",
           "What is your biggest weakness and how are you working on it?", "Where do you see yourself in three years?"],
    "zh": ["请用一分钟做一下自我介绍。", "你为什么申请我们公司和这个职位？", "请具体谈谈你最有成就感的一段经历。",
           "团队中出现矛盾时，你是如何解决的？", "你的缺点是什么？你是如何改进的？", "入职后三年内你想实现什么目标？"],
}

# ── 세션 상태 초기화 ─────────────────────────────────────────────────────────
ss = st.session_state
DEFAULTS = {
    "page": PAGES[0], "language": "한국어", "time_limit": 90, "use_camera": True,
    "p_company": "", "p_role": "", "p_types": ["인성", "직무 역량", "경험(STAR)"], "p_jd": "", "p_resume": "",
    "p_n": 6, "manual_q": "", "real_q": [], "real_note": "", "ai_q": [],
    "questions": [], "q_idx": 0, "answers": [], "last_audio_hash": None,
    "answer_started_at": None, "rec_nonce": 0, "overall": None, "flash": None,
}
for k, v in DEFAULTS.items():
    ss.setdefault(k, v)
# 다른 페이지로 이동해도 입력값이 지워지지 않도록 위젯 상태 유지
for k in list(ss.keys()):
    if isinstance(k, str) and (k.startswith("p_") or k.startswith("real_sel_") or k == "manual_q"):
        ss[k] = ss[k]
if "_goto" in ss:
    ss.page = ss.pop("_goto")

LANG = config.LANGUAGES[ss.language]


def profile() -> dict:
    return {"company": ss.p_company.strip(), "role": ss.p_role.strip(), "types": ss.p_types,
            "jd": ss.p_jd.strip(), "resume": ss.p_resume.strip(), "language": ss.language}


def go_to(page: str) -> None:
    ss["_goto"] = page
    st.rerun()


def latest_answers() -> list[dict]:
    """질문별 마지막 시도만 남긴다(순서 유지)."""
    latest: dict[str, dict] = {}
    for a in ss.answers:
        latest[a["question"]] = a
    return list(latest.values())


# ── 사이드바 ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="brand"><div class="brand-logo">◎</div>InterviewLab</div>', unsafe_allow_html=True)
    st.radio("메뉴", PAGES, key="page", label_visibility="collapsed")
    st.divider()
    st.markdown("**면접 설정**")
    st.selectbox("면접 언어", list(config.LANGUAGES), key="language")
    st.slider("답변 제한 시간(초)", 30, 180, step=10, key="time_limit")
    st.toggle("카메라 비언어 분석 (MediaPipe)", key="use_camera")
    lo, hi = LANG["pace_range"]
    st.caption(f"말하기 속도 참고 범위: {lo}–{hi} {LANG['pace_unit']} (연습용 기준)")
    st.divider()
    if config.api_key_ready():
        st.markdown(f'<span class="badge good">● OpenAI 연결됨</span> <span class="muted">{esc(config.CHAT_MODEL)}</span>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<span class="badge bad">● API 키 없음</span>', unsafe_allow_html=True)
        st.caption("`.env` 파일에 `OPENAI_API_KEY=sk-...`를 입력한 뒤 앱을 다시 실행하세요.")
    st.caption("🔒 카메라 영상은 내 PC에서만 분석되며 외부로 전송되지 않습니다. 녹음한 음성과 답변 텍스트는 분석을 위해 OpenAI API로 전송됩니다.")
    if st.button("세션 초기화", width="stretch"):
        for k in ["questions", "answers", "q_idx", "overall", "last_audio_hash", "answer_started_at"]:
            ss[k] = DEFAULTS[k] if not isinstance(DEFAULTS[k], list) else []
        st.rerun()

LANG = config.LANGUAGES[ss.language]


# ── 공통 헤더 ────────────────────────────────────────────────────────────────
def header(cta_label: str | None = None, cta_page: str | None = None) -> None:
    p = profile()
    title = " • ".join([x for x in (p["company"], p["role"]) if x]) or "AI 모의 면접"
    left, right = st.columns([3, 1], vertical_alignment="center")
    with left:
        status = "진행 중인 면접" if ss.questions else "면접 준비"
        st.markdown(
            f'<div class="hdr-sub">{status} <span class="badge">{esc(ss.language)}</span>'
            f'<span class="badge gray">{len(ss.questions)}문항</span></div>'
            f'<div class="hdr-title">{esc(title)}</div>', unsafe_allow_html=True)
    with right:
        if cta_label and st.button(cta_label, key="btn_cta_header", width="stretch"):
            go_to(cta_page)
    st.write("")


def need_api() -> bool:
    if not config.api_key_ready():
        st.warning("OpenAI API 키가 필요합니다. 프로젝트 폴더의 `.env`에 `OPENAI_API_KEY`를 넣고 다시 실행하세요.")
        return False
    return True


# ══════════════════════════════════════════════════════════════════════════
# 1. 질문 준비
# ══════════════════════════════════════════════════════════════════════════
def page_prepare() -> None:
    header("🎥 모의 면접으로 이동", PAGES[1])
    c1, c2 = st.columns([1, 1.25], gap="large")

    with c1, st.container(key="card_profile"):
        st.markdown('<p class="sec-title">지원 정보</p>', unsafe_allow_html=True)
        a, b = st.columns(2)
        a.text_input("회사명", key="p_company", placeholder="예: 태웅로직스")
        b.text_input("직무", key="p_role", placeholder="예: 해상 수출 영업")
        st.multiselect("면접 유형", config.QUESTION_TYPES, key="p_types")
        st.slider("생성할 예상 질문 수", 3, 12, key="p_n")
        st.text_area("채용공고 / 직무기술서(JD)", key="p_jd", height=140,
                     placeholder="주요 업무, 자격 요건, 우대 사항을 붙여넣으면 질문이 더 정확해집니다.")
        st.text_area("이력서·자기소개서 핵심 (선택)", key="p_resume", height=140,
                     placeholder="경험·프로젝트·성과를 붙여넣으면 경험 기반 꼬리질문이 생성됩니다.")

    with c2:
        with st.container(key="card_real"):
            st.markdown('<p class="sec-title">🔎 실제 면접 질문 수집</p>', unsafe_allow_html=True)
            st.caption("공개된 면접 후기·채용 페이지·기사를 웹 검색해 기출 질문을 모읍니다. "
                       "로그인이 필요한 후기(잡플래닛 상세 등)는 읽을 수 없으니 아래 칸에 직접 붙여넣으세요. "
                       "'출처 확인'은 해당 URL이 실제 검색 인용에 포함됐다는 뜻이며, 질문 내용은 링크에서 한 번 더 확인하세요.")
            if st.button("웹에서 기출 질문 찾기", type="primary", disabled=not ss.p_company.strip()):
                if need_api():
                    with st.spinner("공개 면접 후기를 검색하는 중… (30초~1분)"):
                        try:
                            res = ai.collect_real_questions(ss.p_company, ss.p_role or "전체 직무", LANG["label"])
                            ss.real_q, ss.real_note = res["questions"], res.get("note", "")
                            for k in [k for k in ss.keys() if str(k).startswith("real_sel_")]:
                                del ss[k]
                        except Exception as e:
                            st.error(f"검색 실패: {e}")
            if not ss.p_company.strip():
                st.caption("회사명을 입력하면 검색할 수 있습니다.")
            if ss.real_note:
                st.info(ss.real_note)
            for i, q in enumerate(ss.real_q):
                cols = st.columns([0.07, 0.93])
                ss.setdefault(f"real_sel_{i}", bool(q.get("verified")))
                cols[0].checkbox("선택", key=f"real_sel_{i}", label_visibility="collapsed")
                badge = '<span class="badge good">출처 확인</span>' if q.get("verified") else '<span class="badge warn">출처 미확인</span>'
                meta = " ".join(f'<span class="badge gray">{esc(x)}</span>' for x in (q.get("role_match"), q.get("category"), q.get("year")) if x)
                link = f' · <a href="{esc(q.get("source_url"))}" target="_blank">{esc(q.get("source_title") or "출처")}</a>' if q.get("source_url") else ""
                trans = f'<div class="muted">{esc(q["question_translated"])}</div>' if q.get("question_translated") and q["question_translated"] != q["question"] else ""
                cols[1].markdown(f'{badge} {meta}<div style="margin:4px 0 2px 0;font-weight:600">{esc(q.get("question"))}</div>{trans}'
                                 f'<div class="muted">{link}</div>', unsafe_allow_html=True)
            st.text_area("직접 수집한 기출 질문 붙여넣기 (한 줄에 하나)", key="manual_q", height=100)

        with st.container(key="card_ai"):
            st.markdown('<p class="sec-title">✨ AI 예상 질문 생성</p>', unsafe_allow_html=True)
            st.caption("지원 정보 + 선택한 기출 질문을 참고해 예상 질문을 만듭니다. AI가 만든 '예상' 질문이며 실제 출제 여부와는 무관합니다.")
            if st.button("예상 질문 생성", type="primary"):
                if need_api():
                    with st.spinner("예상 질문을 만드는 중…"):
                        try:
                            ss.ai_q = ai.generate_questions(profile(), [q["question"] for q in selected_real()] + manual_list(),
                                                            ss.p_n, LANG["label"])
                        except Exception as e:
                            st.error(f"생성 실패: {e}")
            for q in ss.ai_q:
                with st.expander(f"[{q.get('category', '')}] {q.get('question', '')}"):
                    st.markdown(f"**의도** {q.get('intent', '')}  \n**팁** {q.get('tip', '')}")

    # 최종 질문 세트
    with st.container(key="card_qset"):
        st.markdown('<p class="sec-title">🗂️ 모의 면접 질문 세트</p>', unsafe_allow_html=True)
        rows = ([{"사용": True, "질문": q["question"], "출처": "기출(웹)", "유형": q.get("category", ""), "팁": ""} for q in selected_real()]
                + [{"사용": True, "질문": q, "출처": "직접 입력", "유형": "", "팁": ""} for q in manual_list()]
                + [{"사용": True, "질문": q.get("question", ""), "출처": "AI 예상", "유형": q.get("category", ""), "팁": q.get("tip", "")} for q in ss.ai_q])
        if not rows:
            st.caption("아직 질문이 없습니다. 위에서 질문을 수집·생성하거나, 기본 질문으로 바로 연습할 수 있어요.")
            rows = [{"사용": True, "질문": q, "출처": "기본 질문", "유형": "공통", "팁": ""} for q in DEFAULT_QUESTIONS[LANG["code"]]]
        df = pd.DataFrame(rows)
        key = "qset_" + hashlib.md5(df.to_json().encode()).hexdigest()[:10]
        edited = st.data_editor(
            df, key=key, hide_index=True, num_rows="dynamic", width="stretch",
            column_config={
                "사용": st.column_config.CheckboxColumn(width="small"),
                "질문": st.column_config.TextColumn(width="large", required=True),
                "출처": st.column_config.TextColumn(width="small"),
                "유형": st.column_config.TextColumn(width="small"),
                "팁": st.column_config.TextColumn(width="medium"),
            })
        st.caption("행을 추가·수정·삭제할 수 있고, '사용' 체크된 질문만 순서대로 출제됩니다.")
        if st.button("이 질문으로 모의 면접 시작 →", key="btn_cta_start", width="stretch"):
            use = edited["사용"].fillna(False).astype(bool)
            has_text = edited["질문"].map(_s).str.len() > 0
            chosen = edited[use & has_text]
            if chosen.empty:
                st.warning("사용할 질문을 1개 이상 선택하세요.")
            else:
                ss.questions = [{"question": _s(r["질문"]), "source": _s(r["출처"]) or "직접 입력",
                                 "category": _s(r["유형"]), "tip": _s(r["팁"])} for _, r in chosen.iterrows()]
                ss.q_idx, ss.answer_started_at, ss.overall = 0, None, None
                ss.rec_nonce += 1
                go_to(PAGES[1])


def _s(v) -> str:
    """data_editor 셀 값(None/NaN 포함)을 안전하게 문자열로."""
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()


def selected_real() -> list[dict]:
    return [q for i, q in enumerate(ss.real_q) if ss.get(f"real_sel_{i}", bool(q.get("verified")))]


def manual_list() -> list[str]:
    return [l.strip(" -•\t") for l in ss.manual_q.splitlines() if l.strip(" -•\t")]


# ══════════════════════════════════════════════════════════════════════════
# 2. 모의 면접
# ══════════════════════════════════════════════════════════════════════════
@st.cache_resource(show_spinner="MediaPipe 얼굴 인식 모델을 준비하는 중… (최초 1회 약 4MB 다운로드)")
def prepare_face_model() -> str | None:
    from core.vision import ensure_face_model
    try:
        ensure_face_model()
        return None
    except Exception as e:
        return str(e)


def tts_button(text: str, lang_tag: str) -> None:
    """브라우저 내장 음성합성(Web Speech API)으로 질문 읽기 — API 비용 없음."""
    # </script> 등으로 스크립트를 깨지 않도록 이스케이프 (질문은 AI가 만든 텍스트일 수 있음)
    payload = json.dumps(text, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")
    html_src = f"""
<button id="tts" style="width:100%;height:40px;border-radius:12px;white-space:nowrap;border:1px solid #E4E7EC;background:#fff;
 font-weight:600;font-size:14px;cursor:pointer;color:#1D2939;font-family:-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif">
 🔊 질문 듣기</button>
<script>
const t = {payload};
document.getElementById('tts').onclick = () => {{
  const s = window.speechSynthesis; if (!s) {{ alert('이 브라우저는 음성 읽기를 지원하지 않습니다.'); return; }}
  s.cancel(); const u = new SpeechSynthesisUtterance(t); u.lang = '{lang_tag}'; u.rate = 1.0;
  const v = s.getVoices().find(v => v.lang && v.lang.replace('_','-').startsWith('{lang_tag[:2]}')); if (v) u.voice = v;
  s.speak(u);
}};
</script>"""
    if hasattr(st, "iframe"):
        st.iframe(html_src, height=46)
    else:  # 구버전 Streamlit
        components.html(html_src, height=46)


def metrics_brief(audio: dict, text: dict, vision: dict | None) -> str:
    lo, hi = LANG["pace_range"]
    fill = ", ".join(f"{k}×{v}" for k, v in text["fillers"].items()) or "없음"
    habit = ", ".join(f"{k}×{v}" for k, v in text["habits"].items()) or "없음"
    lines = [
        f"- 답변 시간 {audio['duration_sec']}초 (제한 {ss.time_limit}초)",
        f"- 말하기 속도 {text['pace']} {LANG['pace_unit']} → {text['pace_label']} (참고 범위 {lo}-{hi})",
        f"- 간투사 {text['filler_total']}회, 분당 {text['filler_per_min']}회: {fill}",
        f"- 습관 표현 후보: {habit}",
        f"- 2초 이상 멈춤 {audio.get('long_pause_count', 0)}회, 첫 마디까지 {audio.get('lead_silence_sec')}초",
        f"- 억양 변화 {audio.get('pitch_variation_st')}반음, 말끝 음량 변화 {audio.get('tail_drop_db')}dB",
    ]
    if vision:
        lines.append(f"- 카메라 정면 응시(추정) {vision['eye_contact']*100:.0f}%, 미소 {vision['smile_ratio']*100:.0f}%")
    return "\n".join(lines)


def process_answer(wav: bytes, q: dict, ctx, box) -> None:
    proc = getattr(ctx, "video_processor", None) if ctx else None
    vision = proc.snapshot() if proc else None
    if vision and (vision["frames"] < 15 or vision.get("error") and vision["face_presence"] == 0):
        vision = None
    with box:
        status = st.status("답변 분석 중…", expanded=True)
        try:
            audio = analyze_audio(wav)
            status.write("✅ 음성 신호 분석 (속도·침묵·억양)")
            if not audio["has_speech"]:
                status.update(label="음성이 거의 감지되지 않았어요. 마이크를 확인하고 다시 녹음해 주세요.", state="error")
                return
            transcript = ai.transcribe(wav, LANG["code"])
            status.write("✅ 음성 → 텍스트 변환")
            text = text_metrics(transcript, LANG["code"], audio["duration_sec"], LANG["pace_range"])
            voice = voice_confidence(audio, text["filler_per_min"])
            brief = metrics_brief(audio, text, vision)
            status.update(label="AI 코치가 피드백을 작성하는 중…", state="running", expanded=False)
            st.markdown('<div class="bubble-name">AI 코치 · 즉시 피드백</div>', unsafe_allow_html=True)
            with st.container(key="panel_quick_live"):
                quick = st.write_stream(ai.stream_quick_feedback(q["question"], transcript, brief, LANG["label"]))
            with st.spinner("논리성·구체성·STAR 상세 평가 중…"):
                evaluation = ai.evaluate_answer(q["question"], transcript, brief, profile(), LANG["label"])
            status.update(label="분석 완료", state="complete", expanded=False)
        except Exception as e:
            status.update(label="분석 중 오류가 발생했습니다", state="error")
            st.error(f"{type(e).__name__}: {e}")
            return

    scores = compute_scores(evaluation, text, voice, vision, LANG["pace_range"])
    prev = [a for a in ss.answers if a["question"] == q["question"]]
    ss.answers.append({
        "question": q["question"], "category": q.get("category", ""), "attempt": len(prev) + 1,
        "transcript": transcript, "audio": audio, "text": text, "voice": voice, "vision": vision,
        "quick": quick if isinstance(quick, str) else "".join(map(str, quick)),
        "evaluation": evaluation, "scores": scores,
        "over_time": max(0, round(audio["duration_sec"] - ss.time_limit)),
        "prev_total": prev[-1]["scores"]["total"] if prev else None,
    })
    if proc:
        proc.reset()
    ss.answer_started_at = None
    st.rerun()


def live_panel(ctx) -> None:
    playing = bool(ctx and ctx.state.playing)

    @st.fragment(run_every=1.0 if (playing or ss.answer_started_at) else None)
    def _panel():
        # 답변 타이머
        if ss.answer_started_at:
            el = time.time() - ss.answer_started_at
            limit = ss.time_limit
            over = el > limit
            st.markdown(live_row("⏱ 답변 시간", f"{int(el)//60:02d}:{int(el)%60:02d} / {limit//60:02d}:{limit%60:02d}",
                                 "bad" if over else ("warn" if el > limit * 0.8 else "good")), unsafe_allow_html=True)
            st.progress(min(el / limit, 1.0))
        proc = getattr(ctx, "video_processor", None) if ctx else None
        if not proc:
            st.markdown('<div class="muted">카메라를 켜면 시선·자세 실시간 코칭이 시작됩니다.</div>', unsafe_allow_html=True)
            return
        s = proc.snapshot()
        if s["error"]:
            st.error(s["error"])
        st.markdown(f'<div class="coach-msg {s["live_level"]}">{esc(s["live_msg"])}</div>', unsafe_allow_html=True)
        lvl = lambda v, g, w: "good" if v >= g else ("warn" if v >= w else "bad")  # noqa: E731
        rows = [
            live_row("얼굴 인식률", f"{s['face_presence']*100:.0f}%", lvl(s["face_presence"], .9, .7)),
            live_row("정면 응시 (최근)", f"{s['recent_eye_contact']*100:.0f}%", lvl(s["recent_eye_contact"], .7, .4)),
            live_row("정면 응시 (누적)", f"{s['eye_contact']*100:.0f}%", lvl(s["eye_contact"], .7, .5)),
            live_row("미소 비율", f"{s['smile_ratio']*100:.0f}%", "good" if 0.1 <= s["smile_ratio"] <= 0.6 else "warn"),
            live_row("눈 깜빡임", f"{s['blinks_per_min']:.0f}회/분", "good" if s["blinks_per_min"] <= 30 else "warn"),
            live_row("머리 움직임", f"{s['head_movement']:.2f}", "good" if s["head_movement"] <= 0.3 else "warn"),
        ]
        st.markdown("".join(rows), unsafe_allow_html=True)
        st.caption("수치는 MediaPipe 표정 계수로 추정한 연습용 지표입니다.")

    _panel()


def render_result(r: dict) -> None:
    sc, ev, tx, au = r["scores"], r["evaluation"], r["text"], r["audio"]
    st.markdown(f'<div class="bubble-name" style="text-align:right">나 · {r["attempt"]}번째 시도</div>'
                f'<div class="bubble me">{esc(r["transcript"])}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="bubble-name">AI 코치</div><div class="bubble">{esc(r["quick"])}</div>', unsafe_allow_html=True)

    delta = f" ({sc['total'] - r['prev_total']:+d})" if r.get("prev_total") is not None else ""
    chips = [chip("종합", f"{sc['total']}{delta}"), chip("내용", sc["content"]), chip("전달력", sc["delivery"]),
             chip("비언어", sc["nonverbal"] if sc["nonverbal"] is not None else "-"),
             chip("속도", f"{tx['pace']:.0f} {LANG['pace_unit']} · {tx['pace_label']}"),
             chip("간투사", f"{tx['filler_total']}회"), chip("시간", f"{au['duration_sec']:.0f}초")]
    if r["over_time"]:
        chips.append(f'<span class="badge bad">시간 초과 +{r["over_time"]}초</span>')
    st.markdown("".join(chips), unsafe_allow_html=True)

    with st.expander("상세 평가 보기", expanded=False):
        s = ev.get("scores", {})
        c = st.columns(4)
        for col, k in zip(c, ["logic", "specificity", "relevance", "structure"]):
            col.metric(LABELS[k], s.get(k, 0))
        star = ev.get("star", {})
        if star.get("applicable", True):
            st.markdown("**STAR 체크** " + " ".join(
                f'<span class="badge {"good" if star.get(k) else "gray"}">{"✓" if star.get(k) else "·"} {n}</span>'
                for k, n in [("situation", "상황"), ("task", "과제"), ("action", "행동"), ("result", "결과")]),
                unsafe_allow_html=True)
        st.markdown(f"**총평** {ev.get('summary', '')}")
        for title, key in [("👍 잘한 점", "strengths"), ("🛠 개선점", "improvements"), ("🔍 보강할 근거", "missing_evidence")]:
            if ev.get(key):
                st.markdown(f"**{title}**\n" + "\n".join(f"- {x}" for x in ev[key]))
        if tx["fillers"] or tx["habits"]:
            st.markdown("**습관어** " + "".join(chip(k, f"×{v}") for k, v in tx["fillers"].items())
                        + (" &nbsp;<span class='muted'>습관 표현 후보:</span> " + "".join(chip(k, f"×{v}") for k, v in tx["habits"].items()) if tx["habits"] else ""),
                        unsafe_allow_html=True)
        if r["voice"].get("notes"):
            st.markdown(f"**🎙 목소리·자신감 (추정 {r['voice']['score']}점)**\n" + "\n".join(f"- {x}" for x in r["voice"]["notes"]))
        if ev.get("improved_answer"):
            st.markdown("**✍️ 개선 답안 예시** — `[ ]`는 본인 경험으로 채울 부분")
            st.info(ev["improved_answer"])


def page_practice() -> None:
    header("📊 리포트 보기", PAGES[2])
    if not ss.questions:
        with st.container(key="card_empty"):
            st.markdown('<p class="sec-title">질문 세트가 없습니다</p>', unsafe_allow_html=True)
            st.caption("‘질문 준비’에서 질문을 만들거나, 기본 질문으로 바로 시작하세요.")
            if st.button("기본 질문으로 바로 시작", type="primary"):
                ss.questions = [{"question": q, "source": "기본 질문", "category": "공통", "tip": ""} for q in DEFAULT_QUESTIONS[LANG["code"]]]
                ss.q_idx = 0
                st.rerun()
        return

    ss.q_idx = min(ss.q_idx, len(ss.questions) - 1)
    q = ss.questions[ss.q_idx]
    left, right = st.columns([1.65, 1], gap="large")
    ctx = None

    with left, st.container(key="card_stage"):
        top = st.columns([3, 1], vertical_alignment="center")
        top[0].markdown(f'<div class="hdr-sub">Q {ss.q_idx + 1} / {len(ss.questions)} '
                        f'<span class="badge">{esc(q.get("source"))}</span>'
                        f'{"<span class=badge>" + esc(q["category"]) + "</span>" if q.get("category") else ""}</div>',
                        unsafe_allow_html=True)
        if ss.use_camera:
            err = prepare_face_model()
            if err:
                st.error(f"얼굴 인식 모델 다운로드 실패: {err}\n\nREADME의 '모델 수동 다운로드'를 참고하세요. 카메라 없이도 음성 연습은 가능합니다.")
            else:
                from streamlit_webrtc import WebRtcMode, webrtc_streamer
                from core.vision import InterviewVideoProcessor
                ctx = webrtc_streamer(
                    key="interview-cam", mode=WebRtcMode.SENDRECV,
                    video_processor_factory=InterviewVideoProcessor,
                    media_stream_constraints={"video": {"width": {"ideal": 960}, "height": {"ideal": 540}}, "audio": False},
                    rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
                    async_processing=True,
                    video_html_attrs={"style": {"width": "100%", "borderRadius": "14px"}, "autoPlay": True, "controls": False, "muted": True},
                    translations={"start": "📷 카메라 켜기", "stop": "카메라 끄기", "select_device": "카메라 선택",
                                  "device_ask_permission": "브라우저에서 카메라 권한을 허용해 주세요.",
                                  "device_access_denied": "카메라 권한이 거부되었습니다.",
                                  "device_not_available": "사용 가능한 카메라가 없습니다.",
                                  "media_api_not_available": "이 브라우저/주소에서는 카메라를 사용할 수 없습니다(localhost 또는 HTTPS 필요)."},
                )
        else:
            st.info("카메라 분석이 꺼져 있습니다. 사이드바에서 켤 수 있어요. (음성 연습은 그대로 가능)")

        tip = f'<div class="q-tip">💡 {esc(q["tip"])}</div>' if q.get("tip") else ""
        st.markdown(f'<div class="q-card"><div class="q-meta">면접관 질문</div><div class="q-text">{esc(q["question"])}</div>{tip}</div>',
                    unsafe_allow_html=True)

        b = st.columns([1.3, 1.2, 0.55, 0.55, 1.15])
        with b[0]:
            tts_button(q["question"], LANG["tts"])
        if b[1].button("▶ 답변 시작", width="stretch", type="primary", help="타이머와 비언어 지표를 0부터 다시 잽니다."):
            ss.answer_started_at = time.time()
            proc = getattr(ctx, "video_processor", None) if ctx else None
            if proc:
                proc.reset()
        if b[2].button("◀", width="stretch", disabled=ss.q_idx == 0, help="이전 질문"):
            ss.q_idx -= 1; ss.rec_nonce += 1; ss.answer_started_at = None; st.rerun()
        if b[3].button("▶", width="stretch", disabled=ss.q_idx >= len(ss.questions) - 1, help="다음 질문"):
            ss.q_idx += 1; ss.rec_nonce += 1; ss.answer_started_at = None; st.rerun()
        if b[4].button("⏹ 면접 종료", key="btn_danger_end", width="stretch"):
            go_to(PAGES[2])

        st.caption("① ▶ 답변 시작 → ② 🎙 마이크 버튼으로 녹음 → ③ 답변이 끝나면 정지 버튼. 정지하면 자동으로 분석됩니다.")
        audio = st.audio_input("🎙️ 답변 녹음", key=f"rec_{ss.q_idx}_{ss.rec_nonce}")

    with right:
        with st.container(key="card_live"):
            st.markdown('<p class="sec-title">실시간 코칭</p>', unsafe_allow_html=True)
            live_panel(ctx)
        fb = st.container(key="card_feedback")
        with fb:
            st.markdown('<p class="sec-title">AI 피드백</p>', unsafe_allow_html=True)

    if audio is not None:
        data = audio.getvalue()
        h = hashlib.md5(data).hexdigest()
        if h != ss.last_audio_hash:
            ss.last_audio_hash = h
            if not need_api():
                return
            process_answer(data, q, ctx, fb)
            return

    with fb:
        mine = [a for a in ss.answers if a["question"] == q["question"]]
        if not mine:
            st.markdown('<div class="muted">답변을 녹음하면 즉시 피드백과 점수가 여기에 표시됩니다.</div>', unsafe_allow_html=True)
            return
        r = mine[-1]
        render_result(r)
        fu = r["evaluation"].get("follow_up_question")
        if fu:
            st.markdown(f'<div class="bubble-name">예상 꼬리질문</div><div class="bubble">{esc(fu)}</div>', unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            if c1.button("↪ 꼬리질문 연습하기", width="stretch"):
                ss.questions.insert(ss.q_idx + 1, {"question": fu, "source": "꼬리질문", "category": "꼬리질문", "tip": ""})
                ss.q_idx += 1; ss.rec_nonce += 1; st.rerun()
            if c2.button("🔁 같은 질문 다시 답하기", width="stretch"):
                ss.rec_nonce += 1; st.rerun()


# ══════════════════════════════════════════════════════════════════════════
# 3. 리포트
# ══════════════════════════════════════════════════════════════════════════
def radar_chart(values: dict[str, float]) -> go.Figure:
    labels = [LABELS[k] for k in values]
    vals = list(values.values())
    fig = go.Figure(go.Scatterpolar(r=vals + vals[:1], theta=labels + labels[:1], fill="toself",
                                    line=dict(color=PRIMARY, width=2), fillcolor="rgba(21,112,201,0.18)", name="평균"))
    fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100], tickfont=dict(size=10), gridcolor="#E4E7EC"),
                                 angularaxis=dict(gridcolor="#E4E7EC")),
                      showlegend=False, margin=dict(l=80, r=80, t=30, b=30), height=380,
                      paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Pretendard, sans-serif", color="#1D2939"))
    return fig


def page_report() -> None:
    header("🎥 연습 계속하기", PAGES[1])
    ans = latest_answers()
    if not ans:
        st.info("아직 분석된 답변이 없습니다. 모의 면접에서 답변을 녹음해 보세요.")
        return
    n = len(ans)
    avg = lambda k: round(sum(a["scores"][k] or 0 for a in ans) / n)  # noqa: E731
    nv = [a["scores"]["nonverbal"] for a in ans if a["scores"]["nonverbal"] is not None]
    fpm = sum(a["text"]["filler_per_min"] for a in ans) / n
    k = st.columns(5)
    k[0].markdown(kpi("종합 점수", avg("total"), grade(avg("total"))), unsafe_allow_html=True)
    k[1].markdown(kpi("내용 (논리·구체·적합·구조)", avg("content"), "GPT 루브릭 평가"), unsafe_allow_html=True)
    k[2].markdown(kpi("전달력 (속도·습관어·음성)", avg("delivery"), "음성 신호 기반"), unsafe_allow_html=True)
    k[3].markdown(kpi("비언어 (시선·자세·표정)", round(sum(nv) / len(nv)) if nv else "-", "MediaPipe 기반"), unsafe_allow_html=True)
    k[4].markdown(kpi("간투사", f"{fpm:.1f}", "분당 평균 횟수"), unsafe_allow_html=True)
    st.write("")

    c1, c2 = st.columns([1, 1.2], gap="large")
    with c1, st.container(key="card_radar"):
        st.markdown('<p class="sec-title">역량 레이더</p>', unsafe_allow_html=True)
        keys = list(LABELS)
        radar = {key: sum(a["scores"]["radar"][key] for a in ans) / n for key in keys}
        if not nv:
            radar.pop("eye")
        st.plotly_chart(radar_chart(radar), width="stretch")
    with c2, st.container(key="card_overall"):
        st.markdown('<p class="sec-title">AI 종합 진단</p>', unsafe_allow_html=True)
        if st.button("종합 리포트 생성", type="primary") and need_api():
            with st.spinner("전체 답변을 종합하는 중…"):
                try:
                    ss.overall = ai.overall_report(profile(), ans)
                except Exception as e:
                    st.error(f"생성 실패: {e}")
        o = ss.overall
        if o:
            st.markdown(f'<div class="bubble" style="font-weight:700">{esc(o.get("headline", ""))}</div>', unsafe_allow_html=True)
            for title, key in [("강점", "strengths"), ("반복되는 약점", "patterns"), ("우선순위", "priorities"), ("다음 연습 계획", "practice_plan")]:
                if o.get(key):
                    st.markdown(f"**{title}**\n" + "\n".join(f"{i}. {x}" for i, x in enumerate(o[key], 1)))
        else:
            st.caption("답변 전체를 묶어 반복되는 패턴과 우선순위를 정리합니다.")

    with st.container(key="card_bars"):
        st.markdown('<p class="sec-title">질문별 점수</p>', unsafe_allow_html=True)
        names = [f"Q{i}" for i in range(1, n + 1)]
        fig = go.Figure()
        for key, label, color in [("content", "내용", PRIMARY), ("delivery", "전달력", "#59A8F0"), ("nonverbal", "비언어", "#A9CDF3")]:
            fig.add_bar(x=names, y=[a["scores"][key] or 0 for a in ans], name=label, marker_color=color)
        fig.add_scatter(x=names, y=[a["scores"]["total"] for a in ans], name="종합", mode="lines+markers",
                        line=dict(color="#E5372B", width=2))
        fig.update_layout(barmode="group", height=320, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(range=[0, 100]),
                          legend=dict(orientation="h", y=1.12), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(family="Pretendard, sans-serif"))
        st.plotly_chart(fig, width="stretch")

    st.markdown("#### 질문별 상세")
    for i, a in enumerate(ans, 1):
        with st.expander(f"Q{i}. {a['question']}  —  {a['scores']['total']}점"):
            render_result(a)

    md = build_markdown(profile(), ans, ss.overall, LANG["pace_unit"])
    c = st.columns(2)
    c[0].download_button("⬇️ 리포트 다운로드 (.md)", md, file_name="interview_report.md", mime="text/markdown", width="stretch")
    if c[1].button("💾 성장 기록에 저장", width="stretch"):
        rec = save_session(profile(), ans)
        st.success(f"저장했습니다 ({rec['date']}, 종합 {rec['total']}점).")


# ══════════════════════════════════════════════════════════════════════════
# 4. 성장 기록
# ══════════════════════════════════════════════════════════════════════════
def page_history() -> None:
    header()
    hist = load_history()
    if not hist:
        st.info("저장된 기록이 없습니다. 리포트 화면에서 ‘성장 기록에 저장’을 눌러 보세요.")
        return
    df = pd.DataFrame([{k: h.get(k) for k in ("date", "company", "role", "language", "count", "total", "content", "delivery", "nonverbal", "filler_per_min")} for h in hist])
    with st.container(key="card_trend"):
        st.markdown('<p class="sec-title">점수 추이</p>', unsafe_allow_html=True)
        fig = go.Figure()
        for key, label, color in [("total", "종합", "#E5372B"), ("content", "내용", PRIMARY), ("delivery", "전달력", "#59A8F0"), ("nonverbal", "비언어", "#A9CDF3")]:
            fig.add_scatter(x=df["date"], y=df[key], name=label, mode="lines+markers", line=dict(color=color, width=2))
        fig.update_layout(height=340, yaxis=dict(range=[0, 100]), margin=dict(l=10, r=10, t=10, b=10),
                          legend=dict(orientation="h", y=1.12), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(family="Pretendard, sans-serif"))
        st.plotly_chart(fig, width="stretch")
    st.dataframe(df.rename(columns={"date": "일시", "company": "회사", "role": "직무", "language": "언어", "count": "답변 수",
                                    "total": "종합", "content": "내용", "delivery": "전달력", "nonverbal": "비언어",
                                    "filler_per_min": "간투사/분"}), hide_index=True, width="stretch")
    for h in reversed(hist):
        with st.expander(f"{h['date']} · {h.get('company') or '-'} / {h.get('role') or '-'} · 종합 {h['total']}점"):
            for a in h["answers"]:
                st.markdown(f"**{a['question']}** — {a['scores']['total']}점  \n{a.get('summary', '')}")


# ── 라우팅 ───────────────────────────────────────────────────────────────────
{PAGES[0]: page_prepare, PAGES[1]: page_practice, PAGES[2]: page_report, PAGES[3]: page_history}[ss.page]()
