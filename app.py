import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re

# 1. 페이지 설정 및 디자인
st.set_page_config(page_title="한일고 40기 상담 시스템", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@400;600;800&display=swap');
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif; background-color: #F8FAFC; }
    .stMetric { background: white; border: 1px solid #E2E8F0; padding: 15px !important; border-radius: 12px !important; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }
    .timeline-card { background: white; border: 1px solid #E2E8F0; border-radius: 15px; padding: 25px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.03); border-left: 6px solid #2563EB; }
    .badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: 700; background: #EFF6FF; color: #1D4ED8; margin-bottom: 10px; margin-right: 5px; }
    .ai-container { background: linear-gradient(135deg, #F0F9FF 0%, #E0F2FE 100%); border: 1px solid #BAE6FD; border-radius: 12px; padding: 20px; margin-top: 15px; line-height: 1.8; font-size: 0.95rem; }
    .stat-box { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 15px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }
</style>
""", unsafe_allow_html=True)

# 숫자를 안전하게 추출하는 함수 (백분위 0 오류 해결용)
def safe_numeric(val):
    if pd.isna(val) or val == '': return 0.0
    try:
        cleaned = re.sub(r'[^0-9.]', '', str(val))
        return float(cleaned) if cleaned else 0.0
    except:
        return 0.0

# 2. 데이터 및 AI 로드 (캐시 적용)
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
                
                # 중복 컬럼 제거 (DuplicateError 방지)
                df = df.loc[:, ~df.columns.duplicated()]
                
                # 학번 세탁
                if '학번' in df.columns:
                    df['학번'] = df['학번'].astype(str).str.replace(',', '').str.split('.').str[0].str.strip()
                
                # 학생 식별 키 생성
                n_col = '성명' if '성명' in df.columns else '이름'
                if '학번' in df.columns and n_col in df.columns:
                    df['학생명'] = df[n_col].astype(str).str.strip()
                    df['식별'] = df['학번'] + " " + df['학생명']
                return df
            except: 
                return pd.DataFrame()
        return process_sheet("31_내신"), process_sheet("21_모의고사"), process_sheet("51_시험복기"), process_sheet("61_비교과")
    except Exception as e:
        st.error(f"구글 시트 로드 실패: {e}")
        return [pd.DataFrame()]*4

df_scores, df_mock, df_ref, df_act = load_all_data()

# AI 설정
try:
    genai.configure(api_key=st.secrets["gemini_api_key"])
    ai_model = genai.GenerativeModel('gemini-1.5-flash')
except:
    ai_model = None

# 3. 사이드바 (필터 및 메뉴)
if df_scores.empty:
    st.error("데이터가 비어있습니다. 시트 이름을 확인하거나 Reboot 해주세요.")
    st.stop()

with st.sidebar:
    st.title("🏫 한일고 40기 상담실")
    terms = sorted(df_scores['학기'].unique(), reverse=True)
    sel_term = st.selectbox("📅 학기 선택", terms)
    
    students = sorted(df_scores[df_scores['학기'] == sel_term]['식별'].unique())
    sel_student = st.selectbox("👤 학생 선택", students)
    sel_num = sel_student.split(" ")[0]
    
    st.markdown("---")
    menu = st.radio("📑 분석 메뉴", ["📈 내신 분석", "🎯 모의고사 분석", "🧠 성찰 리포트", "🏆 비교과 타임라인"])

st.header(f"📊 {sel_student} 리포트")

# 4. 내신 분석 (색상 차별화 + 중위값 + 백분위 2중 축)
if menu == "📈 내신 분석":
    t1, t2 = st.tabs(["📊 시험별 상세", "📈 성적 추이"])
    my_s_all = df_scores[(df_scores['학기'] == sel_term)].copy()
    my_s = my_s_all[my_s_all['식별'] == sel_student]
    
    with t1:
        exam = st.selectbox("시험 선택", ["1회고사", "2회고사", "학기말"])
        filtered = my_s[my_s['시험'] == exam].copy()
        
        if not filtered.empty:
            if exam == "학기말":
                cols = st.columns(len(filtered))
                for i, (_, r) in enumerate(filtered.iterrows()):
                    cols[i].metric(r['과목'], f"{r.get('등급','-')}등급")
            else:
                plot_data = []
                for _, row in filtered.iterrows():
                    all_scores = pd.to_numeric(my_s_all[(my_s_all['시험'] == exam) & (my_s_all['과목'] == row['과목'])]['점수'], errors='coerce').dropna()
                    median_val = all_scores.median() if not all_scores.empty else 0
                    plot_data.append({
                        '과목': row['과목'], 
                        '점수': safe_numeric(row['점수']), 
                        '중위값': median_val, 
                        '백분위': safe_numeric(row.get('백분위', 0))
                    })
                pdf = pd.DataFrame(plot_data)

                fig = px.bar(pdf, x='과목', y='점수', color='과목', text='점수', color_discrete_sequence=px.colors.qualitative.Pastel)
                fig.add_trace(go.Scatter(x=pdf['과목'], y=pdf['중위값'], name="학년 중위값", mode='lines+markers', line=dict(color='black', dash='dash')))
                
                # 백분위 이중 축 (0 이상인 경우만 텍스트 표시)
                fig.add_trace(go.Scatter(x=pdf['과목'], y=pdf['백분위'], name="백분위(%)", yaxis="y2", mode='lines+markers+text', 
                                         text=pdf['백분위'].apply(lambda x: f"{int(x)}%" if x > 0 else ""), 
                                         line=dict(color='red', width=3)))
                
                fig.update_layout(
                    xaxis=dict(tickangle=-45, tickfont=dict(size=14, color='black')),
                    yaxis=dict(title="원점수", range=[0, 105]),
                    yaxis2=dict(title="백분위", overlaying="y", side="right", range=[0, 105]),
                    margin=dict(b=120), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig, use_container_width=True)
        else: st.info("데이터가 없습니다.")
    
    with t2:
        subs = sorted(my_s['과목'].unique())
        s_sub = st.selectbox("과목 선택", subs)
        trend = my_s[my_s['과목'] == s_sub].copy()
        trend['점수'] = pd.to_numeric(trend['점수'], errors='coerce')
        trend['ord'] = trend['시험'].map({'1회고사':1, '2회고사':2, '학기말':3})
        st.plotly_chart(px.line(trend.sort_values('ord'), x='시험', y='점수', markers=True, text='점수'), use_container_width=True)

# 5. 모의고사 분석 (표점 복구 + 백분위 추이 + 전체 누적 표)
elif menu == "🎯 모의고사 분석":
    my_m = df_mock[df_mock['학번'] == sel_num].copy()
    if not my_m.empty:
        my_m = my_m.loc[:, ~my_m.columns.duplicated()].copy()
        latest = my_m.iloc[-1]
        st.subheader(f"🎯 최근 모의고사 요약: {latest['시험명']}")
        
        subs = ["국어", "수학", "영어", "한국사", "사회탐구", "과학탐구"]
        summary = []
        for s in subs:
            summary.append({
                "과목": s,
                "표준점수": latest.get(f'{s}_표준점수', latest.get(f'{s}표준점수', '-')),
                "백분위": f"{latest.get(f'{s}_백분위', latest.get(f'{s}백분위', '-'))}%",
                "등급": f"{latest.get(f'{s}_등급', latest.get(f'{s}등급', '-'))}등급"
            })
        st.table(pd.DataFrame(summary))
        
        st.markdown("---")
        st.subheader("📈 백분위 변화 추이")
        perc_cols = [c for c in my_m.columns if '백분위' in c]
        plot_m = my_m[['시험명'] + perc_cols].copy()
        for c in perc_cols:
            plot_m[c] = plot_m[c].apply(safe_numeric)
        
        # 중복 방지를 위한 Melt 처리
        melted_m = plot_m.melt(id_vars=['시험명'], var_name='과목', value_name='백분위')
        fig_m = px.line(melted_m, x='시험명', y='백분위', color='과목', markers=True)
        fig_m.update_layout(yaxis=dict(title="백분위(%)", range=[0, 105]), margin=dict(b=80))
        st.plotly_chart(fig_m, use_container_width=True)

        st.markdown("---")
        st.subheader("📝 전체 모의고사 누적 기록")
        st.dataframe(my_m.drop(columns=['학번','식별','학생명'], errors='ignore'), use_container_width=True)
    else: st.info("모의고사 기록이 없습니다.")

# 6. 성찰 리포트 (AI 피드백 복구)
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
                st.markdown(f"""<div style="background:white; border-left:5px solid #3B82F6; padding:15px; margin-bottom:10px; border-radius:10px; box-shadow:0 1px 3px rgba(0,0,0,0.1);">
                    <b>{k}</b><br>{v}</div>""", unsafe_allow_html=True)
            idx += 1
        
        st.markdown("---")
        if st.button("🤖 AI 상담교사 피드백 생성"):
            if ai_model:
                with st.spinner("AI 분석 중..."):
                    try:
                        clean_data = {str(k): str(v) for k, v in row.items() if len(str(v)) > 5 and k not in ['학번','타임스탬프']}
                        res = ai_model.generate_content(f"상담교사의 관점에서 다음 성찰을 분석하고 조언해줘: {str(clean_data)}")
                        st.markdown(f'<div class="ai-container"><b>🤖 AI 상담 조언</b><br>{res.text}</div>', unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"AI 생성 중 오류가 발생했습니다: {e}")
            else: st.warning("AI 설정이 필요합니다.")
    else: st.info("기록이 없습니다.")

# 7. 비교과 타임라인 (역량 통계 + 필터링 + AI 요약)
elif menu == "🏆 비교과 타임라인":
    my_act = df_act[df_act['학번'] == sel_num].copy()
    if not my_act.empty:
        col_type = '활동의 성격'
        col_comp = '핵심 역량' if '핵심 역량' in my_act.columns else '핵심역량'
        
        # [역량 통계 대시보드]
        if col_comp in my_act.columns:
            st.subheader("📊 핵심역량별 활동 분포")
            counts = my_act[col_comp].value_counts()
            s_cols = st.columns(len(counts) if len(counts) > 0 else 1)
            for i, (name, count) in enumerate(counts.items()):
                with s_cols[i % len(s_cols)]:
                    st.markdown(f'<div class="stat-box"><small>{name}</small><br><b style="font-size:1.5rem; color:#2563EB;">{count}건</b></div>', unsafe_allow_html=True)
            st.markdown("---")
        
        # [필터링 기능]
        f1, f2 = st.columns(2)
        with f1: sel_t = st.selectbox("활동 성격 필터", ["전체"] + sorted(my_act[col_type].unique().tolist()))
        with f2: sel_c = st.selectbox("역량 필터", ["전체"] + sorted(my_act[col_comp].unique().tolist()))
        
        filtered = my_act.copy()
        if sel_t != "전체": filtered = filtered[filtered[col_type] == sel_t]
        if sel_c != "전체": filtered = filtered[filtered[col_comp] == sel_c]
        
        st.write(f"검색 결과: {len(filtered)}건")
        
        for i, row in filtered.sort_values('활동 일자', ascending=False).iterrows():
            st.markdown(f"""
            <div class="timeline-card">
                <span class="badge">#{row.get(col_type,'활동')}</span>
                <span class="badge" style="background:#DCFCE7; color:#166534;">🏆 {row.get(col_comp,'역량')}</span>
                <div style="font-size:1.3rem; font-weight:800; color:#1E40AF; margin:10px 0;">{row.get('활동 주제','주제 없음')}</div>
                <div style="font-size:0.85rem; color:#64748B; margin-bottom:15px;">📅 {row.get('활동 일자','-')} | 📚 {row.get('연계 가능 교과(선택)','-')}</div>
                <div style="background:#F8FAFC; padding:18px; border-radius:12px; font-size:0.95rem; line-height:1.7;">
                    <b>💡 동기:</b> {row.get('활동 동기(왜 시작했나요)','')}<br><br>
                    <b>📝 주요 활동:</b><br>{row.get('핵심 활동 내용(무엇을 어떻게 했나요)','')}<br><br>
                    <b>🌱 성장과 변화:</b><br>{row.get('결과 및 배우고 느낀 점(어떤 변화가 있었나요?)','')}
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"🪄 AI 생기부 초안 생성 ({i})"):
                with st.spinner("작성 중..."):
                    p = f"다음 활동을 바탕으로 생기부용 문구를 작성해줘(~함 체): {row.get('핵심 활동 내용','')}"
                    st.info(ai_model.generate_content(p).text if ai_model else "AI 설정 필요")
    else: st.info("활동 기록이 없습니다.")
