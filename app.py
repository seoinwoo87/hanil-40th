import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re

# ==========================================
# 1. 페이지 설정 및 디자인
# ==========================================
st.set_page_config(page_title="한일고 40기 상담 시스템", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@400;600;800&display=swap');
html, body, [class*="css"] { 
    font-family: 'Pretendard', sans-serif; 
    background-color: #F8FAFC; 
}
.stMetric { 
    background: white; 
    border: 1px solid #E2E8F0; 
    padding: 15px !important; 
    border-radius: 12px !important; 
    box-shadow: 0 2px 4px rgba(0,0,0,0.02); 
}
.timeline-card { 
    background: white; 
    border: 1px solid #E2E8F0; 
    border-radius: 15px; 
    padding: 25px; 
    margin-bottom: 20px; 
    box-shadow: 0 4px 6px rgba(0,0,0,0.03); 
    border-left: 6px solid #2563EB; 
}
.badge { 
    display: inline-block; 
    padding: 4px 12px; 
    border-radius: 20px; 
    font-size: 0.8rem; 
    font-weight: 700; 
    background: #EFF6FF; 
    color: #1D4ED8; 
    margin-bottom: 10px; 
    margin-right: 5px; 
}
.ai-container { 
    background: linear-gradient(135deg, #F0F9FF 0%, #E0F2FE 100%); 
    border: 1px solid #BAE6FD; 
    border-radius: 12px; 
    padding: 20px; 
    margin-top: 15px; 
    line-height: 1.8; 
    font-size: 0.95rem; 
}
.stat-box { 
    background: #FFFFFF; 
    border: 1px solid #E2E8F0; 
    border-radius: 10px; 
    padding: 15px; 
    text-align: center; 
    box-shadow: 0 2px 4px rgba(0,0,0,0.02); 
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 보안 설정 (선생님 전용 로그인)
# ==========================================
def check_password():
    """비밀번호가 맞으면 True를 반환합니다."""
    def password_entered():
        # st.secrets에 admin_password가 없다면 기본값 'hanil40'을 사용합니다.
        correct_password = st.secrets.get("admin_password", "hanil40")
        if st.session_state["password"] == correct_password:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # 보안을 위해 세션에서 비밀번호 삭제
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # 로그인 화면
        st.markdown("### 🔒 한일고 40기 상담 시스템 접속")
        st.text_input("선생님 비밀번호를 입력해주세요.", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        # 비밀번호 틀렸을 때
        st.markdown("### 🔒 한일고 40기 상담 시스템 접속")
        st.text_input("비밀번호가 틀렸습니다. 다시 입력해주세요.", type="password", on_change=password_entered, key="password")
        st.error("😕 권한이 없습니다.")
        return False
    else:
        # 로그인 성공
        return True

if not check_password():
    st.stop() # 로그인 전까지 아래 코드 실행 안함

# ==========================================
# 3. 데이터 로드 및 숫자 추출 유틸리티
# ==========================================
def safe_numeric(val):
    if pd.isna(val) or val is None: return 0.0
    val_str = str(val).strip()
    if not val_str or val_str == '-' or val_str == '미응시': return 0.0
    try:
        cleaned = re.sub(r'[^0-9.]', '', val_str)
        if cleaned.count('.') > 1:
            parts = cleaned.split('.')
            cleaned = parts[0] + '.' + ''.join(parts[1:])
        return float(cleaned) if cleaned else 0.0
    except: return 0.0

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
                df = pd.DataFrame(data[1:], columns=[str(c).strip() for c in data[0]])
                df = df.loc[:, ~df.columns.duplicated()] 
                if '학번' in df.columns:
                    df['학번'] = df['학번'].astype(str).str.replace(',', '').str.split('.').str[0].str.strip()
                n_col = next((c for c in df.columns if '성명' in c or '이름' in c), None)
                if '학번' in df.columns and n_col:
                    df['학생명'] = df[n_col].astype(str).str.strip()
                    df['식별'] = df['학번'] + " " + df['학생명']
                return df
            except: return pd.DataFrame()
        return process_sheet("31_내신"), process_sheet("21_모의고사"), process_sheet("51_시험복기"), process_sheet("61_비교과")
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return [pd.DataFrame()]*4

df_scores, df_mock, df_ref, df_act = load_all_data()

# AI 모델 자동 설정
try:
    genai.configure(api_key=st.secrets["gemini_api_key"])
    m_list = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    t_m = 'models/gemini-1.5-flash' if 'models/gemini-1.5-flash' in m_list else ('models/gemini-pro' if 'models/gemini-pro' in m_list else m_list[0])
    ai_model = genai.GenerativeModel(t_m)
except:
    ai_model = None

# ==========================================
# 4. 새로고침 시 상태 유지 (Query Params)
# ==========================================
# URL에서 현재 파라미터를 읽어옵니다.
query_params = st.query_params

# ==========================================
# 5. 사이드바 구성
# ==========================================
with st.sidebar:
    st.title("🏫 한일고 40기 상담실")
    
    # 학기 선택
    terms = sorted(df_scores['학기'].unique(), reverse=True)
    sel_term = st.selectbox("📅 학기 선택", terms)
    
    # 학생 선택 (상태 유지 반영)
    students = sorted(df_scores[df_scores['학기'] == sel_term]['식별'].unique())
    default_student_idx = 0
    if "student" in query_params and query_params["student"] in students:
        default_student_idx = students.index(query_params["student"])
    
    sel_student = st.selectbox("👤 학생 선택", students, index=default_student_idx)
    sel_num = sel_student.split(" ")[0]
    
    # URL 파라미터 업데이트
    st.query_params["student"] = sel_student
    
    st.markdown("---")
    
    # 메뉴 선택 (상태 유지 반영)
    menu_list = ["📈 내신 분석", "🎯 모의고사 분석", "🧠 성찰 리포트", "🏆 비교과 타임라인"]
    default_menu_idx = 0
    if "menu" in query_params and query_params["menu"] in menu_list:
        default_menu_idx = menu_list.index(query_params["menu"])
        
    menu = st.radio("📑 분석 메뉴", menu_list, index=default_menu_idx)
    st.query_params["menu"] = menu

st.header(f"📊 {sel_student} 분석 리포트")

# ==========================================
# 6. 내신 분석
# ==========================================
if menu == "📈 내신 분석":
    t1, t2 = st.tabs(["📊 시험별 상세", "📈 성적 추이"])
    my_s_all = df_scores[(df_scores['학기'] == sel_term)].copy()
    my_s = my_s_all[my_s_all['식별'] == sel_student]
    s_col = next((c for c in my_s_all.columns if '점수' in c.replace(" ", "")), '점수')
    
    with t1:
        exam = st.selectbox("시험 선택", ["1회고사", "2회고사", "학기말"])
        filtered = my_s[my_s['시험'] == exam].copy()
        if not filtered.empty:
            if exam == "학기말":
                cols = st.columns(len(filtered))
                for i, (_, row) in enumerate(filtered.iterrows()):
                    cols[i].metric(row['과목'], f"{row.get('등급','-')}등급")
            else:
                plot_data = []
                for _, row in filtered.iterrows():
                    all_scores = my_s_all[(my_s_all['시험'] == exam) & (my_s_all['과목'] == row['과목'])][s_col].apply(safe_numeric).dropna()
                    median_val = all_scores.median() if not all_scores.empty else 0
                    my_score = safe_numeric(row.get(s_col, 0))
                    count_below = (all_scores <= my_score).sum() if not all_scores.empty else 0
                    calc_perc = (count_below / len(all_scores)) * 100 if not all_scores.empty else 0
                    plot_data.append({'과목': row['과목'], '점수': my_score, '중위값': median_val, '백분위': round(calc_perc, 1)})
                pdf = pd.DataFrame(plot_data)
                fig = px.bar(pdf, x='과목', y='점수', color='과목', text='점수', color_discrete_sequence=px.colors.qualitative.Pastel)
                fig.add_trace(go.Scatter(x=pdf['과목'], y=pdf['중위값'], name="학년 중위값", mode='lines+markers', line=dict(color='black', dash='dash', width=2)))
                fig.add_trace(go.Scatter(x=pdf['과목'], y=pdf['백분위'], name="계산 백분위(%)", yaxis="y2", mode='lines+markers+text', 
                                         text=pdf['백분위'].apply(lambda x: f"{int(x)}%" if x > 0 else ""), 
                                         line=dict(color='red', width=3)))
                fig.update_layout(xaxis=dict(tickangle=-45, tickfont=dict(size=14, color='black')), yaxis=dict(title="원점수", range=[0, 105]), yaxis2=dict(title="백분위(%)", overlaying="y", side="right", range=[0, 105]), margin=dict(b=120), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                st.plotly_chart(fig, use_container_width=True)
        else: st.info("해당 시험 데이터가 없습니다.")

# ==========================================
# 7. 모의고사 분석
# ==========================================
elif menu == "🎯 모의고사 분석":
    my_m = df_mock[df_mock['학번'] == sel_num].copy()
    if not my_m.empty:
        my_m = my_m.loc[:, ~my_m.columns.duplicated()].copy()
        latest = my_m.iloc[-1]
        st.subheader(f"🎯 최근 모의고사 요약: {latest.get('시험명', '최근 시험')}")
        def get_flex_val(series, subj_keys, keywords):
            for col in series.index:
                c_clean = str(col).replace(" ", "").replace("_", "").lower()
                if any(s in c_clean for s in subj_keys) and any(k in c_clean for k in keywords):
                    val = series[col]
                    return val if pd.notna(val) and str(val).strip() != '' else '-'
            return '-'
        subj_map = {"국어": ["국어"], "수학": ["수학"], "영어": ["영어"], "한국사": ["한국사", "국사"], "사회탐구": ["사회탐구", "사탐"], "과학탐구": ["과학탐구", "과탐"]}
        summary = []
        for s_name, s_keys in subj_map.items():
            summary.append({"과목": s_name, "표준점수": get_flex_val(latest, s_keys, ['표준점수', '표점']), "백분위": f"{get_flex_val(latest, s_keys, ['백분위', '백분'])}%", "등급": get_flex_val(latest, s_keys, ['등급'])})
        st.table(pd.DataFrame(summary))
        st.markdown("---")
        st.subheader("📈 백분위 변화 추이")
        p_cols = [c for c in my_m.columns if '백분' in c]
        if p_cols:
            plot_m = my_m[['시험명'] + p_cols].copy()
            for c in p_cols: plot_m[c] = plot_m[c].apply(safe_numeric)
            melted_m = plot_m.melt(id_vars=['시험명'], var_name='과목', value_name='백분위')
            st.plotly_chart(px.line(melted_m, x='시험명', y='백분위', color='과목', markers=True).update_layout(yaxis=dict(range=[0, 105])), use_container_width=True)
        st.subheader("📝 전체 모의고사 누적 기록")
        st.dataframe(my_m.drop(columns=['학번', '식별', '학생명'], errors='ignore'), use_container_width=True)
    else: st.info("모의고사 기록이 없습니다.")

# ==========================================
# 8. 성찰 리포트
# ==========================================
elif menu == "🧠 성찰 리포트":
    my_r = df_ref[df_ref['학번'] == sel_num].copy()
    if not my_r.empty:
        sel_ex = st.selectbox("시험 선택", my_r['시험명'].unique())
        row = my_r[my_r['시험명'] == sel_ex].iloc[-1]
        cols = st.columns(2)
        idx = 0
        for k, v in row.items():
            if k in ['타임스탬프', '학번', '이름', '성명', '학생식별', '식별', '학생명', '시험명'] or not v: continue
            with cols[idx % 2]: st.markdown(f"""<div style="background:white; border-left:5px solid #3B82F6; padding:15px; margin-bottom:10px; border-radius:10px; box-shadow:0 1px 3px rgba(0,0,0,0.1);"><b>{k}</b><br>{v}</div>""", unsafe_allow_html=True)
            idx += 1
        st.markdown("---")
        if st.button("🤖 AI 상담교사 피드백 생성"):
            if ai_model:
                with st.spinner("AI 분석 중..."):
                    try:
                        clean_data = {str(k): str(v) for k, v in row.items() if len(str(v)) > 5 and k not in ['학번', '타임스탬프']}
                        res = ai_model.generate_content(f"한일고 상담교사의 관점에서 다음 성찰 내용을 분석하고 조언해줘: {str(clean_data)}")
                        st.markdown(f"""<div class="ai-container"><b>🤖 AI 상담 조언</b><br><br>{res.text}</div>""", unsafe_allow_html=True)
                    except Exception as e: st.error(f"AI 오류: {e}")
            else: st.warning("AI 모델 설정 필요.")
    else: st.info("성찰 기록이 없습니다.")

# ==========================================
# 9. 비교과 타임라인 (세분화 필터링 적용)
# ==========================================
elif menu == "🏆 비교과 타임라인":
    my_act = df_act[df_act['학번'] == sel_num].copy()
    
    if not my_act.empty:
        # 열 자동 탐색
        col_type = next((c for c in my_act.columns if '성격' in c), None)
        col_comp = next((c for c in my_act.columns if '역량' in c), None)
        
        # [역량 통계]
        if col_comp:
            st.subheader("📊 핵심역량별 활동 분포")
            counts = my_act[col_comp].value_counts()
            s_cols = st.columns(len(counts) if len(counts) > 0 else 1)
            for i, (name, count) in enumerate(counts.items()):
                with s_cols[i % len(s_cols)]: st.markdown(f"""<div class="stat-box"><small style="color:#64748B;">{name}</small><br><b style="font-size:1.5rem; color:#2563EB;">{count}건</b></div>""", unsafe_allow_html=True)
            st.markdown("---")
        
        # [세분화된 필터링]
        st.subheader("🔍 활동 맞춤 필터")
        f1, f2 = st.columns(2)
        filtered_act = my_act.copy()
        
        with f1:
            # 활동 성격 카테고리 (선생님 요청 사항)
            type_options = ["전체", "자율 활동", "진로 활동", "독서 활동", "문헌 탐구 활동", "협력 토론 활동", "실증 탐구 활동", "비평 성찰 활동", "발표 공유 활동", "융합 탐구 활동", "교사 개별 상담"]
            sel_type = st.selectbox("활동 성격별 필터", type_options)
            if sel_type != "전체":
                # 시트에 여러 개가 적혀 있을 수 있으므로 contains 사용
                filtered_act = filtered_act[filtered_act[col_type].str.contains(sel_type, na=False)]
                
        with f2:
            # 핵심 역량 카테고리 (선생님 요청 사항)
            comp_options = ["전체", "탐구력/지식정보처리", "창의적 사고", "비판적 사고", "자기주도성/자기관리", "협력적 소통", "공동체 의식/윤리"]
            sel_comp = st.selectbox("핵심 역량별 필터", comp_options)
            if sel_comp != "전체":
                filtered_act = filtered_act[filtered_act[col_comp].str.contains(sel_comp, na=False)]
        
        st.write(f"🔍 검색 결과: 총 **{len(filtered_act)}**건")
        
        for i, row in filtered_act.sort_values('활동 일자', ascending=False).iterrows():
            st.markdown(f"""<div class="timeline-card">
<span class="badge">#{row.get(col_type,'활동')}</span>
<span class="badge" style="background:#DCFCE7; color:#166534;">🏆 {row.get(col_comp,'역량')}</span>
<div style="font-size:1.3rem; font-weight:800; color:#1E40AF; margin:10px 0;">{row.get('활동 주제','주제 없음')}</div>
<div style="font-size:0.85rem; color:#64748B; margin-bottom:15px;">📅 {row.get('활동 일자','-')} | 📚 연계 교과: {row.get('연계 가능 교과(선택)', '-')}</div>
<div style="background:#F8FAFC; padding:18px; border-radius:12px; font-size:0.95rem; line-height:1.7;">
<b>💡 활동 동기:</b><br>{row.get('활동 동기(왜 시작했나요)', '-')}<br><br>
<b>📝 핵심 활동 내용:</b><br>{row.get('핵심 활동 내용(무엇을 어떻게 했나요)', row.get('핵심 활동 내용', '-'))}<br><br>
<b>🌱 결과 및 배운 점:</b><br>{row.get('결과 및 배우고 느낀 점(어떤 변화가 있었나요?)', row.get('결과 및 배우고 느낀 점', '-'))}
</div>
</div>""", unsafe_allow_html=True)
            
            if st.button(f"🪄 AI 생기부 초안 생성 ({i})"):
                if ai_model:
                    with st.spinner("작성 중..."):
                        p = f"활동기록을 바탕으로 생기부 문구를 작성해줘(~함 체): {row.get('핵심 활동 내용', '')}"
                        try: st.info(ai_model.generate_content(p).text)
                        except Exception as e: st.error(f"AI 오류: {e}")
    else: st.info("기록된 활동이 없습니다.")
