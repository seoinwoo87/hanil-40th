import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

# ==========================================
# 1. Gemini AI 설정 (Secrets 금고 사용)
# ==========================================
try:
    # 클라우드 배포 시 Secrets에서 API 키를 가져옵니다.
    GOOGLE_API_KEY = st.secrets["gemini_api_key"]
    genai.configure(api_key=GOOGLE_API_KEY)
    
    valid_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    target_model = next((m for m in ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-pro'] if m in valid_models), valid_models[0] if valid_models else None)
    model = genai.GenerativeModel(target_model) if target_model else None
except Exception as e:
    st.error(f"AI 설정 오류 (Secrets 설정을 확인해주세요): {e}")
    model = None

# ==========================================
# 2. 페이지 설정 및 모던 UI 디자인
# ==========================================
st.set_page_config(page_title="한일고 40기 통합 상담 시스템", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@400;600;800&display=swap');
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif; background-color: #F8FAFC; }
    
    .stMetric { background: white; border: 1px solid #E2E8F0; padding: 20px !important; border-radius: 12px !important; }
    .timeline-container { border-left: 4px solid #DBEAFE; padding-left: 25px; margin-left: 15px; position: relative; }
    .timeline-item { position: relative; margin-bottom: 30px; }
    .timeline-node { position: absolute; width: 18px; height: 18px; background: #2563EB; border-radius: 50%; left: -34px; top: 5px; border: 3px solid #F8FAFC; }
    .timeline-card { background: white; border: 1px solid #E2E8F0; border-radius: 15px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.02); }
    .badge { display: inline-block; padding: 3px 10px; border-radius: 15px; font-size: 0.8rem; font-weight: 700; margin-right: 5px; background: #EFF6FF; color: #1D4ED8; }
    .reflection-card { background: white; border: 1px solid #E2E8F0; border-radius: 12px; padding: 24px; margin-bottom: 16px; border-left: 6px solid #2563EB; }
    .ai-container { background: linear-gradient(135deg, #F0F9FF 0%, #E0F2FE 100%); border: 1px solid #BAE6FD; border-radius: 12px; padding: 20px; margin-top: 10px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 데이터 로드 (Secrets 금고에서 구글 열쇠 사용)
# ==========================================
@st.cache_resource
def load_all_data():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    try:
        # [핵심 수정] Secrets 객체를 완벽한 파이썬 딕셔너리로 강제 변환합니다.
        creds_info = dict(st.secrets["gcp_service_account"])
      creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        client = gspread.authorize(creds)
        doc = client.open("40기 마스터 파일")
    except Exception as e:
        # 연결에 실패하면 뭉뚱그리지 않고, "정확히 뭐 때문에 실패했는지" 화면에 출력합니다.
        st.error(f"🚨 구글 시트 연결 실패 상세 원인: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    
    def get_safe_df(sheet_name):
        try:
            sheet = doc.worksheet(sheet_name)
            data = sheet.get_all_values()
            if not data: return pd.DataFrame()
            header = [h.strip() for h in data[0]]
            clean_header = []
            counts = {}
            for h in header:
                if h == "" or h in clean_header:
                    counts[h] = counts.get(h, 0) + 1
                    clean_header.append(f"{h}_idx_{counts[h]}")
                else: clean_header.append(h)
            df = pd.DataFrame(data[1:], columns=clean_header)
            
            # 고유 식별자 생성
            name_col = next((c for c in ['이름', '성명'] if c in df.columns), None)
            if name_col and '학번' in df.columns:
                df['학번_정제'] = df['학번'].astype(str).str.replace('.0', '', regex=False).str.strip()
                df['식별'] = df['학번_정제'] + " " + df[name_col].astype(str).str.strip()
            return df
        except: return pd.DataFrame()

    return get_safe_df("31_내신"), get_safe_df("21_모의고사"), get_safe_df("51_시험복기"), get_safe_df("61_비교과")

df_scores, df_mock, df_reflection, df_activity = load_all_data()

# 에러 메시지를 더 구체적으로 띄우도록 수정
if df_scores.empty and df_mock.empty:
    st.warning("데이터가 비어있거나 불러오기에 실패했습니다. 위 🚨상세 원인🚨을 확인해주세요.")
    st.stop()

for df in [df_scores, df_mock]:
    for col in df.columns:
        if any(k in col for k in ['점수', '등급', '백분위', '표점']):
            df[col] = pd.to_numeric(df[col], errors='coerce')

# ==========================================
# 4. 사이드바 및 필터
# ==========================================
with st.sidebar:
    st.title("🏫 한일고 상담실")
    if not df_scores.empty:
        term = st.selectbox("📅 학기 선택", sorted(df_scores['학기'].unique(), reverse=True))
        term_df = df_scores[df_scores['학기'] == term]
        student_list = sorted(term_df['식별'].unique())
        selected_student_id = st.selectbox("👤 학생 선택", student_list)
        selected_name = selected_student_id.split(" ", 1)[-1]
        
        st.markdown("---")
        view_mode = st.radio("📑 분석 메뉴", ["📈 내신 성적", "🎯 모의고사", "🧠 성찰 리포트", "🏆 비교과 타임라인"])
    else: st.warning("데이터가 없습니다.")

st.title(f"{selected_student_id} 리포트")

# ==========================================
# 5. 각 메뉴별 시각화 로직
# ==========================================
if view_mode == "📈 내신 성적":
    exam = st.selectbox("시험 선택", ["1회고사", "2회고사", "학기말"])
    exam_df = df_scores[(df_scores['학기'] == term) & (df_scores['식별'] == selected_student_id) & (df_scores['시험'] == exam)]
    
    if not exam_df.empty and exam != "학기말":
        plot_data = []
        for _, row in exam_df.iterrows():
            all_scores = df_scores[(df_scores['학기'] == term) & (df_scores['시험'] == exam) & (df_scores['과목'] == row['과목'])]['점수']
            rank = (all_scores > row['점수']).sum() + 1
            standard_pct = round(100 - ((rank / len(all_scores)) * 100), 1)
            median_score = round(all_scores.median(), 1)
            plot_data.append({'과목': row['과목'], '점수': row['점수'], '백분위': standard_pct, '중위값': median_score})
        
        pdf = pd.DataFrame(plot_data)
        fig = go.Figure()
        fig.add_trace(go.Bar(x=pdf['과목'], y=pdf['점수'], name="원점수", marker_color=px.colors.qualitative.Pastel, text=pdf['점수'], textposition='auto'))
        fig.add_trace(go.Scatter(x=pdf['과목'], y=pdf['중위값'], name="중위값", mode='lines+markers', line=dict(color='#10B981', dash='dash')))
        fig.add_trace(go.Scatter(x=pdf['과목'], y=pdf['백분위'], name="백분위(%)", yaxis='y2', mode='lines+markers+text', text=pdf['백분위'].apply(lambda x: f"{x}%"), line=dict(color='#EF4444', width=3)))
        
        fig.update_layout(
            yaxis=dict(title="원점수", range=[0, 110]),
            yaxis2=dict(title="백분위(%) - 높을수록 우수", overlaying='y', side='right', range=[0, 100], dtick=10),
            legend=dict(orientation="h", y=1.2), plot_bgcolor='white'
        )
        st.plotly_chart(fig, use_container_width=True)
    elif exam == "학기말":
        cols = st.columns(len(exam_df))
        for i, (_, r) in enumerate(exam_df.iterrows()): cols[i].metric(r['과목'], f"{int(r['등급'])}등급")

elif view_mode == "🎯 모의고사":
    m_sub = df_mock[df_mock['식별'] == selected_student_id].copy()
    if not m_sub.empty:
        latest = m_sub.iloc[-1]
        st.subheader(f"📊 {latest['시험명']} 결과")
        cols = st.columns(4)
        subjects = [("국어", "국어_등급", "국어_표점", "국어_백분위"), ("수학", "수학_등급", "수학_표점", "수학_백분위"), ("영어", "영어_등급", None, None), ("한국사", "한국사_등급", None, None)]
        for i, (label, g, p, b) in enumerate(subjects):
            with cols[i]:
                grade = latest.get(g, '-')
                st.markdown(f"""<div style="text-align:center; padding:15px; border:1px solid #eee; border-radius:10px; background:white;"><b>{label}</b><br><span style="font-size:1.5rem; color:#2563EB;">{grade}등급</span></div>""", unsafe_allow_html=True)
        st.dataframe(m_sub.set_index('시험명'), use_container_width=True)

elif view_mode == "🧠 성찰 리포트":
    s_ref = df_reflection[df_reflection['식별'] == selected_student_id].copy()
    if not s_ref.empty:
        exam_sel = st.selectbox("시험 선택", s_ref['시험명'].unique())
        s_data = s_ref[s_ref['시험명'] == exam_sel].iloc[-1]
        cols = st.columns(2)
        idx = 0
        for k, v in s_data.items():
            if k in ['시험명', '타임스탬프', '학번', '이름', '성명', '식별', '학번_정제'] or "idx" in k: continue
            with cols[idx % 2]: st.markdown(f"""<div class="reflection-card"><b style="color:#2563EB;">{k}</b><br>{v}</div>""", unsafe_allow_html=True)
            idx += 1
            
        st.markdown("---")
        # [복구 완료] 성찰 리포트 AI 분석 버튼 로직
        if st.button("🤖 AI 맞춤형 솔루션 생성하기"):
            if model is None:
                st.error("❌ 사용 가능한 AI 모델을 찾을 수 없습니다. (API 키 확인 필요)")
            else:
                with st.spinner(f'선생님의 관점으로 학생의 고민을 읽고 있습니다... (모델: {target_model})'):
                    try:
                        ref_sum = "\n".join([f"Q: {k}\nA: {v}" for k, v in s_data.items() if len(str(v)) > 5 and "idx" not in k and k not in ['학번_정제', '식별', '타임스탬프']])
                        system_prompt = f"당신은 한일고등학교 상담교사입니다. {selected_name} 학생의 성찰 답변을 바탕으로, 부족한 점에 공감하며 실질적인 학습 전략을 400자 이내로 따뜻하게 조언해주세요.\n\n[학생의 성찰 내용]\n{ref_sum}"
                        response = model.generate_content(system_prompt)
                        st.markdown(f"""<div class="ai-container"><h3 style="margin-top:0; color:#1E3A8A;">🤖 AI 전담교사의 분석 리포트</h3><div style="white-space:pre-wrap;">{response.text}</div></div>""", unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"AI 호출 오류: {e}")

elif view_mode == "🏆 비교과 타임라인":
    if not df_activity.empty and '식별' in df_activity.columns:
        my_act = df_activity[df_activity['식별'] == selected_student_id].sort_values(by='활동 일자', ascending=False)
        if not my_act.empty:
            st.markdown('<div class="timeline-container">', unsafe_allow_html=True)
            for idx, row in my_act.iterrows():
                st.markdown(f"""
                <div class="timeline-item">
                    <div class="timeline-node"></div>
                    <div class="timeline-card">
                        <span style="color:#64748B; font-size:0.9rem;">📅 {row.get('활동 일자','')} | {row.get('활동의 성격','')}</span>
                        <div style="font-size:1.2rem; font-weight:800; margin:10px 0;">{row.get('활동 주제','')}</div>
                        <div style="margin-bottom:10px;"><span class="badge">#{row.get('핵심 역량 선택(최대 2개 선택)','')}</span></div>
                        <div style="background:#F8FAFC; padding:15px; border-radius:10px; font-size:0.95rem;">
                            <b>활동 내용:</b> {row.get('핵심 활동 내용(무엇을 어떻게 했나요)','')}<br>
                            <b>성찰:</b> {row.get('결과 및 배우고 느낀 점(어떤 변화가 있었나요?)','')}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"🤖 AI 생기부 문구 생성 (기록 {idx})"):
                    if model is None:
                        st.error("❌ 사용 가능한 AI 모델을 찾을 수 없습니다.")
                    else:
                        with st.spinner('생기부 초안을 작성 중입니다...'):
                            prompt = f"한일고 교사로서 다음 활동을 바탕으로 생기부 세특 문구를 작성해줘. 주어는 생략할 것. 주제: {row.get('활동 주제','')}, 내용: {row.get('핵심 활동 내용','')}, 결과: {row.get('결과 및 배우고 느낀 점','')}"
                            st.markdown(f'<div class="ai-container"><b>📝 AI 추천 생기부 초안</b><br>{model.generate_content(prompt).text}</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("해당 학생의 비교과 활동 기록이 아직 없습니다.")
