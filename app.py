import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 1. 페이지 설정
st.set_page_config(page_title="한일고 40기 상담 시스템", layout="wide")

# UI 디자인 유지
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@400;600;800&display=swap');
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif; }
    .stMetric { background: white; border: 1px solid #E2E8F0; padding: 15px !important; border-radius: 10px !important; }
    .timeline-card { background: white; border: 1px solid #E2E8F0; border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border-left: 5px solid #2563EB; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.75rem; font-weight: 700; background: #EFF6FF; color: #1D4ED8; margin-bottom: 5px; }
    .ai-box { background: #F0F9FF; border: 1px solid #BAE6FD; border-radius: 10px; padding: 15px; margin-top: 10px; }
</style>
""", unsafe_allow_html=True)

# 2. AI 설정
try:
    genai.configure(api_key=st.secrets["gemini_api_key"])
    model = genai.GenerativeModel('gemini-1.5-flash')
except:
    model = None

# 3. 데이터 로드 (핵심 수정 부분)
@st.cache_resource
def load_all_data():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
        client = gspread.authorize(creds)
        doc = client.open("40기 마스터 파일")
        
        def get_clean_df(sheet_name):
            try:
                # 탭 이름을 직접 찾되, 앞뒤 공백 무시하고 검색
                all_sheets = doc.worksheets()
                target_sheet = next((s for s in all_sheets if s.title.strip() == sheet_name), None)
                
                if target_sheet is None:
                    return pd.DataFrame()
                
                data = target_sheet.get_all_values()
                if not data: return pd.DataFrame()
                
                df = pd.DataFrame(data[1:], columns=data[0])
                
                # [강력 세탁] 학번 정제: 소수점 제거, 공백 제거, 문자열화
                if '학번' in df.columns:
                    df['학번'] = df['학번'].astype(str).str.split('.').str[0].str.strip()
                
                # 식별값 생성 (학번 + 성명)
                name_col = '성명' if '성명' in df.columns else '이름'
                if '학번' in df.columns and name_col in df.columns:
                    df['학생명'] = df[name_col].astype(str).str.strip()
                    df['식별'] = df['학번'] + " " + df['학생명']
                return df
            except:
                return pd.DataFrame()

        return get_clean_df("31_내신"), get_clean_df("21_모의고사"), get_clean_df("51_시험복기"), get_clean_df("61_비교과")
    except Exception as e:
        st.error(f"구글 시트 연결 실패: {e}")
        return [pd.DataFrame()]*4

df_scores, df_mock, df_ref, df_act = load_all_data()

# 4. 메인 로직 및 사이드바
if df_scores.empty:
    st.error("데이터를 불러오지 못했습니다. 구글 시트 공유 설정이나 탭 이름을 확인해주세요.")
    st.stop()

with st.sidebar:
    st.title("🏫 40기 통합 상담")
    terms = sorted(df_scores['학기'].unique(), reverse=True)
    sel_term = st.selectbox("학기", terms)
    
    # 해당 학기 학생 목록
    students = sorted(df_scores[df_scores['학기'] == sel_term]['식별'].unique())
    sel_student = st.selectbox("학생", students)
    sel_num = sel_student.split(" ")[0] # 학번만 추출
    
    st.markdown("---")
    menu = st.radio("메뉴 선택", ["📈 내신 분석", "🎯 모의고사", "🧠 성찰 리포트", "🏆 비교과 타임라인"])

# 5. 비교과 타임라인 (수정 핵심)
if menu == "🏆 비교과 타임라인":
    st.header(f"🏆 {sel_student} 활동 기록")
    
    # 학번으로 매칭 (가장 정확함)
    my_act = df_act[df_act['학번'] == sel_num].copy()
    
    if my_act.empty:
        st.warning(f"'{sel_num}' 학번으로 등록된 활동이 없습니다.")
        with st.expander("🛠️ 데이터가 안 보이나요? (진단 도구)"):
            st.write("현재 앱이 찾는 학번:", f"[{sel_num}]")
            if not df_act.empty:
                st.write("시트 내 첫 번째 데이터 학번:", f"[{df_act['학번'].iloc[0]}]")
                st.write("시트 내 전체 열 이름:", df_act.columns.tolist())
            else:
                st.error("61_비교과 탭에서 데이터를 읽어오지 못했습니다.")
    else:
        # 활동 일자 순 정렬
        try:
            my_act = my_act.sort_values('활동 일자', ascending=False)
        except:
            pass
            
        for idx, row in my_act.iterrows():
            st.markdown(f"""
            <div class="timeline-card">
                <div class="badge">#{row.get('활동의 성격','활동')}</div>
                <div style="font-size:1.3rem; font-weight:800; color:#1E40AF; margin-bottom:8px;">{row.get('활동 주제','주제 없음')}</div>
                <div style="font-size:0.85rem; color:#64748B; margin-bottom:15px;">
                    📅 {row.get('활동 일자','-')} | 📚 {row.get('연계 가능 교과(선택)','-')}
                </div>
                <div style="background:#F8FAFC; padding:15px; border-radius:10px; font-size:0.95rem; line-height:1.7;">
                    <b>💡 동기:</b> {row.get('활동 동기(왜 시작했나요)','')}<br><br>
                    <b>📝 주요 활동:</b><br>{row.get('핵심 활동 내용(무엇을 어떻게 했나요)','')}<br><br>
                    <b>🌱 성장과 변화:</b><br>{row.get('결과 및 배우고 느낀 점(어떤 변화가 있었나요?)','')}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button(f"🪄 AI 생기부 초안 생성", key=f"btn_{idx}"):
                with st.spinner("AI가 내용을 분석하여 문구를 작성 중입니다..."):
                    p = f"교사 관점에서 학생의 활동을 생기부용으로 요약해줘. '~함'체 사용.\n내용: {row.get('핵심 활동 내용','')}\n변화: {row.get('결과 및 배우고 느낀 점','')}"
                    res = model.generate_content(p)
                    st.info(res.text)

# 6. 나머지 메뉴 (내신, 모의고사, 성찰은 기존 로직 유지)
elif menu == "📈 내신 분석":
    # ... (기존 내신 코드 생략 - 위 통합본 코드 참고) ...
    st.write("내신 분석 화면입니다.") # 실제 코드에는 위 통합본의 내신 로직이 들어갑니다.

elif menu == "🎯 모의고사":
    # ... (기존 모의고사 코드 생략) ...
    st.write("모의고사 화면입니다.")

elif menu == "🧠 성찰 리포트":
    # ... (기존 성찰 리포트 코드 생략) ...
    st.write("성찰 리포트 화면입니다.")
