import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import datetime

# ==========================================
# 1. 페이지 설정 및 디자인 (인쇄 강제 숨김 강화)
# ==========================================
st.set_page_config(page_title="한일고 40기 상담 시스템", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght=400;600;800&display=swap');
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif; background-color: #F8FAFC; }
    .stMetric { background: white; border: 1px solid #E2E8F0; padding: 15px !important; border-radius: 12px !important; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }
    .timeline-card { background: white; border: 1px solid #E2E8F0; border-radius: 15px; padding: 25px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.03); border-left: 6px solid #2563EB; }
    .badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: 700; background: #EFF6FF; color: #1D4ED8; margin-bottom: 10px; margin-right: 5px; }
    .stat-box { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 15px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }
    table, th, td { text-align: center !important; }

    /* 🖨️ 인쇄 미리보기 레이아웃 전면 개조 (사이드바 완벽 차단) */
    @media print {
        /* 1. 스트림릿의 사이드바 관련 모든 요소를 클래스명까지 추적해서 강제 삭제 */
        [data-testid="stSidebar"], 
        [data-testid="stSidebarCollapseButton"],
        .stSidebar, 
        section[data-testid="stSidebar"] {
            display: none !important;
            width: 0px !important;
            visibility: hidden !important;
        }
        
        /* 2. 상단 헤더, 여백 조절용 컴포넌트, 상단 메뉴 싹 제거 */
        header, .print-hide, button, [data-testid="stForm"], [data-testid="stToolbar"] { 
            display: none !important; 
            visibility: hidden !important;
        }
        
        /* 3. 본문 영역이 왼쪽 사이드바가 있던 빈 자리를 채우도록 폭 100% 강제 세팅 */
        .block-container { 
            max-width: 100% !important; 
            width: 100% !important;
            padding: 15mm 15mm 15mm 15mm !important; 
            margin: 0 !important; 
            position: absolute !important;
            left: 0 !important;
            top: 0 !important;
            background-color: #FFFFFF !important;
        }
        
        /* 4. 종이 인쇄 시 텍스트 및 테이블 가독성 확보 */
        html, body, [class*="css"] { 
            background-color: #FFFFFF !important; 
            color: #000000 !important;
        }
        
        .timeline-card, table, .js-plotly-plot, tr { 
            page-break-inside: avoid !important; 
        }
    }
</style>
""", unsafe_allow_html=True)

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
        st.text_input("선생님 공통 비밀번호를 입력해주세요.", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.markdown("### 🔒 한일고 40기 상담 시스템 접속")
        st.text_input("비밀번호가 틀렸습니다. 다시 입력해주세요.", type="password", on_change=password_entered, key="password")
        st.error("😕 권한이 없습니다.")
        return False
    return True

if not check_password(): st.stop()

# ==========================================
# 3. 계산 로직 함수
# ==========================================
def safe_numeric(val):
    if pd.isna(val) or val is None: return 0.0
    val_str = str(val).strip()
    if not val_str or val_str in ['-', '미응시']: return 0.0
    try:
        cleaned = re.sub(r'[^0-9.]', '', val_str)
        if cleaned.count('.') > 1: parts = cleaned.split('.'); cleaned = parts[0] + '.' + ''.join(parts[1:])
        return float(cleaned) if cleaned else 0.0
    except: return 0.0

def calc_9_tier(score, all_scores):
    if all_scores.empty: return 0
    pct = (((all_scores > score).sum() + ((all_scores == score).sum() / 2.0)) / len(all_scores)) * 100
    if pct <= 4: return 1
    elif pct <= 11: return 2
    elif pct <= 23: return 3
    elif pct <= 40: return 4
    elif pct <= 60: return 5
    elif pct <= 77: return 6
    elif pct <= 89: return 7
    elif pct <= 96: return 8
    else: return 9

def calc_5_tier(score, all_scores):
    if all_scores.empty: return 0
    pct = (((all_scores > score).sum() + ((all_scores == score).sum() / 2.0)) / len(all_scores)) * 100
    if pct <= 10: return 1
    elif pct <= 34: return 2
    elif pct <= 66: return 3
    elif pct <= 90: return 4
    else: return 5

def get_time_rank(row):
    t_map = {"1학년 1학기": 10, "1학년 2학기": 20, "2학년 1학기": 30, "2학년 2학기": 40, "3학년 1학기": 50, "3학년 2학기": 60}
    e_map = {"1회고사": 1, "2회고사": 2, "학기말": 3}
    return t_map.get(row.get('학기',''), 0) + e_map.get(row.get('시험',''), 0)

# ==========================================
# 4. 구글 시트 연동
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

try:
    genai.configure(api_key=st.secrets["gemini_api_key"])
    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    target_model_name = next((p for p in ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-pro', 'models/gemini-1.0-pro'] if p in available_models), available_models[0] if available_models else None)
    ai_model = genai.GenerativeModel(target_model_name) if target_model_name else None
except Exception: ai_model = None

# ==========================================
# 5. 사이드바 메뉴 
# ==========================================
query_params = st.query_params

with st.sidebar:
    st.title("🏫 상담 시스템 v2")
    st.markdown("<div style='text-align: right; font-size: 0.8rem; color: #94A3B8; margin-top: -15px; margin-bottom: 20px;'><i>✨ made by 40 admin</i></div>", unsafe_allow_html=True)
    if st.button("🔄 최신 데이터 불러오기", use_container_width=True):
        st.cache_resource.clear()
        st.rerun()

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
            <p style="font-size: 1.15rem; color: #475569; line-height: 1.8;">학생 상담을 시작하시려면 <b>왼쪽 사이드바</b>에서 <b>학급</b>과 <b>학생 이름</b>을 선택해주세요.</p>
        </div>
        """, unsafe_allow_html=True)
        st.stop()
        
    st.query_params["student"] = sel_student
    sel_uid = class_students[class_students['표시식별'] == sel_student]['고유번호'].iloc[0]
    sel_name = sel_student.split(" ")[1]
    
    if "current_student" not in st.session_state or st.session_state["current_student"] != sel_uid:
        st.session_state["current_student"] = sel_uid
        st.session_state["ai_cache"] = {} 

    menu_list = ["📈 내신 분석", "🎯 모의고사 분석", "🧠 성찰 리포트", "🏆 비교과 타임라인", "📝 상담 기록", "🖨️ 맞춤형 리포트 출력", "🌟 학급 대시보드"]
    d_menu_idx = menu_list.index(query_params["menu"]) if "menu" in query_params and query_params["menu"] in menu_list else 0
    menu = st.radio("📑 분석 메뉴", menu_list, index=d_menu_idx)
    st.query_params["menu"] = menu

st.header(f"📊 {sel_student} 분석 리포트" if menu not in ["🖨️ 맞춤형 리포트 출력", "🌟 학급 대시보드"] else "")

# ==========================================
# 6. 내신 분석
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
        else: st.info("데이터가 없습니다.")
            
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
        else: st.info("학기말 데이터와 '단위' 열이 필요합니다.")
            
    with t3:
        st.subheader("📈 과목군별 누적 성적 추이 (백분위 기준)")
        if '교과군' in uid_scores.columns:
            trend_df = uid_scores[uid_scores['시험'].str.contains('고사')].copy()
            trend_df['백분위'] = trend_df.apply(lambda r: ((df_scores[(df_scores['학기']==r['학기'])&(df_scores['시험']==r['시험'])&(df_scores['과목']==r['과목'])][s_col].apply(safe_numeric).dropna() <= safe_numeric(r.get(s_col,0))).sum() / len(df_scores[(df_scores['학기']==r['학기'])&(df_scores['시험']==r['시험'])&(df_scores['과목']==r['과목'])][s_col].apply(safe_numeric).dropna()) * 100) if not df_scores[(df_scores['학기']==r['학기'])&(df_scores['시험']==r['시험'])&(df_scores['과목']==r['과목'])][s_col].apply(safe_numeric).dropna().empty else 0, axis=1)
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

# ==========================================
# 7. 모의고사 분석
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
                summary.append({"과목": n, "표준점수": v_p, "백분위": v_b if v_b=='-' else f"{v_b}%", "등급": v_g if v_g=='-' else f"{v_g}등급"})
            st.table(style_centered(pd.DataFrame(summary)))
            st.markdown("---")
            p_cols = [c for c in uid_mk.columns if '백분' in c]
            if p_cols:
                plot_m = uid_mk[['시험명'] + p_cols].copy()
                for c in p_cols: plot_m[c] = plot_m[c].apply(safe_numeric)
                st.plotly_chart(px.line(plot_m.melt(id_vars=['시험명'], var_name='과목', value_name='백분위'), x='시험명', y='백분위', color='과목', markers=True).update_layout(yaxis=dict(range=[0, 105])), use_container_width=True)
            st.dataframe(style_centered(uid_mk.drop(columns=['학번', '표시식별', '학생명', '반', '고유번호'], errors='ignore')), use_container_width=True)
        else: st.info("모의고사 기록이 없습니다.")

    with mt2:
        st.subheader("🔍 단일 시험 오답 분석")
        if not df_m_info.empty and not df_m_ans.empty:
            s_ex = st.selectbox("시험 선택", df_m_ans['시험명'].unique(), key='mk2_ex')
            s_su = st.selectbox("과목 선택", df_m_ans[df_m_ans['시험명']==s_ex]['과목'].unique(), key='mk2_su')
            ex_i = df_m_info[(df_m_info['시험명']==s_ex)&(df_m_info['과목']==s_su)].copy()
            st_a = df_m_ans[(df_m_ans['시험명']==s_ex)&(df_m_ans['과목']==s_su)&(df_m_ans['고유번호']==sel_uid)]
            if not ex_i.empty and not st_a.empty:
                ox_list = list(re.sub(r'[^OXox]', '', str(st_a.iloc[0]['OMR답안'])).upper())
                ex_i['채점결과'] = [ox_list[i] if i<len(ox_list) else 'X' for i in range(len(ex_i))]
                wrong = ex_i[ex_i['채점결과'] == 'X'].copy()
                if wrong.empty: st.success("이 과목은 틀린 문항이 없습니다 (100점).")
                else:
                    st.table(style_centered(wrong[[c for c in ['문항번호', '정답', '채점결과', '출제 의도', '출제의도', '배점'] if c in wrong.columns]].copy()))
                    cache_key = f"mock_single_{s_ex}_{s_su}"
                    if st.button("🤖 맞춤형 처방전 생성"):
                        if ai_model:
                            with st.spinner("분석 중..."):
                                it_col = '출제 의도' if '출제 의도' in wrong.columns else ('출제의도' if '출제의도' in wrong.columns else None)
                                prompt = f"고등학생이 모의고사 {s_su} 과목에서 다음 의도의 문항을 틀렸습니다: [{', '.join(wrong[it_col].dropna().astype(str).tolist()) if it_col else ''}]. 핵심 취약점과 구체적 보완 전략을 'AI' 단어 없이 개조식(명사형)으로 작성하세요."
                                try: st.session_state["ai_cache"][cache_key] = ai_model.generate_content(prompt).text
                                except Exception as e: st.error(f"오류: {e}")
                    if cache_key in st.session_state.get("ai_cache", {}):
                        st.markdown(f'<div class="ai-container"><b>🤖 맞춤형 학습 처방전</b><br><br>{st.session_state["ai_cache"][cache_key]}</div>', unsafe_allow_html=True)
            else: st.warning("데이터가 부족합니다.")
        else: st.info("문항 정보 또는 학생 답안 시트에 데이터를 채워주세요.")

    with mt3:
        st.subheader("📊 누적 취약점 분석 (전체 모의고사 통합)")
        if not df_m_info.empty and not df_m_ans.empty:
            user_all_ans = df_m_ans[df_m_ans['고유번호'] == sel_uid].copy()
            if not user_all_ans.empty:
                sel_subj_cum = st.selectbox("누적 분석할 과목 선택", user_all_ans['과목'].unique(), key='cum_subj')
                all_wrong_intents = []
                for _, ans_row in user_all_ans[user_all_ans['과목'] == sel_subj_cum].iterrows():
                    ox_list = list(re.sub(r'[^OXox]', '', str(ans_row['OMR답안'])).upper())
                    ex_i = df_m_info[(df_m_info['시험명'] == ans_row['시험명']) & (df_m_info['과목'] == sel_subj_cum)].copy()
                    if not ex_i.empty:
                        ex_i['채점결과'] = [ox_list[i] if i < len(ox_list) else 'X' for i in range(len(ex_i))]
                        wrong_df = ex_i[ex_i['채점결과'] == 'X']
                        it_col = '출제 의도' if '출제 의도' in wrong_df.columns else ('출제의도' if '출제의도' in wrong_df.columns else None)
                        if it_col: all_wrong_intents.extend(wrong_df[it_col].dropna().astype(str).tolist())
                if not all_wrong_intents: st.success("누적된 오답 기록이 없습니다.")
                else:
                    st.info(", ".join(all_wrong_intents))
                    cache_key = f"mock_cum_{sel_subj_cum}"
                    if st.button("🤖 누적 패턴 클러스터링 및 장기 로드맵 생성"):
                        if ai_model:
                            with st.spinner("분석 중..."):
                                prompt_cum = f"학생이 모의고사 {sel_subj_cum} 과목에서 누적해서 틀린 문제 의도들입니다: [{', '.join(all_wrong_intents)}]. 공통 취약점 1~3가지와 장기 학습 로드맵을 'AI' 단어 없이 개조식(명사형)으로 작성하세요."
                                try: st.session_state["ai_cache"][cache_key] = ai_model.generate_content(prompt_cum).text
                                except Exception as e: st.error(f"오류: {e}")
                    if cache_key in st.session_state.get("ai_cache", {}):
                        st.markdown(f'<div class="ai-container"><b>🤖 누적 약점 정밀 보고서</b><br><br>{st.session_state["ai_cache"][cache_key]}</div>', unsafe_allow_html=True)
            else: st.info("모의고사 답안 기록이 없습니다.")

# ==========================================
# 8. 성찰 리포트 
# ==========================================
elif menu == "🧠 성찰 리포트":
    curr_y = sel_term[:3] if sel_term else ""
    uid_ref = df_ref[(df_ref['고유번호'] == sel_uid) & (df_ref.apply(lambda r: curr_y in str(r.get('학기','')) or curr_y in str(r.get('시험명','')), axis=1))].copy() if not df_ref.empty else pd.DataFrame()
    
    if not uid_ref.empty:
        st.subheader(f"🧠 {sel_name} 학생의 시험 성찰 기록")
        s_ex = st.selectbox("시험 선택", uid_ref['시험명'].unique())
        row = uid_ref[uid_ref['시험명'] == s_ex].iloc[-1]
        cols = st.columns(2); idx = 0
        for k, v in row.items():
            if k in ['타임스탬프', '학번', '이름', '성명', '학생식별', '표시식별', '학생명', '시험명', '반', '고유번호', '학기'] or not v: continue
            with cols[idx % 2]: st.markdown(f'<div style="background:white; border-left:5px solid #3B82F6; padding:15px; margin-bottom:10px; border-radius:10px;"><b>{k}</b><br>{v}</div>', unsafe_allow_html=True)
            idx += 1
        st.markdown("---")
        cache_key = f"ref_{s_ex}"
        if st.button("🤖 성찰 기반 피드백 생성"):
            if ai_model:
                with st.spinner("작성 중..."):
                    clean_data = {str(k): str(v) for k, v in row.items() if len(str(v)) > 5 and k not in ['학번', '타임스탬프']}
                    try: st.session_state["ai_cache"][cache_key] = ai_model.generate_content(f"학습 성찰 내용: {str(clean_data)}. 교사의 입장에서 조언을 'AI' 단어 없이 개조식 명사형으로 작성해주세요.").text
                    except Exception as e: st.error(f"오류: {e}")
        if cache_key in st.session_state.get("ai_cache", {}):
            st.markdown(f'<div class="ai-container"><b>🤖 컨설팅 조언</b><br><br>{st.session_state["ai_cache"][cache_key]}</div>', unsafe_allow_html=True)
    else: st.info("성찰 기록이 없습니다.")

# ==========================================
# 9. 비교과 타임라인
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
            with s_cols[i]: st.markdown(f'<div class="stat-box" style="padding:10px;"><small style="color:#64748B; font-size:0.65rem;">{comp_name}</small><br><b style="font-size:1.2rem; color:#2563EB;">{count}건</b></div>', unsafe_allow_html=True)
                
        st.markdown("---")
        f1, f2 = st.columns(2)
        filtered_act = uid_act.copy()
        with f1:
            sel_type = st.selectbox("활동 성격별 필터", ["전체", "자율 활동", "진로 활동", "독서 활동", "문헌 탐구 활동", "협력 토론 활동", "실증 탐구 활동", "비평 성찰 활동", "발표 공유 활동", "융합 탐구 활동", "교사 개별 상담"])
            if sel_type != "전체" and col_type: filtered_act = filtered_act[filtered_act[col_type].str.contains(sel_type, na=False)]
        with f2:
            sel_comp = st.selectbox("핵심 역량별 필터", ["전체"] + comp_standards)
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
            if st.button(f"🪄 생기부 초안 생성 (기록번호: {i})"):
                if ai_model:
                    with st.spinner("작성 중..."):
                        try: st.session_state["ai_cache"][cache_key] = ai_model.generate_content(f"활동 내용: {row.get('핵심 활동 내용', '')}. 이를 바탕으로 생기부에 들어갈 문구를 'AI' 단어 없이 개조식(~함, ~임)으로 작성해줘.").text
                        except Exception as e: st.error(f"오류: {e}")
            if cache_key in st.session_state.get("ai_cache", {}): st.info(st.session_state["ai_cache"][cache_key])
    else: st.info("활동 기록이 없습니다.")

# ==========================================
# 10. 상담 기록
# ==========================================
elif menu == "📝 상담 기록":
    u_cs = df_counsel[df_counsel['고유번호']==sel_uid].copy() if '고유번호' in df_counsel.columns else df_counsel[df_counsel['학번']==sel_student.split(" ")[0]].copy()
    tab_new, tab_history = st.tabs(["✍️ 신규 상담 작성", "🔒 누적 상담 기록 (비공개)"])
    
    with tab_new:
        st.subheader("✍️ 신규 상담 기록 작성")
        with st.form("c_f", clear_on_submit=True):
            d = st.date_input("상담 일자")
            t = st.selectbox("상담 유형", ["학습/성적", "진로/진학", "학교생활/교우관계", "심리/정서", "학부모상담", "기타"])
            c = st.text_area("상담 내용 및 결과", height=150, placeholder="아이들에게 보이지 않으니 편하게 작성하세요.")
            if st.form_submit_button("💾 상담 기록 저장하기"):
                if c.strip():
                    with st.spinner("저장 중..."):
                        try:
                            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
                            doc = gspread.authorize(creds).open("40기 마스터 파일")
                            try: sh = doc.worksheet("71_상담기록")
                            except:
                                sh = doc.add_worksheet(title="71_상담기록", rows="1000", cols="10")
                                sh.append_row(["학번", "이름", "상담일자", "상담유형", "상담내용"])
                            sh.append_row([sel_student.split(" ")[0], sel_name, str(d), t, c])
                            st.cache_resource.clear()
                            st.success("✅ 저장 완료! 사이드바의 '🔄 최신 데이터 불러오기' 버튼을 누르시면 기록이 갱신됩니다.")
                        except Exception as e: st.error(f"저장 실패: {e}")
                            
    with tab_history:
        st.subheader(f"📖 {sel_name} 누적 상담 기록")
        st.info("💡 학생과 함께 모니터를 볼 때는 이 탭을 닫아두시는 것을 권장합니다.")
        if not u_cs.empty:
            for _, r in u_cs.sort_values('상담일자', ascending=False).iterrows():
                st.markdown(f"""
                <div class="timeline-card" style="border-left: 6px solid #8B5CF6;">
                    <span class="badge" style="background:#F3E8FF; color:#7E22CE;">🗣️ {r.get("상담유형", "일반 상담")}</span>
                    <div style="font-size:0.85rem; color:#64748B; margin-bottom:10px;">📅 {r.get("상담일자", "-")}</div>
                    <div style="background:#F8FAFC; padding:18px; border-radius:12px; font-size:0.95rem; line-height:1.7;">{r.get("상담내용", "-")}</div>
                </div>
                """, unsafe_allow_html=True)
        else: st.warning("이전에 작성된 상담 기록이 없습니다.")

# ==========================================
# 11. 🖨️ 맞춤형 리포트 출력 (A4 레포트 스킨 전면 개조)
# ==========================================
elif menu == "🖨️ 맞춤형 리포트 출력":
    st.markdown("<div class='print-hide'>", unsafe_allow_html=True)
    st.subheader("🌟 학생 종합 컨설팅 생성")
    st.write("학생의 내신, 모의고사, 비교과 데이터를 융합하여 종합적인 학습 전략을 즉시 도출합니다.")
    
    if st.button("🪄 통합 컨설팅 리포트 생성", use_container_width=True):
        if ai_model:
            with st.spinner("학생의 모든 데이터를 통합 분석 중입니다..."):
                uid_scores = df_scores[df_scores['고유번호'] == sel_uid]
                s_col = next((c for c in uid_scores.columns if '점수' in c.replace(" ","")), '점수')
                g_data = uid_scores.tail(15)[['학기','시험','과목',s_col,'등급']].to_dict('records') if not uid_scores.empty else "기록 없음"
                uid_mk = df_mock[df_mock['고유번호'] == sel_uid]
                m_data = uid_mk.tail(2).drop(columns=['학번','표시식별','학생명','반','고유번호'], errors='ignore').to_dict('records') if not uid_mk.empty else "기록 없음"
                uid_act = df_act[df_act['고유번호'] == sel_uid]
                a_data = f"비교과 활동 총 {len(uid_act)}건" if not uid_act.empty else "활동 기록 없음"
                
                master_prompt = f"""
                당신은 대한민국 최고 수준의 고등학교 입시/교과 데이터 컨설턴트입니다.
                학생({sel_name})의 아래 데이터를 바탕으로 완벽한 종합 컨설팅 리포트를 작성하세요.
                
                [수집된 학생 데이터 요약]
                1. 최근 내신 성적: {g_data}
                2. 최근 모의고사 성적: {m_data}
                3. 비교과 활동 현황: {a_data}
                
                [필수 포함 항목 및 양식]
                1. 종합 총평 (학생의 현재 상황에 대한 핵심 3줄 요약)
                2. 집중 공략 대상: 보다 치중해야 하는 취약/핵심 과목 지정
                3. 맞춤형 학습법: 해당 과목에 대한 구체적이고 실천 가능한 학습 방법 제시
                4. 향후 비교과 및 진로 연계 조언
                
                [엄격한 작성 규칙]
                - 'AI', '인공지능'이라는 단어는 절대 사용하지 마세요.
                - 반드시 간결하고 명확한 '개조식(명사형 종결, ~함, ~임 등)'으로 작성하세요.
                - 대화형 문구(~해요, ~습니다 등)는 절대 금지합니다.
                """
                try: 
                    st.session_state["ai_cache"]["master_consulting"] = ai_model.generate_content(master_prompt).text
                except Exception as e: 
                    st.error(f"컨설팅 생성 중 오류가 발생했습니다: {e}")
        else: 
            st.warning("AI 모델을 사용할 수 없습니다. 인터넷 연결과 API 키를 확인해주세요.")

    st.markdown("---")
    st.subheader("🖨️ 맞춤형 종합 리포트 출력 옵션")
    st.write("보고서에 포함할 항목을 선택하고 하단에서 확인 후 `Ctrl + P`를 눌러 인쇄하세요.")

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: p_master = st.checkbox("🌟 학생 종합 컨설팅", value=True)
    with c2: p_grade = st.checkbox("📈 내신 요약 및 성적표", value=True)
    with c3: p_mock = st.checkbox("🎯 모의고사 요약 및 추이", value=True)
    with c4: p_act = st.checkbox("🏆 비교과 핵심역량 분포", value=True)
    with c5: p_ai = st.checkbox("🔍 세부 처방전 모아보기", value=True)
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("---")

    # ================= 🖨️ 실제 인쇄용 초고급 스킨 스타일링 렌더링 영역 =================
    today_str = datetime.datetime.now().strftime("%Y년 %m월 %d일")
    
    # 상단 헤더 섹션 디자인
    st.markdown(f"""
    <div style="border-bottom: 2px solid #1E3A8A; padding-bottom: 10px; margin-bottom: 30px;">
        <table style="width: 100%; border: none !important; margin: 0 !important; background: transparent !important;">
            <tr style="border: none !important; background: transparent !important;">
                <td style="text-align: left !important; font-size: 1.1rem; color: #1E3A8A; font-weight: bold; border: none !important; padding:0 !important;">한일고등학교 40기 학업 성취 종합 분석</td>
                <td style="text-align: right !important; font-size: 0.95rem; color: #64748B; border: none !important; padding:0 !important;">발행일자: {today_str}</td>
            </tr>
        </table>
        <h1 style="text-align: center; color: #0F172A; margin: 25px 0 10px 0; font-weight: 800; font-size: 2.4rem; letter-spacing: -1px;">개별 학생 맞춤형 종합 리포트</h1>
        <p style="text-align: center; color: #2563EB; font-size: 1.3rem; font-weight: 600; margin: 0;">대상 학생: {sel_student} (담임 확인 서명란: &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;)</p>
    </div>
    """, unsafe_allow_html=True)

    # 1. 학생 종합 컨설팅 출력 스킨
    if p_master:
        st.markdown("<h3 style='color: #1E3A8A; border-left: 5px solid #1E3A8A; padding-left: 10px; margin-top: 30px; font-weight: 700;'>💡 1. 담임교사 종합 컨설팅 의견</h3>", unsafe_allow_html=True)
        if "master_consulting" in st.session_state.get("ai_cache", {}):
            # 줄바꿈과 마크다운 스타일을 HTML 내부에서 깨지지 않게 보정
            formatted_text = st.session_state["ai_cache"]["master_consulting"].replace("\n", "<br>")
            st.markdown(f"""
            <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-left: 6px solid #2563EB; padding: 22px; border-radius: 8px; font-size: 1rem; line-height: 1.8; color: #1E293B;">
                {formatted_text}
            </div>
            """, unsafe_allow_html=True)
        else: 
            st.markdown("<div class='print-hide' style='color:#EF4444; font-weight:bold; padding: 10px; background: #FEF2F2; border-radius: 6px;'>⚠️ 상단의 '통합 컨설팅 리포트 생성' 버튼을 누르시면 컨설팅 의견이 여기에 결합됩니다.</div>", unsafe_allow_html=True)

    # 2. 내신 요약 스킨 (A4 맞춤 표 서식)
    if p_grade:
        st.markdown("<h3 style='color: #1E3A8A; border-left: 5px solid #1E3A8A; padding-left: 10px; margin-top: 40px; font-weight: 700;'>📈 2. 학교 교과 내신 성적 요약</h3>", unsafe_allow_html=True)
        uid_scores = df_scores[df_scores['고유번호'] == sel_uid].copy()
        s_col = next((c for c in uid_scores.columns if '점수' in c.replace(" ","")), '점수')
        
        f_df = uid_scores[uid_scores['시험'] == '학기말'].copy()
        u_col = '단위' if '단위' in f_df.columns else ('이수단위' if '이수단위' in f_df.columns else '')
        
        if not f_df.empty and u_col:
            f_df['9등급(자동)'] = f_df.apply(lambda r: calc_9_tier(safe_numeric(r.get(s_col,0)), df_scores[(df_scores['학기']==r['학기'])&(df_scores['시험']=='학기말')&(df_worksheet:=df_scores['과목']==r['과목'])][s_col].apply(safe_numeric).dropna()), axis=1)
            t_u = f_df[u_col].apply(safe_numeric).sum()
            g5 = (f_df['등급'].apply(safe_numeric)*f_df[u_col].apply(safe_numeric)).sum()/t_u if t_u > 0 else 0
            g9 = (f_df['9등급(자동)']*f_df[u_col].apply(safe_numeric)).sum()/t_u if t_u > 0 else 0
            
            # 메트릭 인쇄 시 깨짐 방지용 정밀 HTML 스킨
            st.markdown(f"""
            <table style="width: 100%; margin-bottom: 20px; border: 1px solid #E2E8F0; border-collapse: collapse;">
                <tr style="background-color: #F1F5F9;">
                    <th style="padding: 12px; border: 1px solid #E2E8F0; text-align: center; color: #475569;">📊 {sel_term} 교과 종합 평점 (5등급제 기준)</th>
                    <th style="padding: 12px; border: 1px solid #E2E8F0; text-align: center; color: #475569;">📊 {sel_term} 교과 종합 평점 (9등급제 시뮬레이션)</th>
                </tr>
                <tr>
                    <td style="padding: 16px; border: 1px solid #E2E8F0; text-align: center; font-size: 1.6rem; font-weight: 800; color: #1E40AF;">{g5:.2f} 등급</td>
                    <td style="padding: 16px; border: 1px solid #E2E8F0; text-align: center; font-size: 1.6rem; font-weight: 800; color: #0F766E;">{g9:.2f} 등급</td>
                </tr>
            </table>
            """, unsafe_allow_html=True)
        
        uid_scores['순서'] = uid_scores.apply(get_time_rank, axis=1)
        if not uid_scores.empty and uid_scores['순서'].max() > 0:
            latest_order = uid_scores['순서'].max()
            latest_df = uid_scores[uid_scores['순서'] == latest_order].copy()
            latest_term = latest_df.iloc[0]['학기']
            latest_exam = latest_df.iloc[0]['시험']
            
            def format_expected_grade(row):
                my_s = safe_numeric(row.get(s_col, 0))
                all_s = df_scores[(df_scores['학기']==row['학기']) & (df_scores['시험']==row['시험']) & (df_scores['과목']==row['과목'])][s_col].apply(safe_numeric).dropna()
                if all_s.empty: return row.get('등급', '-')
                rank = (all_s > my_s).sum() + 1
                total = len(all_s)
                return f"{calc_5_tier(my_s, all_s)}등급 / {calc_9_tier(my_s, all_s)}등급 [{rank}/{total}등]"
                
            latest_df['등급(예상 등수)'] = latest_df.apply(format_expected_grade, axis=1)
            
            st.markdown(f"<p style='font-weight: 700; color: #334155; margin-bottom: 8px;'>📍 최근 고사 상세 성적 내역 ({latest_term} {latest_exam})</p>", unsafe_allow_html=True)
            target_cols = ['교과군', '과목', '단위', '이수단위', s_col, '원점수', '등급(예상 등수)', '성취도']
            display_cols = list(dict.fromkeys([c for c in target_cols if c in latest_df.columns]))
            
            # 표 렌더링을 완전히 깔끔한 레포트 스킨 HTML로 우회 출력
            table_html = "<table style='width: 100%; border-collapse: collapse; margin-bottom: 25px; border: 1px solid #CBD5E1; font-size: 0.95rem;'>"
            table_html += "<tr style='background-color: #F8FAFC; border-bottom: 2px solid #94A3B8;'>"
            for col in display_cols:
                table_html += f"<th style='padding: 10px; border: 1px solid #CBD5E1; text-align: center; color: #334155; font-weight: 700;'>{col}</th>"
            table_html += "</tr>"
            
            for _, row in latest_df[display_cols].iterrows():
                table_html += "<tr style='border-bottom: 1px solid #E2E8F0;'>"
                for col in display_cols:
                    val = row[col]
                    val_str = f"{val:.2f}" if isinstance(val, (int, float)) and col == s_col else str(val)
                    table_html += f"<td style='padding: 10px; border: 1px solid #CBD5E1; text-align: center;'>{val_str}</td>"
                table_html += "</tr>"
            table_html += "</table>"
            st.markdown(table_html, unsafe_allow_html=True)
        else: 
            st.info("표시할 성적 데이터가 없습니다.")

    # 3. 모의고사 성적 서식 개조
    if p_mock:
        st.markdown("<h3 style='color: #1E3A8A; border-left: 5px solid #1E3A8A; padding-left: 10px; margin-top: 40px; font-weight: 700;'>🎯 3. 수능 전국 모의고사 성적 현황</h3>", unsafe_allow_html=True)
        uid_mk = df_mock[df_mock['고유번호'] == sel_uid].copy()
        if not uid_mk.empty:
            latest = uid_mk.iloc[-1]
            st.markdown(f"<p style='font-weight: 700; color: #334155; margin-bottom: 8px;'>📍 가장 최근 시행 시험: {latest.get('시험명', '최근 고사')}</p>", unsafe_allow_html=True)
            subj_map = {"국어": ["국어"], "수학": ["수학"], "영어": ["영어"], "한국사": ["한국사", "국사"], "사탐": ["사탐", "사회"], "과탐": ["과탐", "과학"]}
            
            m_table_html = "<table style='width: 100%; border-collapse: collapse; margin-bottom: 25px; border: 1px solid #CBD5E1; font-size: 0.95rem;'>"
            m_table_html += "<tr style='background-color: #F8FAFC; border-bottom: 2px solid #94A3B8;'><th style='padding: 10px; border: 1px solid #CBD5E1;'>영역</th><th style='padding: 10px; border: 1px solid #CBD5E1;'>표준점수</th><th style='padding: 10px; border: 1px solid #CBD5E1;'>전국 백분위</th><th style='padding: 10px; border: 1px solid #CBD5E1;'>산출 등급</th></tr>"
            
            for n, keys in subj_map.items():
                def f_val(k_list, target_k):
                    for col in latest.index:
                        if any(s in str(col).replace(" ", "").replace("_", "").lower() for s in k_list) and target_k in str(col): return latest[col]
                    return '-'
                v_p = f_val(keys, '표'); v_b = f_val(keys, '백분'); v_g = f_val(keys, '등급')
                f_perc = f"{float(v_b):.2f}%" if v_b!='-' else "-"
                f_grade = f"{int(float(v_g))}등급" if v_g!='-' else "-"
                m_table_html += f"<tr><td style='padding: 10px; border: 1px solid #CBD5E1; font-weight:700; background:#F8FAFC;'>{n}</td><td style='padding: 10px; border: 1px solid #CBD5E1;'>{v_p}</td><td style='padding: 10px; border: 1px solid #CBD5E1; color:#EA580C; font-weight:700;'>{f_perc}</td><td style='padding: 10px; border: 1px solid #CBD5E1; font-weight:700;'>{f_grade}</td></tr>"
            m_table_html += "</table>"
            st.markdown(m_table_html, unsafe_allow_html=True)
            
            p_cols = [c for c in uid_mk.columns if '백분' in c]
            if p_cols:
                plot_m = uid_mk[['시험명'] + p_cols].copy()
                for c in p_cols: plot_m[c] = plot_m[c].apply(safe_numeric)
                fig_m = px.line(plot_m.melt(id_vars=['시험명'], var_name='과목', value_name='백분위'), x='시험명', y='백분위', color='과목', markers=True, title="모의고사 성적 등락 추이")
                fig_m.update_layout(yaxis=dict(range=[0, 105]), height=280, margin=dict(l=20, r=20, t=40, b=20))
                st.plotly_chart(fig_m, use_container_width=True)
        else: 
            st.info("모의고사 기록이 없습니다.")

    # 4. 비교과 핵심역량 분포 서식 개조
    if p_act:
        st.markdown("<h3 style='color: #1E3A8A; border-left: 5px solid #1E3A8A; padding-left: 10px; margin-top: 40px; font-weight: 700;'>🏆 4. 비교과 창의적 체험활동 역량 균형도</h3>", unsafe_allow_html=True)
        curr_y = sel_term[:3] if sel_term else ""
        t_col = next((c for c in df_act.columns if any(k in c for k in ['학년', '학기', '시기', '연도'])), None)
        u_ac = df_act[(df_act['고유번호'] == sel_uid) & (df_act[t_col].str.contains(curr_y, na=False))].copy() if t_col else df_act[df_act['고유번호'] == sel_uid].copy()
        
        if not u_ac.empty:
            col_comp = next((c for c in u_ac.columns if '역량' in c), None)
            comp_standards = ["탐구력/지식정보처리", "창의적 사고", "비판적 사고", "자기주도성/자기관리", "협력적 소통", "공동체 의식/윤리"]
            
            act_table_html = "<table style='width: 100%; border-collapse: collapse; border: 1px solid #CBD5E1;'>"
            act_table_html += "<tr style='background-color: #F8FAFC;'>"
            for comp_name in comp_standards:
                act_table_html += f"<th style='padding: 8px; border: 1px solid #CBD5E1; font-size: 0.8rem; font-weight:700; color:#475569;'>{comp_name}</th>"
            act_table_html += "</tr><tr>"
            for comp_name in comp_standards:
                count = u_ac[col_comp].str.contains(comp_name, na=False).sum() if col_comp else 0
                act_table_html += f"<td style='padding: 12px; border: 1px solid #CBD5E1; font-size: 1.2rem; font-weight: 800; color: #2563EB;'>{count}건</td>"
            act_table_html += "</tr></table>"
            st.markdown(act_table_html, unsafe_allow_html=True)

    # 5. 세부 처방전 모아보기 스킨 개조
    if p_ai:
        st.markdown("<h3 style='color: #1E3A8A; border-left: 5px solid #1E3A8A; padding-left: 10px; margin-top: 40px; font-weight: 700;'>🔍 5. 세부 영역별 피드백 및 처방전</h3>", unsafe_allow_html=True)
        if "ai_cache" in st.session_state and len([k for k in st.session_state["ai_cache"].keys() if k != "master_consulting"]) > 0:
            for key, text in st.session_state["ai_cache"].items():
                if key == "master_consulting": continue
                title = "학업 역량 정밀 분석"
                if "mock_single" in key: title = f"모의고사 문항별 취약점 분석 ({key.split('_')[-2]} - {key.split('_')[-1]})"
                elif "mock_cum" in key: title = f"모의고사 누적 패턴 클러스터링 및 로드맵 ({key.split('_')[-1]})"
                elif "ref_" in key: title = f"정기 고사 학습 성찰에 대한 피드백 ({key.split('_')[-1]})"
                elif "act_" in key: title = "비교과 탐구 활동 생기부 연계 초안 문구"
                
                formatted_detail = text.replace("\n", "<br>")
                st.markdown(f"""
                <div style="margin-bottom: 20px; border: 1px solid #E2E8F0; border-radius: 6px; overflow: hidden;">
                    <div style="background-color: #F1F5F9; padding: 8px 12px; font-weight: 700; color: #334155; font-size: 0.9rem; border-bottom: 1px solid #E2E8F0;">📌 {title}</div>
                    <div style="padding: 15px; font-size: 0.9rem; line-height: 1.7; color: #475569; background: #FFFFFF;">{formatted_detail}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("현재 누적 보관된 세부 처방전이 없습니다. 각 분석 메뉴 탭에서 분석 버튼을 누르시면 기록이 유지되어 여기에 함께 결합됩니다.")

# ==========================================
# 12. 🌟 학급 대시보드 (담임교사 전용)
# ==========================================
elif menu == "🌟 학급 대시보드":
    def check_dashboard_password():
        correct_pwd = st.secrets.get("dashboard_password", "0005")
        if st.session_state.get("dashboard_unlocked"): return True
        st.markdown(f"<h2 style='color: #1E40AF;'>🔒 {sel_class} 담임 전용 대시보드</h2>", unsafe_allow_html=True)
        pwd = st.text_input("대시보드 접속 비밀번호를 입력하세요.", type="password")
        if pwd == correct_pwd:
            st.session_state["dashboard_unlocked"] = True
            st.rerun()
        elif pwd: st.error("비밀번호가 틀렸습니다.")
        return False

    if check_dashboard_password():
        st.markdown(f"<h2 style='color: #1E40AF;'>🌟 {sel_term} {sel_class} 종합 대시보드</h2>", unsafe_allow_html=True)
        st.info("💡 담임 선생님을 위한 학급 전체 요약 현황입니다.")
        counsel_summary = []
        for _, stu_row in class_students.iterrows():
            uid = stu_row['고유번호']
            stu_name = stu_row['학생명']
            stu_hakbun = str(stu_row['학번'])
            u_cs = df_counsel[df_counsel['고유번호']==uid] if '고유번호' in df_counsel.columns else df_counsel[df_counsel['학번'].astype(str)==stu_hakbun]
            if not u_cs.empty and '상담일자' in u_cs.columns:
                last_date = u_cs['상담일자'].max()
                count = len(u_cs)
            else:
                last_date = "-"
                count = 0
            u_ac = df_act[df_act['고유번호']==uid]
            act_count = len(u_ac)
            counsel_summary.append({"학번": stu_hakbun, "이름": stu_name, "누적 상담(건)": count, "최근 상담일": last_date, "비교과 활동(건)": act_count})
        
        dash_df = pd.DataFrame(counsel_summary).sort_values('학번')
        c1, c2, c3 = st.columns(3)
        c1.metric("👩‍🎓 우리 반 총 인원", f"{len(dash_df)}명")
        c2.metric("🗣️ 상담 진행 학생 (1회 이상)", f"{len(dash_df[dash_df['누적 상담(건)'] > 0])}명")
        c3.metric("🏆 비교과 최다 활동 학생", f"{dash_df.sort_values('비교과 활동(건)', ascending=False).iloc[0]['이름']} ({dash_df['비교과 활동(건)'].max()}건)" if not dash_df.empty and dash_df['비교과 활동(건)'].max() > 0 else "-")
        
        st.markdown("---")
        st.subheader("📋 우리 반 학생 개별 현황표")
        st.dataframe(style_centered(dash_df), use_container_width=True, height=500)
