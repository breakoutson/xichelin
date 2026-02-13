
import streamlit as st
import pandas as pd
import os
import streamlit.components.v1 as components
import json
import time
import requests
import math
import random

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
        #map {
            height: 350px !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)

DATA_DIR = 'data'
DATA_FILE = os.path.join(DATA_DIR, 'restaurants.csv')
DEFAULT_LAT = 37.5617864
DEFAULT_LON = 126.9910438

# --- Data Loading ---
@st.cache_data(ttl=60)
def load_data():
    if not os.path.exists(DATA_FILE):
        return pd.DataFrame(columns=['id', 'Name', 'Cuisine', 'Rating', 'RatingCount', 'Review', 'Latitude', 'Longitude', 'BestMenu', 'Recommender'])
    try:
        df = pd.read_csv(DATA_FILE)
        # Ensure numeric types
        df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce').fillna(0)
        df['Latitude'] = pd.to_numeric(df['Latitude'], errors='coerce')
        df['Longitude'] = pd.to_numeric(df['Longitude'], errors='coerce')
        if 'id' not in df.columns:
            df['id'] = range(1, len(df) + 1)
        return df
    except Exception as e:
        st.error(f"Error loading data: {e}")
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

# --- State Init ---
if 'active_category' not in st.session_state: st.session_state.active_category = None
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
        st.session_state.active_category = None
        st.rerun()
    
    # Filter content
    filtered = df[
        df['Name'].str.contains(st.session_state.search_query) | 
        df['Cuisine'].str.contains(st.session_state.search_query) |
        df['BestMenu'].str.contains(st.session_state.search_query, na=False)
    ]
    # 1. Sort Controls (Inside Search)
    s_col1, s_col2, s_col3 = st.columns(3)
    current_sort = st.session_state.sort_option
    
    if s_col1.button("⭐ 평점순", key="sort_rate_search", type="primary" if current_sort=='Rating' else "secondary", use_container_width=True):
        st.session_state.sort_option = 'Rating'
        st.rerun()
    if s_col2.button("📏 거리순", key="sort_dist_search", type="primary" if current_sort=='Distance' else "secondary", use_container_width=True):
        st.session_state.sort_option = 'Distance'
        st.rerun()
    if s_col3.button("🆕 최신순", key="sort_new_search", type="primary" if current_sort=='Newest' else "secondary", use_container_width=True):
        st.session_state.sort_option = 'Newest'
        st.rerun()

    # Sort Logic
    target_df = filtered.copy()
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

    # 2. List View
    if not target_df.empty:
        st.caption(f"📋 검색 결과 ({len(target_df)}곳)")
        with st.container(height=300):
            for _, row in target_df.iterrows():
                n = row['Name']
                if len(n)>8: n = n[:7]+".."
                c = row['Cuisine'][:4]
                r = f"{row['Rating']:.1f}"
                m = row['BestMenu'] if pd.notna(row['BestMenu']) else ""
                
                label = f"{n} | {c} | ⭐{r} | {m}"
                
                # Selection Hook
                is_sel = (st.session_state.selection_status and st.session_state.selection_status.get('data', {}).get('Name') == row['Name'])
                
                if st.button(label, key=f"btn_search_{row['id']}", type="primary" if is_sel else "secondary", use_container_width=True):
                    st.session_state.selection_status = {'type': 'existing', 'data': row}
                    st.session_state.selected_lat = row['Latitude']
                    st.session_state.selected_lon = row['Longitude']
                    st.rerun()
    else:
        st.info("검색 결과가 없습니다.")
        
    # 3. Map (Below List)
    map_markers = []
    for _, row in target_df.iterrows():
        if pd.notna(row['Latitude']):
            map_markers.append({"lat": row['Latitude'], "lng": row['Longitude'], "name": row['Name'], "rating": row['Rating']})
    
    # Add Kakao Search Results (Red Markers) if any?
    try:
        kakao_res = search_kakao_place(st.session_state.search_query)
    except:
        kakao_res = []
        
    search_markers = []
    for p in kakao_res:
         search_markers.append({"lat": float(p['y']), "lng": float(p['x']), "name": p['place_name']})
    
    c_lat = st.session_state.selected_lat or DEFAULT_LAT
    c_lon = st.session_state.selected_lon or DEFAULT_LON
    
    map_id = "map_search"
    html = f"""
    <div id="{map_id}" style="width:100%; height:350px;"></div>
    <script>
        if (typeof kakao !== 'undefined') {{
            kakao.maps.load(function() {{
                var container = document.getElementById('{map_id}');
                var options = {{ center: new kakao.maps.LatLng({c_lat}, {c_lon}), level: 5 }};
                var map = new kakao.maps.Map(container, options);
                
                new kakao.maps.CustomOverlay({{
                    position: new kakao.maps.LatLng({DEFAULT_LAT}, {DEFAULT_LON}),
                    content: '<div style="font-size:30px;">🏢</div>',
                    map: map
                }});
                
                var places = {json.dumps(map_markers)};
                places.forEach(function(p) {{
                    var m = new kakao.maps.Marker({{ map: map, position: new kakao.maps.LatLng(p.lat, p.lng), title: p.name }});
                    var iw = new kakao.maps.InfoWindow({{ content: '<div style="padding:5px;">' + p.name + '</div>' }});
                    kakao.maps.event.addListener(m, 'click', function() {{ iw.open(map, m); }});
                }});
                
                var searchM = {json.dumps(search_markers)};
                searchM.forEach(function(p) {{
                     var img = 'https://t1.daumcdn.net/localimg/localimages/07/mapapidoc/marker_red.png';
                     var m = new kakao.maps.Marker({{ map: map, position: new kakao.maps.LatLng(p.lat, p.lng), image: new kakao.maps.MarkerImage(img, new kakao.maps.Size(24, 35)) }});
                     var iw = new kakao.maps.InfoWindow({{ content: '<div style="padding:5px; color:red;">' + p.name + ' (외부검색)</div>' }});
                     kakao.maps.event.addListener(m, 'click', function() {{ iw.open(map, m); }});
                }});
            }});
        }}
    </script>
    <script src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={DEFAULT_JS_API_KEY}&libraries=services&autoload=false"></script>
    """
    components.html(html, height=370)
    
else:
    # --- CATEGORY BUTTONS ---
    for cat in categories:
        # Determine if this category is open
        is_open = (st.session_state.active_category == cat)
        icon = "📂" if is_open else "📁"
        btn_type = "primary" if is_open else "secondary"
        
        # Accordion Header Button
        if st.button(f"{icon} {cat}", key=f"cat_btn_{cat}", type=btn_type, use_container_width=True):
            if is_open:
                st.session_state.active_category = None # Toggle Close
            else:
                st.session_state.active_category = cat # Toggle Open
            st.rerun()
            
        # Accordion Content (List + Map)
        if is_open:
            # 1. Sort Controls (Inside Accordion)
            s_col1, s_col2, s_col3 = st.columns(3)
            current_sort = st.session_state.sort_option
            
            if s_col1.button("⭐ 평점순", key=f"sort_rate_{cat}", type="primary" if current_sort=='Rating' else "secondary", use_container_width=True):
                st.session_state.sort_option = 'Rating'
                st.rerun()
            if s_col2.button("📏 거리순", key=f"sort_dist_{cat}", type="primary" if current_sort=='Distance' else "secondary", use_container_width=True):
                st.session_state.sort_option = 'Distance'
                st.rerun()
            if s_col3.button("🆕 최신순", key=f"sort_new_{cat}", type="primary" if current_sort=='Newest' else "secondary", use_container_width=True):
                st.session_state.sort_option = 'Newest'
                st.rerun()

            # 2. Filter Data
            target_df = df.copy()
            if cat != "전체":
                target_df = target_df[target_df['Cuisine'] == cat]
                
            # Sort
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

            # 3. Selected Item Detail (If any)
            status = st.session_state.selection_status
            if status and status.get('type')=='existing' and status['data']['Cuisine'] == cat: # Only show if matches cat? Or global?
                # Actually if user selected something in "Korean" then switched to "Chinese", selection might persist?
                # User request: "Click other button -> Previous content disappears".
                # So Detail view should probably close if category changes?
                # I will handle detail view rendering here.
                d_row = status['data']
                with st.container(border=True):
                    st.subheader(f"🍽️ {d_row['Name']}")
                    st.caption(f"⭐ {d_row['Rating']:.1f} | {d_row['BestMenu']}")
                    if st.button("닫기", key=f"close_{cat}"):
                        st.session_state.selection_status = None
                        st.rerun()
                    st.info(d_row['Review'])

            # 4. List View (Compact Monospace)
            if not target_df.empty:
                st.caption(f"📋 {cat} 리스트 ({len(target_df)}곳)")
                with st.container(height=300): # Scrollable
                    for _, row in target_df.iterrows():
                        n = row['Name']
                        if len(n)>8: n = n[:7]+".."
                        c = row['Cuisine'][:4]
                        r = f"{row['Rating']:.1f}"
                        m = row['BestMenu'] if pd.notna(row['BestMenu']) else ""
                        
                        label = f"{n} | {c} | ⭐{r} | {m}"
                        
                        # Selection Hook
                        is_sel = (status and status.get('data', {}).get('Name') == row['Name'])
                        
                        if st.button(label, key=f"btn_{cat}_{row['id']}", type="primary" if is_sel else "secondary", use_container_width=True):
                            st.session_state.selection_status = {'type': 'existing', 'data': row}
                            st.session_state.selected_lat = row['Latitude']
                            st.session_state.selected_lon = row['Longitude']
                            st.rerun()
            else:
                st.info("데이터가 없습니다.")

            # 5. Map (Below List)
            # Prepare Markers
            map_markers = []
            for _, row in target_df.iterrows():
                if pd.notna(row['Latitude']):
                    map_markers.append({"lat": row['Latitude'], "lng": row['Longitude'], "name": row['Name'], "rating": row['Rating']})
            
            c_lat = st.session_state.selected_lat or DEFAULT_LAT
            c_lon = st.session_state.selected_lon or DEFAULT_LON
            
            # Map HTML
            map_id = f"map_{cat}"
            html = f"""
            <div id="{map_id}" style="width:100%; height:350px;"></div>
            <script>
                if (typeof kakao !== 'undefined') {{
                    kakao.maps.load(function() {{
                        var container = document.getElementById('{map_id}');
                        var options = {{ center: new kakao.maps.LatLng({c_lat}, {c_lon}), level: 5 }};
                        var map = new kakao.maps.Map(container, options);
                        
                        // Company
                        new kakao.maps.CustomOverlay({{
                            position: new kakao.maps.LatLng({DEFAULT_LAT}, {DEFAULT_LON}),
                            content: '<div style="font-size:30px;">🏢</div>',
                            map: map
                        }});
                        
                        // Places
                        var places = {json.dumps(map_markers)};
                        places.forEach(function(p) {{
                            var m = new kakao.maps.Marker({{ map: map, position: new kakao.maps.LatLng(p.lat, p.lng), title: p.name }});
                            var iw = new kakao.maps.InfoWindow({{ content: '<div style="padding:5px;">' + p.name + '</div>' }});
                            kakao.maps.event.addListener(m, 'click', function() {{ iw.open(map, m); }});
                        }});
                    }});
                }}
            </script>
            <script src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={DEFAULT_JS_API_KEY}&libraries=services&autoload=false"></script>
            """
            components.html(html, height=370)

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

