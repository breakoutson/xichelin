import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

import streamlit.components.v1 as components
import json
import time
import random
import streamlit.components.v1 as components
import json
import time
import random
import requests
from supabase import create_client, Client

# Helper function to get secrets/env
def get_secret(key):
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        # If secrets not found or generic error, fallback to env
        pass
    return os.getenv(key)

# Kakao API Key
DEFAULT_REST_API_KEY = get_secret("KAKAO_REST_API_KEY")
DEFAULT_JS_API_KEY = get_secret("KAKAO_JS_API_KEY")

# Check if keys are loaded
if not DEFAULT_REST_API_KEY or not DEFAULT_JS_API_KEY:
    st.error("API Key가 설정되지 않았습니다. .env 파일 또는 Streamlit Secrets를 확인해주세요!")


# Configuration
# Page config must be the first Streamlit command
st.set_page_config(page_title="회사 점심 지도", page_icon="🍽️", layout="wide")

# CSS 주입: 버튼 안의 텍스트를 좌측으로 정렬
# CSS 주입: 모바일 레이아웃 강제 조정 (가로 스크롤/한줄 정렬)
st.markdown("""
    <style>
    /* 모바일 환경 (768px 이하)에서 컬럼 강제 가로 정렬 */
    @media (max-width: 768px) {
        /* 컬럼 컨테이너: 가로 방향 유지, 줄바꿈 금지, 가로 스크롤 허용 */
        div[data-testid="stHorizontalBlock"] {
             flex-direction: row !important;
             flex-wrap: nowrap !important;
             overflow-x: auto !important;
             gap: 5px !important;
             padding-bottom: 5px; /* 스크롤바 공간 */
        }
        
        /* 개별 컬럼: 내용물 크기에 맞게 자동 조절 (비율 무시) */
        div[data-testid="column"] {
            flex: 0 0 auto !important;
            width: auto !important;
            min-width: auto !important; 
        }
        
        /* 버튼 스타일: 컴팩트하게, 강제 한줄 표시 */
        div.stButton > button {
            width: auto !important; /* 버튼 내용만큼만 차지 */
            padding: 4px 8px !important; /* 내부 여백 축소 */
            font-size: 13px !important; /* 글자 크기 축소 */
            white-space: nowrap !important; /* 줄바꿈 금지 */
            height: auto !important;
            min-height: 0px !important;
        }
        
        /* 리스트 내부의 텍스트가 잘리지 않게 조정 */
        p, div {
             font-size: 13px !important;
        }
    }
    
    /* PC/전체 공통: 버튼 텍스트 정렬 */
    div.stButton > button {
        text-align: left; /* 좌측 정렬 복구 */
    }
    </style>
    """, unsafe_allow_html=True)

DATA_DIR = 'data'
DATA_FILE = os.path.join(DATA_DIR, 'restaurants.csv')
DEFAULT_LAT = 37.5617864  # Namsan Square (Xi S&D)
DEFAULT_LON = 126.9910438

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# Supabase Setup
SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_KEY = get_secret("SUPABASE_KEY")

@st.cache_resource
def init_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        # st.warning("Supabase URL or Key not found in .env or secrets")
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

def load_data():
    if not supabase:
         return pd.DataFrame(columns=['Name', 'Cuisine', 'Rating', 'RatingCount', 'Review', 'Location', 'Latitude', 'Longitude', 'BestMenu', 'Recommender', 'id'])

    try:
        response = supabase.table('restaurants').select("*").execute()
        data = response.data
        
        if not data:
             return pd.DataFrame(columns=['Name', 'Cuisine', 'Rating', 'RatingCount', 'Review', 'Location', 'Latitude', 'Longitude', 'BestMenu', 'Recommender', 'id'])
        
        df = pd.DataFrame(data)
        
        # Rename lower_case DB columns to Title_Case App columns
        # Map: db_col -> App_Col
        rename_map = {
            'name': 'Name', 
            'cuisine': 'Cuisine', 
            'rating': 'Rating', 
            'rating_count': 'RatingCount', 
            'review': 'Review', 
            'location': 'Location', 
            'latitude': 'Latitude', 
            'longitude': 'Longitude', 
            'best_menu': 'BestMenu', 
            'recommender': 'Recommender',
            'price': 'Price',
            # id is kept as is (lowercase 'id' from DB usually, or I can map it to 'ID')
            'id': 'id' 
        }
        # Only rename columns that exist (in case DB has extra or missing)
        df = df.rename(columns=rename_map)
        
        return df
    except Exception as e:
        st.error(f"Error loading data from Supabase: {e}")
        return pd.DataFrame(columns=['Name', 'Cuisine', 'Rating', 'RatingCount', 'Review', 'Location', 'Latitude', 'Longitude', 'BestMenu', 'Recommender', 'id'])

def save_data(df):
    # Deprecated: Saving entire DF to CSV is replaced by direct DB inserts/updates.
    # Keeping this pass to prevent immediate crashes before refactoring call sites.
    pass

# Helper: Get current REST API Key (Deprecated logic removed, using global var)
# def get_rest_api_key():
#     return st.session_state.get('rest_api_key', DEFAULT_REST_API_KEY)

def search_kakao_place(keyword):
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {DEFAULT_REST_API_KEY}"}
    params = {
        "query": keyword, 
        "size": 15,
        "x": DEFAULT_LON, # Center Longitude
        "y": DEFAULT_LAT, # Center Latitude
        "radius": 1000,    # Radius in meters (1km)
        "radius": 1000,    # Radius in meters (1km)
        # "sort": "distance" # Sort by distance
        "sort": "accuracy" # Default is accuracy
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json().get('documents', [])
    except requests.exceptions.HTTPError as err:
        try:
            error_json = response.json()
            st.error(f"Kakao API Error: {error_json.get('msg', str(err))}")
        except:
            st.error(f"HTTP Error: {err}")
    except Exception as e:
        st.error(f"검색 중 오류가 발생했습니다: {e}")
        return []

import math

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371  # radius of earth in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) * math.sin(dlat / 2) + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dlon / 2) * math.sin(dlon / 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c * 1000 # meters

def get_kakao_address(lat, lon):
    url = "https://dapi.kakao.com/v2/local/geo/coord2address.json"
    headers = {"Authorization": f"KakaoAK {DEFAULT_REST_API_KEY}"}
    params = {"x": lon, "y": lat}
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        documents = response.json().get('documents', [])
        if documents:
            address_info = documents[0]
            road_address = address_info.get('road_address')
            address = address_info.get('address')
            
            if road_address:
                building_name = road_address.get('building_name', '')
                addr_name = road_address.get('address_name', '')
                return building_name if building_name else addr_name
            elif address:
                return address.get('address_name', '')
        return "주소 정보 없음"
    except Exception:
        return "주소 확인 불가"

df = load_data()

# Initialize session state for selected location and winner
if 'selected_lat' not in st.session_state:
    st.session_state.selected_lat = None
if 'selected_lon' not in st.session_state:
    st.session_state.selected_lon = None
if 'selected_name' not in st.session_state:
    st.session_state.selected_name = None # For reverse geocoding result
if 'winner' not in st.session_state:
    st.session_state.winner = None
if 'selection_status' not in st.session_state:
    st.session_state.selection_status = None # {'type': 'new'|'existing', 'data': ...}
if 'selected_category' not in st.session_state:
    st.session_state.selected_category = "전체"
if 'search_query' not in st.session_state:
    st.session_state.search_query = ""

# --- Header Area: Title & Roulette ---

col_header, col_roulette = st.columns([3, 1], gap="medium") 

with col_header:
    st.title("자이에스앤디 점심 메뉴 추천 시스템")
    # st.markdown("회사 근처 맛집을 공유하고 찾아보세요! 지도에서 위치를 선택하여 추가할 수 있습니다.")  <-- Removed

with col_roulette:
    st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True) # Spacer for alignment
    
    # 1. Button first
    start_structure = st.button("🎲 랜덤 선택!", use_container_width=True)
    
    # 2. Placeholder for the result (BELOW the button)
    result_placeholder = st.empty()

    # 3. Handle Button Click (Animation)
    if start_structure:
        if df.empty:
            st.warning("등록된 맛집이 없습니다!")
        else:
            # Animation: Fast -> Slow
            candidates = df['Name'].tolist()
            sleep_time = 0.05
            for i in range(20):  # More iterations
                random_name = random.choice(candidates)
                result_placeholder.markdown(f"<h4 style='text-align: center; color: #555; margin: 5px;'>🤔 {random_name}</h4>", unsafe_allow_html=True)
                
                # Decelerate: Increase sleep time gradually
                if i > 10:
                    sleep_time += 0.05
                time.sleep(sleep_time)
            
            winner_row = df.sample(1).iloc[0]
            st.session_state.winner = winner_row['Name'] # Save winner to session state
            st.balloons()
            
            # Auto-select the winner in Sidebar and Map
            st.session_state.selection_status = {'type': 'existing', 'data': winner_row}
            st.session_state.selected_lat = winner_row['Latitude']
            st.session_state.selected_lon = winner_row['Longitude']
            st.session_state.selected_name = winner_row['Name']
            
            # Reset filters so the sidebar shows ONLY this winner's info (Case 1)
            st.session_state.search_query = ""
            st.session_state.selected_category = "전체"
            
            st.rerun()

    # 4. Show Persistent Result (if winner exists)
    # This runs on reruns as well, keeping the result visible
    if st.session_state.winner:
        # Find the row for the winner to get details again
        winner_info = df[df['Name'] == st.session_state.winner]
        if not winner_info.empty:
            w_row = winner_info.iloc[0]
            winner_html = f"""
            <div style="background-color: #e8f5e9; padding: 5px; border-radius: 8px; border: 1px solid #4CAF50; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <h5 style="color: #2e7d32; margin:0; font-size: 16px;">🎉 {w_row['Name']}</h5>
                <p style="margin:2px 0 0 0; font-size: 12px; color: #555;">{w_row['BestMenu']}</p>
            </div>
            """
            result_placeholder.markdown(winner_html, unsafe_allow_html=True)





# Calculate average location for map center
# Calculate average location for map center
# If selection exists, center map there. Otherwise avg or default.
if st.session_state.selected_lat:
    avg_lat = st.session_state.selected_lat
    avg_lon = st.session_state.selected_lon
elif not df.empty and pd.notna(df['Latitude'].mean()):
    avg_lat = df['Latitude'].mean()
    avg_lon = df['Longitude'].mean()
else:
    avg_lat, avg_lon = DEFAULT_LAT, DEFAULT_LON

# --- Layout with Tabs (Removed for Mobile UX) ---
# Previous tab logic removed. Now using single page vertical
# --- Layout Reorganization for Mobile UX ---

# 1. Search & Filter Controls (Top)
# Header Removed as requested

# Search Bar
def reset_selection():
    st.session_state.selection_status = None
    st.session_state.selected_lat = None
    st.session_state.selected_lon = None
    st.session_state.selected_name = None
    st.session_state.winner = None

def reset_all_state():
    st.session_state.search_query = ""
    st.session_state.selected_category = "전체"
    reset_selection()

def set_category_state(cat):
    st.session_state.selected_category = cat
    st.session_state.search_query = ""
    st.session_state.winner = None # Reset random result

col_search, col_reset = st.columns([3, 1])
with col_search:
    st.text_input("장소 검색", label_visibility="collapsed", placeholder="장소명 검색 (예: 닭갈비)", key="search_query", on_change=reset_selection)
with col_reset:
    st.button("🔄 초기화", use_container_width=True, on_click=reset_all_state)

# Category Buttons (1 Row of 8)
categories = ["전체", "한식", "중식", "일식", "양식", "분식", "술집", "기타"]
cat_cols = st.columns(8) # One row for all

for i, cat in enumerate(categories):
    btn_type = "primary" if st.session_state.selected_category == cat else "secondary"
    cat_cols[i].button(cat, key=f"cat_{i}", type=btn_type, use_container_width=True, on_click=set_category_state, args=(cat,))

# Sort Options (No Label)
st.write("") # Spacer
sort_col1, sort_col2, sort_col3 = st.columns(3)
if 'sort_option' not in st.session_state:
    st.session_state.sort_option = 'Rating' # Default

if sort_col1.button("⭐ 평점순", use_container_width=True, type="primary" if st.session_state.sort_option == 'Rating' else "secondary"):
    st.session_state.sort_option = 'Rating'
    st.session_state.winner = None # Reset random result
    st.rerun()
if sort_col2.button("📏 거리순", help="현재 지도 중심 기준", use_container_width=True, type="primary" if st.session_state.sort_option == 'Distance' else "secondary"):
    st.session_state.sort_option = 'Distance'
    st.session_state.winner = None # Reset random result
    st.rerun()
if sort_col3.button("🆕 최신순", use_container_width=True, type="primary" if st.session_state.sort_option == 'Newest' else "secondary"):
    st.session_state.sort_option = 'Newest'
    st.session_state.winner = None # Reset random result
    st.rerun()

st.divider()

# --- Logic for Filtering & Sorting ---
search_markers = [] # For map

# Global Filter Logic
filtered_df = df.copy()

# 1. Search Query Filter
if st.session_state.search_query:
    # If search, ignore category? Or combined? Usually search overrides category.
    # Let's search Kakao API first
    places = search_kakao_place(st.session_state.search_query)
    
    # Also filter local DB for name match
    filtered_df = filtered_df[filtered_df['Name'].str.contains(st.session_state.search_query)]
    
    if places:
        st.caption(f"🔍 **{len(places)}**개의 장소가 검색되었습니다.")
        for p in places:
            is_registered = False
            if not df.empty:
                if p['place_name'] in df['Name'].values:
                        is_registered = True
            
            search_markers.append({
                "lat": float(p['y']),
                "lng": float(p['x']),
                "name": p['place_name'],
                "isRegistered": is_registered,
                "address": p['address_name']
            })
else:
    # 2. Category Filter
    if st.session_state.selected_category != "전체":
        filtered_df = filtered_df[filtered_df['Cuisine'] == st.session_state.selected_category]

# 3. Sorting
if not filtered_df.empty:
    if st.session_state.sort_option == 'Rating':
        filtered_df = filtered_df.sort_values(by='Rating', ascending=False)
    elif st.session_state.sort_option == 'Newest':
        # Assuming 'id' is somewhat chronological or if we had created_at
        if 'id' in filtered_df.columns:
             filtered_df = filtered_df.sort_values(by='id', ascending=False)
    elif st.session_state.sort_option == 'Distance':
        # Sort by distance from current map center (or default)
        # Sort by distance from Company (Xi S&D)
        center_lat = DEFAULT_LAT
        center_lon = DEFAULT_LON
        
        def calc_dist(row):
            if pd.isna(row['Latitude']) or pd.isna(row['Longitude']):
                return 99999
            return calculate_distance(center_lat, center_lon, row['Latitude'], row['Longitude'])
        
        filtered_df['Distance'] = filtered_df.apply(calc_dist, axis=1)
        filtered_df = filtered_df.sort_values(by='Distance', ascending=True)


# --- 2. Dashboard Interface (List & Detail) ---
# This replaces the Sidebar and Dataframe logic
status = st.session_state.selection_status

# Container for the dashboard list
dashboard_container = st.container()

with dashboard_container:
    # A. Selected Item Detail View (Top Priority if specific selection exists)
    if status and status.get('type') == 'existing':
        # Existing Restaurant View
        row = status['data']
        
        with st.container(border=True): # Card Style
            # Header with Close Button
            d_col1, d_col2 = st.columns([9, 1])
            with d_col1:
                st.subheader(f"🍽️ {row['Name']}")
                st.caption(f"{row['Cuisine']} | ⭐ {row['Rating']:.1f}점 ({int(row.get('RatingCount', 1))}명 참여)")
            with d_col2:
                if st.button("❌", key="close_dashboard_list"):
                     st.session_state.selection_status = None
                     st.session_state.selected_lat = None
                     st.session_state.selected_lon = None
                     st.session_state.selected_name = None
                     st.rerun()

            st.markdown(f"**👍 맛있었던 메뉴**: {row['BestMenu']}")
            if pd.notna(row.get('Recommender')):
                st.caption(f"💁‍♂️ 추천인: {row['Recommender']}")
                
            with st.expander("🗣️ 리뷰 및 평가 보기", expanded=False):
                st.info(row['Review'])
                
                # Review Form
                st.markdown("---")
                st.caption("✍️ 나도 평가하기")
                with st.form("add_review_form_list"):
                    new_rating = st.slider("내 평점", 0, 100, 80)
                    new_comment = st.text_area("내 의견 (한줄평)", height=60)
                    new_user = st.text_input("내 이름")
                    
                    if st.form_submit_button("평가 등록"):
                        if not new_comment or not new_user:
                            st.error("이름과 의견을 입력해주세요.")
                        else:
                            try:
                                # Reload fresh DF
                                fresh_df = load_data() 
                                target_row = fresh_df[fresh_df['Name'] == row['Name']].iloc[0]
                                
                                row_id = int(target_row['id'])
                                current_rating = target_row['Rating']
                                current_count = target_row['RatingCount'] if pd.notna(target_row['RatingCount']) else 1
                                current_review = target_row['Review']
                                current_recommender = target_row['Recommender']
                                
                                new_total_rating = (current_rating * current_count) + new_rating
                                new_count = current_count + 1
                                updated_rating = new_total_rating / new_count
                                
                                updated_review = f"{current_review}\n\n[{new_user}] {new_comment} (⭐{new_rating})"
                                updated_recommender = f"{current_recommender}, {new_user}" if pd.notna(current_recommender) else f"{new_user}"
                                
                                payload = {
                                    'rating': float(updated_rating),
                                    'rating_count': int(new_count),
                                    'review': updated_review,
                                    'recommender': updated_recommender
                                }
                                supabase.table('restaurants').update(payload).eq('id', row_id).execute()
                                
                                # Update Local State
                                row['Rating'] = updated_rating
                                row['RatingCount'] = new_count
                                row['Review'] = updated_review
                                row['Recommender'] = updated_recommender
                                st.session_state.selection_status['data'] = row
                                st.success("평가가 등록되었습니다!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"오류 발생: {e}")

    elif status and status.get('type') == 'new':
        # New Restaurant Registration View
        item = status['data']
        
        with st.container(border=True):
            d_col1, d_col2 = st.columns([9, 1])
            with d_col1:
                st.subheader(f"📍 {item['name']}")
                st.caption(item.get('address', '위치 정보 없음'))
            with d_col2:
                 if st.button("❌", key="close_new_dash_list"):
                     st.session_state.selection_status = None
                     st.session_state.selected_lat = None
                     st.session_state.selected_lon = None
                     st.session_state.selected_name = None
                     st.rerun()

            st.info("이 장소를 맛집으로 등록하시겠습니까?")
            
            with st.form("add_rest_form_list"):
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    name = st.text_input("식당 이름", value=item['name'])
                    cuisine = st.selectbox("카테고리", ["한식", "중식", "일식", "양식", "분식", "술집", "기타"], key="new_cuisine")
                with col_f2:
                    rating = st.slider("평점", 0, 100, 80, key="new_rating")
                
                best_menu = st.text_input("추천 메뉴", key="new_menu")
                review = st.text_area("한줄평", placeholder="오징어볶음이 정말 맛있어요!", key="new_review")
                recommender = st.text_input("추천인 이름", key="new_rec")
                
                if st.form_submit_button("맛집 등록하기"):
                    if not recommender or not review:
                        st.error("추천인과 한줄평은 필수입니다!")
                    else:
                        db_payload = {
                            'name': name,
                            'cuisine': cuisine,
                            'rating': rating,
                            'rating_count': 1,
                            'review': f"[{recommender}] {review} (⭐{rating})",
                            'location': item.get('address', ''),
                            'latitude': float(item['lat']),
                            'longitude': float(item['lng']),
                            'best_menu': best_menu,
                            'recommender': recommender
                        }
                        try:
                            resp = supabase.table('restaurants').insert(db_payload).execute()
                            if resp.data:
                                 st.success(f"{name} 등록 완료!")
                                 st.session_state.selection_status = None
                                 st.session_state.search_query = ""
                                 st.rerun()
                            else:
                                st.error("데이터 저장 실패")
                        except Exception as e:
                            st.error(f"저장 중 오류: {e}")

    # B. List View (Always Visible unless search active but map handles that too)
    # Similar to Sidebar List - Compact buttons
    if not filtered_df.empty:
        st.markdown(f"**📋 맛집 리스트 ({len(filtered_df)}곳)**")
        
        # Use simple iteration for buttons
        # If too many items, utilize pagination or scroll (Streamlit native scrolling is automatic inside container)
        
        # To mimic sidebar style clearly:
        list_container = st.container(height=300, border=False) # Fixed height with scroll
        
        with list_container:
            # Header (Simple text guide)
            st.caption("🏠식당명(10) | 종류(5) | 평점 | 메뉴")

            for i, (idx, row) in enumerate(filtered_df.iterrows()):
                # Prepare Actionable Button Label with Monospace Alignment
                # 1. Name (Truncate to 10 chars)
                name_val = row['Name']
                if len(name_val) > 8:
                    name_val = name_val[:7] + ".."
                
                # 2. Cuisine (Truncate to 4)
                cuisine_val = row['Cuisine'][:4]
                
                # 3. Menu (Truncate rest)
                menu_val = row['BestMenu'] if pd.notna(row['BestMenu']) else ""
                if len(menu_val) > 10:
                    menu_val = menu_val[:9] + ".."
                    
                # Format: Use fixed width padding
                # Name (10) | Cuisine (5) | Rating (5) | Spacing | Menu
                rating_val = f"{row['Rating']:.1f}"
                
                # Using simple spaces for alignment since we enforced monospace
                # Added extra spaces before menu_val
                label = f"{name_val:<10} {cuisine_val:<5} ⭐{rating_val:<4}    {menu_val}"
                
                is_selected = (status and status.get('data', {}).get('Name') == row['Name'])
                btn_type = "primary" if is_selected else "secondary"
                
                if st.button(label, key=f"list_btn_{idx}", type=btn_type, use_container_width=True):
                     st.session_state.selection_status = {'type': 'existing', 'data': row}
                     st.session_state.selected_lat = row['Latitude']
                     st.session_state.selected_lon = row['Longitude']
                     st.session_state.selected_name = row['Name']
                     st.rerun()
    else:
        st.info("조건에 맞는 맛집이 없습니다.")



# --- 3. Map Section ---
st.markdown("### 🗺️ 지도")

# Prepare Map Data
# Company Marker
company_marker = {
    "lat": DEFAULT_LAT,
    "lng": DEFAULT_LON,
    "name": "Xi S&D",
    "type": "company"
}

restaurant_markers = []
# If search query, show search markers (handled in JS logic mostly, but passed here)
# If NO search query, show filtered_df markers
if not st.session_state.search_query and not filtered_df.empty:
    for _, row in filtered_df.iterrows():
        if pd.notna(row['Latitude']) and pd.notna(row['Longitude']):
            is_winner = (row['Name'] == st.session_state.winner)
            marker_data = {
                "lat": row['Latitude'],
                "lng": row['Longitude'],
                "name": row['Name'],
                "cuisine": row['Cuisine'],
                "rating": row['Rating'],
                "bestMenu": row['BestMenu'],
                "price": row['Price'] if pd.notna(row['Price']) else "-",
                "isWinner": is_winner
            }
            restaurant_markers.append(marker_data)

# Selected Marker
selected_marker = None
if st.session_state.selected_lat:
    selected_marker = {
        "lat": st.session_state.selected_lat,
        "lng": st.session_state.selected_lon,
        "name": st.session_state.selected_name or "선택된 위치"
    }

# Center Logic
center_lat = st.session_state.selected_lat if st.session_state.selected_lat else (df['Latitude'].mean() if not df.empty else DEFAULT_LAT)
center_lon = st.session_state.selected_lon if st.session_state.selected_lon else (df['Longitude'].mean() if not df.empty else DEFAULT_LON)

# JavaScript Template
js_key = st.session_state.get('kakao_js_api_key', DEFAULT_JS_API_KEY) # Ensure key name matches global

kakao_map_html = f"""
<!-- Map Container -->
<meta http-equiv="Content-Security-Policy" content="upgrade-insecure-requests">
<div id="map" style="width:100%; height:420px; border:1px solid #ccc; touch-action: none;"></div>

<script>
    function initMap() {{
        if (typeof kakao === 'undefined') {{ return; }}

        kakao.maps.load(function() {{
            var container = document.getElementById('map');
            var options = {{
                center: new kakao.maps.LatLng({center_lat}, {center_lon}),
                level: 3
            }};

            var map = new kakao.maps.Map(container, options);
            
            // --- Markers Logic (Same as before) ---
            var company = {json.dumps(company_marker)};
            var restaurants = {json.dumps(restaurant_markers)};
            var selected = {json.dumps(selected_marker)};
            var searchResults = {json.dumps(search_markers)};
            var activeInfoWindow = null;

            // 1. Company
             var companyOverlay = new kakao.maps.CustomOverlay({{
                position: new kakao.maps.LatLng(company.lat, company.lng),
                content: '<div style="font-size:60px; text-shadow: 2px 2px 5px rgba(0,0,0,0.3); cursor: pointer;">🏢</div>',
                yAnchor: 0.3,
                zIndex: 9
            }});
            companyOverlay.setMap(map);

            // 2. Restaurants
            var standardBlue = "https://maps.google.com/mapfiles/ms/icons/blue-dot.png";
            restaurants.forEach(function(place) {{
                var marker = new kakao.maps.Marker({{
                    map: map,
                    position: new kakao.maps.LatLng(place.lat, place.lng),
                    title: place.name,
                    image: new kakao.maps.MarkerImage(standardBlue, new kakao.maps.Size(32, 32))
                }});
                
                var content = '<div style="padding:5px;width:150px;font-size:12px;"><b>' + place.name + '</b><br>⭐ ' + place.rating + '</div>';
                var iw = new kakao.maps.InfoWindow({{ content: content, removable: true }});
                
                kakao.maps.event.addListener(marker, 'click', function() {{
                    if (activeInfoWindow) activeInfoWindow.close();
                    iw.open(map, marker);
                    activeInfoWindow = iw;
                }});
            }});

            // 3. Search Results
            searchResults.forEach(function(place, i) {{
                var color = place.isRegistered ? 'blue' : 'red';
                var imageSrc = 'https://raw.githubusercontent.com/Concept211/Google-Maps-Markers/master/images/marker_' + color + (i+1) + '.png';
                var marker = new kakao.maps.Marker({{
                    map: map,
                    position: new kakao.maps.LatLng(place.lat, place.lng),
                    image: new kakao.maps.MarkerImage(imageSrc, new kakao.maps.Size(22, 40)),
                     zIndex: place.isRegistered ? 5 : 3
                }});
                
                var infoContent = '<div style="padding:5px;width:150px;font-size:12px;"><b>' + place.name + '</b><br>' + (place.isRegistered ? '✅ 등록됨' : '👉 미등록') + '</div>';
                var iw = new kakao.maps.InfoWindow({{ content: infoContent, removable: true }});
                 kakao.maps.event.addListener(marker, 'click', function() {{
                    if (activeInfoWindow) activeInfoWindow.close();
                    iw.open(map, marker);
                    activeInfoWindow = iw;
                }});
            }});
            
             // 4. Selected Marker 
            if (selected) {{
                var marker = new kakao.maps.Marker({{
                    map: map,
                    position: new kakao.maps.LatLng(selected.lat, selected.lng),
                    zIndex: 10
                }});
                 var infowindow = new kakao.maps.InfoWindow({{
                    content: '<div style="padding:5px;width:150px;font-size:13px;"><b>' + selected.name + '</b><br><span style="color:red;">📍 선택됨</span></div>'
                }});
                infowindow.open(map, marker);
            }}

            var zoomControl = new kakao.maps.ZoomControl();
            map.addControl(zoomControl, kakao.maps.ControlPosition.RIGHT);
        }});
    }}
</script>

<script type="text/javascript" 
        src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={js_key}&libraries=services&autoload=false"
        onload="initMap()"></script>
"""

# Render Map (Fixed Height for Mobile ~Reduced)
components.html(kakao_map_html, height=440)




# (Optional) Footer or Spacer if needed, otherwise empty.
