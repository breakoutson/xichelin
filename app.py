
import streamlit as st
import pandas as pd
import os
import streamlit.components.v1 as components
import json
import time
import requests
import math
import random

from dotenv import load_dotenv
load_dotenv()

# --- Utilities ---

def get_secret(key):
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key)

# Kakao API Key
DEFAULT_REST_API_KEY = get_secret("KAKAO_REST_API_KEY")
DEFAULT_JS_API_KEY = get_secret("KAKAO_JS_API_KEY")

if not DEFAULT_JS_API_KEY:
    st.error("⚠️ KAKAO_JS_API_KEY가 설정되지 않았습니다. .env 파일이나 Streamlit Secrets를 확인해주세요.")
    st.stop()

# Configuration
st.set_page_config(page_title="회사 점심 지도", page_icon="🍽️", layout="wide")

# CSS: Mobile Layout & Styling
st.markdown("""
    <style>
    /* Global: Center align standard buttons if desired, but left for lists */
    div.stButton > button {
        text-align: center;
    }
    
    /* Accordion Button Style (Categories) */
    /* We want these to look distinct? Optional. */
    
    /* Mobile Layout Adjustment */
    @media (max-width: 768px) {
        /* Force buttons to be full width for Accordion headers */
        div.stButton > button {
            width: 100% !important;
        }
        
        /* Map Container Height adjustment */
        div[id^="map_"] {
            height: 300px !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)

DATA_DIR = 'data'
DATA_FILE = os.path.join(DATA_DIR, 'restaurants.csv')
DEFAULT_LAT = 37.5617864
DEFAULT_LON = 126.9910438

def save_data(df_or_row, is_new=True):
    if not supabase:
        st.error("Supabase client not initialized.")
        return False
    try:
        if isinstance(df_or_row, pd.DataFrame):
            # This is a bit complex for bulk save, usually we save one by one in this app
            # But let's handle the single row insertion/update logic as requested
            st.error("Bulk save not implemented for Supabase.")
            return False
        
        # Mapping App keys to DB columns
        db_payload = {
            'name': df_or_row['Name'],
            'cuisine': df_or_row['Cuisine'],
            'rating': float(df_or_row['Rating']),
            'rating_count': int(df_or_row.get('RatingCount', 1)),
            'review': df_or_row['Review'],
            'latitude': float(df_or_row['Latitude']),
            'longitude': float(df_or_row['Longitude']),
            'best_menu': df_or_row['BestMenu'],
            'recommender': df_or_row['Recommender']
        }
        
        if is_new:
            supabase.table('restaurants').insert(db_payload).execute()
        else:
            supabase.table('restaurants').update(db_payload).eq('id', df_or_row['id']).execute()
            
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error saving to database: {e}")
        return False

# --- Data Loading ---
@st.cache_data(ttl=60)
def load_data():
    if not supabase:
        # Fallback to empty DF or local CSV if needed, but primary is Supabase
        if os.path.exists(DATA_FILE):
             df = pd.read_csv(DATA_FILE)
             if 'id' not in df.columns: df['id'] = range(1, len(df) + 1)
             return df
        return pd.DataFrame(columns=['id', 'Name', 'Cuisine', 'Rating', 'RatingCount', 'Review', 'Latitude', 'Longitude', 'BestMenu', 'Recommender'])
    
    try:
        response = supabase.table('restaurants').select("*").execute()
        data = response.data
        if not data:
            return pd.DataFrame(columns=['id', 'Name', 'Cuisine', 'Rating', 'RatingCount', 'Review', 'Latitude', 'Longitude', 'BestMenu', 'Recommender'])
        
        df = pd.DataFrame(data)
        # Rename DB columns to App columns
        rename_map = {
            'name': 'Name',
            'cuisine': 'Cuisine',
            'rating': 'Rating',
            'rating_count': 'RatingCount',
            'review': 'Review',
            'latitude': 'Latitude',
            'longitude': 'Longitude',
            'best_menu': 'BestMenu',
            'recommender': 'Recommender'
        }
        df = df.rename(columns=rename_map)
        return df
    except Exception as e:
        st.error(f"Error loading from database: {e}")
        return pd.DataFrame()

# Import Supabase
from supabase import create_client, Client

url = get_secret("SUPABASE_URL")
key = get_secret("SUPABASE_KEY")

supabase: Client = None
if url and key:
    try:
        supabase = create_client(url, key)
    except:
        pass

# --- Helper Functions ---

def search_kakao_place(keyword):
    if not DEFAULT_REST_API_KEY: return []
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {DEFAULT_REST_API_KEY}"}
    params = {"query": keyword, "x": DEFAULT_LON, "y": DEFAULT_LAT, "radius": 1000, "sort": "accuracy"}
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json().get('documents', [])
    except Exception:
        return []

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) * math.sin(dlat / 2) + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) * math.sin(dlon / 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c * 1000

def render_kakao_map(map_id, markers, center_lat, center_lon, selected_name=None, search_markers=None):
    if search_markers is None: search_markers = []
    
    # Kakao SDK is loaded once globally in the app, but kept here for backward compatibility if called separately.
    # However, to avoid conflicts, we'll try to ensure it loads efficiently.
    html = f"""
    <head>
        <meta http-equiv="Content-Security-Policy" content="upgrade-insecure-requests">
    </head>
    <div id="{map_id}" style="width:100%; height:350px; background-color:#f8f9fa; border-radius:12px; border:1px solid #ddd; display:flex; align-items:center; justify-content:center; position:relative;">
        <div id="{map_id}_loader" style="position:absolute; z-index:5; color:#666; font-size:14px;">지도를 로드 중...</div>
        <div id="{map_id}_canvas" style="position:absolute; top:0; left:0; width:100%; height:100%;"></div>
    </div>
    <script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={DEFAULT_JS_API_KEY}&libraries=services,clusterer,drawing&autoload=false"></script>
    <script>
        (function() {{
            var container = document.getElementById('{map_id}_canvas');
            var loader = document.getElementById('{map_id}_loader');
            var attempt = 0;
            
            function init() {{
                if (typeof kakao === 'undefined' || !kakao.maps) {{
                    if (attempt < 100) {{
                        attempt++;
                        setTimeout(init, 100);
                    }} else {{
                        loader.innerHTML = "⚠️ 지도 로드 실패 (로그 확인)";
                    }}
                    return;
                }}
                
                kakao.maps.load(function() {{
                    loader.style.display = 'none';
                    var level = parseInt(sessionStorage.getItem('map_zoom_{map_id}') || '2');
                    var options = {{
                        center: new kakao.maps.LatLng({center_lat}, {center_lon}),
                        level: level
                    }};
                    var map = new kakao.maps.Map(container, options);
                    
                    kakao.maps.event.addListener(map, 'zoom_changed', function() {{
                        sessionStorage.setItem('map_zoom_{map_id}', map.getLevel());
                    }});
                    
                    // Home Marker
                    new kakao.maps.CustomOverlay({{
                        position: new kakao.maps.LatLng({DEFAULT_LAT}, {DEFAULT_LON}),
                        content: '<div style="font-size:32px; filter:drop-shadow(0 2px 4px rgba(0,0,0,0.3));">🏢</div>',
                        map: map
                    }});
                    
                    var infowindow = new kakao.maps.InfoWindow({{ zIndex: 10 }});
                    var places = {json.dumps(markers)};
                    var selName = {json.dumps(selected_name) if selected_name else "null"};
                    
                    places.forEach(function(p) {{
                        var marker = new kakao.maps.Marker({{ map: map, position: new kakao.maps.LatLng(p.lat, p.lng) }});
                        kakao.maps.event.addListener(marker, 'click', function() {{
                            infowindow.setContent('<div style="padding:5px; font-size:13px;">' + p.name + '</div>');
                            infowindow.open(map, marker);
                        }});
                        if (selName && p.name === selName) {{
                            infowindow.setContent('<div style="padding:5px; font-size:13px;">' + p.name + '</div>');
                            infowindow.open(map, marker);
                            map.setCenter(new kakao.maps.LatLng(p.lat, p.lng));
                        }}
                    }});
                    
                    // External Results
                    var sMarkers = {json.dumps(search_markers)};
                    sMarkers.forEach(function(p) {{
                        var marker = new kakao.maps.Marker({{
                            map: map, 
                            position: new kakao.maps.LatLng(p.lat, p.lng),
                            image: new kakao.maps.MarkerImage('https://t1.daumcdn.net/localimg/localimages/07/mapapidoc/marker_red.png', new kakao.maps.Size(24, 35))
                        }});
                        
                        // Always show name above external marker
                        var customOverlay = new kakao.maps.CustomOverlay({{
                            position: new kakao.maps.LatLng(p.lat, p.lng),
                            content: '<div style="padding:2px 5px; background:#fff; border:1px solid #ff4b4b; border-radius:3px; font-size:11px; font-weight:bold; color:#ff4b4b; transform:translateY(-40px); white-space:nowrap; box-shadow:0 1px 2px rgba(0,0,0,0.2);">' + p.name + '</div>',
                            map: map
                        }});

                        kakao.maps.event.addListener(marker, 'click', function() {{
                            infowindow.setContent('<div style="padding:5px; font-size:13px;">' + p.name + ' <span style="color:red; font-size:11px;">(외부)</span></div>');
                            infowindow.open(map, marker);
                        }});
                    }});
                    
                    // Essential for mobile & iframe
                    setTimeout(function() {{
                        map.relayout();
                        if (!selName) map.setCenter(new kakao.maps.LatLng({DEFAULT_LAT}, {DEFAULT_LON}));
                    }}, 200);
                }});
            }}
            
            init();
        }})();
    </script>
    """
    components.html(html, height=370)

# --- State Init ---
if 'active_category' not in st.session_state: st.session_state.active_category = "전체" # Default to Open "All"
if 'sort_option' not in st.session_state: st.session_state.sort_option = 'Rating'
if 'search_query' not in st.session_state: st.session_state.search_query = ""
if 'selection_status' not in st.session_state: st.session_state.selection_status = None
if 'selected_lat' not in st.session_state: st.session_state.selected_lat = None
if 'selected_lon' not in st.session_state: st.session_state.selected_lon = None
if 'winner' not in st.session_state: st.session_state.winner = None

df = load_data()

# --- HEADER ---
col_h1, col_h2 = st.columns([2, 1])
with col_h1:
    st.markdown(f"<h1 style='margin:0; padding:0;'>자슐랭</h1>", unsafe_allow_html=True)
with col_h2:
    st.write("") # Adjust vertical space
    if st.button("🎲 랜덤 맛집 선택", use_container_width=True, type="primary"):
        if not df.empty:
            # 1. Clear Search State FIRST
            st.session_state.search_query = ""
            
            # 2. Roulette Animation (Enhanced Tension & Slow Finish)
            placeholder = st.empty()
            names = df['Name'].tolist()
            
            # Phase 1: Fast (First 10)
            for i in range(10):
                placeholder.markdown(f"<div style='text-align:center; font-size:24px; font-weight:bold; color:#ff4b4b; background:#fff2f2; padding:10px; border-radius:10px; border:2px solid #ff4b4b;'>🎲 {random.choice(names)}</div>", unsafe_allow_html=True)
                time.sleep(0.05)
            
            # Phase 2: Decelerating (Next 10)
            for i in range(10):
                delay = 0.05 + (i * 0.05) # 이 숫자를 키우면 점점 더 느려집니다.
                placeholder.markdown(f"<div style='text-align:center; font-size:24px; font-weight:bold; color:#ff4b4b; background:#fff2f2; padding:10px; border-radius:10px; border:2px solid #ff4b4b;'>🎲 {random.choice(names)}</div>", unsafe_allow_html=True)
                time.sleep(delay)
            
            # Phase 3: Final Tension (Final 3)
            for i in range(3):
                delay = 0.6 + (i * 0.1) # 0.4를 더 크게 하면 마지막이 아주 천천히 바뀝니다.
                placeholder.markdown(f"<div style='text-align:center; font-size:24px; font-weight:bold; color:#ff4b4b; background:#fff2f2; padding:10px; border-radius:10px; border:2px solid #ff4b4b;'>🕒 {random.choice(names)}...</div>", unsafe_allow_html=True)
                time.sleep(delay)
            
            # 3. Final Selection
            winner = df.sample(1).iloc[0]
            st.session_state.winner = winner['Name']
            st.session_state.active_category = winner['Cuisine']
            st.session_state.selection_status = {'type': 'existing', 'data': winner}
            st.session_state.selected_lat = winner['Latitude']
            st.session_state.selected_lon = winner['Longitude']
            st.balloons()
            st.rerun()
            
# Winner Display
if st.session_state.winner:
    st.success(f"🎉 오늘의 추천: **{st.session_state.winner}**")

# --- DATA PREPARATION ---
categories = ["전체", "한식", "중식", "일식", "양식", "분식", "술집", "기타"]

# 1. Category Selector (Horizontal Radio)
current_cat = st.radio("📂 카테고리 선택", categories, index=categories.index(st.session_state.active_category) if st.session_state.active_category in categories else 0, horizontal=True)
if current_cat != st.session_state.active_category:
    st.session_state.active_category = current_cat
    st.session_state.selection_status = None # Reset selection on category change
    st.rerun()

# 2. Global Search
search_input = st.text_input("🔍 통합 검색", value=st.session_state.search_query, placeholder="메뉴, 식당명 검색...")
if search_input != st.session_state.search_query:
    st.session_state.search_query = search_input
    if search_input:
        st.session_state.active_category = "전체" # Switch to show all if searching
    st.rerun()

# Filtering Logic
target_df = df.copy()
if st.session_state.search_query:
    target_df = target_df[
        target_df['Name'].str.contains(st.session_state.search_query) | 
        target_df['Cuisine'].str.contains(st.session_state.search_query) |
        target_df['BestMenu'].str.contains(st.session_state.search_query, na=False)
    ]
elif st.session_state.active_category != "전체":
    target_df = target_df[target_df['Cuisine'] == st.session_state.active_category]

# Sort Logic
if st.session_state.sort_option == 'Rating': 
    target_df = target_df.sort_values(by='Rating', ascending=False)
elif st.session_state.sort_option == 'Newest': 
    target_df = target_df.sort_values(by='id', ascending=False)
elif st.session_state.sort_option == 'Distance':
    def _calc(r):
        if pd.isna(r['Latitude']): return 99999
        return calculate_distance(DEFAULT_LAT, DEFAULT_LON, r['Latitude'], r['Longitude'])
    target_df['Distance'] = target_df.apply(_calc, axis=1)
    target_df = target_df.sort_values(by='Distance', ascending=True)

# Selection Detail View
s_status = st.session_state.selection_status
selected_name = None
if s_status:
    if s_status.get('type') == 'existing':
        d_row = s_status['data']
        selected_name = d_row['Name']
        with st.container(border=True):
            st.subheader(f"🍽️ {d_row['Name']}")
            st.caption(f"⭐ {d_row['Rating']:.1f} | {d_row['BestMenu']}")
            st.info(d_row['Review'])
            if st.button("닫기", key="close_detail"):
                st.session_state.selection_status = None
                st.rerun()
    elif s_status.get('type') == 'new':
        new_place = s_status['data']
        selected_name = new_place['place_name']
        with st.container(border=True):
            st.subheader(f"🆕 맛집 등록: {selected_name}")
            st.caption(f"📍 {new_place['address_name']}")
            with st.form("reg_form"):
                col1, col2 = st.columns(2)
                with col1:
                    new_cuisine = st.selectbox("카테고리", ["한식", "중식", "일식", "양식", "분식", "술집", "기타"], index=(["한식", "중식", "일식", "양식", "분식", "술집", "기타"].index(st.session_state.active_category) if st.session_state.active_category in ["한식", "중식", "일식", "양식", "분식", "술집", "기타"] else 0))
                    new_rating = st.slider("평점", 0.0, 5.0, 4.0, 0.5)
                with col2:
                    new_menu = st.text_input("대표 메뉴", placeholder="추천 메뉴")
                    new_recommender = st.text_input("추천인", value="익명")
                new_review = st.text_area("한줄평", placeholder="맛이나 분위기...")
                if st.form_submit_button("등록", type="primary", use_container_width=True):
                    if not new_menu: st.warning("대표 메뉴를 적어주세요!")
                    else:
                        f_review = new_review if new_review.strip() else "리뷰가 없습니다."
                        if save_data({'Name': selected_name, 'Cuisine': new_cuisine, 'Rating': new_rating, 'RatingCount': 1, 'Review': f_review, 'Latitude': float(new_place['y']), 'Longitude': float(new_place['x']), 'BestMenu': new_menu, 'Recommender': new_recommender}, is_new=True):
                            st.success("등록 완료!"); time.sleep(1); st.session_state.selection_status = None; st.rerun()
            if st.button("취소"): st.session_state.selection_status = None; st.rerun()

# --- DATA PREP FOR MAP & EXTERNAL ---
map_markers = []
for _, row in target_df.iterrows():
    if pd.notna(row['Latitude']):
        map_markers.append({"lat": row['Latitude'], "lng": row['Longitude'], "name": row['Name'], "rating": row['Rating']})
if selected_name and s_status and s_status.get('type') == 'existing':
    map_markers = [m for m in map_markers if m['name'] == selected_name]

kakao_res = []
if st.session_state.search_query:
    try: kakao_res = search_kakao_place(st.session_state.search_query)
    except: pass
search_markers = []
registered_names = set(df['Name'].tolist())
external_new = []
for p in kakao_res:
    search_markers.append({"lat": float(p['y']), "lng": float(p['x']), "name": p['place_name']})
    if p['place_name'] not in registered_names: external_new.append(p)

# --- RECENT SEARCH LIST (If searching) ---
if st.session_state.search_query and external_new:
    st.caption(f"➕ 미등록 장소 바로 등록하기")
    # Remove fixed height for full page scroll
    for i, p in enumerate(external_new):
        n = p['place_name']
        if len(n) > 15: n = n[:14] + ".."
        addr = p['address_name']
        if len(addr) > 20: addr = addr[:19] + ".."
        if st.button(f"➕ {n} | {addr}", key=f"new_btn_{i}", use_container_width=True):
            st.session_state.selection_status = {'type': 'new', 'data': p}
            st.rerun()

# --- LIST VIEW (Moved up for Mobile) ---
st.caption(f"📋 맛집 리스트 ({len(target_df)}곳)")
with st.expander("🌪️ 정렬 옵션", expanded=False):
    c1, c2, c3 = st.columns(3)
    if c1.button("⭐ 평점순", use_container_width=True, type="primary" if st.session_state.sort_option=='Rating' else "secondary"): st.session_state.sort_option='Rating'; st.rerun()
    if c2.button("📏 거리순", use_container_width=True, type="primary" if st.session_state.sort_option=='Distance' else "secondary"): st.session_state.sort_option='Distance'; st.rerun()
    if c3.button("🆕 최신순", use_container_width=True, type="primary" if st.session_state.sort_option=='Newest' else "secondary"): st.session_state.sort_option='Newest'; st.rerun()

# Remove fixed height for full page scroll
for _, row in target_df.iterrows():
    n = row['Name']; c = row['Cuisine'][:2]; r = f"{row['Rating']:.1f}"
    m = row['BestMenu'] if pd.notna(row['BestMenu']) else ""
    
    # Compact Version for Mobile (Prevent Line Breaks)
    if len(n) > 8: n = n[:7] + ".."
    if len(m) > 10: m = m[:9] + ".."
    
    label = f"{n} | {c} | ⭐{r}"
    if m: label += f" | {m}"
    
    is_sel = (selected_name == row['Name'])
    if st.button(label, key=f"list_{row['id']}", type="primary" if is_sel else "secondary", use_container_width=True):
        st.session_state.selection_status = {'type': 'existing', 'data': row}
        st.rerun()

if target_df.empty and not external_new:
    st.info("해당 조건의 맛집이 없습니다.")
    if st.session_state.search_query:
        if st.button("검색 초기화"): st.session_state.search_query=""; st.rerun()

# --- MAP VIEW (Moved down) ---
render_kakao_map("main_map", map_markers, DEFAULT_LAT, DEFAULT_LON, selected_name, search_markers)



