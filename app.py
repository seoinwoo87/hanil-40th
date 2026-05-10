import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re

# ==========================================
# 1. 페이지 설정 및 디자인 (인쇄 최적화 포함)
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
    table, th, td { text-align: center !important; }

    /* 🖨️ 인쇄용 마법 코드 (Ctrl+P 누를 때 작동) */
    @media print {
        [data-testid="stSidebar"] { display: none !important; }
        header { display: none !important; }
        .block-container { max-width: 100% !important; padding: 0 !important; margin: 0 !important; }
        * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
        canvas, .js-plotly-plot { page-break-inside: avoid; }
    }
</style>
""", unsafe_allow_html=True)

def style_centered(df):
    return df.style.set_properties(**{'text-align': 'center'}).set_table_styles([dict(selector='th', props=[('text-align', 'center')])])

# ==========================================
# 2. 보안 설정 (비밀번호)
# ==========================================
def check_password():
    def password_entered():
        correct_password = st.secrets.get("admin_password", "hanil40")
        if st.session_state["password"] == correct_password:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.markdown("### 🔒 한일고 40기 상담 시스템 접속")
        st.text_input("선생님 비밀번호를 입력해주세요.", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.markdown("### 🔒 한일고 40기 상담 시스템 접속")
        st.text_input("비밀번호가 틀렸습니다. 다시 입력해주세요.", type="password", on_change=password_entered, key="password")
        st.error("😕 권한이 없습니다.")
        return False
    else:
        return True

if not check_password(): 
    st.stop()

# ==========================================
# 3. 유틸리티 로직 (계산 함수)
# ==========================================
def safe_numeric(val):
    if pd.isna(val) or val is None: return 0.0
    val_str = str(val).strip()
    if not val_str or val_str in ['-', '미응시']: return 0.0
    try:
        cleaned = re.sub(r'[^0-9.]', '', val_str)
        if cleaned.count('.') > 1:
            parts = cleaned.split('.')
            cleaned = parts[0] + '.' + ''.join(parts[1:])
        return float(cleaned) if cleaned else 0.0
    except: return 0.0

def calc_9_tier(score, all_scores):
    if all_scores.empty: return 0
    greater = (all_scores > score).sum()
    equal = (all_scores == score).sum()
    pct = ((greater + (equal / 2.0)) / len(all_scores)) * 100
    
    if pct <= 4: return 1
    elif pct <= 11: return 2
    elif pct <= 23: return 3
    elif pct <= 40: return 4
    elif pct <= 60: return 5
    elif pct <= 77: return 6
    elif pct <= 89: return 7
    elif pct <= 96: return 8
    else: return 9

def get_time_rank(row):
    t_map = {"1학년 1학기": 10, "1학년 2학기": 20, "2학년 1학기": 30, "2학년 2학기": 40, "3학년 1학기": 50, "3학년 2학기": 60}
    e_map = {"1회고사": 1, "2회고사": 2, "학기말": 3}
    return t_map.get(row.get('학기',''), 0) + e_map.get(row.get('시험',''), 0)

# ==========================================
# 4. 데이터 로드 (구글 시트 연동)
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
                df = pd.DataFrame(data[1:], columns=[str(c).strip() for c in data[0]])
                df = df.loc[:, ~df.columns.duplicated()] 
                if '학번' in df.columns:
                    df['학번'] = df['학번'].astype(str).str.replace(',', '').str.split('.').str[0].str.strip()
                    df['반'] = df['학번'].apply(lambda x: f"{x[1]}반" if len(x) >= 4 else "기타")
                n_col = next((c for c in df.columns if any(k in c for k in ['성명','이름'])), None)
                if n_col:
                    df['학생명'] = df[n_col].astype(str).str.strip()
                    df['표시식별'] = df['학번'] + " " + df['학생명']
                return df
            except: return pd.DataFrame()
            
        dfs = [process_sheet(n) for n in ["31_내신", "21_모의고사", "51_시험복기", "61_비교과", "71_상담기록", "99_학생_마스터", "22_모의고사_문항정보", "23_모의고사_학생답안"]]
        df_sc, df_mk, df_rf, df_ac, df_cs, df_ms, df_m_info, df_m_ans = dfs
        
        if not df_ms.empty and '고유번호' in df_ms.columns:
            mapping = df_ms[['학번', '고유번호']].drop_duplicates()
            def apply_uid(df):
                if not df.empty and '학번' in df.columns:
                    m = pd.merge(df, mapping, on='학번', how='left')
                    m['고유번호'] = m['고유번호'].fillna(m['표시식별'])
                    return m
                return df
            return apply_uid(df_sc), apply_uid(df_mk), apply_uid(df_rf), apply_uid(df_ac), apply_uid(df_cs), df_m_info, df_m_ans
        return [d.assign(고유번호=d.get('표시식별','')) for d in [df_sc, df_mk, df_rf, df_ac, df_cs]] + [df_m_info, df_m_ans]
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return [pd.DataFrame()]*8

df_scores, df_mock, df_ref, df_act, df_counsel, df_m_info, df_m_ans = load_all_data()

# ==========================================
# 5. [핵심수정] AI 모델 동적 할당 (404 에러 완벽 차단)
# ==========================================
try:
    genai.configure(api_key=st.secrets["gemini_api_key"])
    
    # 1. 내 API 키로 사용할 수 있는 실제 모델 리스트를 구글 서버에서 가져옵니다.
    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    
    target_model_name = None
    
    # 2. 우선순위에 따라 존재하는 모델을 안전하게 매칭합니다.
    priorities = ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-pro', 'models/gemini-1.0-pro']
    for p_model in priorities:
        if p_model in available_models:
            target_model_name = p_model
            break
            
    # 3. 위 목록에 없다면, 구글이 허락한 첫 번째 모델을 강제로 지정합니다.
    if target_model_name is None and len(available_models) > 0:
        target_model_name = available_models[0]
        
    if target_model_name:
        ai_model = genai.GenerativeModel(target_model_name)
    else:
        ai_model = None
except Exception as e:
    ai_model = None

# ==========================================
# 6. 사이드바 구성 및 [AI 기억장치 초기화]
# ==========================================
query_params = st.query_params

with st.sidebar:
    st.title("🏫 상담 시스템 v2")
    sel_term = st.selectbox("📅 학기 선택", sorted(df_scores['학기'].unique(), reverse=True) if not df_scores.empty else [])
    sel_class = st.selectbox("🏘️ 학급 선택", sorted(df_scores[df_scores['학기'] == sel_term]['반'].unique()) if sel_term else [])
    
    class_students = df_scores[(df_scores['학기'] == sel_term) & (df_scores['반'] == sel_class)] if sel_term else pd.DataFrame()
    s_list = ["학생을 선택해주세요"] + sorted(class_students['표시식별'].unique().tolist()) if not class_students.empty else ["학생을 선택해주세요"]
    
    d_idx = s_list.index(query_params["student"]) if "student" in query_params and query_params["student"] in s_list else 0
    sel_student = st.selectbox("👤 학생 선택", s_list, index=d_idx)
    
    if sel_student == "학생을 선택해주세요":
        if "student" in st.query_params: del st.query_params["student"]
        st.title("🏫 한일고 40기 통합 상담 시스템")
        st.markdown("""
        <div style="background-color: #FFFFFF; padding: 40px; border-radius: 15px; border: 1px solid #E2E8F0; text-align: center; margin-top: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
            <h2 style="color: #1E40AF; margin-bottom: 15px;">환영합니다, 선생님! 👋</h2>
            <p style="font-size: 1.15rem; color: #475569; line-height: 1.8;">
                학생 상담을 시작하시려면 <b>왼쪽 사이드바</b>에서 <b>학급</b>과 <b>학생 이름</b>을 선택해주세요.
            </p>
        </div>
        """, unsafe_allow_html=True)
        st.stop()
        
    st.query_params["student"] = sel_student
    sel_uid = class_students[class_students['표시식별'] == sel_student]['고유번호'].iloc[0]
    sel_name = sel_student.split(" ")[1]
    
    # [기억장치] 학생이 바뀌면 AI 답변 저장소 초기화
    if "current_student" not in st.session_state or st.session_state["current_student"] != sel_uid:
        st.session_state["current_student"] = sel_uid
        st.session_state["ai_cache"] = {} 

    st.markdown("---")
    menu_list = ["📈 내신 분석", "🎯 모의고사 분석", "🧠 성찰 리포트", "🏆 비교과 타임라인", "📝 상담 기록"]
    d_menu_idx = menu_list.index(query_params["menu"]) if "menu" in query_params and query_params["menu"] in menu_list else 0
    menu = st.radio("📑 분석 메뉴", menu_list, index=d_menu_idx)
    st.query_params["menu"] = menu

st.header(f"📊 {sel_student} 분석 리포트")

# ==========================================
# 7. 내신 분석
# ==========================================
if menu == "📈 내신 분석":
    t1, t2, t3 = st.tabs(["📊 상세 성적", "📉 학기별 평점", "📈 과목군 추이"])
    uid_scores = df_scores[df_scores['고유번호'] == sel_uid].copy()
    s_col = next((c for c in uid_scores.columns if '점수' in c.replace(" ","")), '점수')
    
    with t1:
        st.subheader(f"📍 {sel_term} 상세 성적")
        exam = st.selectbox("시험 선택", ["1회고사", "2회고사", "학기말"])
        f = uid_scores[(uid_scores['학기'] == sel_term) & (uid_scores['시험'] == exam)].copy()
        if not f.empty:
            if exam == "학기말":
                cols = st.columns(len(f))
                for i, (_, r) in enumerate(f.iterrows()): 
                    cols[i].metric(r['과목'], f"{r.get('등급','-')}등급 ({r.get('성취도','')})".strip())
            else:
                p_d = []
                for _, r in f.iterrows():
                    all_e = df_scores[(df_scores['학기']==sel_term)&(df_scores['시험']==exam)&(df_scores['과목']==r['과목'])][s_col].apply(safe_numeric).dropna()
                    my_s = safe_numeric(r.get(s_col,0))
                    median_val = all_e.median() if not all_e.empty else 0
                    calc_perc = (all_e <= my_s).sum() / len(all_e) * 100 if not all_e.empty else 0
                    p_d.append({'과목':r['과목'], '점수':round(my_s,2), '중위값':round(median_val,2), '백분위':round(calc_perc,2)})
                    
                pdf = pd.DataFrame(p_d)
                fig = px.bar(pdf, x='과목', y='점수', color='과목', text=pdf['점수'].apply(lambda x: f"{x:.2f}"), color_discrete_sequence=px.colors.qualitative.Pastel)
                fig.add_trace(go.Scatter(x=pdf['과목'], y=pdf['중위값'], name="학년 중위값", mode='markers', marker=dict(size=12, color='black', symbol='diamond')))
                fig.add_trace(go.Scatter(x=pdf['과목'], y=pdf['백분위'], name="백분위(%)", yaxis="y2", mode='lines+markers', line=dict(color='red', width=2)))
                fig.update_layout(yaxis=dict(title="원점수", range=[0,105]), yaxis2=dict(overlaying="y", side="right", title="백분위(%)", range=[0,105]))
                st.plotly_chart(fig, use_container_width=True)
                st.table(style_centered(pdf[['과목', '점수', '중위값', '백분위']].rename(columns={'점수':'내 점수', '백분위':'백분위(%)'})).format(precision=2))
        else: 
            st.info("데이터가 없습니다.")
            
    with t2:
        st.subheader("📑 학기말 성적 및 내신 평점 산출")
        f_df = uid_scores[uid_scores['시험'] == '학기말'].copy()
        u_col = '단위' if '단위' in f_df.columns else ('이수단위' if '이수단위' in f_df.columns else '')
        if not f_df.empty and u_col:
            f_df['9등급(자동)'] = f_df.apply(lambda r: calc_9_tier(safe_numeric(r.get(s_col,0)), df_scores[(df_scores['학기']==r['학기'])&(df_scores['시험']=='학기말')&(df_scores['과목']==r['과목'])][s_col].apply(safe_numeric).dropna()), axis=1)
            sel_rows = st.data_editor(f_df[[c for c in ['학기','과목','점수','등급','성취도',u_col,'9등급(자동)'] if c in f_df.columns]], use_container_width=True)
            c_df = sel_rows[sel_rows[u_col].apply(safe_numeric)>0].copy()
            if not c_df.empty:
                t_u = c_df[u_col].apply(safe_numeric).sum()
                g5 = (c_df['등급'].apply(safe_numeric)*c_df[u_col].apply(safe_numeric)).sum()/t_u if t_u > 0 else 0
                g9 = (c_df['9등급(자동)']*c_df[u_col].apply(safe_numeric)).sum()/t_u if t_u > 0 else 0
                c1, c2 = st.columns(2)
                c1.metric("📊 5등급제 평점", f"{g5:.2f} 등급")
                c2.metric("📊 9등급제 평점 (자동 산출)", f"{g9:.2f} 등급")
        else: 
            st.info("학기말 데이터와 '단위' 열이 필요합니다.")
            
    with t3:
        st.subheader("📈 과목군별 누적 성적 추이 (백분위 기준)")
        if '교과군' in uid_scores.columns:
            trend_df = uid_scores[uid_scores['시험'].str.contains('고사')].copy()
            
            def get_hist_perc(row):
                all_e = df_scores[(df_scores['학기']==row['학기'])&(df_scores['시험']==row['시험'])&(df_scores['과목']==row['과목'])][s_col].apply(safe_numeric).dropna()
                my_s = safe_numeric(row.get(s_col,0))
                return (all_e <= my_s).sum() / len(all_e) * 100 if not all_e.empty else 0
                
            trend_df['백분위'] = trend_df.apply(get_hist_perc, axis=1)
            trend_df['점수'] = trend_df[s_col].apply(safe_numeric)
            trend_df['시기'] = trend_df['학기'] + " " + trend_df['시험']
            trend_df['순서'] = trend_df.apply(get_time_rank, axis=1)
            trend_df = trend_df.sort_values('순서')
            
            s_g = st.multiselect("교과군", sorted(trend_df['교과군'].dropna().unique()), default=sorted(trend_df['교과군'].dropna().unique())[:1])
            if s_g: 
                plot_t = trend_df[trend_df['교과군'].isin(s_g)]
                fig_t = px.line(plot_t, x='시기', y='백분위', color='과목', markers=True, text=plot_t['점수'].apply(lambda x: f"{x:.2f}"))
                fig_t.update_traces(textposition="top center")
                fig_t.update_layout(yaxis=dict(title="백분위(%) - 높을수록 상위권", range=[-5, 110]))
                st.plotly_chart(fig_t, use_container_width=True)
                st.info("💡 Y축은 상대적 위치(백분위)이며, 점 위의 숫자는 실제 원점수입니다.")

# ==========================================
# 8. 모의고사 분석 (O/X 처리 및 누적 분석, AI 기억 포함)
# ==========================================
elif menu == "🎯 모의고사 분석":
    mt1, mt2, mt3 = st.tabs(["📉 전체 성적 추이", "🔍 단일 시험 분석", "📊 누적 취약점 분석"])
    uid_mk = df_mock[df_mock['고유번호'] == sel_uid].copy()
    
    with mt1:
        if not uid_mk.empty:
            latest = uid_mk.iloc[-1]
            st.subheader(f"🎯 최근 모의고사 요약: {latest.get('시험명', '최근 시험')}")
            subj_map = {"국어": ["국어"], "수학": ["수학"], "영어": ["영어"], "한국사": ["한국사", "국사"], "사탐": ["사탐", "사회"], "과탐": ["과탐", "과학"]}
            summary = []
            for n, keys in subj_map.items():
                def f_val(k_list, target_k):
                    for col in latest.index:
                        if any(s in str(col).replace(" ", "").replace("_", "").lower() for s in k_list) and target_k in str(col): return latest[col]
                    return '-'
                v_p = f_val(keys, '표'); v_b = f_val(keys, '백분'); v_g = f_val(keys, '등급')
                
                try: f_score = f"{int(float(v_p))}"
                except: f_score = v_p
                try: f_perc = f"{float(v_b):.2f}%"
                except: f_perc = v_b if v_b == '-' else f"{v_b}%"
                try: f_grade = f"{int(float(v_g))}등급"
                except: f_grade = v_g if v_g == '-' else f"{v_g}등급"
                
                summary.append({"과목": n, "표준점수": f_score, "백분위": f_perc, "등급": f_grade})
                
            st.table(style_centered(pd.DataFrame(summary)))
            st.markdown("---")
            
            p_cols = [c for c in uid_mk.columns if '백분' in c]
            if p_cols:
                plot_m = uid_mk[['시험명'] + p_cols].copy()
                for c in p_cols: plot_m[c] = plot_m[c].apply(safe_numeric)
                st.plotly_chart(px.line(plot_m.melt(id_vars=['시험명'], var_name='과목', value_name='백분위'), x='시험명', y='백분위', color='과목', markers=True).update_layout(yaxis=dict(range=[0, 105])), use_container_width=True)
            st.dataframe(style_centered(uid_mk.drop(columns=['학번', '표시식별', '학생명', '반', '고유번호'], errors='ignore')), use_container_width=True)
        else: 
            st.info("모의고사 기록이 없습니다.")

    with mt2:
        st.subheader("🔍 단일 시험 오답 및 AI 정밀 분석")
        if not df_m_info.empty and not df_m_ans.empty:
            s_ex = st.selectbox("시험 선택", df_m_ans['시험명'].unique(), key='mk2_ex')
            s_su = st.selectbox("과목 선택", df_m_ans[df_m_ans['시험명']==s_ex]['과목'].unique(), key='mk2_su')
            
            ex_i = df_m_info[(df_m_info['시험명']==s_ex)&(df_m_info['과목']==s_su)].copy()
            st_a = df_m_ans[(df_m_ans['시험명']==s_ex)&(df_m_ans['과목']==s_su)&(df_m_ans['고유번호']==sel_uid)]
            
            if not ex_i.empty and not st_a.empty:
                raw_ox = str(st_a.iloc[0]['OMR답안'])
                clean_ox = re.sub(r'[^OXox]', '', raw_ox).upper()
                ox_list = list(clean_ox)
                
                ex_i['채점결과'] = [ox_list[i] if i<len(ox_list) else 'X' for i in range(len(ex_i))]
                ex_i['채점'] = ex_i['채점결과'].apply(lambda x: 1 if x == 'O' else 0)
                
                wrong = ex_i[ex_i['채점'] == 0].copy()
                
                if wrong.empty:
                    st.success("🎉 축하합니다! 이 과목은 틀린 문항이 없습니다 (100점).")
                else:
                    safe_cols = []
                    target_cols = ['문항번호', '문항 번호', '정답', '채점결과', '출제 의도', '출제의도', '배점']
                    for col in target_cols:
                        if col in wrong.columns and col not in safe_cols: safe_cols.append(col)
                    
                    st.markdown(f"**💡 {sel_name} 학생의 오답 목록**")
                    st.table(style_centered(wrong[safe_cols].copy()))
                    
                    # [AI 기억 기능 적용]
                    cache_key = f"mock_single_{s_ex}_{s_su}"
                    if st.button("🤖 개조식 AI 맞춤형 처방전 생성"):
                        if ai_model:
                            with st.spinner("AI가 분석을 생성 중입니다..."):
                                it_col = '출제 의도' if '출제 의도' in wrong.columns else ('출제의도' if '출제의도' in wrong.columns else None)
                                weak_points = ", ".join(wrong[it_col].astype(str).tolist()) if it_col else "출제 의도 정보 없음"
                                
                                prompt = f"""
                                당신은 대한민국 최고 수준의 고등학교 입시/교과 데이터 분석가입니다.
                                학생이 모의고사 {s_su} 과목에서 틀린 문항들의 출제 의도는 다음과 같습니다: [{weak_points}]
                                
                                이 데이터를 종합하여 다음을 도출하세요:
                                1. 핵심 취약점 (틀린 문제들을 관통하는 개념적 약점)
                                2. 맞춤형 보완 전략 (구체적인 학습 방법)
                                
                                [작성 규칙]
                                - 반드시 간결하고 명확한 '개조식(명사형 종결, ~함, ~임 등)'으로 작성할 것.
                                - 대화형 문구(~해요, ~습니다 등) 및 미사여구 절대 금지.
                                - 글머리 기호(-, 1., 2. 등)를 사용하여 가독성을 극대화할 것.
                                """
                                try:
                                    st.session_state["ai_cache"][cache_key] = ai_model.generate_content(prompt).text
                                except Exception as e: st.error(f"오류: {e}")
                        else:
                            st.warning("AI 모델을 사용할 수 없습니다. 인터넷 연결과 API 키를 확인해주세요.")
                    
                    if cache_key in st.session_state["ai_cache"]:
                        st.markdown(f'<div class="ai-container"><b>🤖 AI 개조식 학습 처방전</b><br><br>{st.session_state["ai_cache"][cache_key]}</div>', unsafe_allow_html=True)
            else: 
                st.warning("데이터가 부족합니다.")
        else:
            st.info("문항 정보 또는 학생 답안 시트에 데이터를 채워주세요.")

    with mt3:
        st.subheader("📊 누적 취약점 분석 (전체 모의고사 통합)")
        if not df_m_info.empty and not df_m_ans.empty:
            user_all_ans = df_m_ans[df_m_ans['고유번호'] == sel_uid].copy()
            if user_all_ans.empty:
                st.info("해당 학생의 모의고사 답안 기록이 없습니다.")
            else:
                sel_subj_cum = st.selectbox("누적 분석할 과목 선택", user_all_ans['과목'].unique(), key='cum_subj')
                user_subj_ans = user_all_ans[user_all_ans['과목'] == sel_subj_cum]
                
                all_wrong_intents = []
                for _, ans_row in user_subj_ans.iterrows():
                    exam_name = ans_row['시험명']
                    raw_ox = str(ans_row['OMR답안'])
                    clean_ox = re.sub(r'[^OXox]', '', raw_ox).upper()
                    ox_list = list(clean_ox)
                    
                    exam_info = df_m_info[(df_m_info['시험명'] == exam_name) & (df_m_info['과목'] == sel_subj_cum)].copy()
                    if not exam_info.empty:
                        exam_info['채점결과'] = [ox_list[i] if i < len(ox_list) else 'X' for i in range(len(exam_info))]
                        exam_info['채점'] = exam_info['채점결과'].apply(lambda x: 1 if x == 'O' else 0)
                        
                        wrong_df = exam_info[exam_info['채점'] == 0]
                        intent_col = '출제 의도' if '출제 의도' in wrong_df.columns else ('출제의도' if '출제의도' in wrong_df.columns else None)
                        if intent_col:
                            all_wrong_intents.extend(wrong_df[intent_col].dropna().astype(str).tolist())
                
                if not all_wrong_intents:
                    st.success(f"{sel_subj_cum} 과목에서 누적된 오답 기록이 없습니다.")
                else:
                    st.markdown(f"**💡 {sel_name} 학생이 {sel_subj_cum} 과목에서 누적해서 틀린 문제들의 출제 의도 목록**")
                    st.info(", ".join(all_wrong_intents))
                    
                    # [AI 기억 기능 적용]
                    cache_key = f"mock_cum_{sel_subj_cum}"
                    if st.button("🤖 AI 유사 패턴 클러스터링 및 장기 로드맵 생성"):
                        if ai_model:
                            with st.spinner("AI가 공통된 약점 패턴을 찾아내고 있습니다..."):
                                all_weakness_str = ", ".join(all_wrong_intents)
                                prompt_cum = f"""
                                당신은 대한민국 최고 수준의 고등학교 입시/교과 데이터 분석가입니다.
                                학생이 지금까지 치른 모든 모의고사 {sel_subj_cum} 과목에서 틀린 문제들의 '출제 의도'를 모두 모아놓은 데이터입니다: [{all_weakness_str}]
                                
                                비록 표현들이 서로 다르더라도, 당신의 언어 이해 능력을 활용하여 '유사한 개념이나 요구 역량'끼리 묶어(클러스터링) 분석해 주세요.
                                
                                다음 내용을 반드시 포함하세요:
                                1. 누적 핵심 취약점 1~3가지 (공통된 인지적 결손)
                                2. 단기 꼼수가 아닌, 본질적 체질 개선을 위한 장기 학습 로드맵
                                
                                [작성 규칙]
                                - 반드시 간결하고 명확한 '개조식(명사형 종결, ~함, ~임 등)'으로 작성.
                                - 대화형 문구 절대 금지.
                                - 구조화된 글머리 기호를 사용할 것.
                                """
                                try:
                                    st.session_state["ai_cache"][cache_key] = ai_model.generate_content(prompt_cum).text
                                except Exception as e: st.error(f"AI 오류: {e}")
                        else:
                            st.warning("AI 모델을 사용할 수 없습니다. 인터넷 연결과 API 키를 확인해주세요.")
                                
                    if cache_key in st.session_state["ai_cache"]:
                        st.markdown(f'<div class="ai-container"><b>🤖 AI 누적 약점 정밀 보고서</b><br><br>{st.session_state["ai_cache"][cache_key]}</div>', unsafe_allow_html=True)

# ==========================================
# 9. 성찰 리포트 (기억 기능 추가)
# ==========================================
elif menu == "🧠 성찰 리포트":
    curr_y = sel_term[:3] if sel_term else ""
    
    if '학기' in df_ref.columns: uid_ref = df_ref[(df_ref['고유번호'] == sel_uid) & (df_ref['학기'].str.contains(curr_y))].copy()
    elif '시험명' in df_ref.columns: uid_ref = df_ref[(df_ref['고유번호'] == sel_uid) & (df_ref['시험명'].str.contains(curr_y))].copy()
    else: uid_ref = df_ref[df_ref['고유번호'] == sel_uid].copy()
    
    if not uid_ref.empty:
        s_ex = st.selectbox("시험 선택", uid_ref['시험명'].unique())
        row = uid_ref[uid_ref['시험명'] == s_ex].iloc[-1]
        
        cols = st.columns(2)
        idx = 0
        for k, v in row.items():
            if k in ['타임스탬프', '학번', '이름', '성명', '학생식별', '표시식별', '학생명', '시험명', '반', '고유번호', '학기'] or not v: continue
            with cols[idx % 2]: st.markdown(f'<div style="background:white; border-left:5px solid #3B82F6; padding:15px; margin-bottom:10px; border-radius:10px;"><b>{k}</b><br>{v}</div>', unsafe_allow_html=True)
            idx += 1
            
        st.markdown("---")
        cache_key = f"ref_{s_ex}"
        if st.button("🤖 AI 성찰 기반 피드백 생성"):
            if ai_model:
                with st.spinner("AI 분석 중..."):
                    clean_data = {str(k): str(v) for k, v in row.items() if len(str(v)) > 5 and k not in ['학번', '타임스탬프']}
                    prompt = f"다음은 학생의 학습 성찰 내용입니다: {str(clean_data)}. 교사의 입장에서 조언을 개조식 명사형(~함, ~임)으로 작성해주세요."
                    try:
                        st.session_state["ai_cache"][cache_key] = ai_model.generate_content(prompt).text
                    except Exception as e: st.error(f"오류: {e}")
            else:
                st.warning("AI 모델을 사용할 수 없습니다.")
                    
        if cache_key in st.session_state["ai_cache"]:
            st.markdown(f'<div class="ai-container"><b>🤖 AI 상담 조언</b><br><br>{st.session_state["ai_cache"][cache_key]}</div>', unsafe_allow_html=True)
    else: 
        st.info("성찰 기록이 없습니다.")

# ==========================================
# 10. 비교과 타임라인 (기억 기능 추가)
# ==========================================
elif menu == "🏆 비교과 타임라인":
    curr_y = sel_term[:3] if sel_term else ""
    t_col = next((c for c in df_act.columns if any(k in c for k in ['학년', '학기', '시기', '연도'])), None)
    
    uid_act = df_act[(df_act['고유번호'] == sel_uid) & (df_act[t_col].str.contains(curr_y, na=False))].copy() if t_col else df_act[df_act['고유번호'] == sel_uid].copy()
    
    if not uid_act.empty:
        col_type = next((c for c in uid_act.columns if '성격' in c), None)
        col_comp = next((c for c in uid_act.columns if '역량' in c), None)
        
        st.subheader("📊 핵심역량별 활동 분포")
        comp_standards = ["탐구력/지식정보처리", "창의적 사고", "비판적 사고", "자기주도성/자기관리", "협력적 소통", "공동체 의식/윤리"]
        s_cols = st.columns(6)
        for i, comp_name in enumerate(comp_standards):
            count = uid_act[col_comp].str.contains(comp_name, na=False).sum() if col_comp else 0
            with s_cols[i]: st.markdown(f'<div class="stat-box"><small style="color:#64748B; font-size:0.75rem;">{comp_name}</small><br><b style="font-size:1.4rem; color:#2563EB;">{count}건</b></div>', unsafe_allow_html=True)
                
        st.markdown("---")
        f1, f2 = st.columns(2)
        filtered_act = uid_act.copy()
        
        with f1:
            type_opts = ["전체", "자율 활동", "진로 활동", "독서 활동", "문헌 탐구 활동", "협력 토론 활동", "실증 탐구 활동", "비평 성찰 활동", "발표 공유 활동", "융합 탐구 활동", "교사 개별 상담"]
            sel_type = st.selectbox("활동 성격별 필터", type_opts)
            if sel_type != "전체" and col_type: filtered_act = filtered_act[filtered_act[col_type].str.contains(sel_type, na=False)]
        with f2:
            comp_opts = ["전체"] + comp_standards
            sel_comp = st.selectbox("핵심 역량별 필터", comp_opts)
            if sel_comp != "전체" and col_comp: filtered_act = filtered_act[filtered_act[col_comp].str.contains(sel_comp, na=False)]
        
        st.write(f"🔍 검색 결과: 총 **{len(filtered_act)}**건")
        
        for i, row in filtered_act.sort_values('활동 일자', ascending=False).iterrows():
            st.markdown(f"""
            <div class="timeline-card">
                <span class="badge">#{row.get(col_type,'활동')}</span>
                <span class="badge" style="background:#DCFCE7; color:#166534;">🏆 {row.get(col_comp,'역량')}</span>
                <div style="font-size:1.3rem; font-weight:800; color:#1E40AF; margin:10px 0;">{row.get('활동 주제','주제 없음')}</div>
                <div style="font-size:0.85rem; color:#64748B; margin-bottom:15px;">📅 {row.get('활동 일자','-')} | 📚 연계 교과: {row.get('연계 가능 교과(선택)', '-')}</div>
                <div style="background:#F8FAFC; padding:18px; border-radius:12px; font-size:0.95rem; line-height:1.7;">
                    <b>💡 활동 동기:</b><br>{row.get('활동 동기(왜 시작했나요)', '-')}<br><br>
                    <b>📝 핵심 활동 내용:</b><br>{row.get('핵심 활동 내용(무엇을 어떻게 했나요)', row.get('핵심 활동 내용', '-'))}<br><br>
                    <b>🌱 결과 및 배운 점:</b><br>{row.get('결과 및 배우고 느낀 점(어떤 변화가 있었나요?)', row.get('결과 및 배우고 느낀 점', '-'))}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            cache_key = f"act_{i}"
            if st.button(f"🪄 AI 생기부 초안 생성 (기록번호: {i})"):
                if ai_model:
                    with st.spinner("작성 중..."):
                        try:
                            st.session_state["ai_cache"][cache_key] = ai_model.generate_content(f"활동 내용: {row.get('핵심 활동 내용', '')}. 이를 바탕으로 생기부에 들어갈 문구를 개조식(~함, ~임)으로 작성해줘.").text
                        except Exception as e: st.error(f"오류: {e}")
                else:
                    st.warning("AI 모델을 사용할 수 없습니다.")
            if cache_key in st.session_state["ai_cache"]:
                st.info(st.session_state["ai_cache"][cache_key])
    else: 
        st.info("활동 기록이 없습니다.")

# ==========================================
# 11. 상담 기록 작성 (학번 기반 인간 친화적 저장)
# ==========================================
elif menu == "📝 상담 기록":
    uid_counsel = pd.DataFrame()
    
    if not df_counsel.empty:
        if '고유번호' in df_counsel.columns:
            uid_counsel = df_counsel[df_counsel['고유번호'] == sel_uid].copy()
        elif '학번' in df_counsel.columns:
            sel_hakbun = sel_student_label.split(" ")[0]
            uid_counsel = df_counsel[df_counsel['학번'].astype(str) == sel_hakbun].copy()

    st.subheader(f"📖 {sel_name} 누적 상담 기록")
    if not uid_counsel.empty and '상담일자' in uid_counsel.columns:
        for i, row in uid_counsel.sort_values('상담일자', ascending=False).iterrows():
            st.markdown(f"""
            <div class="timeline-card" style="border-left: 6px solid #8B5CF6;">
                <span class="badge" style="background:#F3E8FF; color:#7E22CE;">🗣️ {row.get("상담유형", "일반 상담")}</span>
                <div style="font-size:0.85rem; color:#64748B; margin-bottom:10px;">📅 {row.get("상담일자", "-")}</div>
                <div style="background:#F8FAFC; padding:18px; border-radius:12px; font-size:0.95rem; line-height:1.7;">
                    {row.get("상담내용", "-")}
                </div>
            </div>
            """, unsafe_allow_html=True)
    else: 
        st.info("이전에 작성된 상담 기록이 없습니다.")
        
    st.markdown("---")
    st.subheader("✍️ 신규 상담 기록 작성")
    
    with st.form("counsel_form", clear_on_submit=True):
        c_date = st.date_input("상담 일자")
        c_type = st.selectbox("상담 유형", ["학습/성적", "진로/진학", "학교생활/교우관계", "심리/정서", "기타"])
        c_content = st.text_area("상담 내용 및 결과", height=150, placeholder="내용을 입력해주세요.")
        
        if st.form_submit_button("💾 저장하기"):
            if c_content.strip() != "":
                with st.spinner("구글 시트에 저장 중입니다..."):
                    try:
                        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
                        client = gspread.authorize(creds)
                        doc = client.open("40기 마스터 파일")
                        
                        try: 
                            sh = doc.worksheet("71_상담기록")
                        except:
                            sh = doc.add_worksheet(title="71_상담기록", rows="1000", cols="10")
                            sh.append_row(["학번", "이름", "상담일자", "상담유형", "상담내용"])
                            
                        sel_hakbun = sel_student_label.split(" ")[0]
                        sh.append_row([sel_hakbun, sel_name, str(c_date), c_type, c_content])
                        
                        st.cache_resource.clear() 
                        st.success("✅ 저장 완료! 앱을 '새로고침(F5)' 하시면 기록이 나타납니다.")
                        
                    except Exception as e: 
                        st.error(f"저장 중 오류 발생: {e}")
