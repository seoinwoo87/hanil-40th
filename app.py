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
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif; background-color: #F8FAFC; }
    .stMetric { background: white; border: 1px solid #E2E8F0; padding: 15px !important; border-radius: 12px !important; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }
    .timeline-card { background: white; border: 1px solid #E2E8F0; border-radius: 15px; padding: 25px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.03); border-left: 6px solid #2563EB; }
    .badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: 700; background: #EFF6FF; color: #1D4ED8; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# 2. AI 및 데이터 로드 (캐시 적용)
try:
    genai.configure(api_key=st.secrets["gemini_api_key"])
    model = genai.GenerativeModel('gemini-1.5-flash')
except:
    model = None

@st.cache_resource
def load_all_data():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        client = gspread.authorize(creds)
        doc = client.open("40기 마스터 파일")
        
        def process_sheet(name):
            try:
                sh = doc.worksheet(name)
                data = sh.get_all_values()
                if not data: return pd.DataFrame()
                df = pd.DataFrame(data[1:], columns=data[0])
                if '학번' in df.columns:
                    df['학번'] = df['학번'].astype(str).str.replace(',', '').str.split('.').str[0].str.strip()
                n_col = '성명' if '성명' in df.columns else '이름'
                if '학번' in df.columns and n_col in df.columns:
                    df['학생명'] = df[n_col].astype(str).str.strip()
                    df['식별'] = df['학번'] + " " + df['학생명']
                return df
            except: return pd.DataFrame()
        return process_sheet("31_내신"), process_sheet("21_모의고사"), process_sheet("51_시험복기"), process_sheet("61_비교과")
    except: return [pd.DataFrame()]*4

df_scores, df_mock, df_ref, df_act = load_all_data()

# 3. 사이드바 및 필터
if df_scores.empty:
    st.error("데이터를 불러오지 못했습니다. Secrets 설정이나 구글 시트 권한을 확인해주세요.")
    st.stop()

with st.sidebar:
    st.title("🏫 한일고 40기 상담실")
    terms = sorted(df_scores['학기'].unique(), reverse=True)
    sel_term = st.selectbox("📅 학기 선택", terms)
    students = sorted(df_scores[df_scores['학기'] == sel_term]['식별'].unique())
    sel_student = st.selectbox("👤 학생 선택", students)
    sel_num = sel_student.split(" ")[0]
    st.markdown("---")
    menu = st.radio("📑 메뉴", ["📈 내신 성적", "🎯 모의고사 분석", "🧠 성찰 리포트", "🏆 누적 비교과"])

st.header(f"📊 {sel_student} 리포트")

# 4. 내신 성적 (과목명 가독성 개선)
if menu == "📈 내신 성적":
    t1, t2 = st.tabs(["📊 시험별 상세", "📈 성적 추이"])
    my_s = df_scores[(df_scores['식별'] == sel_student) & (df_scores['학기'] == sel_term)]
    
    with t1:
        exam = st.selectbox("시험 선택", ["1회고사", "2회고사", "학기말"])
        filtered = my_s[my_s['시험'] == exam].copy()
        if not filtered.empty:
            if exam == "학기말":
                cols = st.columns(len(filtered))
                for i, (_, r) in enumerate(filtered.iterrows()):
                    cols[i].metric(r['과목'], f"{r.get('등급','-')}등급")
            else:
                filtered['점수'] = pd.to_numeric(filtered['점수'], errors='coerce')
                fig = px.bar(filtered, x='과목', y='점수', text='점수', color='점수', color_continuous_scale='Blues')
                fig.update_layout(margin=dict(b=100), xaxis=dict(tickangle=-45, title=""), yaxis=dict(range=[0, 105], title="원점수"))
                st.plotly_chart(fig, use_container_width=True)
        else: st.info("데이터가 없습니다.")
    
    with t2:
        subs = sorted(my_s['과목'].unique())
        s_sub = st.selectbox("과목 선택", subs)
        trend = my_s[my_s['과목'] == s_sub].copy()
        trend['점수'] = pd.to_numeric(trend['점수'], errors='coerce')
        trend['ord'] = trend['시험'].map({'1회고사':1, '2회고사':2, '학기말':3})
        st.plotly_chart(px.line(trend.sort_values('ord'), x='시험', y='점수', markers=True, text='점수'), use_container_width=True)

# 5. 모의고사 분석 (표점/백분위/등급 3단 배치)
elif menu == "🎯 모의고사 분석":
    my_m = df_mock[df_mock['학번'] == sel_num].copy()
    if not my_m.empty:
        latest = my_m.iloc[-1]
        st.subheader(f"🎯 최근 시험: {latest['시험명']}")
        
        def score_row(label, subj):
            st.markdown(f"**{label}**")
            c1, c2, c3 = st.columns(3)
            c1.metric("표준점수", latest.get(f'{subj}_표준점수','-'))
            c2.metric("백분위", f"{latest.get(f'{subj}_백분위','-')}%")
            c3.metric("등급", f"{latest.get(f'{subj}_등급','-')}급")
            st.markdown("---")

        score_row("📘 국어", "국어")
        score_row("📐 수학", "수학")
        
        ec1, ec2 = st.columns(2)
        ec1.metric("🔤 영어 등급", f"{latest.get('영어_등급','-')}등급")
        t_kind = "사탐" if pd.notnull(latest.get('사회탐구_등급')) and latest.get('사회탐구_등급') != "" else "과탐"
        ec2.metric(f"🧪 {t_kind} 등급", f"{latest.get(f'{t_kind}1_등급', latest.get(f'{t_kind}탐구_등급','-'))}등급")
        
        st.subheader("📈 백분위 추이")
        for col in my_m.columns:
            if '백분위' in col: my_m[col] = pd.to_numeric(my_m[col], errors='coerce')
        fig_m = px.line(my_m, x='시험명', y=[c for c in my_m.columns if '백분위' in c], markers=True)
        fig_m.update_layout(yaxis=dict(range=[0, 105]), margin=dict(b=80))
        st.plotly_chart(fig_m, use_container_width=True)
    else: st.info("모의고사 데이터가 없습니다.")

# 6. 성찰 리포트
elif menu == "🧠 성찰 리포트":
    my_r = df_ref[df_ref['학번'] == sel_num].copy()
    if not my_r.empty:
        sel_ex = st.selectbox("시험 선택", my_r['시험명'].unique())
        row = my_r[my_r['시험명'] == sel_ex].iloc[-1]
        cols = st.columns(2)
        idx = 0
        for k, v in row.items():
            if k in ['타임스탬프','학번','이름','성명','학생식별','식별','학생명','시험명'] or not v: continue
            with cols[idx%2]:
                st.markdown(f"""<div style="background:white; border-left:5px solid #3B82F6; padding:15px; margin-bottom:10px; border-radius:5px; box-shadow:0 1px 3px rgba(0,0,0,0.1);">
                    <b>{k}</b><br>{v}</div>""", unsafe_allow_html=True)
            idx += 1
    else: st.info("기록이 없습니다.")

# 7. 누적 비교과
elif menu == "🏆 누적 비교과":
    st.subheader("🏆 누적 활동 타임라인")
    my_act = df_act[df_act['학번'] == sel_num].copy()
    if my_act.empty:
        st.info("기록된 활동이 없습니다.")
    else:
        my_act = my_act.sort_values('활동 일자', ascending=False)
        for i, row in my_act.iterrows():
            st.markdown(f"""
            <div class="timeline-card">
                <div class="badge">#{row.get('활동의 성격','활동')}</div>
                <div style="font-size:1.3rem; font-weight:800; color:#1E40AF; margin-bottom:8px;">{row.get('활동 주제','주제 없음')}</div>
                <div style="font-size:0.85rem; color:#64748B; margin-bottom:15px;">📅 {row.get('활동 일자','-')} | 📚 {row.get('연계 가능 교과(선택)','-')}</div>
                <div style="background:#F8FAFC; padding:18px; border-radius:12px; font-size:0.95rem; line-height:1.7;">
                    <b>💡 동기:</b> {row.get('활동 동기(왜 시작했나요)','')}<br><br>
                    <b>📝 주요 활동:</b><br>{row.get('핵심 활동 내용(무엇을 어떻게 했나요)','')}<br><br>
                    <b>🌱 성장과 변화:</b><br>{row.get('결과 및 배우고 느낀 점(어떤 변화가 있었나요?)','')}
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"🪄 생기부 문구 생성 ({i})"):
                with st.spinner("작성 중..."):
                    p = f"교사 관점에서 생기부용 요약 (~함 체): {row.get('핵심 활동 내용','')}"
                    st.info(model.generate_content(p).text)
