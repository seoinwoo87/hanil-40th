import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import datetime
import json
import time
import streamlit.components.v1 as components

# ==========================================
# 🏫 학교 로고 설정
# ==========================================
SCHOOL_LOGO_URL = "https://github.com/seoinwoo87/hanil-40th/blob/main/%ED%95%9C%EC%9D%BC%EB%A6%AC%EB%B3%B8%EB%A7%88%ED%81%AC%EC%B2%AD.jpg?raw=true"

# ==========================================
# 1. 페이지 설정 및 전문가용 디자인 CSS (가독성 강화)
# ==========================================
st.set_page_config(page_title="한일고 진학 컨설팅 시스템", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@300;400;600;800&display=swap');
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif; background-color: #F8FAFC; color: #0F172A; }
    
    /* 드롭다운(선택칸) 및 입력창 또렷하게 명도 조정 */
    div[data-baseweb="select"] > div { background-color: #FFFFFF !important; border: 1px solid #94A3B8 !important; border-radius: 4px !important; }
    div[data-baseweb="input"] > div { background-color: #FFFFFF !important; border: 1px solid #94A3B8 !important; border-radius: 4px !important; }
    input, textarea, div[data-baseweb="select"] * { color: #0F172A !important; }
    
    /* 탭(Tab) 메뉴 가독성 상향 */
    button[data-baseweb="tab"] { font-size: 1.05rem !important; font-weight: 600 !important; color: #64748B !important; }
    button[data-baseweb="tab"][aria-selected="true"] { color: #1E3A8A !important; border-bottom: 3px solid #1E3A8A !important; font-weight: 800 !important; }

    /* 각진 테두리와 깊은 네이비 포인트 컬러 */
    .stMetric { background: white; border: 1px solid #CBD5E1; padding: 15px !important; border-radius: 4px !important; border-top: 3px solid #1E3A8A !important; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .timeline-card { background: white; border: 1px solid #CBD5E1; border-radius: 4px; padding: 25px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border-left: 4px solid #1E3A8A; }
    .badge { display: inline-block; padding: 4px 10px; border-radius: 2px; font-size: 0.75rem; font-weight: 700; background: #F1F5F9; color: #1E293B; border: 1px solid #94A3B8; margin-bottom: 10px; margin-right: 5px; letter-spacing: -0.5px; }
    .stat-box { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; padding: 15px; text-align: center; border-top: 3px solid #475569; }
    .stApp [data-testid="stExpander"] { background: white !important; border-radius: 4px; border: 1px solid #CBD5E1; }
    
    /* 표(테이블) 가독성 세팅 */
    table, th, td { text-align: center !important; border-color: #CBD5E1 !important; }
    th { background-color: #E2E8F0 !important; color: #0F172A !important; font-weight: 800 !important; }
    
    h1, h2, h3 { color: #0F172A; font-weight: 800; letter-spacing: -1px; }

    @media print {
        body::before {
            content: "인쇄 방식 변경 안내: 단축키(Ctrl+P)를 사용하지 마세요. 화면 우측 상단의 [인쇄하기] 버튼을 클릭하셔야 공식 리포트 양식으로 정상 출력됩니다.";
            display: flex; justify-content: center; align-items: center; height: 100vh; font-size: 20px; font-weight: bold; color: white; background-color: #0F172A; text-align: center; padding: 20px; z-index: 999999; position: fixed; top: 0; left: 0; width: 100vw;
        }
        [data-testid="stAppViewContainer"] { display: none !important; }
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
        st.markdown("### 한일고 40기 진학 컨설팅 시스템 접속")
        st.text_input("접속 비밀번호를 입력해주세요.", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.markdown("### 한일고 40기 진학 컨설팅 시스템 접속")
        st.text_input("비밀번호가 일치하지 않습니다.", type="password", on_change=password_entered, key="password")
        st.error("권한이 없습니다.")
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
# 4. 데이터 로드
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
            
        dfs = [process_sheet(n) for n in ["31_내신", "21_모의고사", "51_시험복기", "61_비교과", "71_상담기록", "99_학생_마스터", "22_모의고사_문항정보", "23_모의고사_학생답안", "72_종합컨설팅"]]
        df_sc, df_mk, df_rf, df_ac, df_cs, df_ms, df_m_info, df_m_ans, df_consult_saved = dfs
        
        if not df_ms.empty and '고유번호' in df_ms.columns:
            mapping = df_ms[['학번', '고유번호']].drop_duplicates()
            def apply_uid(df):
                if not df.empty and '학번' in df.columns:
                    m = pd.merge(df, mapping, on='학번', how='left')
                    m['고유번호'] = m['고유번호'].fillna(m['표시식별'])
                    return m
                return df
            return apply_uid(df_sc), apply_uid(df_mk), apply_uid(df_rf), apply_uid(df_ac), apply_uid(df_cs), df_m_info, df_m_ans, df_consult_saved
        return [d.assign(고유번호=d.get('표시식별','')) for d in [df_sc, df_mk, df_rf, df_ac, df_cs]] + [df_m_info, df_m_ans, df_consult_saved]
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return [pd.DataFrame()]*9

df_scores, df_mock, df_ref, df_act, df_counsel, df_m_info, df_m_ans, df_consult_saved = load_all_data()

try:
    genai.configure(api_key=st.secrets["gemini_api_key"])
    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    target_model_name = next((p for p in ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-pro', 'models/gemini-1.0-pro'] if p in available_models), available_models[0] if available_models else None)
    ai_model = genai.GenerativeModel(target_model_name) if target_model_name else None
except Exception: ai_model = None

# ==========================================
# 5. 사이드바 메뉴 및 메인 랜딩 페이지
# ==========================================
query_params = st.query_params

with st.sidebar:
    if SCHOOL_LOGO_URL:
        st.markdown(f"""
        <div style="text-align: center; margin-bottom: 20px;">
            <img src="{SCHOOL_LOGO_URL}" style="max-width: 150px; max-height: 80px; object-fit: contain;">
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<h2 style='text-align: center; margin-top: 0; color: #1E3A8A; font-weight: 800; font-size: 1.4rem;'>통합 진학 컨설팅 시스템</h2>", unsafe_allow_html=True)
    st.markdown("<div style='text-align: right; font-size: 0.75rem; color: #94A3B8; margin-bottom: 20px;'>Ver 2.0 Pro</div>", unsafe_allow_html=True)
    
    if st.button("데이터 동기화 (새로고침)", use_container_width=True):
        st.cache_resource.clear()
        st.rerun()

    sel_term = st.selectbox("분석 학기 선택", sorted(df_scores['학기'].unique(), reverse=True) if not df_scores.empty else [])
    sel_class = st.selectbox("소속 학급 선택", sorted(df_scores[df_scores['학기'] == sel_term]['반'].unique()) if sel_term else [])
    class_students = df_scores[(df_scores['학기'] == sel_term) & (df_scores['반'] == sel_class)] if sel_term else pd.DataFrame()
    s_list = ["학생을 선택해주세요"] + sorted(class_students['표시식별'].unique().tolist()) if not class_students.empty else ["학생을 선택해주세요"]
    
    d_idx = s_list.index(query_params["student"]) if "student" in query_params and query_params["student"] in s_list else 0
    sel_student = st.selectbox("컨설팅 대상 학생", s_list, index=d_idx)

if sel_student == "학생을 선택해주세요":
    if "student" in st.query_params: del st.query_params["student"]
    st.markdown("""
    <div style="background: linear-gradient(135deg, #1E3A8A 0%, #3B82F6 100%); padding: 60px 30px; border-radius: 8px; text-align: center; color: white; margin-top: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
        <h1 style="color: white; font-size: 2.8rem; margin-bottom: 10px; letter-spacing: -1px; font-weight: 800;">한일고등학교 통합 진학 컨설팅 시스템</h1>
        <p style="font-size: 1.2rem; opacity: 0.9; font-weight: 400; letter-spacing: 0.5px;">Hanil High School College Admission Consulting Platform Ver 2.0 Pro</p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.stop()

with st.sidebar:
    st.query_params["student"] = sel_student
    sel_uid = class_students[class_students['표시식별'] == sel_student]['고유번호'].iloc[0]
    sel_name = sel_student.split(" ")[1]
    
    if "global_ai_cache" not in st.session_state: st.session_state["global_ai_cache"] = {}
    if sel_uid not in st.session_state["global_ai_cache"]: st.session_state["global_ai_cache"][sel_uid] = {}
        
    st.session_state["ai_cache"] = st.session_state["global_ai_cache"][sel_uid]
    st.session_state["current_student"] = sel_uid

    if "master_consulting" not in st.session_state["global_ai_cache"][sel_uid]:
        if not df_consult_saved.empty and '고유번호' in df_consult_saved.columns:
            saved_match = df_consult_saved[df_consult_saved['고유번호'].astype(str) == str(sel_uid)]
            if not saved_match.empty:
                st.session_state["global_ai_cache"][sel_uid]["master_consulting"] = saved_match.iloc[0]['컨설팅내용']

    menu_list = ["내신 성적 분석", "모의고사 분석", "학습 성찰 리포트", "비교과 활동 타임라인", "상담 기록 관리", "종합 컨설팅 리포트 출력", "교사용 통합 대시보드"]
    d_menu_idx = menu_list.index(query_params["menu"]) if "menu" in query_params and query_params["menu"] in menu_list else 0
    st.markdown("<br>", unsafe_allow_html=True)
    menu = st.radio("분석 메뉴", menu_list, index=d_menu_idx)
    st.query_params["menu"] = menu

st.markdown(f"<h2 style='color: #0F172A; border-bottom: 2px solid #1E3A8A; padding-bottom: 10px;'>[ {sel_student} ] 분석 리포트</h2>", unsafe_allow_html=True)

# ==========================================
# 💡 [추가 기능] 퀵 상담 기록창 (어느 메뉴에서든 성적 보면서 바로 기록!)
# ==========================================
with st.expander(f"📝 {sel_name} 학생 퀵 상담 기록창 (성적 조회 중 즉시 입력 가능)", expanded=False):
    with st.form("quick_counsel_form", clear_on_submit=True):
        qc_cols = st.columns([1, 1])
        with qc_cols[0]:
            qc_date = st.date_input("상담 진행 일자", key="qc_date")
        with qc_cols[1]:
            qc_type = st.selectbox("상담 주요 유형", ["학습/성적", "진로/진학", "학교생활/교우관계", "심리/정서", "학부모상담", "기타"], key="qc_type")
        
        qc_memo = st.text_area("상담 결과 및 주요 코멘트", height=100, placeholder="아래 성적이나 그래프를 보며 분석한 내용을 즉시 기록하세요.")
        
        if st.form_submit_button("상담 기록 구글 시트에 바로 저장하기 💾"):
            if qc_memo.strip():
                with st.spinner("구글 시트 '71_상담기록'에 저장 중..."):
                    try:
                        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
                        doc = gspread.authorize(creds).open("40기 마스터 파일")
                        try: 
                            sh_c = doc.worksheet("71_상담기록")
                        except:
                            sh_c = doc.add_worksheet(title="71_상담기록", rows="1000", cols="10")
                            sh_c.append_row(["학번", "이름", "상담일자", "상담유형", "상담내용"])
                        
                        sh_c.append_row([sel_student.split(" ")[0], sel_name, str(qc_date), qc_type, qc_memo])
                        st.cache_resource.clear()
                        st.success("✅ 퀵 상담 기록이 성공적으로 안전하게 저장되었습니다! (데이터 동기화를 위해 좌측 '데이터 동기화' 버튼을 눌러주세요)")
                    except Exception as e:
                        st.error(f"저장 실패: {e}")
            else:
                st.warning("상담 내용을 입력해 주세요.")


# ==========================================
# 6. 내신 분석 
# ==========================================
if menu == "내신 성적 분석":
    uid_scores = df_scores[df_scores['고유번호'] == sel_uid].copy()
    s_col = next((c for c in uid_scores.columns if '점수' in c.replace(" ","")), '점수')

    t1, t2, t3 = st.tabs(["상세 성적", "학기별 평점", "과목군 추이"])
    
    with t1:
        st.subheader(f"{sel_term} 상세 성적")
        exam = st.selectbox("시험 선택", ["1회고사", "2회고사", "학기말"])
        f = uid_scores[(uid_scores['학기'] == sel_term) & (uid_scores['시험'] == exam)].copy()
        
        if not f.empty:
            if exam == "학기말":
                f_term_for_badges = uid_scores[(uid_scores['학기'] == sel_term) & (uid_scores['시험'] == '학기말')]
                if not f_term_for_badges.empty:
                    subject_ranks = []
                    for _, r in f_term_for_badges.iterrows():
                        my_s = safe_numeric(r.get(s_col, 0))
                        all_s = df_scores[(df_scores['학기'] == sel_term) & (df_scores['시험'] == '학기말') & (df_scores['과목'] == r['과목'])][s_col].apply(safe_numeric).dropna()
                        if len(all_s) > 0:
                            pct = ((all_s <= my_s).sum() / len(all_s)) * 100
                            subject_ranks.append({'과목': r['과목'], '백분위': pct})
                    
                    if subject_ranks:
                        sr_df = pd.DataFrame(subject_ranks).sort_values('백분위', ascending=False)
                        strengths = sr_df.head(2)['과목'].tolist()
                        weaknesses = sr_df.tail(2)['과목'].tolist()
                        
                        st.markdown(f"""
                        <div style="display: flex; gap: 15px; margin-bottom: 25px; margin-top: 10px;">
                            <div style="flex: 1; background: #EFF6FF; border: 1px solid #BFDBFE; padding: 20px; border-radius: 8px;">
                                <div style="color: #1E3A8A; font-weight: 800; margin-bottom: 8px; font-size: 1.1rem;">🔥 {sel_term} 강점 과목 (백분위 기준)</div>
                                <div style="color: #1E40AF; font-size: 1.3rem; font-weight: 800;">{', '.join(strengths) if strengths else '-'}</div>
                            </div>
                            <div style="flex: 1; background: #FEF2F2; border: 1px solid #FECACA; padding: 20px; border-radius: 8px;">
                                <div style="color: #991B1B; font-weight: 800; margin-bottom: 8px; font-size: 1.1rem;">🛠️ {sel_term} 보완 필요 과목 (백분위 기준)</div>
                                <div style="color: #B91C1C; font-size: 1.3rem; font-weight: 800;">{', '.join(weaknesses) if weaknesses else '-'}</div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                all_term_raw = df_scores[(df_scores['학기'] == sel_term) & (df_scores['시험'] == '학기말')]
                raw_sums = all_term_raw.groupby('고유번호')[s_col].apply(lambda x: x.apply(safe_numeric).sum())
                my_raw = raw_sums.get(sel_uid, 0)
                my_raw_rank = (raw_sums > my_raw).sum() + 1
                total_raw_st = len(raw_sums)
                
                st.info(f"🏆 **[{sel_term} 학기말]** 원점수 총합 기준 예상 등수: **전교 {my_raw_rank}등** / 전체 {total_raw_st}명")
                st.markdown("<br>", unsafe_allow_html=True)

                for i in range(0, len(f), 4):
                    cols = st.columns(4)
                    for j in range(4):
                        if i + j < len(f):
                            r = f.iloc[i + j]
                            my_subj_s = safe_numeric(r.get(s_col, 0))
                            all_subj_s = all_term_raw[all_term_raw['과목'] == r['과목']][s_col].apply(safe_numeric).dropna()
                            subj_rank = (all_subj_s > my_subj_s).sum() + 1
                            subj_total = len(all_subj_s)
                            
                            with cols[j]:
                                st.markdown(f"""
                                <div style="background:white; border: 1px solid #CBD5E1; padding: 18px 10px; border-radius: 6px; text-align: center; margin-bottom: 15px; border-top: 4px solid #1E3A8A; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                                    <div style="color:#64748B; font-size:1rem; font-weight:700; margin-bottom:8px;">{r['과목']}</div>
                                    <div style="color:#0F172A; font-size:1.6rem; font-weight:800; margin-bottom:8px;">{r.get('등급','-')}등급 <span style="font-size:1.1rem; color:#475569;">({r.get('성취도','')})</span></div>
                                    <div style="background:#F1F5F9; border-radius:4px; padding:6px; color:#DC2626; font-size:0.95rem; font-weight:800;">
                                        전교 {subj_rank}등 <span style="color:#64748B; font-weight:600; font-size:0.85rem;">/ {subj_total}명</span>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
            else:
                p_d = []
                for _, r in f.iterrows():
                    all_e = df_scores[(df_scores['학기']==sel_term)&(df_scores['시험']==exam)&(df_scores['과목']==r['과목'])][s_col].apply(safe_numeric).dropna()
                    my_s = safe_numeric(r.get(s_col,0))
                    p_d.append({'과목':r['과목'], '점수':round(my_s,2), '중위값':round(all_e.median() if not all_e.empty else 0,2), '백분위':round((all_e<=my_s).sum()/len(all_e)*100 if not all_e.empty else 0,2)})
                pdf = pd.DataFrame(p_d)
                fig = px.bar(pdf, x='과목', y='점수', color='과목', text=pdf['점수'].apply(lambda x: f"{x:.2f}"), color_discrete_sequence=px.colors.qualitative.Prism)
                fig.add_trace(go.Scatter(x=pdf['과목'], y=pdf['중위값'], name="학년 중위값", mode='markers', marker=dict(size=12, color='#1E293B', symbol='diamond')))
                fig.add_trace(go.Scatter(x=pdf['과목'], y=pdf['백분위'], name="백분위(%)", yaxis="y2", mode='lines+markers', line=dict(color='#DC2626', width=2)))
                fig.update_layout(yaxis=dict(title="원점수", range=[0,105]), yaxis2=dict(overlaying="y", side="right", title="백분위(%)", range=[0,105]))
                st.plotly_chart(fig, use_container_width=True)
                st.table(style_centered(pdf[['과목', '점수', '중위값', '백분위']].rename(columns={'점수':'취득 점수', '백분위':'백분위(%)'})).format(precision=2))
        else: st.info("해당 시험의 성적 데이터가 없습니다.")
            
    with t2:
        st.subheader("학기말 성적 및 내신 평점 산출")
        f_df = uid_scores[uid_scores['시험'] == '학기말'].copy()
        u_col = '단위' if '단위' in f_df.columns else ('이수단위' if '이수단위' in f_df.columns else '')
        
        if not f_df.empty and u_col:
            f_df['9등급(자동)'] = f_df.apply(lambda r: calc_9_tier(safe_numeric(r.get(s_col,0)), df_scores[(df_scores['학기']==r['학기'])&(df_scores['시험']=='학기말')&(df_scores['과목']==r['과목'])][s_col].apply(safe_numeric).dropna()), axis=1)
            sel_rows = st.data_editor(f_df[[c for c in ['학기','과목','점수','등급','성취도',u_col,'9등급(자동)'] if c in f_df.columns]], use_container_width=True)
            c_df = sel_rows[sel_rows[u_col].apply(safe_numeric)>0].copy()
            
            if not c_df.empty:
                all_term_df = df_scores[(df_scores['학기'] == sel_term) & (df_scores['시험'] == '학기말')].copy()
                all_term_df[u_col] = all_term_df[u_col].apply(safe_numeric)
                all_term_df[s_col] = all_term_df[s_col].apply(safe_numeric)
                all_term_df['등급'] = all_term_df['등급'].apply(safe_numeric)
                
                def assign_9_tier_batch(group):
                    all_s_batch = group[s_col].dropna()
                    return group[s_col].apply(lambda x: calc_9_tier(x, all_s_batch))
                all_term_df['9등급(자동)'] = all_term_df.groupby('과목', group_keys=False).apply(assign_9_tier_batch)
                
                def calc_gpas(student_df):
                    valid_df = student_df[student_df[u_col] > 0]
                    total_u = valid_df[u_col].sum()
                    if total_u == 0: return pd.Series({'g5': 9.0, 'g9': 9.0})
                    g5_val = (valid_df['등급'] * valid_df[u_col]).sum() / total_u
                    g9_val = (valid_df['9등급(자동)'] * valid_df[u_col]).sum() / total_u
                    return pd.Series({'g5': g5_val, 'g9': g9_val})
                
                gpas = all_term_df.groupby('고유번호').apply(calc_gpas)
                
                my_g5 = gpas.loc[sel_uid, 'g5'] if sel_uid in gpas.index else 0
                my_g9 = gpas.loc[sel_uid, 'g9'] if sel_uid in gpas.index else 0
                
                rank_g5 = (gpas['g5'] < my_g5).sum() + 1
                rank_g9 = (gpas['g9'] < my_g9).sum() + 1
                total_st = len(gpas)

                c1, c2 = st.columns(2)
                c1.metric(f"5등급제 평균 평점 (전교 {rank_g5}등 / {total_st}명)", f"{my_g5:.2f} 등급")
                c2.metric(f"9등급제 환산 평점 (전교 {rank_g9}등 / {total_st}명)", f"{my_g9:.2f} 등급")
        else: st.info("학기말 데이터와 '단위' 기준 데이터가 필요합니다.")
            
    with t3:
        st.subheader("과목군별 누적 성적 추이 분석 (백분위 기준)")
        if '교과군' in uid_scores.columns:
            trend_df = uid_scores[uid_scores['시험'].str.contains('고사')].copy()
            trend_df['백분위'] = trend_df.apply(lambda r: ((df_scores[(df_scores['학기']==r['학기'])&(df_scores['시험']==r['시험'])&(df_scores['과목']==r['과목'])][s_col].apply(safe_numeric).dropna() <= safe_numeric(r.get(s_col,0))).sum() / len(df_scores[(df_scores['학기']==r['학기'])&(df_scores['시험']==r['시험'])&(df_scores['과목']==r['과목'])][s_col].apply(safe_numeric).dropna()) * 100) if not df_scores[(df_scores['학기']==r['학기'])&(df_scores['시험']==r['시험'])&(df_scores['과목']==r['과목'])][s_col].apply(safe_numeric).dropna().empty else 0, axis=1)
            trend_df['점수'] = trend_df[s_col].apply(safe_numeric)
            trend_df['시기'] = trend_df['학기'] + " " + trend_df['시험']
            trend_df['순서'] = trend_df.apply(get_time_rank, axis=1)
            trend_df = trend_df.sort_values('순서')
            s_g = st.multiselect("분석 교과군 선택", sorted(trend_df['교과군'].dropna().unique()), default=sorted(trend_df['교과군'].dropna().unique())[:1])
            if s_g: 
                plot_t = trend_df[trend_df['교과군'].isin(s_g)]
                fig_t = px.line(plot_t, x='시기', y='백분위', color='과목', markers=True, text=plot_t['점수'].apply(lambda x: f"{x:.2f}"))
                fig_t.update_traces(textposition="top center")
                fig_t.update_layout(yaxis=dict(title="백분위(%) - 상단일수록 우수", range=[-5, 110]))
                st.plotly_chart(fig_t, use_container_width=True)

# ==========================================
# 7. 모의고사 분석
# ==========================================
elif menu == "모의고사 분석":
    mt1, mt2, mt3 = st.tabs(["전체 성적 추이", "단일 시험 분석", "누적 취약점 분석"])
    uid_mk = df_mock[df_mock['고유번호'] == sel_uid].copy()
    
    with mt1:
        if not uid_mk.empty:
            latest = uid_mk.iloc[-1]
            st.subheader(f"최근 모의고사 종합 요약: {latest.get('시험명', '최근 시험')}")
            subj_map = {"국어": ["국어"], "수학": ["수학"], "영어": ["영어"], "한국사": ["한국사", "국사"], "사탐": ["사탐", "사회"], "과탐": ["과탐", "과학"]}
            summary = []
            for n, keys in subj_map.items():
                def f_val(k_list, target_k):
                    for col in latest.index:
                        if any(s in str(col).replace(" ", "").replace("_", "").lower() for s in k_list) and target_k in str(col): return latest[col]
                    return '-'
                v_p = f_val(keys, '표'); v_b = f_val(keys, '백분'); v_g = f_val(keys, '등급')
                summary.append({"과목": n, "표준점수": v_p, "백분위": f"{float(v_b):.2f}%" if v_b!='-' else "-", "등급": f"{int(float(v_g))}등급" if v_g!='-' else "-"})
            st.table(style_centered(pd.DataFrame(summary)))
            st.markdown("---")
            p_cols = [c for c in uid_mk.columns if '백분' in c]
            if p_cols:
                plot_m = uid_mk[['시험명'] + p_cols].copy()
                for c in p_cols: plot_m[c] = plot_m[c].apply(safe_numeric)
                
                fig_m = px.line(plot_m.melt(id_vars=['시험명'], var_name='과목', value_name='백분위'), 
                                x='시험명', y='백분위', color='과목', symbol='과목', line_dash='과목', markers=True)
                fig_m.update_traces(marker=dict(size=12), line=dict(width=3))
                fig_m.update_layout(yaxis=dict(range=[0, 105]))
                st.plotly_chart(fig_m, use_container_width=True)
                
            st.dataframe(style_centered(uid_mk.drop(columns=['학번', '표시식별', '학생명', '반', '고유번호'], errors='ignore')), use_container_width=True)
        else: st.info("모의고사 성적 기록이 존재하지 않습니다.")

    with mt2:
        st.subheader("단일 시험 오답 정밀 분석")
        if not df_m_info.empty and not df_m_ans.empty:
            s_ex = st.selectbox("시험명 선택", df_m_ans['시험명'].unique(), key='mk2_ex')
            s_su = st.selectbox("영역 선택", df_m_ans[df_m_ans['시험명']==s_ex]['과목'].unique(), key='mk2_su')
            ex_i = df_m_info[(df_m_info['시험명']==s_ex)&(df_m_info['과목']==s_su)].copy()
            st_a = df_m_ans[(df_m_ans['시험명']==s_ex)&(df_m_ans['과목']==s_su)&(df_m_ans['고유번호']==sel_uid)]
            if not ex_i.empty and not st_a.empty:
                ox_list = list(re.sub(r'[^OXox]', '', str(st_a.iloc[0]['OMR답안'])).upper())
                ex_i['채점결과'] = [ox_list[i] if i<len(ox_list) else 'X' for i in range(len(ex_i))]
                wrong = ex_i[ex_i['채점결과'] == 'X'].copy()
                if wrong.empty: st.success("해당 영역의 오답 문항이 존재하지 않습니다.")
                else:
                    st.table(style_centered(wrong[[c for c in ['문항번호', '정답', '채점결과', '출제 의도', '출제의도', '배점'] if c in wrong.columns]].copy()))
                    cache_key = f"mock_single_{s_ex}_{s_su}"
                    if st.button("맞춤형 학습 처방전 도출"):
                        if ai_model:
                            with st.spinner("AI 엔진 분석 진행 중..."):
                                it_col = '출제 의도' if '출제 의도' in wrong.columns else ('출제의도' if '출제의도' in wrong.columns else None)
                                prompt = f"고등학생이 모의고사 {s_su} 과목에서 다음 출제 의도의 문항들을 오답 처리했습니다: [{', '.join(wrong[it_col].dropna().astype(str).tolist()) if it_col else ''}]. 해당 학생의 핵심 취약점을 진단하고, 구체적이고 실질적인 보완 전략을 'AI' 단어 없이 전문적인 개조식(명사형 종결)으로 제시하십시오."
                                try: st.session_state["ai_cache"][cache_key] = ai_model.generate_content(prompt).text
                                except Exception as e: st.error(f"분석 오류: {e}")
                    if cache_key in st.session_state.get("ai_cache", {}):
                        st.markdown(f'<div style="background:#F8FAFC; border-left:4px solid #1E3A8A; padding:20px; border-radius:4px; margin-top:20px;"><b>[ 컨설팅 처방 ]</b><br><br>{st.session_state["ai_cache"][cache_key]}</div>', unsafe_allow_html=True)
            else: st.warning("비교 분석을 위한 문항 정보 또는 학생 답안 데이터가 부족합니다.")
        else: st.info("문항 정보 시트 설정이 필요합니다.")

    with mt3:
        st.subheader("영역별 누적 취약점 클러스터링")
        if not df_m_info.empty and not df_m_ans.empty:
            user_all_ans = df_m_ans[df_m_ans['고유번호'] == sel_uid].copy()
            if not user_all_ans.empty:
                sel_subj_cum = st.selectbox("분석 대상 영역", user_all_ans['과목'].unique(), key='cum_subj')
                all_wrong_intents = []
                for _, ans_row in user_all_ans[user_all_ans['과목'] == sel_subj_cum].iterrows():
                    ox_list = list(re.sub(r'[^OXox]', '', str(ans_row['OMR답안'])).upper())
                    ex_i = df_m_info[(df_m_info['시험명'] == ans_row['시험명']) & (df_m_info['과목'] == sel_subj_cum)].copy()
                    if not ex_i.empty:
                        ex_i['채점결과'] = [ox_list[i] if i < len(ox_list) else 'X' for i in range(len(ex_i))]
                        wrong_df = ex_i[ex_i['채점결과'] == 'X']
                        intent_col = '출제 의도' if '출제 의도' in wrong_df.columns else ('출제의도' if '출제의도' in wrong_df.columns else None)
                        if intent_col: all_wrong_intents.extend(wrong_df[intent_col].dropna().astype(str).tolist())
                if not all_wrong_intents: st.success("선택 영역의 누적 오답 데이터가 없습니다.")
                else:
                    st.info(", ".join(all_wrong_intents))
                    cache_key = f"mock_cum_{sel_subj_cum}"
                    if st.button("누적 약점 패턴 분석 및 장기 로드맵 도출"):
                        if ai_model:
                            with st.spinner("패턴 클러스터링 진행 중..."):
                                prompt_cum = f"학생이 모의고사 {sel_subj_cum} 과목에서 누적 반복하여 오답을 낸 문항의 출제 의도 목록입니다: [{', '.join(all_wrong_intents)}]. 이를 바탕으로 공통된 취약점 패턴 3가지를 도출하고, 이를 극복하기 위한 장기 학습 로드맵을 'AI' 단어 없이 전문적인 개조식(명사형)으로 작성하십시오."
                                try: st.session_state["ai_cache"][cache_key] = ai_model.generate_content(prompt_cum).text
                                except Exception as e: st.error(f"오류 발생: {e}")
                    if cache_key in st.session_state.get("ai_cache", {}):
                        st.markdown(f'<div style="background:#F8FAFC; border-left:4px solid #1E3A8A; padding:20px; border-radius:4px; margin-top:20px;"><b>[ 정밀 분석 보고서 ]</b><br><br>{st.session_state["ai_cache"][cache_key]}</div>', unsafe_allow_html=True)
            else: st.info("모의고사 답안 누적 기록이 없습니다.")

# ==========================================
# 8. 성찰 리포트 
# ==========================================
elif menu == "학습 성찰 리포트":
    curr_y = sel_term[:3] if sel_term else ""
    uid_ref = df_ref[(df_ref['고유번호'] == sel_uid) & (df_ref.apply(lambda r: curr_y in str(r.get('학기','')) or curr_y in str(r.get('시험명','')), axis=1))].copy() if not df_ref.empty else pd.DataFrame()
    if not uid_ref.empty:
        st.subheader(f"{sel_name} 학생 고사 성찰 기록")
        s_ex = st.selectbox("시험 선택", uid_ref['시험명'].unique())
        row = uid_ref[uid_ref['시험명'] == s_ex].iloc[-1]
        cols = st.columns(2); idx = 0
        for k, v in row.items():
            if k in ['Camp', '학번', '이름', '성명', '학생식별', '표시식별', '학생명', '시험명', '반', '고유번호', '학기'] or not v: continue
            with cols[idx % 2]: st.markdown(f'<div style="background:white; border-left:4px solid #1E3A8A; padding:15px; margin-bottom:10px; border-radius:4px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);"><b>{k}</b><br><span style="color:#475569;">{v}</span></div>', unsafe_allow_html=True)
            idx += 1
        st.markdown("---")
        cache_key = f"ref_{s_ex}"
        if st.button("성찰 내용 기반 피드백 생성"):
            if ai_model:
                with st.spinner("피드백 보고서 작성 중..."):
                    clean_data = {str(k): str(v) for k, v in row.items() if len(str(v)) > 5 and k not in ['학번', '타임스탬프']}
                    try: st.session_state["ai_cache"][cache_key] = ai_model.generate_content(f"학생의 고사 후 학습 성찰 내용입니다: {str(clean_data)}. 진학 컨설턴트 및 담임 교사의 관점에서 구체적인 개선 피드백을 'AI' 단어 없이 개조식 명사형으로 작성해주십시오.").text
                    except Exception as e: st.error(f"오류: {e}")
        if cache_key in st.session_state.get("ai_cache", {}):
            st.markdown(f'<div style="background:#F8FAFC; border-left:4px solid #1E3A8A; padding:20px; border-radius:4px; margin-top:20px;"><b>[ 전문가 피드백 ]</b><br><br>{st.session_state["ai_cache"][cache_key]}</div>', unsafe_allow_html=True)
    else: st.info("작성된 성찰 기록이 존재하지 않습니다.")

# ==========================================
# 9. 비교과 타임라인
# ==========================================
elif menu == "비교과 활동 타임라인":
    curr_y = sel_term[:3] if sel_term else ""
    t_col = next((c for c in df_act.columns if any(k in c for k in ['학년', '학기', '시기', '연도'])), None)
    uid_act = df_act[(df_act['고유번호'] == sel_uid) & (df_act[t_col].str.contains(curr_y, na=False))].copy() if t_col else df_act[df_act['고유번호'] == sel_uid].copy()
    
    if not uid_act.empty:
        col_type = next((c for c in uid_act.columns if '성격' in c), None)
        col_comp = next((c for c in uid_act.columns if '역량' in c), None)
        st.subheader("핵심 역량별 활동 분포 요약")
        comp_standards = ["탐구력/지식정보처리", "창의적 사고", "비판적 사고", "자기주도성/자기관리", "협력적 소통", "공동체 의식/윤리"]
        s_cols = st.columns(6)
        for i, comp_name in enumerate(comp_standards):
            count = uid_act[col_comp].str.contains(comp_name, na=False).sum() if col_comp else 0
            with s_cols[i]: st.markdown(f'<div class="stat-box" style="padding:10px;"><small style="color:#64748B; font-size:0.75rem;">{comp_name}</small><br><b style="font-size:1.3rem; color:#1E3A8A;">{count}건</b></div>', unsafe_allow_html=True)
                
        st.markdown("---")
        f1, f2 = st.columns(2)
        filtered_act = uid_act.copy()
        with f1:
            sel_type = st.selectbox("활동 성격 분류", ["전체", "자율 활동", "진로 활동", "독서 활동", "문헌 탐구 활동", "협력 토론 활동", "실증 탐구 활동", "비평 성찰 활동", "발표 공유 활동", "융합 탐구 활동", "교사 개별 상담"])
            if sel_type != "전체" and col_type: filtered_act = filtered_act[filtered_act[col_type].str.contains(sel_type, na=False)]
        with f2:
            sel_comp = st.selectbox("핵심 역량 분류", ["전체"] + comp_standards)
            if sel_comp != "전체" and col_comp: filtered_act = filtered_act[filtered_act[col_comp].str.contains(sel_comp, na=False)]
        st.write(f"검색 결과: 총 **{len(filtered_act)}**건의 데이터가 확인되었습니다.")
        
        for i, row in filtered_act.sort_values('활동 일자', ascending=False).iterrows():
            st.markdown(f"""
            <div class="timeline-card">
                <span class="badge" style="background:#F1F5F9; color:#0F172A;">{row.get(col_type,'활동유형')}</span>
                <span class="badge" style="background:#F0FDF4; color:#166534; border-color: #BBF7D0;">{row.get(col_comp,'역량')}</span>
                <div style="font-size:1.25rem; font-weight:800; color:#0F172A; margin:10px 0;">{row.get('활동 주제','주제 없음')}</div>
                <div style="font-size:0.85rem; color:#64748B; margin-bottom:15px; border-bottom: 1px dashed #CBD5E1; padding-bottom: 10px;">일자: {row.get('활동 일자','-')} &nbsp;|&nbsp; 연계 교과: {row.get('연계 가능 교과(선택)', '-')}</div>
                <div style="background:#F8FAFC; padding:18px; border-radius:4px; font-size:0.95rem; line-height:1.7;">
                    <b style="color:#1E3A8A;">[ 활동 동기 ]</b><br>{row.get('활동 동기(왜 시작했나요)', '-')}<br><br>
                    <b style="color:#1E3A8A;">[ 핵심 활동 내용 ]</b><br>{row.get('핵심 활동 내용(무엇을 어떻게 했나요)', row.get('핵심 활동 내용', '-'))}<br><br>
                    <b style="color:#1E3A8A;">[ 성취 및 결과 ]</b><br>{row.get('결과 및 배우고 느낀 점(어떤 변화가 있었나요?)', row.get('결과 및 배우고 느낀 점', '-'))}
                </div>
            </div>
            """, unsafe_allow_html=True)
            cache_key = f"act_{i}"
            if st.button(f"배경 기재 문구 추출 (ID: {i})"):
                if ai_model:
                    with st.spinner("초안 텍스트 추출 중..."):
                        try: st.session_state["ai_cache"][cache_key] = ai_model.generate_content(f"다음 활동 내용을 바탕으로 학교생활기록부에 즉시 기재할 수 있는 수준의 공식적이고 전문적인 문구를 작성하십시오. 'AI' 단어를 배제하고 개조식(~함, ~임) 또는 평어체로 작성 바랍니다. 내용: {row.get('핵심 활동 내용', '')}").text
                        except Exception as e: st.error(f"오류: {e}")
            if cache_key in st.session_state.get("ai_cache", {}): st.info(st.session_state["ai_cache"][cache_key])
    else: st.info("등록된 비교과 활동 내역이 없습니다.")

# ==========================================
# 10. 상담 기록 관리
# ==========================================
elif menu == "상담 기록 관리":
    u_cs = df_counsel[df_counsel['고유번호']==sel_uid].copy() if '고유번호' in df_counsel.columns else df_counsel[df_counsel['학번']==sel_student.split(" ")[0]].copy()
    tab_new, tab_history = st.tabs(["신규 상담 작성", "누적 기록 열람"])
    with tab_new:
        st.subheader("신규 상담 내용 등록")
        with st.form("c_f", clear_on_submit=True):
            d = st.date_input("상담 진행 일자")
            t = st.selectbox("상담 주요 유형", ["학습/성적", "진로/진학", "학교생활/교우관계", "심리/정서", "학부모상담", "기타"])
            c = st.text_area("상담 결과 및 주요 코멘트", height=150, placeholder="보안 유지가 필요한 세부 내용을 기재하십시오.")
            if st.form_submit_button("데이터베이스 전송 및 저장"):
                if c.strip():
                    with st.spinner("보안 연결 후 저장 중..."):
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
                            st.success("데이터가 안전하게 기록되었습니다. 좌측 메뉴에서 동기화를 진행하여 주십시오.")
                        except Exception as e: st.error(f"서버 전송 오류: {e}")
                            
    with tab_history:
        st.subheader(f"{sel_name} 누적 상담 히스토리")
        st.info("안내: 학생 동석 상담 시 본 탭의 열람에 주의를 요합니다.")
        if not u_cs.empty:
            for _, r in u_cs.sort_values('상담일자', ascending=False).iterrows():
                st.markdown(f"""
                <div class="timeline-card" style="border-left: 4px solid #475569;">
                    <span class="badge" style="background:#F1F5F9; color:#0F172A;">{r.get("상담유형", "일반 상담")}</span>
                    <div style="font-size:0.85rem; color:#64748B; margin-bottom:10px;">상담일자: {r.get("상담일자", "-")}</div>
                    <div style="background:#F8FAFC; padding:18px; border-radius:4px; font-size:0.95rem; line-height:1.7; color:#1E293B;">{r.get("상담내용", "-")}</div>
                </div>
                """, unsafe_allow_html=True)
        else: st.warning("조회된 이전 상담 이력이 없습니다.")

# ==========================================
# 11. 종합 컨설팅 리포트 출력 
# ==========================================
elif menu == "종합 컨설팅 리포트 출력":
    
    st.subheader("진학 컨설팅 종합 의견 산출")
    st.write("내신, 모의고사, 비교과 데이터를 병합하여 입시 전문가 수준의 통합 전략을 즉시 도출하고 구체적으로 백업합니다.")
    
    master_prompt_template = """
    당신은 한일고등학교의 20년 경력 베테랑 진학부장 자격을 가진 담임 교사입니다. 학생({name})의 성적 및 비교과 데이터를 정밀 분석하여 학부모와 학생에게 전달할 '교사 종합 의견서'를 작성하십시오.
    누가 봐도 컴퓨터나 인공지능이 자동 생성한 느낌이 드는 뻔하고 광범위한 조언(예: '시간 관리를 잘해야 함', '오답 노트를 쓰세요')은 완전히 배제하십시오. 20년 차 교사의 예리한 통찰력이 돋보이도록 실제 취득한 과목명과 등급의 등락 추이를 정확히 짚어가며 구체적이고 현실적인 솔루션만을 작성해야 합니다.

    [제공된 학생 데이터]
    1. 최근 내신 성적 내역: {g_data}
    2. 최근 모의고사 성적 추이: {m_data}
    3. 비교과 활동 현황: {a_data}

    [작성 항목 및 표기 방식]
    [1. 학업 성취 종합 진단]
    - 반드시 이 대괄호 제목 양식을 사용하고 아래 줄에 내용을 서술하십시오.
    - 데이터에 나타난 과목명과 등급을 직접 명시하며 종결하십시오. (예: '수학 영역의 경우 1학기말 3등급에서 이번 고사 원점수 상승과 함께 예상 2등급으로 진입하여 긍정적 추이를 보임.')
    
    [2. 최우선 공략 과목 및 실천 전략]
    - 구체적인 단원명이나 학습 방식을 교사 입장에서 명확하게 지시하십시오. (예: '영어 독해의 경우 빈칸 추론 기출 문항 3개년 매일 5문항씩 분석 필요함.')
    
    [3. 비교과 및 진로 연계 방향]
    - 다음 학기에 세부능력 및 특기사항에 보완해야 할 구체적인 탐구 방향을 제안하십시오.
    
    [4. 담임 교사의 따뜻한 격려]
    - 마지막 줄에는 학생의 이름({name})을 부르며 기운을 북돋아 주는 교사의 진심 어린 격려를 따뜻한 문장으로 딱 한 줄만 추가하십시오. (예: '로운아, 네 잠재력과 성실함을 선생님은 굳게 믿는다. 지치지 말고 함께 끝까지 달려보자.')

    [🔥 엄격한 금지 규칙 - 위반 시 에러]
    - 'AI', '인공지능', '제미나이', '컨설턴트', '플랫폼', '데이터 분석 결과' 등 시스템이 개입한 듯한 단어는 절대 금지합니다.
    - asterisks(**), 하이픈(-), 별표(*), 샵(#) 등의 마크다운 기호는 절대 사용하지 마십시오. 종이에 출력했을 때 지저분한 기호가 노출되어 신뢰도가 떨어집니다. 문단 기호가 필요하다면 숫자(1., 2.)나 평서문으로만 매끄럽게 이어지게 하십시오.
    - 1~3번 항목은 전문적이고 신뢰감을 주는 문어체 개조식(~함, ~임)으로 종결하십시오. 4번 격려 문장만 따뜻한 평어체로 작성합니다.
    """

    c_btn1, c_btn2 = st.columns(2)
    with c_btn1:
        if st.button("현재 학생 리포트 생성", use_container_width=True):
            if ai_model:
                with st.spinner("AI 엔진 통합 분석 알고리즘 가동 중..."):
                    uid_scores = df_scores[df_scores['고유번호'] == sel_uid]
                    s_col = next((c for c in uid_scores.columns if '점수' in c.replace(" ","")), '점수')
                    g_data = uid_scores.tail(15)[['학기','시험','과목',s_col,'등급']].to_dict('records') if not uid_scores.empty else "기록 없음"
                    uid_mk = df_mock[df_mock['고유번호'] == sel_uid]
                    m_data = uid_mk.tail(2).drop(columns=['학번','표시식별','학생명','반','고유번호'], errors='ignore').to_dict('records') if not uid_mk.empty else "기록 없음"
                    uid_act = df_act[df_act['고유번호'] == sel_uid]
                    a_data = f"비교과 활동 총 {len(uid_act)}건" if not uid_act.empty else "활동 기록 없음"
                    
                    p_text = master_prompt_template.format(name=sel_name, g_data=str(g_data), m_data=str(m_data), a_data=str(a_data))
                    
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            resp = ai_model.generate_content(p_text).text
                            
                            resp = resp.replace("**", "").replace("###", "").replace("##", "").replace("#", "").strip()
                            
                            st.session_state["ai_cache"]["master_consulting"] = resp
                            
                            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
                            doc = gspread.authorize(creds).open("40기 마스터 파일")
                            try: sh_c = doc.worksheet("72_종합컨설팅")
                            except:
                                sh_c = doc.add_worksheet(title="72_종합컨설팅", rows="1000", cols="5")
                                sh_c.append_row(["고유번호", "학번", "이름", "컨설팅내용", "최근업데이트"])
                            
                            all_uids = sh_c.col_values(1)
                            u_hakbun = sel_student.split(" ")[0]
                            if str(sel_uid) in all_uids:
                                row_idx = all_uids.index(str(sel_uid)) + 1
                                sh_c.update_cell(row_idx, 4, resp)
                                sh_c.update_cell(row_idx, 5, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                            else:
                                sh_c.append_row([str(sel_uid), str(u_hakbun), str(sel_name), resp, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                            
                            st.success("✅ 컨설팅 보고서가 도출되었으며 구글 드라이브에 안전하게 영구 업데이트되었습니다!")
                            break
                            
                        except Exception as e:
                            error_msg = str(e)
                            if "429" in error_msg or "Quota" in error_msg:
                                if attempt < max_retries - 1:
                                    st.warning(f"⏳ 구글 API 무료 한도 도달! 35초 대기 후 자동으로 재시도합니다... (시도 {attempt+1}/{max_retries})")
                                    time.sleep(35.0)
                                    continue 
                            st.error(f"생성 및 백업 시스템 오류: {e}")
                            break
            else: st.warning("AI 엔진 연결 상태를 확인해주십시오.")

    with c_btn2:
        if st.button("학급 단위 일괄 산출 (자동화 프로세스)", use_container_width=True):
            if ai_model:
                class_uids = class_students['고유번호'].tolist()
                class_names = class_students['학생명'].tolist()
                class_hakbuns = class_students['학번'].tolist()
                
                my_bar = st.progress(0, text="학급 일괄 프로세스 진행 중. 창을 유지해 주십시오.")
                success_count = 0
                
                scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
                doc = gspread.authorize(creds).open("40기 마스터 파일")
                try: sh_c = doc.worksheet("72_종합컨설팅")
                except:
                    sh_c = doc.add_worksheet(title="72_종합컨설팅", rows="1000", cols="5")
                    sh_c.append_row(["고유번호", "학번", "이름", "컨설팅내용", "최근업데이트"])
                
                for i, (u_id, u_name, u_hakbun) in enumerate(zip(class_uids, class_names, class_hakbuns)):
                    if u_id not in st.session_state["global_ai_cache"]: st.session_state["global_ai_cache"][u_id] = {}
                    
                    if "master_consulting" in st.session_state["global_ai_cache"][u_id]:
                        success_count += 1
                    else:
                        uid_scores = df_scores[df_scores['고유번호'] == u_id]
                        s_col = next((c for c in uid_scores.columns if '점수' in c.replace(" ","")), '점수')
                        g_data = uid_scores.tail(15)[['학기','시험','과목',s_col,'등급']].to_dict('records') if not uid_scores.empty else "기록 없음"
                        uid_mk = df_mock[df_mock['고유번호'] == u_id]
                        m_data = uid_mk.tail(2).drop(columns=['학번','표시식별','학생명','반','고유번호'], errors='ignore').to_dict('records') if not uid_mk.empty else "기록 없음"
                        uid_act = df_act[df_act['고유번호'] == u_id]
                        a_data = f"비교과 활동 총 {len(uid_act)}건" if not uid_act.empty else "활동 기록 없음"
                        real_name = u_name.split(" ")[-1] if " " in u_name else u_name
                        
                        p_text = master_prompt_template.format(name=real_name, g_data=str(g_data), m_data=str(m_data), a_data=str(a_data))
                        
                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                resp = ai_model.generate_content(p_text).text
                                resp = resp.replace("**", "").replace("###", "").replace("##", "").replace("#", "").strip()
                                
                                st.session_state["global_ai_cache"][u_id]["master_consulting"] = resp
                                
                                all_uids = sh_c.col_values(1)
                                if str(u_id) in all_uids:
                                    row_idx = all_uids.index(str(u_id)) + 1
                                    sh_c.update_cell(row_idx, 4, resp)
                                    sh_c.update_cell(row_idx, 5, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                                else:
                                    sh_c.append_row([str(u_id), str(u_hakbun), str(real_name), resp, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                                
                                success_count += 1
                                time.sleep(5.0) 
                                break
                            except Exception as e:
                                error_msg = str(e)
                                if "429" in error_msg or "Quota" in error_msg:
                                    if attempt < max_retries - 1:
                                        my_bar.progress(i / len(class_uids), text=f"[시스템 보호] 호출 제한 도달. 35초 대기 후 {u_name}부터 이어서 자동 재개합니다.")
                                        time.sleep(35.0)
                                        continue
                                st.error(f"{u_name} 분석 중 데이터 전송 누락: {e}")
                                break
                            
                    my_bar.progress((i + 1) / len(class_uids), text=f"진행 상태: {u_name} ({i+1}/{len(class_uids)})")
                
                if success_count == len(class_uids): st.success(f"학급 전체({success_count}명) 분석 및 구글 마스터 파일 최신화 저장이 완료되었습니다.")
            else: st.warning("AI 모델 접속에 실패했습니다.")

    st.markdown("---")
    
    col_title, col_print_single, col_print_class = st.columns([3, 1, 1])
    with col_title:
        st.subheader("인쇄 항목 구성 선택")
        st.write("보고서에 포함될 세부 모듈을 선택하여 주십시오.")
        
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: p_grade = st.checkbox("내신 요약 성적표", value=True)
    with c2: p_mock = st.checkbox("모의고사 등락 추이", value=True)
    with c3: p_act = st.checkbox("비교과 역량 분포", value=True)
    with c4: p_ai = st.checkbox("세부 영역별 처방전", value=True)
    with c5: p_master = st.checkbox("종합 컨설팅 총평", value=True)

    st.markdown("---")
    st.info("안내: 하단의 버튼을 클릭하면 최적화된 양식의 출력 전용 팝업창이 렌더링됩니다.")

    today_str = datetime.datetime.now().strftime("%Y년 %m월 %d일")
    
    html_head = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>종합 분석 리포트</title>
        <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@300;400;600;800&display=swap');
            body {{ font-family: 'Pretendard', sans-serif; color: #0F172A; line-height: 1.6; margin: 0 auto; padding: 40px 30px; max-width: 210mm; background: #FFFFFF; }}
            h3 {{ color: #1E3A8A; border-bottom: 2px solid #E2E8F0; padding-bottom: 8px; margin-top: 40px; font-weight: 800; font-size: 1.25rem; letter-spacing: -0.5px; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 0.95rem; border-top: 2px solid #0F172A; }}
            th, td {{ border-bottom: 1px solid #CBD5E1; padding: 12px 10px; text-align: center; }}
            th {{ background-color: #F8FAFC; color: #334155; font-weight: 700; }}
            .ai-box {{ background-color: #F8FAFC; border: 1px solid #E2E8F0; border-left: 4px solid #1E3A8A; padding: 25px; border-radius: 4px; line-height: 1.8; color: #1E293B; margin-bottom: 20px; text-align: justify; }}
            .no-break {{ page-break-inside: avoid; break-inside: avoid; margin-bottom: 30px; }}
            @media print {{
                body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; padding: 0; }}
                @page {{ margin: 15mm; }}
                .print-btn {{ display: none !important; }}
            }}
        </style>
    </head>
    <body>
        <div style="text-align: right; margin-bottom: 10px; position: sticky; top: 20px; z-index: 1000;" class="print-btn">
            <button onclick="window.print()" style="background-color: #1E3A8A; color: white; padding: 12px 24px; font-size: 1rem; font-weight: bold; border: none; border-radius: 4px; cursor: pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">인쇄 옵션 열기</button>
        </div>
    """

    def build_student_report_html(target_uid, target_student_str):
        target_name = target_student_str.split(" ")[1] if " " in target_student_str else target_student_str
        
        chunk = f"""
        <div style="display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 3px solid #1E3A8A; padding-bottom: 15px; margin-bottom: 35px;">
            <div style="display: flex; align-items: center; gap: 15px;">
        """
        if SCHOOL_LOGO_URL:
            chunk += f"""<img src="{SCHOOL_LOGO_URL}" style="height: 55px; object-fit: contain;" onerror="this.style.display='none'">"""
            
        chunk += f"""
                <div>
                    <h1 style="font-size: 2.1rem; margin: 0; color: #0F172A; letter-spacing: -1px;">개별 맞춤형 진학 분석 리포트</h1>
                    <div style="font-size: 1rem; color: #475569; font-weight: 600; margin-top: 5px;">한일고등학교 40기 진학컨설팅팀</div>
                </div>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 0.95rem; color: #64748B;">발행일자: {today_str}</div>
            </div>
        </div>
        <div style="text-align: center; font-size: 1.5rem; font-weight: 800; background-color: #F1F5F9; padding: 15px; border-radius: 4px; color: #1E3A8A; border: 1px solid #E2E8F0; margin-bottom: 20px; letter-spacing: 2px;">대상자 : {target_student_str}</div>
        """
        
        if p_grade:
            chunk += """<div class="no-break"><h3>[ Section 1 ] 학교 교과 내신 성적 분석</h3>"""
            uid_scores = df_scores[df_scores['고유번호'] == target_uid].copy()
            s_col = next((c for c in uid_scores.columns if '점수' in c.replace(" ","")), '점수')
            f_df = uid_scores[uid_scores['시험'] == '학기말'].copy()
            u_col = '단위' if '단위' in f_df.columns else ('이수단위' if '이수단위' in f_df.columns else '')
            if not f_df.empty and u_col:
                f_df['9등급(자동)'] = f_df.apply(lambda r: calc_9_tier(safe_numeric(r.get(s_col,0)), df_scores[(df_scores['학기']==r['학기'])&(df_scores['시험']=='학기말')&(df_scores['과목']==r['과목'])][s_col].apply(safe_numeric).dropna()), axis=1)
                t_u = f_df[u_col].apply(safe_numeric).sum()
                g5 = (f_df['등급'].apply(safe_numeric)*f_df[u_col].apply(safe_numeric)).sum()/t_u if t_u > 0 else 0
                g9 = (f_df['9등급(자동)']*f_df[u_col].apply(safe_numeric)).sum()/t_u if t_u > 0 else 0
                chunk += f"""
                <table style="margin-bottom: 20px;">
                    <tr style="background-color: #F8FAFC;">
                        <th>{sel_term} 5등급제 환산 평점</th>
                        <th>{sel_term} 9등급제 환산 평점</th>
                    </tr>
                    <tr>
                        <td style="font-size: 1.5rem; font-weight: 800; color: #1E3A8A;">{g5:.2f} 등급</td>
                        <td style="font-size: 1.5rem; font-weight: 800; color: #334155;">{g9:.2f} 등급</td>
                    </tr>
                </table>
                """
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
                    return f"{calc_5_tier(my_s, all_s)} / {calc_9_tier(my_s, all_s)}등급 [{rank}/{total}]"
                latest_df['등급(예상 등수)'] = latest_df.apply(format_expected_grade, axis=1)
                chunk += f"<div style='font-weight: 600; margin-bottom: 8px; color:#475569;'>▶ 최근 고사 상세 내역 ({latest_term} {latest_exam})</div>"
                target_cols = ['교과군', '과목', '단위', '이수단위', s_col, '원점수', '등급(예상 등수)', '성취도']
                display_cols = list(dict.fromkeys([c for c in target_cols if c in latest_df.columns]))
                chunk += "<table><tr>"
                for col in display_cols: chunk += f"<th>{col}</th>"
                chunk += "</tr>"
                for _, row in latest_df[display_cols].iterrows():
                    chunk += "<tr>"
                    for col in display_cols:
                        val = row[col]
                        val_str = f"{val:.2f}" if isinstance(val, (int, float)) and col == s_col else str(val)
                        chunk += f"<td>{val_str}</td>"
                    chunk += "</tr>"
                chunk += "</table>"
            else: chunk += "<p>조회된 교과 성적 데이터가 없습니다.</p>"
            chunk += "</div>"

        if p_mock:
            chunk += """<div class="no-break"><h3>[ Section 2 ] 수능 전국 모의고사 성적 추이</h3>"""
            uid_mk = df_mock[df_mock['고유번호'] == target_uid].copy()
            if not uid_mk.empty:
                chunk += f"<div style='font-weight: 600; margin-bottom: 8px; color:#475569;'>▶ 누적 성적 기록표</div>"
                raw_subjects = []
                for c in uid_mk.columns:
                    if any(x in c for x in ['표준점수', '표점', '백분위', '등급']):
                        subj = re.sub(r'표준점수|표점|백분위|등급|\s', '', c)
                        if subj and subj not in raw_subjects: raw_subjects.append(subj)
                def sort_key(x):
                    if '국어' in x: return 1
                    if '수학' in x: return 2
                    if '영어' in x: return 3
                    if '한국사' in x or '국사' in x: return 4
                    if '탐' in x or '과탐' in x or '사탐' in x: return 5 + raw_subjects.index(x)*0.1
                    return 10 + raw_subjects.index(x)*0.1
                ordered_subjects = sorted(raw_subjects, key=sort_key)
                
                chunk += "<table><tr><th style='border-top: none;'>평가명</th>"
                for subj in ordered_subjects: chunk += f"<th style='border-top: none;'>{subj}</th>"
                chunk += "</tr>"
                
                for _, row_mk in uid_mk.iterrows():
                    exam_name = row_mk.get('시험명', '-')
                    chunk += f"<tr style='font-size: 0.85rem;'><td style='font-weight:700; background:#F8FAFC;'>{exam_name}</td>"
                    for subj in ordered_subjects:
                        v_p, v_b, v_g = '-', '-', '-'
                        for col in row_mk.index:
                            col_clean = str(col).replace(" ", "")
                            if subj in col_clean:
                                if '표' in col_clean: v_p = row_mk[col]
                                elif '백분' in col_clean: v_b = row_mk[col]
                                elif '등급' in col_clean: v_g = row_mk[col]
                        def safe_fmt(val, is_float=False):
                            if val == '-' or pd.isna(val) or str(val).strip() == '': return "-"
                            try: return f"{float(val):.1f}" if is_float else f"{int(float(val))}"
                            except: return str(val)
                        f_std = safe_fmt(v_p)
                        f_perc = safe_fmt(v_b, is_float=True)
                        f_grade = safe_fmt(v_g)
                        if subj in ["영어", "한국사", "국사"] or (f_std == "-" and f_perc == "-"):
                            if f_grade != "-": display_str = f"<span style='font-weight:800; color:#1E3A8A; font-size: 1rem;'>{f_grade}등급</span>"
                            else: display_str = "-"
                        else:
                            f_perc_str = f"{f_perc}%" if f_perc != "-" else "-"
                            f_grade_str = f"{f_grade}등급" if f_grade != "-" else "-"
                            display_str = f"<div style='text-align:left; display:inline-block; line-height:1.5;'><small style='color:#64748B;'>표준:</small> {f_std}<br><small style='color:#64748B;'>백분:</small> <span style='font-weight:700;'>{f_perc_str}</span><br><small style='color:#64748B;'>등급:</small> <span style='color:#1E3A8A; font-weight:800;'>{f_grade_str}</span></div>"
                            if f_std == "-" and f_perc == "-" and f_grade == "-": display_str = "-"
                        chunk += f"<td>{display_str}</td>"
                    chunk += "</tr>"
                chunk += "</table>"
                
                p_cols = [c for c in uid_mk.columns if '백분' in c]
                if p_cols:
                    plot_m = uid_mk[['시험명'] + p_cols].copy()
                    for c in p_cols: plot_m[c] = plot_m[c].apply(safe_numeric)
                    fig_m = px.line(plot_m.melt(id_vars=['시험명'], var_name='과목', value_name='백분위'), 
                                    x='시험명', y='백분위', color='과목', symbol='과목', line_dash='과목', markers=True, title="주요 영역 백분위 추이")
                    fig_m.update_traces(marker=dict(size=12), line=dict(width=3))
                    fig_m.update_layout(yaxis=dict(range=[0, 105]), width=700, height=300, margin=dict(l=20, r=20, t=40, b=20), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    fig_html = fig_m.to_html(full_html=False, include_plotlyjs=False)
                    chunk += f"<div style='margin-top:20px; text-align:center;'>{fig_html}</div>"
            else: chunk += "<p>모의고사 기록이 존재하지 않습니다.</p>"
            chunk += "</div>"

        if p_act:
            chunk += """<div class="no-break"><h3>[ Section 3 ] 창의적 체험활동 핵심 역량 지표</h3>"""
            curr_y = sel_term[:3] if sel_term else ""
            t_col = next((c for c in df_act.columns if any(k in c for k in ['학년', '학기', '시기', '연도'])), None)
            u_ac = df_act[(df_act['고유번호'] == target_uid) & (df_act[t_col].str.contains(curr_y, na=False))].copy() if t_col else df_act[df_act['고유번호'] == target_uid].copy()
            if not u_ac.empty:
                col_comp = next((c for c in u_ac.columns if '역량' in c), None)
                comp_standards = ["탐구/지식처리", "창의적 사고", "비판적 사고", "자기주도/관리", "협력/소통", "공동체/윤리"]
                chunk += "<table><tr>"
                for comp_name in comp_standards: chunk += f"<th style='border-top: none; font-size:0.85rem;'>{comp_name}</th>"
                chunk += "</tr><tr>"
                for comp_name in comp_standards:
                    count = u_ac[col_comp].str.contains(comp_name.split('/')[0], na=False).sum() if col_comp else 0
                    chunk += f"<td style='font-size: 1.25rem; font-weight: 800; color: #1E3A8A;'>{count}</td>"
                chunk += "</tr></table>"
            else: chunk += "<p>해당 학기의 비교과 이력이 없습니다.</p>"
            chunk += "</div>"

        if p_ai:
            chunk += """<div class="no-break"><h3>[ Section 4 ] 세부 영역별 컨설팅 코멘트</h3>"""
            student_cache = st.session_state["global_ai_cache"].get(target_uid, {})
            if len([k for k in student_cache.keys() if k != "master_consulting"]) > 0:
                for key, text in student_cache.items():
                    if key == "master_consulting": continue
                    title = "영역별 정밀 진단"
                    if "mock_single" in key: title = f"모의고사 문항 단위 오답 분석 ({key.split('_')[-2]} - {key.split('_')[-1]})"
                    elif "mock_cum" in key: title = f"모의고사 누적 취약점 클러스터링 ({key.split('_')[-1]})"
                    elif "ref_" in key: title = f"정기 고사 학습 성찰 피드백 ({key.split('_')[-1]})"
                    elif "act_" in key: title = "교과 세특 연계 활동 기재 가이드"
                    formatted_detail = text.replace("\n", "<br>")
                    chunk += f"""
                    <div style="margin-bottom: 20px; border: 1px solid #E2E8F0; border-radius: 4px; overflow: hidden;">
                        <div style="background-color: #F8FAFC; padding: 12px 15px; font-weight: 800; font-size: 0.95rem; border-bottom: 1px solid #E2E8F0; color: #0F172A;">{title}</div>
                        <div style="padding: 15px; font-size: 0.95rem; line-height: 1.8; color: #334155;">{formatted_detail}</div>
                    </div>
                    """
            else: chunk += "<p>세부 처방 이력이 없습니다.</p>"
            chunk += "</div>"

        if p_master:
            chunk += """<div class="no-break"><h3>[ Section 5 ] 담임 교사 통합 종합 분석</h3>"""
            student_cache = st.session_state["global_ai_cache"].get(target_uid, {})
            if "master_consulting" in student_cache:
                formatted_text = student_cache["master_consulting"].replace("\n", "<br>")
                chunk += f"""<div class="ai-box">{formatted_text}</div>"""
            else:
                chunk += """<div style='color:#DC2626; font-weight:bold; padding: 15px; background: #FEF2F2; border-radius: 4px; border: 1px solid #FCA5A5;'>좌측 메뉴에서 통합 분석 알고리즘을 먼저 실행해 주십시오.</div>"""
            chunk += "</div>"
            
        return chunk

    final_html_single = html_head + build_student_report_html(sel_uid, sel_student) + "</body></html>"
    safe_single_json = json.dumps(final_html_single).replace("</script>", "<\\/script>")
    
    button_single_html = f"""
    <style>body {{ margin: 0; padding: 0; overflow: hidden; background: transparent; }}</style>
    <div style="text-align: right; padding-top: 5px;">
        <button onclick="openPrintWindow()" style="background-color: #1E3A8A; color: white; padding: 10px 15px; font-size: 0.95rem; font-weight: bold; border: none; border-radius: 4px; cursor: pointer; box-shadow: 0 1px 3px rgba(0,0,0,0.1); width: 100%;">선택 학생 인쇄</button>
    </div>
    <script>
    function openPrintWindow() {{
        var htmlContent = {safe_single_json};
        var printWin = window.open('', '_blank');
        if (printWin) {{ printWin.document.open(); printWin.document.write(htmlContent); printWin.document.close(); }}
    }}
    </script>
    """
    with col_print_single: components.html(button_single_html, height=60)

    unique_class_students = class_students[['학번', '학생명', '고유번호']].drop_duplicates().sort_values('학번')
    class_accumulated_body = ""
    for idx, (_, s_row) in enumerate(unique_class_students.iterrows()):
        s_uid = s_row['고유번호']
        s_display = f"{s_row['학번']} {s_row['학생명']}"
        student_report_chunk = build_student_report_html(s_uid, s_display)
        if idx < len(unique_class_students) - 1: student_report_chunk += '<div style="page-break-after: always; break-after: page;"></div>'
        class_accumulated_body += student_report_chunk
        
    final_html_class = html_head + class_accumulated_body + "</body></html>"
    safe_class_json = json.dumps(final_html_class).replace("</script>", "<\\/script>")
    
    button_class_html = f"""
    <style>body {{ margin: 0; padding: 0; overflow: hidden; background: transparent; }}</style>
    <div style="text-align: right; padding-top: 5px;">
        <button onclick="openPrintWindow()" style="background-color: #475569; color: white; padding: 10px 15px; font-size: 0.95rem; font-weight: bold; border: none; border-radius: 4px; cursor: pointer; box-shadow: 0 1px 3px rgba(0,0,0,0.1); width: 100%;">학급 전체 인쇄</button>
    </div>
    <script>
    function openPrintWindow() {{
        var htmlContent = {safe_class_json};
        var printWin = window.open('', '_blank');
        if (printWin) {{ printWin.document.open(); printWin.document.write(htmlContent); printWin.document.close(); }}
    }}
    </script>
    """
    with col_print_class: components.html(button_class_html, height=60)

# ==========================================
# 12. 교사용 통합 대시보드
# ==========================================
elif menu == "교사용 통합 대시보드":
    def check_dashboard_password():
        correct_pwd = st.secrets.get("dashboard_password", "1500")
        if st.session_state.get("dashboard_unlocked"): return True
        st.markdown(f"<h2 style='color: #1E3A8A;'>🔒 교사용 권한 인증</h2>", unsafe_allow_html=True)
        pwd = st.text_input("보안 코드를 입력해주십시오.", type="password")
        if pwd == correct_pwd:
            st.session_state["dashboard_unlocked"] = True
            st.rerun()
        elif pwd: st.error("인증에 실패했습니다.")
        return False

    if check_dashboard_password():
        st.markdown(f"<h2 style='color: #1E3A8A; border-bottom: 2px solid #E2E8F0; padding-bottom: 10px;'>{sel_term} 교사용 통합 대시보드</h2>", unsafe_allow_html=True)
        
        tab_basic, tab_grade = st.tabs(["📊 학생 관리 기본 현황", "📈 학기말 성적 정밀 분석"])
        
        with tab_basic:
            all_term_students = df_scores[df_scores['학기'] == sel_term][['반', '학번', '학생명', '고유번호']].drop_duplicates()
            if all_term_students.empty:
                st.warning("선택하신 학기의 데이터가 존재하지 않습니다.")
            else:
                grade_summary = []
                for _, stu_row in all_term_students.iterrows():
                    uid = stu_row['고유번호']
                    stu_class = stu_row['반']
                    stu_hakbun = str(stu_row['학번'])
                    stu_name = stu_row['학생명']
                    
                    u_cs = df_counsel[df_counsel['고유번호']==uid] if '고유번호' in df_counsel.columns else df_counsel[df_counsel['학번'].astype(str)==stu_hakbun]
                    cs_count = len(u_cs)
                    last_date = u_cs['상담일자'].max() if not u_cs.empty and '상담일자' in u_cs.columns else "-"
                    
                    u_ac = df_act[df_act['고유번호']==uid]
                    act_count = len(u_ac)
                    
                    grade_summary.append({"소속": stu_class, "학번": stu_hakbun, "이름": stu_name, "상담실적": cs_count, "최근등록일": last_date, "활동실적": act_count})
                
                grade_df = pd.DataFrame(grade_summary)
                class_stats = grade_df.groupby('소속').agg(
                    재적인원=('학번', 'count'),
                    상담진행인원=('상담실적', lambda x: (x > 0).sum()),
                    총상담건수=('상담실적', 'sum'),
                    총활동건수=('활동실적', 'sum')
                ).reset_index()
                
                c1, c2, c3 = st.columns(3)
                total_students = class_stats['재적인원'].sum()
                total_counseled = class_stats['상담진행인원'].sum()
                best_class = class_stats.sort_values('총상담건수', ascending=False).iloc[0]['소속'] if not class_stats.empty and class_stats['총상담건수'].sum() > 0 else "-"
                
                c1.metric("학년 전체 재적 인원", f"{total_students}명")
                c2.metric("상담 이력 보유 인원", f"{total_counseled}명")
                c3.metric("최우수 상담 학급", f"{best_class}")
                
                st.markdown("---")
                st.subheader("학급별 컨설팅 진행 현황")
                st.dataframe(style_centered(class_stats), use_container_width=True)
                
                st.markdown("---")
                st.subheader("학생 세부 이력 명세")
                filter_class = st.selectbox("학급 필터링", ["전체"] + sorted(grade_df['소속'].unique().tolist()))
                detail_display = grade_df.copy()
                if filter_class != "전체": detail_display = detail_display[detail_display['소속'] == filter_class]
                    
                detail_display = detail_display.sort_values(['소속', '학번'])
                st.dataframe(style_centered(detail_display), use_container_width=True, height=400)

        with tab_grade:
            st.markdown("#### 📊 분석 범위 설정")
            scope_choice = st.radio("조회할 데이터 범위를 선택하십시오.", [f"선택 학기 ({sel_term})", "전체 학기 누적 (종합 평점 산출)"], horizontal=True)
            
            if "누적" in scope_choice:
                all_term_df = df_scores[df_scores['시험'] == '학기말'].copy()
                title_prefix = "전체 학기 누적"
                show_chart_and_subj = False
            else:
                all_term_df = df_scores[(df_scores['학기'] == sel_term) & (df_scores['시험'] == '학기말')].copy()
                title_prefix = f"{sel_term}"
                show_chart_and_subj = True

            if all_term_df.empty:
                st.warning(f"선택하신 기준의 [학기말] 성적 데이터가 아직 입력되지 않았습니다.")
            else:
                if show_chart_and_subj:
                    st.subheader(f"📊 {title_prefix} 과목별 성취도(A~E) 분포 비율 분석")
                    if '성취도' in all_term_df.columns:
                        ach_df = all_term_df[all_term_df['성취도'].str.upper().isin(['A','B','C','D','E','P','F'])]
                        if not ach_df.empty:
                            ach_counts = ach_df.groupby(['과목', '성취도']).size().reset_index(name='학생수')
                            ach_totals = ach_counts.groupby('과목')['학생수'].transform('sum')
                            ach_counts['비율(%)'] = (ach_counts['학생수'] / ach_totals) * 100
                            
                            fig_ach = px.bar(ach_counts, x='과목', y='비율(%)', color='성취도', 
                                             text=ach_counts['비율(%)'].apply(lambda x: f"{x:.1f}%"),
                                             color_discrete_sequence=px.colors.qualitative.Pastel)
                            fig_ach.update_traces(textposition="inside")
                            fig_ach.update_layout(barmode='stack', yaxis=dict(title="비율(%)", range=[0,105]))
                            st.plotly_chart(fig_ach, use_container_width=True)
                    
                    st.markdown("---")
                
                st.subheader(f"🏆 40기 {title_prefix} 종합 등수 및 주요 교과 평점")
                
                s_col = next((c for c in all_term_df.columns if '점수' in c.replace(" ","")), '점수')
                u_col = '단위' if '단위' in all_term_df.columns else ('이수단위' if '이수단위' in all_term_df.columns else '')
                
                all_term_df[s_col] = all_term_df[s_col].apply(safe_numeric)
                if u_col: all_term_df[u_col] = all_term_df[u_col].apply(safe_numeric)
                else: 
                    all_term_df['임시단위'] = 1.0
                    u_col = '임시단위'
                    
                def assign_9_tier_batch(group):
                    all_s_batch = group[s_col].dropna()
                    return group[s_col].apply(lambda x: calc_9_tier(x, all_s_batch))
                all_term_df['9등급(자동)'] = all_term_df.groupby(['학기', '과목'], group_keys=False).apply(assign_9_tier_batch)
                
                def agg_student(student_df):
                    student_df['num_grade'] = student_df['등급'].apply(safe_numeric)
                    student_df['num_unit'] = student_df[u_col].apply(safe_numeric)
                    
                    valid_g5 = student_df[student_df['num_grade'] > 0]
                    total_u_g5 = valid_g5['num_unit'].sum() if valid_g5['num_unit'].sum() > 0 else 1
                    g5 = (valid_g5['num_grade'] * valid_g5['num_unit']).sum() / total_u_g5
                    
                    valid_g9 = student_df[student_df['9등급(자동)'] > 0]
                    total_u_g9 = valid_g9['num_unit'].sum() if valid_g9['num_unit'].sum() > 0 else 1
                    g9 = (valid_g9['9등급(자동)'] * valid_g9['num_unit']).sum() / total_u_g9
                    
                    raw_sum = student_df[s_col].sum()
                    
                    kem_df = valid_g5[valid_g5['과목'].str.contains('국어|영어|수학|문학|독서|화법|작문|언어|매체|기하|미적|확률|통계|회화|영작', regex=True)]
                    kem_u = kem_df['num_unit'].sum()
                    kem_g5 = (kem_df['num_grade'] * kem_df['num_unit']).sum() / kem_u if kem_u > 0 else None
                    
                    ms_df = valid_g5[valid_g5['과목'].str.contains('수학|과학|물리|화학|생명|지구|기하|미적|확률|통계|정보', regex=True)]
                    ms_u = ms_df['num_unit'].sum()
                    ms_g5 = (ms_df['num_grade'] * ms_df['num_unit']).sum() / ms_u if ms_u > 0 else None
                    
                    student_df = student_df.sort_values('학기', ascending=False)
                    
                    return pd.Series({
                        '소속': student_df['반'].iloc[0] if '반' in student_df.columns else '-',
                        '학번': student_df['학번'].iloc[0],
                        '이름': student_df['학생명'].iloc[0],
                        '총점합계': raw_sum,
                        '5등급평점': g5,
                        '9등급평점': g9,
                        '국영수평점': kem_g5,
                        '수과평점': ms_g5
                    })
                    
                stu_agg = all_term_df.groupby('고유번호').apply(agg_student).reset_index(drop=True)
                
                stu_agg['전교등수(총점)'] = stu_agg['총점합계'].rank(ascending=False, method='min').astype(int)
                stu_agg['전교등수(5등급)'] = stu_agg['5등급평점'].rank(ascending=True, method='min').astype(int)
                stu_agg['전교등수(9등급)'] = stu_agg['9등급평점'].rank(ascending=True, method='min').astype(int)
                stu_agg['등수(국영수)'] = stu_agg['국영수평점'].rank(ascending=True, method='min').astype('Int64')
                stu_agg['등수(수과)'] = stu_agg['수과평점'].rank(ascending=True, method='min').astype('Int64')
                
                show_cols = ['소속', '학번', '이름', '전교등수(5등급)', '5등급평점', '전교등수(9등급)', '9등급평점', 
                             '전교등수(총점)', '총점합계', '등수(국영수)', '국영수평점', '등수(수과)', '수과평점']
                
                st.dataframe(style_centered(stu_agg.sort_values('전교등수(5등급)')[show_cols]).format(precision=2), use_container_width=True, height=400, hide_index=True)
                
                if show_chart_and_subj:
                    st.markdown("---")
                    st.subheader("🔍 특정 과목별 전체 전교 등수 조회")
                    sel_subj_dash = st.selectbox("조회할 교과목을 선택하십시오.", ["선택하세요"] + sorted(all_term_df['과목'].unique()))
                    
                    if sel_subj_dash != "선택하세요":
                        subj_df = all_term_df[all_term_df['과목'] == sel_subj_dash].copy()
                        subj_df['과목등수'] = subj_df[s_col].rank(ascending=False, method='min').astype(int)
                        subj_df['전체백분위(%)'] = ((len(subj_df) - subj_df['과목등수'] + 1) / len(subj_df) * 100).round(2)
                        
                        show_subj = subj_df[['반', '학번', '학생명', '과목', s_col, '성취도', '등급', '과목등수', '전체백분위(%)']].sort_values('과목등수')
                        show_subj.rename(columns={s_col: '취득점수'}, inplace=True)
                        
                        st.dataframe(style_centered(show_subj), use_container_width=True, height=400, hide_index=True)
