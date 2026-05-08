import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 1. Gemini AI 설정
# ==========================================
try:
    GOOGLE_API_KEY = st.secrets["gemini_api_key"]
    genai.configure(api_key=GOOGLE_API_KEY)
    valid_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    target_model = next((m for m in ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-pro'] if m in valid_models), valid_models[0] if valid_models else None)
    model = genai.GenerativeModel(target_model) if target_model else None
except Exception as e:
    st.error(f"AI 설정 오류: {e}")
    model = None

# ==========================================
# 2. 페이지 설정 및 UI 디자인
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
# 3. 데이터 로드 (Secrets 금고)
# ==========================================
@st.cache_resource
def load_all_data():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds_info = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        client = gspread.authorize(creds)
        doc = client.open("40기 마스터 파일")
        
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
                name_col = next((c for c in ['이름', '성명'] if c in df.columns), None)
                if name_col and '학번' in df.columns:
                    df['학번_정제'] = df['학번'].astype(str).str.replace('.0', '', regex=False).str.strip()
                    df['식별'] = df['학번_정제'] + " " + df[name_col].astype(str).str.strip()
                return df
            except: return pd.DataFrame()

        return get_safe_df("31_내신"), get_safe_df("21_모의고사"), get_safe_df("51_시험복기"), get_safe_df("61_비교과")
    except Exception as e:
        st.error(f"🚨 연결 실패: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_scores, df_mock, df_reflection, df_activity = load_all_data()

if df_scores.empty and df_mock.empty:
    st.warning("데이터를 불러오는 중입니다...")
    st.stop()

# 숫자형 데이터 변환
for df in [df_scores, df_mock]:
    if not df.empty:
        for col in df.columns:
            if any(k in col for k in ['점수', '등급', '백분위', '표점']):
                df[col] = pd.to_numeric(df[col], errors='coerce')

# ==========================================
# 4. 사이드바 및 필터
# ==========================================
with st.sidebar:
    st.title("🏫 한일고 상담실")
    term = st.selectbox("📅 학기 선택", sorted(df_scores['학기'].unique(), reverse=True))
    term_df = df_scores[df_scores['학기'] == term]
    student_list = sorted(term_df['식별'].unique())
    selected_student_id = st.selectbox("👤 학생 선택", student_list)
    selected_name = selected_student_id.split(" ", 1)[-1]
    st.markdown("---")
    view_mode = st.radio("📑 분석 메뉴", ["📈 내신 성적", "🎯 모의고사", "🧠 성찰 리포트", "🏆 비교과 타임라인"])

st.title(f"{selected_student_id} 리포트")

# ==========================================
# 5. 내신 성적 (추이 그래프 복구)
# ==========================================
if view_mode == "📈 내신 성적":
    t1, t2 = st.tabs(["📊 시험별 현황 (이중축)", "📈 과목별 성적 추이"])
    with t1:
        exam = st.selectbox("시험 선택", ["1회고사", "2회고사", "학기말"])
        exam_df = df_scores[(df_scores['학기'] == term) & (df_scores['식별'] == selected_student_id) & (df_scores['시험'] == exam)]
        if not exam_df.empty and exam != "학기말":
            plot_data = []
            for _, row in exam_df.iterrows():
                all_s = df_scores[(df_scores['학기'] == term) & (df_scores['시험'] == exam) & (df_scores['과목'] == row['과목'])]['점수']
                rank = (all_s > row['점수']).sum() + 1
                standard_pct = round(100 - ((rank / len(all_s)) * 100), 1)
                median_s = round(all_s.median(), 1)
                plot_data.append({'과목': row['과목'], '점수': row['점수'], '백분위': standard_pct, '중위값': median_s})
            pdf = pd.DataFrame(plot_data)
            fig = go.Figure()
            fig.add_trace(go.Bar(x=pdf['과목'], y=pdf['점수'], name="내 점수", marker_color=px.colors.qualitative.Pastel, text=pdf['점수'], textposition='auto'))
            fig.add_trace(go.Scatter(x=pdf['과목'], y=pdf['중위값'], name="중위값", mode='lines+markers', line=dict(color='#10B981', dash='dash')))
            fig.add_trace(go.Scatter(x=pdf['과목'], y=pdf['백분위'], name="백분위(%)", yaxis='y2', mode='lines+markers+text', text=pdf['백분위'].apply(lambda x: f"{x}%"), line=dict(color='#EF4444', width=3)))
            fig.update_layout(yaxis=dict(title="원점수", range=[0, 110]), yaxis2=dict(title="백분위(%)", overlaying='y', side='right', range=[0, 100], dtick=10), legend=dict(orientation="h", y=1.2), plot_bgcolor='white')
            st.plotly_chart(fig, use_container_width=True)
        elif exam == "학기말":
            cols = st.columns(len(exam_df))
            for i, (_, r) in enumerate(exam_df.iterrows()): cols[i].metric(r['과목'], f"{int(r['등급'])}등급")
    with t2:
        # [추이 그래프 복구]
        sub_list = sorted(df_scores[df_scores['식별'] == selected_student_id]['과목'].unique())
        sel_sub = st.selectbox("과목 선택", sub_list)
        sub_trend = df_scores[(df_scores['식별'] == selected_student_id) & (df_scores['과목'] == sel_sub)].copy()
        sub_trend['order'] = sub_trend['시험'].map({'1회고사':1, '2회고사':2, '학기말':3})
        st.plotly_chart(px.line(sub_trend.sort_values('order'), x='시험', y='점수', markers=True, text='점수', title=f"[{sel_sub}] 성적 추이"), use_container_width=True)

# ==========================================
# 6. 모의고사 (추이 그래프 복구)
# ==========================================
elif view_mode == "🎯 모의고사":
    m_sub = df_mock[df_mock['식별'] == selected_student_id].copy()
    if not m_sub.empty:
        latest = m_sub.iloc[-1]
        st.subheader(f"📊 {latest['시험명']} 결과")
        cols = st.columns(4)
        m_items = [("국어", "국어_등급", "국어_표점", "국어_백분위"), ("수학", "수학_등급", "수학_표점", "수학_백분위"), ("영어", "영어_등급", None, None), ("한국사", "한국사_등급", None, None)]
        for i, (label, g, p, b) in enumerate(m_items):
            with cols[i]:
                st.markdown(f"""<div style="text-align:center; padding:15px; border:1px solid #eee; border-radius:10px; background:white;"><b>{label}</b><br><span style="font-size:1.5rem; color:#2563EB;">{latest.get(g,'-')}등급</span></div>""", unsafe_allow_html=True)
        
        # [모의고사 그래프 복구]
        st.write("")
        plot_m = m_sub.rename(columns={'국어_백분위':'국어','수학_백분위':'수학','사회탐구_백분위':'사탐','과학탐구_백분위':'과탐'})
        target_cols = [c for c in ['국어','수학','사탐','과탐'] if c in plot_m.columns]
        fig_m = px.line(plot_m, x='시험명', y=target_cols, markers=True, title="주요 과목 백분위 추이")
        fig_m.update_layout(yaxis=dict(title="백분위(%)", range=[0, 105]), plot_bgcolor="white")
        st.plotly_chart(fig_m, use_container_width=True)
        st.dataframe(m_sub.set_index('시험명'), use_container_width=True)

# ==========================================
# 7. 성찰 리포트 (AI 버튼 복구)
# ==========================================
elif view_mode == "🧠 성찰 리포트":
    s_ref = df_reflection[df_reflection['식별'] == selected_student_id].copy()
    if not s_ref.empty:
        exam_sel = st.selectbox("성찰 시험 선택", s_ref['시험명'].unique())
        s_data = s_ref[s_ref['시험명'] == exam_sel].iloc[-1]
        cols = st.columns(2)
        idx = 0
        for k, v in s_data.items():
            if k in ['시험명', '타임스탬프', '학번', '이름', '성명', '식별', '학번_정제'] or "idx" in k: continue
            with cols[idx % 2]: st.markdown(f"""<div class="reflection-card"><b style="color:#2563EB;">{k}</b><br>{v}</div>""", unsafe_allow_html=True)
            idx += 1
        st.markdown("---")
        if st.button("🤖 AI 맞춤형 솔루션 생성하기"):
            with st.spinner('선생님의 관점으로 분석 중입니다...'):
                ref_txt = "\n".join([f"Q: {k}\nA: {v}" for k, v in s_data.items() if len(str(v)) > 5 and k not in ['학번_정제', '식별', '타임스탬프']])
                prompt = f"{selected_name} 학생의 성찰 답변입니다. 상담교사로서 따뜻한 격려와 학습 전략을 조언해줘.\n\n{ref_txt}"
                st.markdown(f"""<div class="ai-container"><b>🤖 AI 전담교사의 분석 리포트</b><br>{model.generate_content(prompt).text}</div>""", unsafe_allow_html=True)
# 이 코드를 추가해서 데이터가 어떻게 읽히는지 확인합니다.
with st.expander("데이터 진단 도구 (클릭해서 확인)"):
    st.write("비교과 시트 전체 행 개수:", len(df_activity))
    st.write("비교과 시트의 열 이름들:", df_activity.columns.tolist())
    if not df_activity.empty:
        st.write("시트의 첫 번째 학생 식별값:", df_activity['식별'].iloc[0] if '식별' in df_activity.columns else "식별 열 없음")
    st.write("현재 선택된 학생 식별값:", selected_student_id)
# ==========================================
# 8. 비교과 타임라인 (디버깅 모드 추가)
# ==========================================
elif view_mode == "🏆 비교과 타임라인":
    if df_activity.empty:
        st.error("⚠️ 비교과 데이터(61_비교과 탭)를 전혀 불러오지 못했습니다. 탭 이름을 확인해주세요.")
    else:
        # 데이터가 있는지 확인하기 위해 상위 3개만 살짝 찍어보기 (나중에 지우셔도 됩니다)
        # st.write("불러온 데이터 미리보기:", df_activity.head(3)) 

        # 필터링 시작
        my_act = df_activity[df_activity['식별'] == selected_student_id].sort_values(by='활동 일자', ascending=False)
        
        if my_act.empty:
            st.warning(f"🔔 {selected_student_id} 학생의 기록이 '61_비교과' 시트에 없습니다.")
            st.info("""
            **확인해보세요:**
            1. 시트의 '학번' 열에 **1514**가 정확히 적혀 있나요?
            2. 시트의 '성명' 혹은 '이름' 열에 **심승민**이 정확히 적혀 있나요?
            3. 혹시 학번에 소수점(1514.0)이 붙어 있지는 않나요?
            """)
        else:
            st.markdown('<div class="timeline-container">', unsafe_allow_html=True)
            for idx, row in my_act.iterrows():
                # 열 이름이 길어서 생기는 문제를 방지하기 위해 안전하게 가져오기
                act_date = row.get('활동 일자', '날짜 없음')
                act_type = row.get('활동의 성격', '구분 없음')
                act_title = row.get('활동 주제', '주제 없음')
                act_cap = row.get('핵심 역량 선택(최대 2개 선택)', '')
                act_content = row.get('핵심 활동 내용(무엇을 어떻게 했나요)', '')
                act_ref = row.get('결과 및 배우고 느낀 점(어떤 변화가 있었나요?)', '')

                st.markdown(f"""<div class="timeline-item"><div class="timeline-node"></div><div class="timeline-card">
                    <span style="color:#64748B; font-size:0.9rem;">📅 {act_date} | {act_type}</span>
                    <div style="font-size:1.2rem; font-weight:800; margin:10px 0;">{act_title}</div>
                    <div style="margin-bottom:10px;"><span class="badge">#{act_cap}</span></div>
                    <div style="background:#F8FAFC; padding:15px; border-radius:10px; font-size:0.95rem;">
                        <b>내용:</b> {act_content}<br>
                        <b>성찰:</b> {act_ref}
                    </div></div></div>""", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
