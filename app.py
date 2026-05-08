import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 1. 페이지 기본 설정 (가장 먼저 실행되어야 함)
# ==========================================
st.set_page_config(page_title="한일고 40기 통합 상담 시스템", layout="wide")

# 모던 UI 디자인 (CSS)
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
# 2. Gemini AI 및 데이터 로드 설정
# ==========================================
try:
    GOOGLE_API_KEY = st.secrets["gemini_api_key"]
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error(f"AI 설정 오류: {e}")
    model = None

@st.cache_resource
def load_all_data():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds_info = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        client = gspread.authorize(creds)
        doc = client.open("40기 마스터 파일")
        
        ddef get_df(sheet_name):
    try:
        sh = doc.worksheet(sheet_name)
        data = sh.get_all_values()
        df = pd.DataFrame(data[1:], columns=data[0])
        
        # 학번 열이 있다면, 공백 제거하고 무조건 문자열로 변환
        if '학번' in df.columns:
            df['학번'] = df['학번'].astype(str).str.split('.').str[0].str.strip()
            
        # 성명/이름 열 처리
        name_col = '성명' if '성명' in df.columns else '이름'
        if '학번' in df.columns and name_col in df.columns:
            df['성명_정제'] = df[name_col].astype(str).str.strip()
            df['식별'] = df['학번'] + " " + df['성명_정제']
        return df
    except: return pd.DataFrame()

        return get_df("31_내신"), get_df("21_모의고사"), get_df("51_시험복기"), get_df("61_비교과")
    except Exception as e:
        st.error(f"데이터 연결 실패: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_scores, df_mock, df_reflection, df_activity = load_all_data()

# 숫자 변환
for df in [df_scores, df_mock]:
    if not df.empty:
        for col in df.columns:
            if any(k in col for k in ['점수', '등급', '백분위', '표점']):
                df[col] = pd.to_numeric(df[col], errors='coerce')

# ==========================================
# 3. 사이드바 (메뉴 선택)
# ==========================================
with st.sidebar:
    st.title("🏫 한일고 40기 상담")
    if not df_scores.empty:
        all_terms = sorted(df_scores['학기'].unique(), reverse=True)
        term = st.selectbox("📅 학기 선택", all_terms)
        
        # 선택 학기 학생 목록
        term_students = sorted(df_scores[df_scores['학기'] == term]['식별'].unique())
        selected_student = st.selectbox("👤 학생 선택", term_students)
        selected_name = selected_student.split(" ")[-1]
        
        st.markdown("---")
        # 이모지를 제거한 순수 텍스트로 메뉴 구성 (오류 방지)
        menu = st.radio("📑 분석 메뉴", ["내신 성적", "모의고사", "성찰 리포트", "비교과 타임라인"])
    else:
        st.error("시트 데이터를 읽지 못했습니다.")
        st.stop()

st.header(f"{selected_student} 리포트")

# ==========================================
# 4. 내신 성적 섹션
# ==========================================
if menu == "내신 성적":
    tab1, tab2 = st.tabs(["📊 시험별 현황", "📈 성적 추이"])
    
    with tab1:
        exam = st.selectbox("시험 선택", ["1회고사", "2회고사", "학기말"])
        exam_df = df_scores[(df_scores['학기'] == term) & (df_scores['식별'] == selected_student) & (df_scores['시험'] == exam)]
        
        if not exam_df.empty:
            if exam == "학기말":
                cols = st.columns(len(exam_df))
                for i, (_, r) in enumerate(exam_df.iterrows()):
                    cols[i].metric(r['과목'], f"{int(r['등급']) if pd.notnull(r['등급']) else '-'}등급")
            else:
                plot_data = []
                for _, row in exam_df.iterrows():
                    all_s = df_scores[(df_scores['학기'] == term) & (df_scores['시험'] == exam) & (df_scores['과목'] == row['과목'])]['점수'].dropna()
                    rank = (all_s > row['점수']).sum() + 1
                    pct = round(100 - ((rank / len(all_s)) * 100), 1) if len(all_s) > 0 else 0
                    plot_data.append({'과목': row['과목'], '점수': row['점수'], '백분위': pct, '중위값': all_s.median()})
                
                pdf = pd.DataFrame(plot_data)
                fig = go.Figure()
                fig.add_trace(go.Bar(x=pdf['과목'], y=pdf['점수'], name="내 점수", marker_color="#3B82F6"))
                fig.add_trace(go.Scatter(x=pdf['과목'], y=pdf['중위값'], name="중위값", mode='lines+markers', line=dict(color='#10B981', dash='dash')))
                fig.add_trace(go.Scatter(x=pdf['과목'], y=pdf['백분위'], name="백분위(%)", yaxis='y2', mode='lines+markers+text', text=pdf['백분위'].apply(lambda x: f"{x}%"), line=dict(color='#EF4444')))
                fig.update_layout(yaxis=dict(title="원점수", range=[0, 105]), yaxis2=dict(title="백분위", overlaying='y', side='right', range=[0, 100]), legend=dict(orientation="h", y=1.1))
                st.plotly_chart(fig, use_container_width=True)
        else: st.info("해당 시험 데이터가 없습니다.")

    with tab2:
        sub_list = sorted(df_scores[df_scores['식별'] == selected_student]['과목'].unique())
        sel_sub = st.selectbox("과목 선택", sub_list)
        trend = df_scores[(df_scores['식별'] == selected_student) & (df_scores['과목'] == sel_sub)].copy()
        trend['ord'] = trend['시험'].map({'1회고사':1, '2회고사':2, '학기말':3})
        fig_t = px.line(trend.sort_values('ord'), x='시험', y='점수', markers=True, text='점수')
        st.plotly_chart(fig_t, use_container_width=True)

# ==========================================
# 5. 모의고사 섹션
# ==========================================
elif menu == "모의고사":
    m_sub = df_mock[df_mock['식별'] == selected_student].copy()
    if not m_sub.empty:
        latest = m_sub.iloc[-1]
        st.subheader(f"🎯 {latest['시험명']} 주요 지표")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("국어 등급", f"{latest.get('국어_등급','-')}급")
        c2.metric("수학 등급", f"{latest.get('수학_등급','-')}급")
        c3.metric("영어 등급", f"{latest.get('영어_등급','-')}급")
        c4.metric("탐구1 등급", f"{latest.get('사회탐구_등급','-') if pd.notnull(latest.get('사회탐구_등급')) else latest.get('과학탐구_등급','-')}급")
        
        st.markdown("---")
        # 백분위 추이 그래프
        m_sub = m_sub.rename(columns={'국어_백분위':'국어','수학_백분위':'수학','사회탐구_백분위':'사탐','과학탐구_백분위':'과탐'})
        target = [c for c in ['국어','수학','사탐','과탐'] if c in m_sub.columns]
        fig_m = px.line(m_sub, x='시험명', y=target, markers=True, title="주요 과목 백분위 추이")
        fig_m.update_layout(yaxis=dict(range=[0, 105]))
        st.plotly_chart(fig_m, use_container_width=True)
    else: st.info("모의고사 기록이 없습니다.")

# ==========================================
# 6. 성찰 리포트 섹션
# ==========================================
elif menu == "성찰 리포트":
    s_ref = df_reflection[df_reflection['식별'] == selected_student].copy()
    if not s_ref.empty:
        sel_exam = st.selectbox("성찰 대상 시험", s_ref['시험명'].unique())
        row = s_ref[s_ref['시험명'] == sel_exam].iloc[-1]
        cols = st.columns(2)
        i = 0
        for k, v in row.items():
            if k in ['시험명','타임스탬프','학번','이름','성명','성명_정제','식별'] or not v: continue
            with cols[i%2]:
                st.markdown(f'<div class="reflection-card"><b>{k}</b><br>{v}</div>', unsafe_allow_html=True)
            i += 1
        
        if st.button("🤖 AI 상담사 조언 듣기"):
            with st.spinner("분석 중..."):
                txt = "\n".join([f"{k}: {v}" for k, v in row.items() if len(str(v)) > 5 and k not in ['타임스탬프', '식별']])
                res = model.generate_content(f"한일고 상담교사로서 다음 학생 성찰을 읽고 따뜻한 조언을 해줘:\n{txt}")
                st.markdown(f'<div class="ai-container"><b>🤖 AI 조언</b><br>{res.text}</div>', unsafe_allow_html=True)
    else: st.info("작성된 성찰 리포트가 없습니다.")

# ==========================================
# 7. 비교과 타임라인 (데이터 형식 강제 통합 버전)
# ==========================================
elif menu == "비교과 타임라인":
    st.subheader("🏆 누적 비교과 활동")
    
    if df_activity.empty:
        st.error("🚨 '61_비교과' 시트에서 데이터를 하나도 읽어오지 못했습니다. 시트 이름을 확인해주세요.")
    else:
        # [핵심 수정] 비교과 시트의 학번 형식을 내신 데이터와 강제로 맞춥니다.
        df_activity['학번_체크'] = df_activity['학번'].astype(str).str.replace('.0', '', regex=False).str.strip()
        
        # 선택된 학생의 학번만 추출 (예: "1514 심승민" -> "1514")
        target_student_num = selected_student.split(" ")[0]
        
        # 학번으로만 필터링 (가장 확실한 방법)
        my_act = df_activity[df_activity['학번_체크'] == target_student_num].copy()
        
        if my_act.empty:
            st.warning(f"🔎 {selected_student} 학생의 학번({target_student_num})과 일치하는 기록이 없습니다.")
            # 진단용 출력
            with st.expander("🛠️ 데이터가 왜 안 보이나요? (진단 클릭)"):
                st.write("1. 내 앱이 찾는 학번:", f"[{target_student_num}]")
                if not df_activity.empty:
                    st.write("2. 시트에 실제 저장된 학번 예시:", f"[{df_activity['학번_체크'].iloc[0]}]")
                st.info("두 번호의 모양이 다르면 시트에서 학번을 '일반 텍스트'로 수정해야 합니다.")
        else:
            # 날짜순 정렬 (에러 방지를 위해 에러 무시 설정)
            try:
                my_act = my_act.sort_values(by='활동 일자', ascending=False)
            except:
                pass

            st.markdown('<div class="timeline-container">', unsafe_allow_html=True)
            for idx, row in my_act.iterrows():
                # 열 이름을 못 찾아도 멈추지 않게 기본값 처리
                d = row.get('활동 일자', '-')
                k = row.get('활동의 성격', '-')
                t = row.get('활동 주제', '제목 없음')
                m = row.get('활동 동기(왜 시작했나요)', '')
                c = row.get('핵심 활동 내용(무엇을 어떻게 했나요)', '')
                f = row.get('결과 및 배우고 느낀 점(어떤 변화가 있었나요?)', '')
                a = row.get('핵심 역량 선택(최대 2개 선택)', '')
                s = row.get('연계 가능 교과(선택)', '')

                st.markdown(f"""
                <div class="timeline-item">
                    <div class="timeline-node"></div>
                    <div class="timeline-card">
                        <span style="color:#64748B; font-size:0.85rem;">📅 {d} | {k} | {s}</span>
                        <div style="font-size:1.15rem; font-weight:800; margin:8px 0; color:#1E40AF;">{t}</div>
                        <div style="margin-bottom:10px;"><span class="badge">#{a}</span></div>
                        <div style="background:#F8FAFC; padding:18px; border-radius:12px; font-size:0.92rem; line-height:1.6; border: 1px solid #E2E8F0;">
                            <div style="margin-bottom:8px;"><b>💡 동기:</b> {m}</div>
                            <div style="margin-bottom:8px;"><b>📝 활동 내용:</b><br>{c}</div>
                            <div style="margin:0;"><b>🌱 변화와 성장:</b><br>{f}</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # 버튼 고유 ID 부여로 충돌 방지
                if st.button(f"🪄 AI 초안 생성", key=f"ai_btn_{idx}"):
                    with st.spinner("AI가 분석 중입니다..."):
                        prompt = f"한일고 생기부 전문가로서 다음 활동을 '~함'체로 요약해줘.\n주제: {t}\n내용: {c}\n변화: {f}"
                        res = model.generate_content(prompt)
                        st.info(res.text)
            st.markdown('</div>', unsafe_allow_html=True)
