import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re

# ==========================================
# 1. 페이지 설정 및 디자인 (UI/UX)
# ==========================================
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
    .stDataFrame { border: 1px solid #E2E8F0; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# [유틸리티] 어떤 형식이든 숫자만 안전하게 추출하는 함수
def safe_numeric(val):
    if pd.isna(val) or val is None: return 0.0
    val_str = str(val).strip()
    if not val_str or val_str == '-' or val_str == '미응시': return 0.0
    try:
        # 숫자와 소수점만 남기고 모두 제거
        cleaned = re.sub(r'[^0-9.]', '', val_str)
        if cleaned.count('.') > 1:
            parts = cleaned.split('.')
            cleaned = parts[0] + '.' + ''.join(parts[1:])
        return float(cleaned) if cleaned else 0.0
    except:
        return 0.0

# [유틸리티] 열 이름에 특정 키워드가 포함되어 있는지 유연하게 검색
def find_col_by_keyword(df, keyword):
    for col in df.columns:
        if keyword in str(col).replace(" ", "").lower():
            return col
    return None

# ==========================================
# 2. 데이터 로드 및 AI 설정
# ==========================================
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
                # 중복 컬럼 제거
                df = df.loc[:, ~df.columns.duplicated()]
                
                if '학번' in df.columns:
                    df['학번'] = df['학번'].astype(str).str.replace(',', '').str.split('.').str[0].str.strip()
                
                n_col = '성명' if '성명' in df.columns else '이름'
                if '학번' in df.columns and n_col in df.columns:
                    df['학생명'] = df[n_col].astype(str).str.strip()
                    df['식별'] = df['학번'] + " " + df['학생명']
                return df
            except: 
                return pd.DataFrame()
        
        return process_sheet("31_내신"), process_sheet("21_모의고사"), process_sheet("51_시험복기"), process_sheet("61_비교과")
    except Exception as e:
        st.error(f"구글 시트 연동 오류: {e}")
        return [pd.DataFrame()]*4

df_scores, df_mock, df_ref, df_act = load_all_data()

# AI 설정 (가장 호환성 높은 gemini-pro 사용)
try:
    genai.configure(api_key=st.secrets["gemini_api_key"])
    ai_model = genai.GenerativeModel('gemini-pro')
except:
    ai_model = None

# ==========================================
# 3. 사이드바 메뉴 및 필터
# ==========================================
if df_scores.empty:
    st.error("데이터 로드 실패. 앱을 Reboot 해주세요.")
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

st.header(f"📊 {sel_student} 분석 리포트")

# ==========================================
# 4. 내신 분석 (백분위 인식 강화 + 색상 차별화)
# ==========================================
if menu == "📈 내신 분석":
    t1, t2 = st.tabs(["📊 시험별 상세", "📈 성적 추이"])
    my_s_all = df_scores[(df_scores['학기'] == sel_term)].copy()
    my_s = my_s_all[my_s_all['식별'] == sel_student]
    
    # 열 이름 유연 탐색
    score_col = find_col_by_keyword(my_s_all, '점수') or '원점수'
    perc_col = find_col_by_keyword(my_s_all, '백분위')
    
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
                    # 학년 중위값 계산
                    all_exam_scores = my_s_all[(my_s_all['시험'] == exam) & (my_s_all['과목'] == row['과목'])][score_col]
                    all_scores = all_exam_scores.apply(safe_numeric).dropna()
                    median_val = all_scores.median() if not all_scores.empty else 0
                    
                    # 백분위 데이터 추출 (0점 방지 핵심 로직)
                    val_perc = safe_numeric(row.get(perc_col, 0)) if perc_col else 0.0
                    
                    plot_data.append({
                        '과목': row['과목'], 
                        '점수': safe_numeric(row.get(score_col, 0)), 
                        '중위값': median_val, 
                        '백분위': val_perc
                    })
                pdf = pd.DataFrame(plot_data)

                # 과목별 색상을 다르게 적용한 막대그래프
                fig = px.bar(pdf, x='과목', y='점수', color='과목', text='점수', color_discrete_sequence=px.colors.qualitative.Pastel)
                
                # 중위값 점선 표시
                fig.add_trace(go.Scatter(x=pdf['과목'], y=pdf['중위값'], name="학년 중위값", mode='lines+markers', line=dict(color='black', dash='dash', width=2)))
                
                # 백분위 이중 축 표시 (0보다 큰 경우에만 텍스트 노출)
                fig.add_trace(go.Scatter(x=pdf['과목'], y=pdf['백분위'], name="백분위(%)", yaxis="y2", mode='lines+markers+text', 
                                         text=pdf['백분위'].apply(lambda x: f"{int(x)}%" if x > 0 else ""), 
                                         line=dict(color='red', width=3)))
                
                fig.update_layout(
                    xaxis=dict(tickangle=-45, tickfont=dict(size=14, color='black')),
                    yaxis=dict(title="원점수", range=[0, 105]),
                    yaxis2=dict(title="백분위", overlaying="y", side="right", range=[0, 105]),
                    margin=dict(b=120),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig, use_container_width=True)
        else: st.info("데이터가 없습니다.")

# ==========================================
# 5. 모의고사 분석 (표준점수 복구 + 그래프 복구)
# ==========================================
elif menu == "🎯 모의고사 분석":
    my_m = df_mock[df_mock['학번'] == sel_num].copy()
    if not my_m.empty:
        my_m = my_m.loc[:, ~my_m.columns.duplicated()].copy()
        latest = my_m.iloc[-1]
        st.subheader(f"🎯 최근 모의고사 요약: {latest.get('시험명', '최근 시험')}")
        
        # [유연 탐색기] 과목명 + 키워드 조합으로 데이터를 찾아오는 만능 로직
        def get_flex_val(series, subj_keys, keywords):
            for col in series.index:
                c_clean = str(col).replace(" ", "").replace("_", "").lower()
                if any(s in c_clean for s in subj_keys) and any(k in c_clean for k in keywords):
                    val = series[col]
                    return val if pd.notna(val) and str(val).strip() != '' else '-'
            return '-'

        subj_map = {
            "국어": ["국어"], "수학": ["수학"], "영어": ["영어"], 
            "한국사": ["한국사", "국사"], "사회탐구": ["사회탐구", "사탐"], "과학탐구": ["과학탐구", "과탐"]
        }
        
        summary_data = []
        for s_name, s_keys in subj_map.items():
            summary_data.append({
                "과목": s_name,
                "표준점수": get_flex_val(latest, s_keys, ['표준점수', '표점']),
                "백분위": f"{get_flex_val(latest, s_keys, ['백분위', '백분'])}%",
                "등급": get_flex_val(latest, s_keys, ['등급'])
            })
        st.table(pd.DataFrame(summary_data))
        
        st.markdown("---")
        st.subheader("📈 백분위 변화 추이")
        perc_cols = [c for c in my_m.columns if '백분위' in c]
        if perc_cols:
            plot_m = my_m[['시험명'] + perc_cols].copy()
            for c in perc_cols:
                plot_m[c] = plot_m[c].apply(safe_numeric)
            
            # 그래프 데이터 정리
            melted_m = plot_m.melt(id_vars=['시험명'], var_name='과목', value_name='백분위')
            fig_m = px.line(melted_m, x='시험명', y='백분위', color='과목', markers=True)
            fig_m.update_layout(yaxis=dict(title="백분위(%)", range=[0, 105]), margin=dict(b=80))
            st.plotly_chart(fig_m, use_container_width=True)

        st.markdown("---")
        st.subheader("📝 전체 모의고사 누적 기록")
        st.dataframe(my_m.drop(columns=['학번','식별','학생명'], errors='ignore'), use_container_width=True)
    else: st.info("기록이 없습니다.")

# ==========================================
# 6. 성찰 리포트 (AI 상담 기능 복구)
# ==========================================
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
                with st.spinner("AI가 성찰 리포트를 분석 중입니다..."):
                    try:
                        clean_data = {str(k): str(v) for k, v in row.items() if len(str(v)) > 5 and k not in ['학번','타임스탬프']}
                        res = ai_model.generate_content(f"한일고 상담교사의 관점에서 다음 성찰 내용을 분석하고 조언해줘: {str(clean_data)}")
                        st.markdown(f'<div class="ai-container"><b>🤖 AI 상담 조언</b><br>{res.text}</div>', unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"AI 생성 오류: {e}")
            else: st.warning("AI 설정(API Key)을 확인해주세요.")
    else: st.info("기록이 없습니다.")

# ==========================================
# 7. 비교과 타임라인 (역량 통계 및 필터링 기능)
# ==========================================
elif menu == "🏆 비교과 타임라인":
    my_act = df_act[df_act['학번'] == sel_num].copy()
    if not my_act.empty:
        # 시트의 열 이름을 지능적으로 탐색
        col_type = next((c for c in my_act.columns if '성격' in c), None)
        col_comp = next((c for c in my_act.columns if '역량' in c), None)
        
        # 핵심역량 대시보드
        if col_comp:
            st.subheader("📊 핵심역량별 활동 분포")
            counts = my_act[col_comp].value_counts()
            s_cols = st.columns(len(counts) if len(counts) > 0 else 1)
            for i, (name, count) in enumerate(counts.items()):
                with s_cols[i % len(s_cols)]:
                    st.markdown(f'<div class="stat-box"><small>{name}</small><br><b style="font-size:1.5rem; color:#2563EB;">{count}건</b></div>', unsafe_allow_html=True)
            st.markdown("---")
        
        # 활동 검색 및 필터
        f1, f2 = st.columns(2)
        filtered = my_act.copy()
        
        if col_type:
            with f1: sel_t = st.selectbox("활동 성격 필터", ["전체"] + sorted(my_act[col_type].dropna().unique().tolist()))
            if sel_t != "전체": filtered = filtered[filtered[col_type] == sel_t]
            
        if col_comp:
            with f2: sel_c = st.selectbox("역량 필터", ["전체"] + sorted(my_act[col_comp].dropna().unique().tolist()))
            if sel_c != "전체": filtered = filtered[filtered[col_comp] == sel_c]
        
        st.write(f"검색 결과: {len(filtered)}건")
        
        # 활동 타임라인 출력
        for i, row in filtered.sort_values('활동 일자', ascending=False).iterrows():
            st.markdown(f"""
            <div class="timeline-card">
                <span class="badge">#{row.get(col_type,'활동')}</span>
                <span class="badge" style="background:#DCFCE7; color:#166534;">🏆 {row.get(col_comp,'역량')}</span>
                <div style="font-size:1.3rem; font-weight:800; color:#1E40AF; margin:10px 0;">{row.get('활동 주제','주제 없음')}</div>
                <div style="font-size:0.85rem; color:#64748B; margin-bottom:15px;">📅 {row.get('활동 일자','-')} | 📚 {row.get('연계 가능 교과(선택)','-')}</div>
                <div style="background:#F8FAFC; padding:18px; border-radius:12px; font-size:0.95rem; line-height:1.7;">
                    <b>📝 활동 내용:</b><br>{row.get('핵심 활동 내용(무엇을 어떻게 했나요)', row.get('핵심 활동 내용', '-'))}<br><br>
                    <b>🌱 성장과 변화:</b><br>{row.get('결과 및 배우고 느낀 점(어떤 변화가 있었나요?)', row.get('결과 및 배우고 느낀 점', '-'))}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button(f"🪄 AI 생기부 초안 생성 (활동 {i})"):
                if ai_model:
                    with st.spinner("생기부 문구 작성 중..."):
                        p = f"다음 학생의 활동 기록을 바탕으로 생기부에 들어갈 핵심 문구를 작성해줘(~함 체 사용):\n{row.get('핵심 활동 내용', '')}"
                        try:
                            st.info(ai_model.generate_content(p).text)
                        except Exception as e:
                            st.error(f"AI 생성 오류: {e}")
                else: st.warning("AI 설정 필요")
    else: st.info("활동 기록이 없습니다.")
