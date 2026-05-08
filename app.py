import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 1. 페이지 설정 및 디자인
st.set_page_config(page_title="한일고 40기 상담 시스템", layout="wide")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@400;600;800&display=swap');
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif; }
    .stMetric { background: white; border: 1px solid #E2E8F0; padding: 15px !important; border-radius: 10px !important; }
    .timeline-card { background: white; border: 1px solid #E2E8F0; border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.75rem; font-weight: 700; background: #EFF6FF; color: #1D4ED8; margin-bottom: 5px; }
    .ai-box { background: #F0F9FF; border: 1px solid #BAE6FD; border-radius: 10px; padding: 15px; margin-top: 10px; }
</style>
""", unsafe_allow_html=True)

# 2. AI 및 데이터 로드 설정
try:
    genai.configure(api_key=st.secrets["gemini_api_key"])
    model = genai.GenerativeModel('gemini-1.5-flash')
except:
    model = None

@st.cache_resource
def load_data():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        client = gspread.authorize(creds)
        doc = client.open("40기 마스터 파일")
        
        def process_sheet(name):
            try:
                sheet = doc.worksheet(name)
                data = sheet.get_all_values()
                df = pd.DataFrame(data[1:], columns=data[0])
                # 학번 정제: 소수점 제거 및 문자열화
                if '학번' in df.columns:
                    df['학번'] = df['학번'].astype(str).str.split('.').str[0].str.strip()
                # 성명/이름 통합
                n_col = '성명' if '성명' in df.columns else '이름'
                if '학번' in df.columns and n_col in df.columns:
                    df['학생식별'] = df['학번'] + " " + df[n_col].astype(str).str.strip()
                return df
            except: return pd.DataFrame()

        return process_sheet("31_내신"), process_sheet("21_모의고사"), process_sheet("51_시험복기"), process_sheet("61_비교과")
    except Exception as e:
        st.error(f"연결 오류: {e}")
        return [pd.DataFrame()]*4

df_scores, df_mock, df_ref, df_act = load_data()

# 3. 사이드바 메뉴
with st.sidebar:
    st.title("🏫 40기 상담 시스템")
    if not df_scores.empty:
        sel_term = st.selectbox("학기 선택", sorted(df_scores['학기'].unique(), reverse=True))
        student_list = sorted(df_scores[df_scores['학기'] == sel_term]['학생식별'].unique())
        sel_student = st.selectbox("학생 선택", student_list)
        target_num = sel_student.split(" ")[0] # 학번만 추출
        
        st.markdown("---")
        menu = st.radio("메뉴", ["📈 내신 성적", "🎯 모의고사", "🧠 성찰 리포트", "🏆 비교과 타임라인"])
    else:
        st.stop()

st.title(f" {sel_student} 리포트")

# 4. 내신 성적
if menu == "📈 내신 성적":
    tab1, tab2 = st.tabs(["📊 상세 현황", "📈 성적 추이"])
    my_s = df_scores[(df_scores['학생식별'] == sel_student) & (df_scores['학기'] == sel_term)]
    
    with tab1:
        exam = st.selectbox("시험", ["1회고사", "2회고사", "학기말"])
        filtered = my_s[my_s['시험'] == exam]
        if not filtered.empty:
            if exam == "학기말":
                cols = st.columns(len(filtered))
                for i, (_, r) in enumerate(filtered.iterrows()):
                    cols[i].metric(r['과목'], f"{r['등급']}등급")
            else:
                # 간단 그래프
                filtered['점수'] = pd.to_numeric(filtered['점수'], errors='coerce')
                fig = px.bar(filtered, x='과목', y='점수', text='점수', color='점수', color_continuous_scale='Blues')
                st.plotly_chart(fig, use_container_width=True)
        else: st.info("데이터가 없습니다.")
    
    with tab2:
        subjects = sorted(my_s['과목'].unique())
        sub = st.selectbox("과목 선택", subjects)
        sub_df = my_s[my_s['과목'] == sub].copy()
        sub_df['점수'] = pd.to_numeric(sub_df['점수'], errors='coerce')
        st.plotly_chart(px.line(sub_df, x='시험', y='점수', markers=True), use_container_width=True)

# 5. 모의고사
elif menu == "🎯 모의고사":
    my_m = df_mock[df_mock['학번'] == target_num]
    if not my_m.empty:
        latest = my_m.iloc[-1]
        st.subheader(f"{latest['시험명']} 결과")
        cols = st.columns(4)
        cols[0].metric("국어", f"{latest.get('국어_등급','-')}등급")
        cols[1].metric("수학", f"{latest.get('수학_등급','-')}등급")
        cols[2].metric("영어", f"{latest.get('영어_등급','-')}등급")
        cols[3].metric("탐구", f"{latest.get('사회탐구_등급','-') or latest.get('과학탐구_등급','-')}등급")
    else: st.info("모의고사 데이터가 없습니다.")

# 6. 성찰 리포트
elif menu == "🧠 성찰 리포트":
    my_r = df_ref[df_ref['학번'] == target_num]
    if not my_r.empty:
        exam_nm = st.selectbox("시험명", my_r['시험명'].unique())
        row = my_r[my_r['시험명'] == exam_nm].iloc[-1]
        cols = st.columns(2)
        idx = 0
        for k, v in row.items():
            if k in ['타임스탬프','학번','이름','성명','학생식별','시험명'] or not v: continue
            with cols[idx%2]:
                st.markdown(f"**{k}**\n\n{v}\n\n---")
            idx += 1
    else: st.info("성찰 기록이 없습니다.")

# 7. 비교과 타임라인 (여기가 핵심!)
elif menu == "🏆 비교과 타임라인":
    st.subheader("누적 활동 기록")
    # 학번으로만 필터링 (가장 안전)
    my_act = df_act[df_act['학번'] == target_num].copy()
    
    if my_act.empty:
        st.warning(f"'{target_num}' 학번으로 조회된 기록이 없습니다.")
        with st.expander("데이터 진단"):
            st.write("선택된 학번:", target_num)
            if not df_act.empty:
                st.write("시트 내 학번 예시:", df_act['학번'].iloc[0])
    else:
        for i, row in my_act.iterrows():
            with st.container():
                st.markdown(f"""
                <div class="timeline-card">
                    <span class="badge">#{row.get('활동의 성격','-')}</span>
                    <div style="font-size:1.2rem; font-weight:800; color:#1E40AF; margin-bottom:10px;">{row.get('활동 주제','제목 없음')}</div>
                    <div style="font-size:0.85rem; color:#64748B; margin-bottom:15px;">📅 {row.get('활동 일자','-')} | {row.get('연계 가능 교과(선택)','-')}</div>
                    <div style="line-height:1.6; font-size:0.95rem;">
                        <b>💡 동기:</b> {row.get('활동 동기(왜 시작했나요)','')}<br><br>
                        <b>📝 핵심 활동:</b><br>{row.get('핵심 활동 내용(무엇을 어떻게 했나요)','')}<br><br>
                        <b>🌱 성찰 및 변화:</b><br>{row.get('결과 및 배우고 느낀 점(어떤 변화가 있었나요?)','')}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"🪄 AI 생기부 문구 생성 ({i})"):
                    prompt = f"다음 활동을 '~함'체로 요약해줘: {row.get('핵심 활동 내용','')}"
                    res = model.generate_content(prompt)
                    st.info(res.text)
