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
    
    /* 모든 표 데이터 가운데 정렬 */
    table, th, td { 
        text-align: center !important; 
    }
</style>
""", unsafe_allow_html=True)

# [유틸리티] 데이터프레임 시각적 가운데 정렬 함수
def style_centered(df):
    return df.style.set_properties(**{'text-align': 'center'}).set_table_styles([dict(selector='th', props=[('text-align', 'center')])])

# ==========================================
# 2. 보안 설정 (비밀번호 로그인)
# ==========================================
def check_password():
    def password_entered():
        correct_password = st.secrets.get("admin_password", "hanil40")
        if st.session_state["password"] == correct_password:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # 보안을 위해 세션에서 비밀번호 삭제
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

# 로그인 전까지 아래 코드 실행 정지
if not check_password():
    st.stop()

# ==========================================
# 3. 유틸리티 및 계산 로직
# ==========================================
# 안전하게 숫자를 추출하는 함수
def safe_numeric(val):
    if pd.isna(val) or val is None: 
        return 0.0
    val_str = str(val).strip()
    if not val_str or val_str == '-' or val_str == '미응시': 
        return 0.0
    try:
        cleaned = re.sub(r'[^0-9.]', '', val_str)
        if cleaned.count('.') > 1:
            parts = cleaned.split('.')
            cleaned = parts[0] + '.' + ''.join(parts[1:])
        return float(cleaned) if cleaned else 0.0
    except: 
        return 0.0

# 9등급 자동 산출 공식 (중간석차 백분율 적용)
def calc_9_tier(score, all_scores):
    if all_scores.empty: 
        return 0
        
    # 나보다 큰 점수 개수
    greater = (all_scores > score).sum()
    # 나와 같은 점수 개수
    equal = (all_scores == score).sum()
    
    # 중간석차 백분율 공식
    mid_rank_pct = ((greater + (equal / 2.0)) / len(all_scores)) * 100
    
    if mid_rank_pct <= 4: return 1
    elif mid_rank_pct <= 11: return 2
    elif mid_rank_pct <= 23: return 3
    elif mid_rank_pct <= 40: return 4
    elif mid_rank_pct <= 60: return 5
    elif mid_rank_pct <= 77: return 6
    elif mid_rank_pct <= 89: return 7
    elif mid_rank_pct <= 96: return 8
    else: return 9

# 시기 정렬 헬퍼 함수 (그래프를 그릴 때 시간순으로 정렬하기 위함)
def get_time_rank(row):
    term_map = {
        "1학년 1학기": 10, "1학년 2학기": 20, 
        "2학년 1학기": 30, "2학년 2학기": 40, 
        "3학년 1학기": 50, "3학년 2학기": 60
    }
    exam_map = {"1회고사": 1, "2회고사": 2, "학기말": 3}
    
    base_score = term_map.get(row.get('학기', ''), 0)
    add_score = exam_map.get(row.get('시험', ''), 0)
    return base_score + add_score

# ==========================================
# 4. 데이터 로드 (마스터 탭 VLOOKUP 연동)
# ==========================================
@st.cache_resource
def load_all_data():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        client = gspread.authorize(creds)
        doc = client.open("40기 마스터 파일")
        
        # 개별 시트 처리 함수
        def process_sheet(name):
            try:
                sh = doc.worksheet(name)
                data = sh.get_all_values()
                if not data: 
                    return pd.DataFrame()
                    
                df = pd.DataFrame(data[1:], columns=[str(c).strip() for c in data[0]])
                df = df.loc[:, ~df.columns.duplicated()] 
                
                # 학번 정리 및 반 추출 (학번 4자리 중 2번째 자리)
                if '학번' in df.columns:
                    df['학번'] = df['학번'].astype(str).str.replace(',', '').str.split('.').str[0].str.strip()
                    df['반'] = df['학번'].apply(lambda x: f"{x[1]}반" if len(x) >= 4 else "기타")
                
                # 이름 정리 및 표시용 식별자 생성
                n_col = next((c for c in df.columns if '성명' in c or '이름' in c), None)
                if n_col:
                    df['학생명'] = df[n_col].astype(str).str.strip()
                    df['표시식별'] = df['학번'] + " " + df['학생명']
                    
                return df
            except Exception: 
                return pd.DataFrame()
            
        # 모든 시트 로드
        df_scores = process_sheet("31_내신")
        df_mock = process_sheet("21_모의고사")
        df_ref = process_sheet("51_시험복기")
        df_act = process_sheet("61_비교과")
        df_counsel = process_sheet("71_상담기록")
        df_master = process_sheet("99_학생_마스터")
        
        # 마스터 탭을 이용한 고유번호 병합 (VLOOKUP)
        if not df_master.empty and '고유번호' in df_master.columns and '학번' in df_master.columns:
            mapping = df_master[['학번', '고유번호']].drop_duplicates()
            
            def apply_uid(df):
                if not df.empty and '학번' in df.columns:
                    merged_df = pd.merge(df, mapping, on='학번', how='left')
                    merged_df['고유번호'] = merged_df['고유번호'].fillna(merged_df['표시식별'])
                    return merged_df
                return df
                
            df_scores = apply_uid(df_scores)
            df_mock = apply_uid(df_mock)
            df_ref = apply_uid(df_ref)
            df_act = apply_uid(df_act)
            df_counsel = apply_uid(df_counsel)
            
        else:
            # 마스터 탭이 없으면 표시식별을 고유번호로 임시 사용
            for df in [df_scores, df_mock, df_ref, df_act, df_counsel]:
                if not df.empty and '표시식별' in df.columns:
                    df['고유번호'] = df['표시식별']
                    
        return df_scores, df_mock, df_ref, df_act, df_counsel
        
    except Exception as e:
        st.error(f"데이터 연동 실패: {e}")
        return [pd.DataFrame()]*5

df_scores, df_mock, df_ref, df_act, df_counsel = load_all_data()

# AI 모델 셋업
try:
    genai.configure(api_key=st.secrets["gemini_api_key"])
    # 사용 가능한 모델 탐색 및 호환성 높은 모델 선택
    models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    if 'models/gemini-1.5-flash' in models:
        target_model = 'models/gemini-1.5-flash'
    elif 'models/gemini-pro' in models:
        target_model = 'models/gemini-pro'
    else:
        target_model = models[0]
    ai_model = genai.GenerativeModel(target_model)
except: 
    ai_model = None

# ==========================================
# 5. 사이드바 구성 (프라이버시 세팅)
# ==========================================
query_params = st.query_params

with st.sidebar:
    st.title("🏫 상담 시스템 v2")
    
    # 학기 필터
    terms = sorted(df_scores['학기'].unique(), reverse=True) if not df_scores.empty else []
    sel_term = st.selectbox("📅 학기 선택", terms)
    
    # 학급 필터
    classes = sorted(df_scores[df_scores['학기'] == sel_term]['반'].unique()) if sel_term else []
    sel_class = st.selectbox("🏘️ 학급 선택", classes)
    
    # 학생 필터 리스트 생성
    class_students = df_scores[(df_scores['학기'] == sel_term) & (df_scores['반'] == sel_class)]
    students_list = sorted(class_students['표시식별'].unique()) if not class_students.empty else []
    
    student_options = ["학생을 선택해주세요"] + students_list
    
    # 파라미터 상태 복원
    default_student_idx = 0
    if "student" in query_params and query_params["student"] in student_options:
        default_student_idx = student_options.index(query_params["student"])
    
    sel_student_label = st.selectbox("👤 학생 선택", student_options, index=default_student_idx)
    
    # 학생이 선택되지 않은 경우 진행 중지 (프라이버시 기능)
    if sel_student_label == "학생을 선택해주세요":
        if "student" in st.query_params: 
            del st.query_params["student"]
        
        st.title("🏫 한일고 40기 통합 상담 시스템")
        st.markdown("""
        <div style="background-color: #FFFFFF; padding: 40px; border-radius: 15px; border: 1px solid #E2E8F0; text-align: center; margin-top: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
            <h2 style="color: #1E40AF; margin-bottom: 15px;">환영합니다, 선생님! 👋</h2>
            <p style="font-size: 1.15rem; color: #475569; line-height: 1.8;">
                학생 상담을 시작하시려면 <b>왼쪽 사이드바</b>에서 <b>학급</b>과 <b>학생 이름</b>을 선택해주세요.<br>
                <span style="color: #EF4444; font-size: 0.95rem;">※ 학생 개인정보 보호를 위해, 선택 전까지 데이터는 숨김 처리됩니다.</span>
            </p>
        </div>
        """, unsafe_allow_html=True)
        st.stop()
    
    # 선택된 학생 정보 추출 및 파라미터 저장
    st.query_params["student"] = sel_student_label
    sel_uid = class_students[class_students['표시식별'] == sel_student_label]['고유번호'].iloc[0]
    sel_name = sel_student_label.split(" ")[1]
    
    st.markdown("---")
    
    # 메뉴 선택
    menu_list = ["📈 내신 분석", "🎯 모의고사 분석", "🧠 성찰 리포트", "🏆 비교과 타임라인", "📝 상담 기록"]
    default_menu_idx = 0
    if "menu" in query_params and query_params["menu"] in menu_list:
        default_menu_idx = menu_list.index(query_params["menu"])
        
    menu = st.radio("📑 분석 메뉴", menu_list, index=default_menu_idx)
    st.query_params["menu"] = menu

st.header(f"📊 {sel_student_label} 분석 리포트")

# ==========================================
# 6. 내신 분석 (백분위 기준 추이 + 개별 과목)
# ==========================================
if menu == "📈 내신 분석":
    t1, t2, t3 = st.tabs(["📊 당해학기 상세", "📉 학기별 성적(평점)", "📈 과목군 누적 추이"])
    
    uid_scores = df_scores[df_scores['고유번호'] == sel_uid].copy()
    s_col = next((c for c in uid_scores.columns if '점수' in c.replace(" ", "")), '점수')
    
    # ---------------- 탭 1: 상세 ----------------
    with t1:
        st.subheader(f"📍 {sel_term} 상세 성적")
        term_scores = uid_scores[uid_scores['학기'] == sel_term]
        exam = st.selectbox("시험 선택", ["1회고사", "2회고사", "학기말"])
        filtered = term_scores[term_scores['시험'] == exam].copy()
        
        if not filtered.empty:
            if exam == "학기말":
                # 학기말은 등급과 성취도를 표시
                cols = st.columns(len(filtered))
                for i, (_, row) in enumerate(filtered.iterrows()):
                    grade_str = f"{row.get('등급', '-')}등급"
                    achieve_str = f"({row['성취도']})" if '성취도' in row and str(row['성취도']).strip() else ""
                    cols[i].metric(row['과목'], f"{grade_str} {achieve_str}".strip())
            else:
                plot_data = []
                for _, row in filtered.iterrows():
                    all_exam = df_scores[(df_scores['학기'] == sel_term) & (df_scores['시험'] == exam) & (df_scores['과목'] == row['과목'])][s_col].apply(safe_numeric).dropna()
                    
                    my_score = safe_numeric(row.get(s_col, 0))
                    median_val = all_exam.median() if not all_exam.empty else 0
                    
                    count_below = (all_exam <= my_score).sum() if not all_exam.empty else 0
                    calc_perc = (count_below / len(all_exam)) * 100 if not all_exam.empty else 0
                    
                    plot_data.append({
                        '과목': row['과목'], 
                        '점수': round(my_score, 2), 
                        '중위값': round(median_val, 2), 
                        '백분위': round(calc_perc, 2)
                    })
                
                pdf = pd.DataFrame(plot_data)
                
                # 막대그래프: 원점수
                fig = px.bar(pdf, x='과목', y='점수', color='과목', text=pdf['점수'].apply(lambda x: f"{x:.2f}"), color_discrete_sequence=px.colors.qualitative.Pastel)
                
                # 점: 학년 중위값
                fig.add_trace(go.Scatter(
                    x=pdf['과목'], y=pdf['중위값'], name="학년 중위값", 
                    mode='markers', marker=dict(size=12, color='black', symbol='diamond', line=dict(width=1, color='white'))
                ))
                
                # 꺾은선: 계산된 백분위
                fig.add_trace(go.Scatter(
                    x=pdf['과목'], y=pdf['백분위'], name="계산 백분위(%)", 
                    yaxis="y2", mode='lines+markers', line=dict(color='red', width=2)
                ))
                
                fig.update_layout(
                    xaxis=dict(tickangle=-45), 
                    yaxis=dict(title="원점수", range=[0, 105]), 
                    yaxis2=dict(overlaying="y", side="right", title="백분위(%)", range=[0, 105]), 
                    margin=dict(b=120), 
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig, use_container_width=True)
                
                # 표
                st.markdown("#### 📝 과목별 성적 상세 지표")
                display_df = pdf[['과목', '점수', '중위값', '백분위']].copy()
                display_df.columns = ['과목명', '내 점수', '학년 중위값', '계산 백분위(%)']
                
                styled_df = style_centered(display_df).format({
                    '내 점수': '{:.2f}', 
                    '학년 중위값': '{:.2f}', 
                    '계산 백분위(%)': '{:.2f}'
                })
                st.table(styled_df)
        else: 
            st.info("해당 시험 데이터가 없습니다.")

    # ---------------- 탭 2: 학기별 평점 ----------------
    with t2:
        st.subheader("📑 학기말 성적 및 내신 평점 산출")
        f_df = uid_scores[uid_scores['시험'] == '학기말'].copy()
        
        unit_col = '단위' if '단위' in f_df.columns else '이수단위'
        grade_col = '등급'
        
        if not f_df.empty and unit_col in f_df.columns:
            
            # 9등급 자동 계산
            nine_tiers = []
            for _, row in f_df.iterrows():
                all_exam_scores = df_scores[(df_scores['학기'] == row['학기']) & (df_scores['시험'] == '학기말') & (df_scores['과목'] == row['과목'])][s_col].apply(safe_numeric).dropna()
                my_score = safe_numeric(row.get(s_col, 0))
                
                nt = calc_9_tier(my_score, all_exam_scores)
                nine_tiers.append(nt)
                
            f_df['9등급(자동)'] = nine_tiers
            f_df[unit_col] = f_df[unit_col].apply(safe_numeric)
            
            cols_to_show = ['학기', '과목', '점수', grade_col, '성취도', unit_col, '9등급(자동)']
            avail_cols = [c for c in cols_to_show if c in f_df.columns]
            
            st.write("계산에 포함할 과목을 선택하세요:")
            selected_rows = st.data_editor(
                f_df[avail_cols],
                column_config={"선택": st.column_config.CheckboxColumn(default=True)},
                disabled=avail_cols,
                use_container_width=True
            )
            
            calc_df = selected_rows[selected_rows[unit_col] > 0].copy()
            
            if not calc_df.empty:
                calc_df[grade_col] = calc_df[grade_col].apply(safe_numeric)
                total_units = calc_df[unit_col].sum()
                
                # 5등급 GPA
                weighted_sum_5 = (calc_df[grade_col] * calc_df[unit_col]).sum()
                gpa_5 = weighted_sum_5 / total_units if total_units > 0 else 0
                
                # 9등급 GPA
                weighted_sum_9 = (calc_df['9등급(자동)'] * calc_df[unit_col]).sum()
                gpa_9 = weighted_sum_9 / total_units if total_units > 0 else 0
                
                st.markdown("---")
                c1, c2 = st.columns(2)
                c1.metric("📊 5등급제 평점 평균 (단위수 가중)", f"{gpa_5:.2f} 등급")
                c2.metric("📊 9등급제 평점 평균 (자동 계산)", f"{gpa_9:.2f} 등급")
        else: 
            st.info("학기말 데이터와 '단위(또는 이수단위)' 열이 필요합니다.")

    # ---------------- 탭 3: 누적 추이 ----------------
    with t3:
        st.subheader("📈 과목군별 누적 성적 추이 (백분위 기준)")
        if '교과군' in uid_scores.columns:
            trend_df = uid_scores[uid_scores['시험'].str.contains('고사')].copy()
            
            # 히스토리 데이터의 백분위 실시간 계산
            def get_hist_perc(row):
                all_exam = df_scores[(df_scores['학기'] == row['학기']) & (df_scores['시험'] == row['시험']) & (df_scores['과목'] == row['과목'])][s_col].apply(safe_numeric).dropna()
                my_score = safe_numeric(row.get(s_col, 0))
                
                count_below = (all_exam <= my_score).sum()
                return (count_below / len(all_exam)) * 100 if not all_exam.empty else 0
                
            trend_df['백분위'] = trend_df.apply(get_hist_perc, axis=1)
            trend_df['점수'] = trend_df[s_col].apply(safe_numeric)
            trend_df['시기'] = trend_df['학기'] + " " + trend_df['시험']
            trend_df['순서'] = trend_df.apply(get_time_rank, axis=1)
            
            trend_df = trend_df.sort_values('순서')
            
            group_list = sorted(trend_df['교과군'].dropna().unique())
            sel_group = st.multiselect("분석할 교과군 선택", group_list, default=group_list[:1] if group_list else [])
            
            if sel_group:
                plot_trend = trend_df[trend_df['교과군'].isin(sel_group)]
                
                # Y축 백분위, 라벨 텍스트 원점수, 색상은 과목 분리
                fig_trend = px.line(
                    plot_trend, 
                    x='시기', 
                    y='백분위', 
                    color='과목', 
                    markers=True, 
                    text=plot_trend['점수'].apply(lambda x: f"{x:.2f}"),
                    hover_data={'과목': True, '점수': True, '백분위': ':.2f', '시기': False}
                )
                
                fig_trend.update_traces(textposition="top center")
                fig_trend.update_layout(
                    yaxis=dict(title="백분위(%) - 높을수록 상위권", range=[-5, 110]), 
                    xaxis=dict(title=""),
                    margin=dict(b=80)
                )
                
                st.plotly_chart(fig_trend, use_container_width=True)
                st.info("💡 Y축은 상대적 위치(백분위)를 나타내며, 점 위의 숫자는 실제 원점수입니다.")
        else: 
            st.warning("시트에 '교과군' 열을 추가하시면 과목을 연결해서 볼 수 있습니다.")

# ==========================================
# 7. 모의고사 분석 (가운데 정렬, 소수점 처리)
# ==========================================
elif menu == "🎯 모의고사 분석":
    uid_mock = df_mock[df_mock['고유번호'] == sel_uid].copy()
    
    if not uid_mock.empty:
        latest = uid_mock.iloc[-1]
        st.subheader(f"🎯 최근 모의고사 요약: {latest.get('시험명', '최근 시험')}")
        
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
        
        summary = []
        for s_name, s_keys in subj_map.items():
            raw_score = get_flex_val(latest, s_keys, ['표준점수', '표점'])
            raw_perc = get_flex_val(latest, s_keys, ['백분위', '백분'])
            raw_grade = get_flex_val(latest, s_keys, ['등급'])
            
            # 표점과 등급은 정수, 백분위는 소수점 2자리
            try: f_score = f"{int(float(raw_score))}"
            except: f_score = raw_score
            
            try: f_perc = f"{float(raw_perc):.2f}%"
            except: f_perc = f"{raw_perc}%" if raw_perc != '-' else '-'
            
            try: f_grade = f"{int(float(raw_grade))}등급"
            except: f_grade = f"{raw_grade}등급" if raw_grade != '-' else '-'
            
            summary.append({"과목": s_name, "표준점수": f_score, "백분위": f_perc, "등급": f_grade})
            
        summary_df = pd.DataFrame(summary)
        st.table(style_centered(summary_df))
        
        st.markdown("---")
        st.subheader("📈 전체 모의고사 백분위 추이 (3개년 누적)")
        
        p_cols = [c for c in uid_mock.columns if '백분' in c]
        if p_cols:
            plot_m = uid_mock[['시험명'] + p_cols].copy()
            for c in p_cols: 
                plot_m[c] = plot_m[c].apply(safe_numeric)
                
            melted_m = plot_m.melt(id_vars=['시험명'], var_name='과목', value_name='백분위')
            
            fig_mock = px.line(melted_m, x='시험명', y='백분위', color='과목', markers=True)
            fig_mock.update_layout(yaxis=dict(range=[0, 105]))
            st.plotly_chart(fig_mock, use_container_width=True)
            
        st.subheader("📝 전체 모의고사 누적 기록")
        display_mock = uid_mock.drop(columns=['학번', '표시식별', '학생명', '반', '고유번호'], errors='ignore')
        st.dataframe(style_centered(display_mock), use_container_width=True)
        
    else: 
        st.info("모의고사 기록이 없습니다.")

# ==========================================
# 8. 성찰 리포트 (현재 학년 필터링)
# ==========================================
elif menu == "🧠 성찰 리포트":
    current_year = sel_term[:3] # "1학년" 등의 글자 추출
    uid_ref = df_ref[(df_ref['고유번호'] == sel_uid) & (df_ref['학기'].str.contains(current_year))].copy()
    
    if not uid_ref.empty:
        sel_ex = st.selectbox("시험 선택", uid_ref['시험명'].unique())
        row = uid_ref[uid_ref['시험명'] == sel_ex].iloc[-1]
        
        cols = st.columns(2)
        idx = 0
        for k, v in row.items():
            if k in ['타임스탬프', '학번', '이름', '성명', '학생식별', '표시식별', '학생명', '시험명', '반', '고유번호'] or not v: 
                continue
            with cols[idx % 2]: 
                st.markdown(f"""
                <div style="background:white; border-left:5px solid #3B82F6; padding:15px; margin-bottom:10px; border-radius:10px; box-shadow:0 1px 3px rgba(0,0,0,0.1);">
                    <b>{k}</b><br>{v}
                </div>
                """, unsafe_allow_html=True)
            idx += 1
            
        st.markdown("---")
        
        if st.button("🤖 AI 상담교사 피드백 생성"):
            if ai_model:
                with st.spinner("AI 분석 중..."):
                    try:
                        clean_data = {str(k): str(v) for k, v in row.items() if len(str(v)) > 5 and k not in ['학번', '타임스탬프']}
                        res = ai_model.generate_content(f"한일고 상담교사의 관점에서 조언해줘: {str(clean_data)}")
                        
                        st.markdown(f"""
                        <div class="ai-container">
                            <b>🤖 AI 상담 조언</b><br><br>{res.text}
                        </div>
                        """, unsafe_allow_html=True)
                    except Exception as e: 
                        st.error(f"AI 오류가 발생했습니다: {e}")
            else:
                st.warning("AI 모델이 연결되지 않았습니다.")
    else: 
        st.info(f"{current_year} 성찰 기록이 없습니다.")

# ==========================================
# 9. 비교과 타임라인 (현재 학년 필터링)
# ==========================================
elif menu == "🏆 비교과 타임라인":
    current_year = sel_term[:3]
    uid_act = df_act[(df_act['고유번호'] == sel_uid) & (df_act['학기'].str.contains(current_year))].copy()
    
    if not uid_act.empty:
        col_type = next((c for c in uid_act.columns if '성격' in c), None)
        col_comp = next((c for c in uid_act.columns if '역량' in c), None)
        
        st.subheader(f"📊 {current_year} 핵심역량별 활동 분포")
        comp_standards = ["탐구력/지식정보처리", "창의적 사고", "비판적 사고", "자기주도성/자기관리", "협력적 소통", "공동체 의식/윤리"]
        
        s_cols = st.columns(6)
        for i, comp_name in enumerate(comp_standards):
            count = uid_act[col_comp].str.contains(comp_name, na=False).sum() if col_comp else 0
            with s_cols[i]: 
                st.markdown(f"""
                <div class="stat-box">
                    <small style="color:#64748B; font-size:0.75rem;">{comp_name}</small><br>
                    <b style="font-size:1.4rem; color:#2563EB;">{count}건</b>
                </div>
                """, unsafe_allow_html=True)
                
        st.markdown("---")
        
        st.subheader("🔍 활동 맞춤 필터")
        f1, f2 = st.columns(2)
        filtered_act = uid_act.copy()
        
        with f1:
            type_options = ["전체", "자율 활동", "진로 활동", "독서 활동", "문헌 탐구 활동", "협력 토론 활동", "실증 탐구 활동", "비평 성찰 활동", "발표 공유 활동", "융합 탐구 활동", "교사 개별 상담"]
            sel_type = st.selectbox("활동 성격별 필터", type_options)
            if sel_type != "전체" and col_type: 
                filtered_act = filtered_act[filtered_act[col_type].str.contains(sel_type, na=False)]
                
        with f2:
            comp_options = ["전체"] + comp_standards
            sel_comp = st.selectbox("핵심 역량별 필터", comp_options)
            if sel_comp != "전체" and col_comp: 
                filtered_act = filtered_act[filtered_act[col_comp].str.contains(sel_comp, na=False)]
        
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
            
            if st.button(f"🪄 AI 생기부 초안 생성 (기록번호: {i})"):
                if ai_model:
                    with st.spinner("작성 중..."):
                        try: 
                            res = ai_model.generate_content(f"활동기록을 바탕으로 생기부 문구를 작성해줘(~함 체): {row.get('핵심 활동 내용', '')}")
                            st.info(res.text)
                        except Exception as e: 
                            st.error(f"AI 오류: {e}")
                else:
                    st.warning("AI 모델이 설정되지 않았습니다.")
                    
    else: 
        st.info(f"{current_year} 활동 기록이 없습니다.")

# ==========================================
# 10. 상담 기록 작성 (누적)
# ==========================================
elif menu == "📝 상담 기록":
    uid_counsel = df_counsel[df_counsel['고유번호'] == sel_uid].copy()
    
    st.subheader(f"📖 {sel_name} 누적 상담 기록 (3개년)")
    if not uid_counsel.empty and '상담일자' in uid_counsel.columns:
        for i, row in uid_counsel.sort_values('상담일자', ascending=False).iterrows():
            st.markdown(f"""
            <div class="timeline-card" style="border-left: 6px solid #8B5CF6;">
                <span class="badge" style="background:#F3E8FF; color:#7E22CE;">🗣️ {row.get('상담유형', '일반 상담')}</span>
                <div style="font-size:0.85rem; color:#64748B; margin-bottom:10px;">📅 {row.get('상담일자', '-')}</div>
                <div style="background:#F8FAFC; padding:18px; border-radius:12px; font-size:0.95rem; line-height:1.7;">
                    {row.get('상담내용', '-')}
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
        c_content = st.text_area("상담 내용 및 결과", height=150, placeholder="학생과 상담한 주요 내용과 향후 계획을 기록해주세요.")
        
        if st.form_submit_button("💾 상담 기록 저장하기"):
            if c_content.strip() == "":
                st.error("상담 내용을 입력해주세요!")
            else:
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
                            sh.append_row(["학생고유번호", "이름", "상담일자", "상담유형", "상담내용"])
                        
                        # 시트에 저장할 때는 '고유번호'로 저장
                        sh.append_row([sel_uid, sel_name, str(c_date), c_type, c_content])
                        
                        st.cache_resource.clear() 
                        st.success("✅ 저장 완료! 새로고침(F5)을 눌러 확인하세요.")
                        
                    except Exception as e: 
                        st.error(f"저장 중 오류 발생: {e}")
