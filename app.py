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
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 강력한 숫자 추출기 (오류 방지용)
# ==========================================
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

# ==========================================
# 3. 구글 시트 데이터 연동
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
                
                n_col = next((c for c in df.columns if '성명' in c or '이름' in c), None)
                if '학번' in df.columns and n_col:
                    df['학생명'] = df[n_col].astype(str).str.strip()
                    df['식별'] = df['학번'] + " " + df['학생명']
                return df
            except: 
                return pd.DataFrame()
                
        return process_sheet("31_내신"), process_sheet("21_모의고사"), process_sheet("51_시험복기"), process_sheet("61_비교과")
    
    except Exception as e:
        st.error(f"구글 시트 연동 중 오류가 발생했습니다: {e}")
        return [pd.DataFrame()]*4

df_scores, df_mock, df_ref, df_act = load_all_data()

# ==========================================
# 4. AI 모델 자동 탐색기 (404 에러 원천 봉쇄)
# ==========================================
try:
    genai.configure(api_key=st.secrets["gemini_api_key"])
    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    
    if 'models/gemini-1.5-flash' in available_models:
        target_model = 'models/gemini-1.5-flash'
    elif 'models/gemini-pro' in available_models:
        target_model = 'models/gemini-pro'
    else:
        target_model = available_models[0]
        
    ai_model = genai.GenerativeModel(target_model)
except Exception as e:
    ai_model = None
    st.sidebar.warning(f"AI 연동에 실패했습니다. API 키를 확인해주세요.")

# ==========================================
# 5. 사이드바 및 공통 필터
# ==========================================
if df_scores.empty:
    st.error("데이터 로드에 실패했습니다. 앱 관리자 화면에서 Reboot를 진행해주세요.")
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
# 6. 내신 분석
# ==========================================
if menu == "📈 내신 분석":
    t1, t2 = st.tabs(["📊 시험별 상세", "📈 성적 추이"])
    my_s_all = df_scores[(df_scores['학기'] == sel_term)].copy()
    my_s = my_s_all[my_s_all['식별'] == sel_student]
    
    score_cols = [c for c in my_s_all.columns if '점수' in c.replace(" ", "")]
    score_col = score_cols[0] if score_cols else '점수'
    
    with t1:
        exam = st.selectbox("시험 선택", ["1회고사", "2회고사", "학기말"])
        filtered = my_s[my_s['시험'] == exam].copy()
        
        if not filtered.empty:
            if exam == "학기말":
                cols = st.columns(len(filtered))
                for i, (_, row) in enumerate(filtered.iterrows()):
                    cols[i].metric(row['과목'], f"{row.get('등급', '-')}등급")
            else:
                plot_data = []
                for _, row in filtered.iterrows():
                    all_exam_scores = my_s_all[(my_s_all['시험'] == exam) & (my_s_all['과목'] == row['과목'])][score_col]
                    all_scores = all_exam_scores.apply(safe_numeric).dropna()
                    
                    median_val = all_scores.median() if not all_scores.empty else 0
                    my_score = safe_numeric(row.get(score_col, 0))
                    
                    if not all_scores.empty:
                        count_below = (all_scores <= my_score).sum()
                        calc_perc = (count_below / len(all_scores)) * 100
                    else:
                        calc_perc = 0
                    
                    plot_data.append({
                        '과목': row['과목'], 
                        '점수': my_score, 
                        '중위값': median_val, 
                        '백분위': round(calc_perc, 1)
                    })
                    
                pdf = pd.DataFrame(plot_data)

                fig = px.bar(pdf, x='과목', y='점수', color='과목', text='점수', color_discrete_sequence=px.colors.qualitative.Pastel)
                fig.add_trace(go.Scatter(x=pdf['과목'], y=pdf['중위값'], name="학년 중위값", mode='lines+markers', line=dict(color='black', dash='dash', width=2)))
                fig.add_trace(go.Scatter(x=pdf['과목'], y=pdf['백분위'], name="계산 백분위(%)", yaxis="y2", mode='lines+markers+text', 
                                         text=pdf['백분위'].apply(lambda x: f"{int(x)}%" if x > 0 else ""), 
                                         line=dict(color='red', width=3)))
                
                fig.update_layout(
                    xaxis=dict(tickangle=-45, tickfont=dict(size=14, color='black')),
                    yaxis=dict(title="원점수", range=[0, 105]),
                    yaxis2=dict(title="백분위(%)", overlaying="y", side="right", range=[0, 105]),
                    margin=dict(b=120), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig, use_container_width=True)
        else: 
            st.info("해당 시험 데이터가 없습니다.")
    
    with t2:
        subs = sorted(my_s['과목'].unique())
        s_sub = st.selectbox("과목 선택", subs)
        trend = my_s[my_s['과목'] == s_sub].copy()
        trend['점수'] = trend.get(score_col, trend.get('점수', 0)).apply(safe_numeric)
        trend['ord'] = trend['시험'].map({'1회고사': 1, '2회고사': 2, '학기말': 3})
        
        fig_trend = px.line(trend.sort_values('ord'), x='시험', y='점수', markers=True, text='점수')
        st.plotly_chart(fig_trend, use_container_width=True)

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
        
        perc_cols = [c for c in my_m.columns if '백분위' in c or '백분' in c]
        if perc_cols:
            plot_m = my_m[['시험명'] + perc_cols].copy()
            for c in perc_cols:
                plot_m[c] = plot_m[c].apply(safe_numeric)
            
            melted_m = plot_m.melt(id_vars=['시험명'], var_name='과목', value_name='백분위')
            fig_m = px.line(melted_m, x='시험명', y='백분위', color='과목', markers=True)
            fig_m.update_layout(yaxis=dict(title="백분위(%)", range=[0, 105]), margin=dict(b=80))
            
            st.plotly_chart(fig_m, use_container_width=True)

        st.markdown("---")
        st.subheader("📝 전체 모의고사 누적 기록")
        st.dataframe(my_m.drop(columns=['학번', '식별', '학생명'], errors='ignore'), use_container_width=True)
        
    else: 
        st.info("모의고사 기록이 없습니다.")

# ==========================================
# 8. 성찰 리포트 (들여쓰기 제거 완료)
# ==========================================
elif menu == "🧠 성찰 리포트":
    my_r = df_ref[df_ref['학번'] == sel_num].copy()
    
    if not my_r.empty:
        sel_ex = st.selectbox("시험 선택", my_r['시험명'].unique())
        row = my_r[my_r['시험명'] == sel_ex].iloc[-1]
        
        cols = st.columns(2)
        idx = 0
        for k, v in row.items():
            if k in ['타임스탬프', '학번', '이름', '성명', '학생식별', '식별', '학생명', '시험명'] or not v: 
                continue
            with cols[idx % 2]:
                # 들여쓰기를 제거하여 코드가 텍스트로 보이지 않게 수정
                st.markdown(f"""<div style="background:white; border-left:5px solid #3B82F6; padding:15px; margin-bottom:10px; border-radius:10px; box-shadow:0 1px 3px rgba(0,0,0,0.1);">
<b>{k}</b><br>{v}
</div>""", unsafe_allow_html=True)
            idx += 1
        
        st.markdown("---")
        
        if st.button("🤖 AI 상담교사 피드백 생성"):
            if ai_model:
                with st.spinner("AI가 학생의 성찰 내용을 꼼꼼히 분석 중입니다..."):
                    try:
                        clean_data = {str(k): str(v) for k, v in row.items() if len(str(v)) > 5 and k not in ['학번', '타임스탬프']}
                        prompt = f"당신은 한일고등학교의 따뜻하고 전문적인 상담교사입니다. 다음 학생의 시험 성찰 내용을 분석하고 격려와 구체적인 학습 조언을 제공해주세요: {str(clean_data)}"
                        
                        res = ai_model.generate_content(prompt)
                        
                        # 들여쓰기를 제거하여 코드가 텍스트로 보이지 않게 수정
                        st.markdown(f"""<div class="ai-container">
<b>🤖 AI 상담교사의 조언</b><br><br>
{res.text}
</div>""", unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"AI 피드백 생성 중 오류가 발생했습니다: {e}")
            else: 
                st.warning("AI 모델이 연결되지 않았습니다. API 키를 확인해주세요.")
    else: 
        st.info("작성된 성찰 기록이 없습니다.")

# ==========================================
# 9. 비교과 타임라인 (들여쓰기 제거 완료)
# ==========================================
elif menu == "🏆 비교과 타임라인":
    my_act = df_act[df_act['학번'] == sel_num].copy()
    
    if not my_act.empty:
        col_type = next((c for c in my_act.columns if '성격' in c), None)
        col_comp = next((c for c in my_act.columns if '역량' in c), None)
        
        if col_comp:
            st.subheader("📊 핵심역량별 활동 분포")
            counts = my_act[col_comp].value_counts()
            
            stat_cols = st.columns(len(counts) if len(counts) > 0 else 1)
            for i, (name, count) in enumerate(counts.items()):
                with stat_cols[i % len(stat_cols)]:
                    # 들여쓰기 제거
                    st.markdown(f"""<div class="stat-box">
<small style="color:#64748B;">{name}</small><br>
<b style="font-size:1.5rem; color:#2563EB;">{count}건</b>
</div>""", unsafe_allow_html=True)
            st.markdown("---")
        
        filter_col1, filter_col2 = st.columns(2)
        filtered_act = my_act.copy()
        
        if col_type:
            with filter_col1: 
                type_list = ["전체"] + sorted(my_act[col_type].dropna().unique().tolist())
                sel_type = st.selectbox("활동 성격별 필터", type_list)
            if sel_type != "전체": 
                filtered_act = filtered_act[filtered_act[col_type] == sel_type]
                
        if col_comp:
            with filter_col2: 
                comp_list = ["전체"] + sorted(my_act[col_comp].dropna().unique().tolist())
                sel_comp = st.selectbox("핵심 역량별 필터", comp_list)
            if sel_comp != "전체": 
                filtered_act = filtered_act[filtered_act[col_comp] == sel_comp]
        
        st.write(f"🔍 검색 결과: 총 **{len(filtered_act)}**건의 활동이 확인되었습니다.")
        
        for i, row in filtered_act.sort_values('활동 일자', ascending=False).iterrows():
            
            act_type = row.get(col_type, '활동') if col_type else '활동'
            act_comp = row.get(col_comp, '역량 미지정') if col_comp else '역량'
            act_title = row.get('활동 주제', '주제 없음')
            act_date = row.get('활동 일자', '-')
            act_subject = row.get('연계 가능 교과(선택)', '-')
            
            act_content = row.get('핵심 활동 내용(무엇을 어떻게 했나요)', row.get('핵심 활동 내용', '-'))
            act_result = row.get('결과 및 배우고 느낀 점(어떤 변화가 있었나요?)', row.get('결과 및 배우고 느낀 점', '-'))
            act_motive = row.get('활동 동기(왜 시작했나요)', '-')
            
            # HTML 코드가 문자열로 출력되지 않도록 들여쓰기 완벽 제거
            st.markdown(f"""<div class="timeline-card">
<span class="badge">#{act_type}</span>
<span class="badge" style="background:#DCFCE7; color:#166534;">🏆 {act_comp}</span>
<div style="font-size:1.3rem; font-weight:800; color:#1E40AF; margin:10px 0;">{act_title}</div>
<div style="font-size:0.85rem; color:#64748B; margin-bottom:15px;">📅 {act_date} | 📚 연계 교과: {act_subject}</div>
<div style="background:#F8FAFC; padding:18px; border-radius:12px; font-size:0.95rem; line-height:1.7;">
<b>💡 활동 동기:</b><br>{act_motive}<br><br>
<b>📝 핵심 활동 내용:</b><br>{act_content}<br><br>
<b>🌱 결과 및 배운 점:</b><br>{act_result}
</div>
</div>""", unsafe_allow_html=True)
            
            if st.button(f"🪄 AI 생기부 초안 생성 (기록번호: {i})"):
                if ai_model:
                    with st.spinner("AI가 생기부 맞춤형 문구를 작성하고 있습니다..."):
                        prompt = f"다음 학생의 학교 활동 기록을 바탕으로, 학교생활기록부에 바로 기재할 수 있는 객관적이고 핵심적인 문구를 작성해줘. 문장의 끝은 '~함', '~보임' 등의 개조식으로 끝내야 해. 활동내용: {act_content} / 결과: {act_result}"
                        try:
                            res = ai_model.generate_content(prompt)
                            st.info(res.text)
                        except Exception as e:
                            st.error(f"AI 생성 중 오류가 발생했습니다: {e}")
                else: 
                    st.warning("AI 모델이 설정되지 않았습니다.")
                    
    else: 
        st.info("기록된 활동 내용이 없습니다.")
