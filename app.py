
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
    
    # Final fix for Mixed Content & Mobile rendering
    html = f"""
    <head>
        <meta http-equiv="Content-Security-Policy" content="upgrade-insecure-requests">
    </head>
    <div id="{map_id}" style="width:100%; height:350px; background-color:#f8f9fa; border-radius:12px; border:1px solid #ddd; display:flex; align-items:center; justify-content:center; position:relative;">
        <div id="{map_id}_loader" style="position:absolute; z-index:5; color:#666; font-size:14px;">지도를 로드 중...</div>
        <div id="{map_id}_canvas" style="position:absolute; top:0; left:0; width:100%; height:100%;"></div>
    </div>
    <script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={DEFAULT_JS_API_KEY}&libraries=services&autoload=false"></script>
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
                    var level = parseInt(sessionStorage.getItem('map_zoom_{map_id}') || '5');
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
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.title("자이에스앤디 점심 🍽️")
with col_h2:
    if st.button("🎲 랜덤"):
        if not df.empty:
            # Roulette Animation
            placeholder = st.empty()
            names = df['Name'].tolist()
            delay = 0.05
            for i in range(15):
                placeholder.markdown(f"<div style='text-align:center; font-size:18px; font-weight:bold; color:#666;'>🎲 {random.choice(names)}</div>", unsafe_allow_html=True)
                if i > 8: delay += 0.03
                time.sleep(delay)
            
            winner = df.sample(1).iloc[0]
            st.session_state.winner = winner['Name']
            st.session_state.active_category = winner['Cuisine'] # Open that category
            st.session_state.selection_status = {'type': 'existing', 'data': winner}
            st.session_state.selected_lat = winner['Latitude']
            st.session_state.selected_lon = winner['Longitude']
            st.balloons()
            st.rerun()

# Winner Display
if st.session_state.winner:
    st.success(f"🎉 오늘의 추천: **{st.session_state.winner}**")

# --- MAIN: Accordion Logic ---

# 1. Global Search (Always visible at top)
search_input = st.text_input("🔍 통합 검색", value=st.session_state.search_query, placeholder="메뉴, 식당명 검색...")
if search_input != st.session_state.search_query:
    st.session_state.search_query = search_input
    st.session_state.active_category = "SEARCH_RESULTS" # Open special section
    st.rerun()

# Categories List
categories = ["전체", "한식", "중식", "일식", "양식", "분식", "술집", "기타"]

# If Search is active, render the Search Results "Accordion" first/only?
# User wants "Accordion Style".
# Let's render the list of Category Buttons.
# If Search is active, we can show a special "Search Results" button at top that is open.

if st.session_state.search_query:
    # --- SEARCH RESULTS SECTION ---
    if st.button(f"🔍 '{st.session_state.search_query}' 검색 결과 (클릭하여 닫기)", type="primary", use_container_width=True):
        st.session_state.search_query = ""
        st.session_state.active_category = "전체"
        st.rerun()
    
    # Filter content
    target_df = df[
        df['Name'].str.contains(st.session_state.search_query) | 
        df['Cuisine'].str.contains(st.session_state.search_query) |
        df['BestMenu'].str.contains(st.session_state.search_query, na=False)
    ]
    
    # 1. Sort Controls (Hidden in Expander)
    with st.expander("🌪️ 정렬 & 필터", expanded=False):
        s_col1, s_col2, s_col3 = st.columns(3)
        current_sort = st.session_state.sort_option
        if s_col1.button("⭐ 평점순", key="sort_rate_search", type="primary" if current_sort=='Rating' else "secondary", use_container_width=True):
            st.session_state.sort_option = 'Rating'; st.rerun()
        if s_col2.button("📏 거리순", key="sort_dist_search", type="primary" if current_sort=='Distance' else "secondary", use_container_width=True):
            st.session_state.sort_option = 'Distance'; st.rerun()
        if s_col3.button("🆕 최신순", key="sort_new_search", type="primary" if current_sort=='Newest' else "secondary", use_container_width=True):
            st.session_state.sort_option = 'Newest'; st.rerun()

    # Sort Logic
    if st.session_state.sort_option == 'Rating': target_df = target_df.sort_values(by='Rating', ascending=False)
    elif st.session_state.sort_option == 'Newest': target_df = target_df.sort_values(by='id', ascending=False)
    elif st.session_state.sort_option == 'Distance':
         def _calc(r):
             if pd.isna(r['Latitude']): return 99999
             return calculate_distance(DEFAULT_LAT, DEFAULT_LON, r['Latitude'], r['Longitude'])
         target_df['Distance'] = target_df.apply(_calc, axis=1)
         target_df = target_df.sort_values(by='Distance', ascending=True)

    # 2. Detail View (Search)
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
                if st.button("닫기", key="close_search_detail"):
                    st.session_state.selection_status = None
                    st.rerun()
        
        elif s_status.get('type') == 'new':
            new_place = s_status['data']
            selected_name = new_place['place_name']
            with st.container(border=True):
                st.subheader(f"🆕 맛집 등록: {selected_name}")
                st.caption(f"📍 {new_place['address_name']}")
                
                with st.form("registration_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        new_cuisine = st.selectbox("카테고리", ["한식", "중식", "일식", "양식", "분식", "술집", "기타"])
                        new_rating = st.slider("평점", 0.0, 5.0, 4.0, 0.5)
                    with col2:
                        new_menu = st.text_input("대표 메뉴", placeholder="추천 메뉴를 적어주세요")
                        new_recommender = st.text_input("추천인", value="익명")
                    
                    new_review = st.text_area("한줄평 / 리뷰", placeholder="맛이나 분위기 등을 공유해주세요")
                    
                    submitted = st.form_submit_button("등록하기", type="primary", use_container_width=True)
                    if submitted:
                        if not new_menu or not new_review:
                            st.warning("대표 메뉴와 리뷰를 작성해주세요!")
                        else:
                            new_row = {
                                'Name': selected_name,
                                'Cuisine': new_cuisine,
                                'Rating': new_rating,
                                'RatingCount': 1,
                                'Review': new_review,
                                'Latitude': float(new_place['y']),
                                'Longitude': float(new_place['x']),
                                'BestMenu': new_menu,
                                'Recommender': new_recommender
                            }
                            if save_data(new_row, is_new=True):
                                st.success(f"✅ '{selected_name}' 등록 완료!")
                                time.sleep(1)
                                st.session_state.selection_status = None
                                st.rerun()
                
                if st.button("취소", key="cancel_reg"):
                    st.session_state.selection_status = None
                    st.rerun()

    # 3. Map (Below Info)
    # Internal Markers
    map_markers = []
    for _, row in target_df.iterrows():
        if pd.notna(row['Latitude']):
            map_markers.append({"lat": row['Latitude'], "lng": row['Longitude'], "name": row['Name'], "rating": row['Rating']})
    
    if selected_name:
        map_markers = [m for m in map_markers if m['name'] == selected_name]
    
    # External Markers
    try:
        kakao_res = search_kakao_place(st.session_state.search_query)
        if selected_name: # Filter external too if selected
            kakao_res = [p for p in kakao_res if p['place_name'] == selected_name]
    except:
        kakao_res = []
        
    search_markers = []
    for p in kakao_res:
         search_markers.append({"lat": float(p['y']), "lng": float(p['x']), "name": p['place_name']})
    
    c_lat = DEFAULT_LAT
    c_lon = DEFAULT_LON
    
    render_kakao_map("map_search", map_markers, DEFAULT_LAT, DEFAULT_LON, selected_name, search_markers)

    # 4. List View
    # Split Kakao results into 'Already Registered' and 'New'
    registered_names = set(df['Name'].tolist())
    external_new = [p for p in kakao_res if p['place_name'] not in registered_names]
    
    if not target_df.empty:
        st.caption(f"📋 등록된 맛집 ({len(target_df)}곳)")
        with st.container(height=200):
            for _, row in target_df.iterrows():
                n = row['Name']; c = row['Cuisine'][:4]; r = f"{row['Rating']:.1f}"
                m = row['BestMenu'] if pd.notna(row['BestMenu']) else ""
                label = f"{n} | {c} | ⭐{r} | {m}"
                is_sel = (s_status and s_status.get('type') == 'existing' and s_status['data']['Name'] == n)
                if st.button(label, key=f"btn_search_{row['id']}", type="primary" if is_sel else "secondary", use_container_width=True):
                    st.session_state.selection_status = {'type': 'existing', 'data': row}
                    st.session_state.selected_lat = row['Latitude']
                    st.session_state.selected_lon = row['Longitude']
                    st.rerun()

    if external_new:
        st.caption(f"🌐 외부 검색 결과 (신규 등록 가능: {len(external_new)}곳)")
        with st.container(height=200):
            for i, p in enumerate(external_new):
                n = p['place_name']
                addr = p['address_name']
                dist = p.get('distance', '')
                dist_str = f"{dist}m" if dist else ""
                label = f"➕ {n} | {addr} ({dist_str})"
                is_sel = (s_status and s_status.get('type') == 'new' and s_status['data']['place_name'] == n)
                if st.button(label, key=f"btn_external_{i}", type="primary" if is_sel else "secondary", use_container_width=True):
                    st.session_state.selection_status = {'type': 'new', 'data': p}
                    st.session_state.selected_lat = float(p['y'])
                    st.session_state.selected_lon = float(p['x'])
                    st.rerun()
    
    if target_df.empty and not external_new:
        st.info("검색 결과가 없습니다.")
        
    st.markdown("---")

else:
    # --- CATEGORY TABS (Scrollable Layout) ---
    st.markdown("### 📂 카테고리")
    tabs = st.tabs(categories)
    
    for cat, tab in zip(categories, tabs):
        with tab:
            # 1. Filter Data
            target_df = df.copy()
            if cat != "전체":
                target_df = target_df[target_df['Cuisine'] == cat]
            
            # 2. Sort Controls (Hidden in Expander)
            with st.expander("🌪️ 정렬 & 필터", expanded=False):
                s_col1, s_col2, s_col3 = st.columns(3)
                current_sort = st.session_state.sort_option
                if s_col1.button("⭐ 평점순", key=f"sort_rate_{cat}", type="primary" if current_sort=='Rating' else "secondary", use_container_width=True):
                    st.session_state.sort_option = 'Rating'; st.rerun()
                if s_col2.button("📏 거리순", key=f"sort_dist_{cat}", type="primary" if current_sort=='Distance' else "secondary", use_container_width=True):
                    st.session_state.sort_option = 'Distance'; st.rerun()
                if s_col3.button("🆕 최신순", key=f"sort_new_{cat}", type="primary" if current_sort=='Newest' else "secondary", use_container_width=True):
                    st.session_state.sort_option = 'Newest'; st.rerun()
            
            # Apply Sort
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

            # 3. Selected Item Info Card (Displayed ABOVE Map)
            status = st.session_state.selection_status
            selected_name = None
            if status and status.get('type')=='existing':
                 d_row = status['data']
                 # Check if item belongs to current view (optional, but good for context)
                 # For "All" show everything. For "Korean" show only Korean.
                 if cat == "전체" or d_row['Cuisine'] == cat:
                     selected_name = d_row['Name']
                     with st.container(border=True):
                         st.subheader(f"🍽️ {d_row['Name']}")
                         st.caption(f"⭐ {d_row['Rating']:.1f} | {d_row['BestMenu']}")
                         st.info(d_row['Review'])
                         if st.button("닫기", key=f"close_{cat}"):
                             st.session_state.selection_status = None
                             st.rerun()

            # 4. Map View
            map_markers = []
            for _, row in target_df.iterrows():
                 if pd.notna(row['Latitude']): 
                     map_markers.append({"lat": row['Latitude'], "lng": row['Longitude'], "name": row['Name']})
            
            if selected_name:
                map_markers = [m for m in map_markers if m['name'] == selected_name]
            
            # Map HTML
            map_id = f"map_tab_{cat.replace(' ', '_')}"
            render_kakao_map(map_id, map_markers, DEFAULT_LAT, DEFAULT_LON, selected_name)

            # 5. List View (Below Map)
            if not target_df.empty:
                 st.caption(f"📋 {cat} 맛집 ({len(target_df)}곳)")
                 with st.container(height=300):
                     for _, row in target_df.iterrows():
                         n = row['Name']; c = row['Cuisine'][:4]; r = f"{row['Rating']:.1f}"
                         m = row['BestMenu'] if pd.notna(row['BestMenu']) else ""
                         if len(m)>10: m = m[:9]+".."
                         if len(n)>8: n = n[:7]+".."
                         label = f"{n} | {c} | ⭐{r} | {m}"
                         
                         is_sel = (selected_name == row['Name'])
                         if st.button(label, key=f"btn_{cat}_{row['id']}", type="primary" if is_sel else "secondary", use_container_width=True):
                             st.session_state.selection_status = {'type':'existing', 'data':row}
                             st.session_state.selected_lat = row['Latitude']
                             st.session_state.selected_lon = row['Longitude']
                             st.rerun()
            else:
                 st.info("등록된 맛집이 없습니다.")

# Check logic for Search Results View (Duplicated layout or helper?)
# To save space, I handled search separately above, but I should probably render the same dashboard structure.
# I will leave the Search View simple (List + Local Map) for now. Use the same patterns.
if st.session_state.search_query:
    st.write("---")
    # Search Dashboard Logic (Simplified)
    # ... (Reuse logic logic if possible, but hard without helper)
    # I will rely on the "Search" accordion button approach I drafted above?
    # Actually, the code above `if st.session_state.search_query:` replaces the loop.
    # So if searching, you see one big "Search Results" block. 
    # That works.
    pass

