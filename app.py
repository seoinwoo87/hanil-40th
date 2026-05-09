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
/* 표 가운데 정렬을 위한 CSS */
table, th, td { text-align: center !important; }
</style>
""", unsafe_allow_html=True)

# [표 가운데 정렬 유틸리티 함수]
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
# 3. 유틸리티 함수 및 데이터 로드
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
                    # 학번 4자리 중 2번째 숫자가 반
                    df['반'] = df['학번'].apply(lambda x: f"{x[1]}반" if len(x) >= 4 else "기타")
                
                n_col = next((c for c in df.columns if '성명' in c or '이름' in c), None)
                if '학번' in df.columns and n_col:
                    df['학생명'] = df[n_col].astype(str).str.strip()
                    df['식별'] = df['학번'] + " " + df['학생명']
                return df
            except: return pd.DataFrame()
            
        return process_sheet("31_내신"), process_sheet("21_모의고사"), process_sheet("51_시험복기"), process_sheet("61_비교과"), process_sheet("71_상담기록")
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return [pd.DataFrame()]*5

df_scores, df_mock, df_ref, df_act, df_counsel = load_all_data()

# AI 모델 자동 설정
try:
    genai.configure(api_key=st.secrets["gemini_api_key"])
    m_list = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    t_m = 'models/gemini-1.5-flash' if 'models/gemini-1.5-flash' in m_list else ('models/gemini-pro' if 'models/gemini-pro' in m_list else m_list[0])
    ai_model = genai.GenerativeModel(t_m)
except:
    ai_model = None

# ==========================================
# 4. 사이드바 구성 (상태 유지 및 학급 필터)
# ==========================================
query_params = st.query_params

with st.sidebar:
    st.title("🏫 한일고 40기 상담실")
    
    terms = sorted(df_scores['학기'].unique(), reverse=True) if not df_scores.empty else []
    sel_term = st.selectbox("📅 학기 선택", terms) if terms else None
    
    classes = sorted(df_scores[df_scores['학기'] == sel_term]['반'].unique()) if sel_term else []
    sel_class = st.selectbox("🏘️ 학급 선택", classes) if classes else None
    
    class_students = df_scores[(df_scores['학기'] == sel_term) & (df_scores['반'] == sel_class)] if sel_class else pd.DataFrame()
    students_list = sorted(class_students['식별'].unique()) if not class_students.empty else []
    
    # [핵심 수정] 첫 화면 보호를 위해 '학생을 선택해주세요' 옵션 추가
    student_options = ["학생을 선택해주세요"] + students_list
    
    default_student_idx = 0
    if "student" in query_params and query_params["student"] in students_list:
        default_student_idx = student_options.index(query_params["student"])
    
    sel_student = st.selectbox("👤 학생 선택", student_options, index=default_student_idx)
    
    if sel_student == "학생을 선택해주세요":
        sel_num = ""
        if "student" in st.query_params:
            del st.query_params["student"]
    else:
        sel_num = sel_student.split(" ")[0]
        st.query_params["student"] = sel_student
    
    st.markdown("---")
    menu_list = ["📈 내신 분석", "🎯 모의고사 분석", "🧠 성찰 리포트", "🏆 비교과 타임라인", "📝 상담 기록"]
    default_menu_idx = 0
    if "menu" in query_params and query_params["menu"] in menu_list:
        default_menu_idx = menu_list.index(query_params["menu"])
        
    menu = st.radio("📑 분석 메뉴", menu_list, index=default_menu_idx)
    st.query_params["menu"] = menu

# ==========================================
# 5. 프라이버시 웰컴 스크린 (학생 미선택 시)
# ==========================================
if sel_student == "학생을 선택해주세요":
    st.title("🏫 한일고 40기 통합 상담 시스템")
    st.markdown("""
    <div style="background-color: #FFFFFF; padding: 40px; border-radius: 15px; border: 1px solid #E2E8F0; text-align: center; margin-top: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
        <h2 style="color: #1E40AF; margin-bottom: 15px;">환영합니다, 선생님! 👋</h2>
        <p style="font-size: 1.15rem; color: #475569; line-height: 1.8;">
            학생 상담을 시작하시려면 <b>왼쪽 사이드바</b>에서 <b>학급</b>과 <b>학생 이름</b>을 선택해주세요.<br>
            <span style="color: #EF4444; font-size: 0.95rem;">※ 학생의 개인정보 보호를 위해, 학생을 선택하기 전까지는 어떠한 데이터도 화면에 표시되지 않습니다.</span>
        </p>
    </div>
    """, unsafe_allow_html=True)
    st.stop() # 여기서 멈춰서 아래 성적표가 그려지는 것을 방지합니다.

# 학생이 선택된 경우에만 아래 로직 실행
st.header(f"📊 {sel_student} 분석 리포트")

# ==========================================
# 6. 내신 분석 (가운데 정렬, 소수점 2자리)
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
                    
                    plot_data.append({
                        '과목': row['과목'], 
                        '점수': round(my_score, 2), 
                        '중위값': round(median_val, 2), 
                        '백분위': round(calc_perc, 2)
                    })
                
                pdf = pd.DataFrame(plot_data)
                fig = px.bar(pdf, x='과목', y='점수', color='과목', text=pdf['점수'].apply(lambda x: f"{x:.2f}"), color_discrete_sequence=px.colors.qualitative.Pastel)
                
                fig.add_trace(go.Scatter(x=pdf['과목'], y=pdf['중위값'], name="학년 중위값", mode='markers', marker=dict(size=12, color='black', symbol='diamond', line=dict(width=1, color='white'))))
                fig.add_trace(go.Scatter(x=pdf['과목'], y=pdf['백분위'], name="계산 백분위(%)", yaxis="y2", mode='lines+markers', line=dict(color='red', width=2)))
                
                fig.update_layout(xaxis=dict(tickangle=-45), yaxis=dict(title="원점수", range=[0, 105]), yaxis2=dict(overlaying="y", side="right", title="백분위(%)", range=[0, 105]), margin=dict(b=120), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                st.plotly_chart(fig, use_container_width=True)
                
                st.markdown("#### 📝 과목별 성적 상세 지표")
                display_df = pdf[['과목', '점수', '중위값', '백분위']].copy()
                display_df.columns = ['과목명', '내 점수', '학년 중위값', '계산 백분위(%)']
                styled_df = style_centered(display_df).format({'내 점수': '{:.2f}', '학년 중위값': '{:.2f}', '계산 백분위(%)': '{:.2f}'})
                st.table(styled_df)
                
        else: st.info("해당 시험 데이터가 없습니다.")
    
    with t2:
        subs = sorted(my_s['과목'].unique())
        s_sub = st.selectbox("과목 선택", subs)
        trend = my_s[my_s['과목'] == s_sub].copy()
        trend['점수'] = trend.get(s_col, trend.get('점수', 0)).apply(safe_numeric)
        trend['ord'] = trend['시험'].map({'1회고사': 1, '2회고사': 2, '학기말': 3})
        st.plotly_chart(px.line(trend.sort_values('ord'), x='시험', y='점수', markers=True, text=trend['점수'].apply(lambda x: f"{x:.2f}")), use_container_width=True)

# ==========================================
# 7. 모의고사 분석 (표점/등급 소수점 X, 백분위 소수점 O)
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
            raw_score = get_flex_val(latest, s_keys, ['표준점수', '표점'])
            raw_perc = get_flex_val(latest, s_keys, ['백분위', '백분'])
            raw_grade = get_flex_val(latest, s_keys, ['등급'])
            
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
        st.subheader("📈 백분위 변화 추이")
        p_cols = [c for c in my_m.columns if '백분' in c]
        if p_cols:
            plot_m = my_m[['시험명'] + p_cols].copy()
            for c in p_cols: plot_m[c] = plot_m[c].apply(safe_numeric)
            melted_m = plot_m.melt(id_vars=['시험명'], var_name='과목', value_name='백분위')
            st.plotly_chart(px.line(melted_m, x='시험명', y='백분위', color='과목', markers=True).update_layout(yaxis=dict(range=[0, 105])), use_container_width=True)
            
        st.subheader("📝 전체 모의고사 누적 기록")
        st.dataframe(style_centered(my_m.drop(columns=['학번', '식별', '학생명', '반'], errors='ignore')), use_container_width=True)
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
            if k in ['타임스탬프', '학번', '이름', '성명', '학생식별', '식별', '학생명', '시험명', '반'] or not v: continue
            with cols[idx % 2]: st.markdown(f"""<div style="background:white; border-left:5px solid #3B82F6; padding:15px; margin-bottom:10px; border-radius:10px; box-shadow:0 1px 3px rgba(0,0,0,0.1);"><b>{k}</b><br>{v}</div>""", unsafe_allow_html=True)
            idx += 1
        st.markdown("---")
        if st.button("🤖 AI 상담교사 피드백 생성"):
            if ai_model:
                with st.spinner("AI 분석 중..."):
                    try:
                        clean_data = {str(k): str(v) for k, v in row.items() if len(str(v)) > 5 and k not in ['학번', '타임스탬프']}
                        res = ai_model.generate_content(f"한일고 상담교사의 관점에서 조언해줘: {str(clean_data)}")
                        st.markdown(f"""<div class="ai-container"><b>🤖 AI 상담 조언</b><br><br>{res.text}</div>""", unsafe_allow_html=True)
                    except Exception as e: st.error(f"AI 오류: {e}")

# ==========================================
# 9. 비교과 타임라인
# ==========================================
elif menu == "🏆 비교과 타임라인":
    my_act = df_act[df_act['학번'] == sel_num].copy()
    if not my_act.empty:
        col_type = next((c for c in my_act.columns if '성격' in c), None)
        col_comp = next((c for c in my_act.columns if '역량' in c), None)
        
        st.subheader("📊 핵심역량별 활동 분포")
        comp_standards = ["탐구력/지식정보처리", "창의적 사고", "비판적 사고", "자기주도성/자기관리", "협력적 소통", "공동체 의식/윤리"]
        s_cols = st.columns(6)
        for i, comp_name in enumerate(comp_standards):
            count = my_act[col_comp].str.contains(comp_name, na=False).sum() if col_comp else 0
            with s_cols[i]: st.markdown(f"""<div class="stat-box"><small style="color:#64748B; font-size:0.75rem;">{comp_name}</small><br><b style="font-size:1.4rem; color:#2563EB;">{count}건</b></div>""", unsafe_allow_html=True)
        st.markdown("---")
        
        st.subheader("🔍 활동 맞춤 필터")
        f1, f2 = st.columns(2)
        filtered_act = my_act.copy()
        
        with f1:
            type_options = ["전체", "자율 활동", "진로 활동", "독서 활동", "문헌 탐구 활동", "협력 토론 활동", "실증 탐구 활동", "비평 성찰 활동", "발표 공유 활동", "융합 탐구 활동", "교사 개별 상담"]
            sel_type = st.selectbox("활동 성격별 필터", type_options)
            if sel_type != "전체" and col_type: filtered_act = filtered_act[filtered_act[col_type].str.contains(sel_type, na=False)]
                
        with f2:
            comp_options = ["전체"] + comp_standards
            sel_comp = st.selectbox("핵심 역량별 필터", comp_options)
            if sel_comp != "전체" and col_comp: filtered_act = filtered_act[filtered_act[col_comp].str.contains(sel_comp, na=False)]
        
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
</div></div>""", unsafe_allow_html=True)
            if st.button(f"🪄 AI 생기부 초안 생성 (기록번호: {i})"):
                if ai_model:
                    with st.spinner("작성 중..."):
                        try: st.info(ai_model.generate_content(f"활동기록을 바탕으로 생기부 문구를 작성해줘(~함 체): {row.get('핵심 활동 내용', '')}").text)
                        except Exception as e: st.error(f"AI 오류: {e}")
    else: st.info("기록된 활동이 없습니다.")

# ==========================================
# 10. 신규 상담 기록 작성 및 저장
# ==========================================
elif menu == "📝 상담 기록":
    my_counsel = df_counsel[df_counsel['학번'] == sel_num].copy() if not df_counsel.empty else pd.DataFrame()
    
    st.subheader(f"📖 {sel_student} 상담 누적 기록")
    if not my_counsel.empty and '상담일자' in my_counsel.columns:
        for i, row in my_counsel.sort_values('상담일자', ascending=False).iterrows():
            st.markdown(f"""<div class="timeline-card" style="border-left: 6px solid #8B5CF6;">
<span class="badge" style="background:#F3E8FF; color:#7E22CE;">🗣️ {row.get('상담유형', '일반 상담')}</span>
<div style="font-size:0.85rem; color:#64748B; margin-bottom:10px;">📅 {row.get('상담일자', '-')}</div>
<div style="background:#F8FAFC; padding:18px; border-radius:12px; font-size:0.95rem; line-height:1.7;">{row.get('상담내용', '-')}</div>
</div>""", unsafe_allow_html=True)
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
                        
                        try: sh = doc.worksheet("71_상담기록")
                        except:
                            sh = doc.add_worksheet(title="71_상담기록", rows="1000", cols="10")
                            sh.append_row(["학번", "이름", "상담일자", "상담유형", "상담내용"])
                        
                        sh.append_row([sel_num, sel_student.split(" ")[1], str(c_date), c_type, c_content])
                        st.cache_resource.clear() 
                        st.success("✅ 저장 완료! 새로고침(F5)을 눌러 확인하세요.")
                    except Exception as e: st.error(f"저장 중 오류 발생: {e}")
                    except Exception as e:
                        st.error(f"저장 중 오류가 발생했습니다: {e}")
