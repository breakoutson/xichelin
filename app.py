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
    if key in st.secrets:
        return st.secrets[key]
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
# If selection exists, center map there. Otherwise avg or default.
if st.session_state.selected_lat:
    avg_lat = st.session_state.selected_lat
    avg_lon = st.session_state.selected_lon
elif not df.empty and pd.notna(df['Latitude'].mean()):
    avg_lat = df['Latitude'].mean()
    avg_lon = df['Longitude'].mean()
else:
    avg_lat, avg_lon = DEFAULT_LAT, DEFAULT_LON

# --- Layout with Tabs ---
tab1, tab2 = st.tabs(["🗺️ 지도 보기", "📋 맛집 리스트"])

# --- Tab 1: Map Logic (Kakao JS API) ---
with tab1:
    # st.header("🍱 맛집 지도 (Kakao Map)") <-- Removed
    
    # 1. Category Filter UI
    categories = ["전체", "한식", "중식", "일식", "양식", "분식", "술집", "기타"]
    # st.write("🔽 **카테고리 필터**") <-- Removed
    cat_cols = st.columns(len(categories))
    for i, cat in enumerate(categories):
        # Determine button type (primary if selected)
        btn_type = "primary" if st.session_state.selected_category == cat else "secondary"
        if cat_cols[i].button(cat, key=f"cat_{i}", type=btn_type, use_container_width=True):
            st.session_state.selected_category = cat
            st.rerun()

    # 2. Search & Select Logic
    # st.write("---") <-- Removed
    search_col1, search_col2 = st.columns([3, 1])
    
    # Refresh Button Logic (must be checked BEFORE text_input to update state)
    with search_col2:
         if st.button("🔄 초기화", use_container_width=True):
             st.session_state.search_query = ""
             st.session_state.selection_status = None
             st.session_state.selected_lat = None
             st.session_state.selected_lon = None
             st.session_state.selected_name = None
             st.session_state.winner = None # Reset random winner
             st.session_state.selected_category = "전체" # Reset category
             st.rerun()

    def reset_selection():
        st.session_state.selection_status = None
        st.session_state.selected_lat = None
        st.session_state.selected_lon = None
        st.session_state.selected_name = None
        st.session_state.winner = None
        st.session_state.selected_category = "전체"

    with search_col1:
        # Placeholder updated, bind to session state
        st.text_input("장소 검색", label_visibility="collapsed", placeholder="장소명을 검색하세요 (예: 닭갈비)", key="search_query", on_change=reset_selection)
    
    search_markers = [] # For map

    if st.session_state.search_query:
        places = search_kakao_place(st.session_state.search_query)
        if places:
             # Just show count, no instruction to use dropdown
            st.caption(f"🔍 **{len(places)}**개의 장소가 검색되었습니다. (좌측 사이드바 목록 확인)")
            
            # Prepare markers for all search results
            for p in places:
                # Check if already registered (by name)
                is_registered = False
                if not df.empty:
                    if p['place_name'] in df['Name'].values:
                         is_registered = True
                
                search_markers.append({
                    "lat": float(p['y']),
                    "lng": float(p['x']),
                    "name": p['place_name'],
                    "isRegistered": is_registered,
                    "address": p['address_name'] # Add address for info window
                })
            
            
    # Removed auto-reset logic here to allow Random/Category selections without search query

    # 3. Prepare Data for JS (Filtered)
    # Company Marker
    company_marker = {
        "lat": DEFAULT_LAT,
        "lng": DEFAULT_LON,
        "name": "Xi S&D",
        "type": "company"
    }
    
    # Filter DataFrame based on Category
    filtered_df = df.copy()
    if st.session_state.selected_category != "전체":
        filtered_df = filtered_df[filtered_df['Cuisine'] == st.session_state.selected_category]

    # Restaurant Markers
    restaurant_markers = []
    # Only show category-filtered existing markers if NO search query is active
    # If search query is active, 'search_markers' will handle the display (Red/Blue)
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
    
    # Selected Location Marker
    selected_marker = None
    if st.session_state.selected_lat:
        selected_marker = {
            "lat": st.session_state.selected_lat,
            "lng": st.session_state.selected_lon,
            "name": st.session_state.selected_name or "선택된 위치"
        }

    # Center Logic
    center_lat = st.session_state.selected_lat if st.session_state.selected_lat else avg_lat
    center_lon = st.session_state.selected_lon if st.session_state.selected_lon else avg_lon

    # JavaScript Template
    js_key = st.session_state.get('js_api_key', DEFAULT_JS_API_KEY)
    
    kakao_map_html = f"""
    <!-- Map Container -->
    <meta http-equiv="Content-Security-Policy" content="upgrade-insecure-requests">
    <div id="map" style="width:100%; height:700px; border:1px solid #ccc;"></div>

    <script>
        function initMap() {{
            if (typeof kakao === 'undefined') {{
                return;
            }}

            kakao.maps.load(function() {{
                try {{
                    var container = document.getElementById('map');
                    var options = {{
                        center: new kakao.maps.LatLng({center_lat}, {center_lon}),
                        level: 3
                    }};

                    var map = new kakao.maps.Map(container, options);
                    
                    // --- Markers & InfoWindows ---
                    
                    // Data from Python
                    var company = {json.dumps(company_marker)};
                    var restaurants = {json.dumps(restaurant_markers)};
                    var selected = {json.dumps(selected_marker)};
                    var searchResults = {json.dumps(search_markers)};
                    
                    // Track active InfoWindow to support toggle
                    var activeInfoWindow = null;

                    // 1. Company Marker (Visual: Big Building Emoji, Function: Invisible Clickable Marker)
                    var companyOverlay = new kakao.maps.CustomOverlay({{
                        position: new kakao.maps.LatLng(company.lat, company.lng),
                        content: '<div style="font-size:80px; text-shadow: 2px 2px 5px rgba(0,0,0,0.3); line-height: 1; cursor: pointer;">🏢</div>',
                        yAnchor: 0.3, // Centered vertically (user request: "middle")
                        zIndex: 9
                    }});
                    companyOverlay.setMap(map);

                    // Invisible marker for clicking
                    var transparentImg = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";
                    // Offset (40, 40) centers the 80x80 image on the coordinate, matching the Overlay's yAnchor: 0.5 (middle)
                    var compImage = new kakao.maps.MarkerImage(transparentImg, new kakao.maps.Size(80, 80), {{offset: new kakao.maps.Point(40, 40)}}); 
                    var companyMarker = new kakao.maps.Marker({{
                        position: new kakao.maps.LatLng(company.lat, company.lng),
                        title: "Xi S&D 본사",
                        image: compImage,
                        zIndex: 10
                    }});
                    companyMarker.setMap(map);

                    var companyIw = new kakao.maps.InfoWindow({{
                        content: '<div style="padding:5px;width:150px;text-align:center;"><b>Xi S&D 본사</b></div>'
                    }});
                    kakao.maps.event.addListener(companyMarker, 'click', function() {{
                        if (activeInfoWindow === companyIw) {{
                            companyIw.close();
                            activeInfoWindow = null;
                        }} else {{
                            if (activeInfoWindow) {{
                                activeInfoWindow.close();
                            }}
                            companyIw.open(map, companyMarker);
                            activeInfoWindow = companyIw;
                        }}
                    }});
                    
                    
                    // 2. Restaurant Markers
                    // 2. Restaurant Markers (Registered Only) - Use standardized Blue
                    var standardBlue = "https://maps.google.com/mapfiles/ms/icons/blue-dot.png";
                    var standardRed = "https://maps.google.com/mapfiles/ms/icons/red-dot.png";

                    restaurants.forEach(function(place) {{
                        var markerImage = new kakao.maps.MarkerImage(standardBlue, new kakao.maps.Size(32, 32));
                        var marker = new kakao.maps.Marker({{
                            map: map,
                            position: new kakao.maps.LatLng(place.lat, place.lng),
                            title: place.name,
                            image: markerImage
                        }});
                        
                        var content = '<div style="padding:5px;width:150px;font-family:sans-serif;font-size:13px;">' + 
                            '<b>' + place.name + '</b>' + (place.isWinner ? ' 👑' : '') + '<br>' +
                            '<span style="font-size:11px;color:gray;">' + place.cuisine + '</span><br>' +
                            '⭐ ' + place.rating + '점' +
                            '</div>'; 

                        var infowindow = new kakao.maps.InfoWindow({{
                            content: content,
                            removable: true
                        }});

                        kakao.maps.event.addListener(marker, 'click', function() {{
                            if (activeInfoWindow === infowindow) {{
                                infowindow.close();
                                activeInfoWindow = null;
                            }} else {{
                                if (activeInfoWindow) {{
                                    activeInfoWindow.close();
                                }}
                                infowindow.open(map, marker);
                                activeInfoWindow = infowindow;
                            }}
                        }});
                    }});

                    // 3. Search Result Markers
                    // Use Numbered Markers (Blue=Registered, Red=Unregistered)
                    
                    searchResults.forEach(function(place, i) {{
                        var index = i + 1;
                        var color = place.isRegistered ? 'blue' : 'red';
                        var imageSrc = 'https://raw.githubusercontent.com/Concept211/Google-Maps-Markers/master/images/marker_' + color + index + '.png';
                        
                        var markerImage = new kakao.maps.MarkerImage(imageSrc, new kakao.maps.Size(22, 40)); 
                        
                        var marker = new kakao.maps.Marker({{
                            map: map,
                            position: new kakao.maps.LatLng(place.lat, place.lng),
                            title: place.name,
                            image: markerImage,
                            zIndex: place.isRegistered ? 5 : 3
                        }});
                        
                        var infoContent = '';
                        if (place.isRegistered) {{
                            infoContent = '<div style="padding:5px;width:150px;font-family:sans-serif;font-size:13px;">' +
                                          '<b>' + place.name + '</b><br>' +
                                          '<span style="color:#d32f2f;font-size:11px;">✅ 이미 등록됨</span>' +
                                          '</div>';
                        }} else {{
                            infoContent = '<div style="padding:5px;width:150px;font-family:sans-serif;font-size:13px;">' +
                                          '<b>' + place.name + '</b><br>' +
                                          '<span style="color:gray;font-size:11px;">' + (place.address || '') + '</span><br>' +
                                          '<span style="color:blue;font-size:11px;">👉 목록에서 선택하여 등록</span>' +
                                          '</div>';
                        }}
                        
                        var infowindow = new kakao.maps.InfoWindow({{
                            content: infoContent,
                            removable: true
                        }});
                        
                        kakao.maps.event.addListener(marker, 'click', function() {{
                             if (activeInfoWindow === infowindow) {{
                                infowindow.close();
                                activeInfoWindow = null;
                            }} else {{
                                if (activeInfoWindow) {{
                                    activeInfoWindow.close();
                                }}
                                infowindow.open(map, marker);
                                activeInfoWindow = infowindow;
                            }}
                        }});
                    }});

                    // 4. Selected Marker (Use same logic or highlight)
                    if (selected) {{
                        // Focus is moved by center option, marker might diligently overlay search result
                        // If selected is already in searchResults, maybe just open its infowindow?
                        // For simplicity, draw it on top
                        var marker = new kakao.maps.Marker({{
                            map: map,
                            position: new kakao.maps.LatLng(selected.lat, selected.lng),
                            zIndex: 10 // Highest priority
                        }});
                         var infowindow = new kakao.maps.InfoWindow({{
                            content: '<div style="padding:5px;width:150px;font-family:sans-serif;font-size:13px;"><b>' + selected.name + '</b><br><span style="color:red;font-size:11px;">📍 선택된 위치</span></div>'
                        }});
                        infowindow.open(map, marker);
                    }}
                    
                    // Zoom Control
                    var zoomControl = new kakao.maps.ZoomControl();
                    map.addControl(zoomControl, kakao.maps.ControlPosition.RIGHT);
                    
                }} catch (e) {{
                    console.error("Map Error:", e);
                }}
            }});
        }}
    </script>
    
    <!-- Load SDK -->
    <script type="text/javascript" 
            src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={js_key}&libraries=services&autoload=false"
            onload="initMap()"></script>
    """
    
    # Render Map
    components.html(kakao_map_html, height=710)
    st.caption("ℹ️ **지도 클릭은 현재 지원되지 않습니다.** 맛집을 등록하려면 위쪽 **'장소 검색'**을 이용해주세요! (검색 후 선택하면 자동으로 입력됩니다)")


# --- Tab 2: List Logic ---
with tab2:
    st.header("� 저장된 맛집 리스트")
    if not df.empty:
        # Metrics
        col1, col2, col3 = st.columns(3)
        col1.metric("총 맛집 수", f"{len(df)}곳")
        col2.metric("평균 평점", f"{df['Rating'].mean():.1f}점")
        if 'Price' in df.columns:
             # Clean price to numeric if possible for calc, but simple mode for now
             pass

        # Highlight winner in dataframe
        def highlight_winner(row):
            if row['Name'] == st.session_state.winner:
                # RGBA for transparency (Green with 0.3 opacity)
                return ['background-color: rgba(76, 175, 80, 0.3); border: 2px solid #4CAF50'] * len(row)
            else:
                return [''] * len(row)

        st.dataframe(
            df.style.apply(highlight_winner, axis=1),
            column_config={
                "Rating": st.column_config.NumberColumn(
                    "평점",
                    help="점수 (0-100)",
                    format="%d 점",
                ),
                 "Review": st.column_config.TextColumn("리뷰", width="large"),
                 "BestMenu": st.column_config.TextColumn("대표 메뉴", width="small"),
                 "Price": st.column_config.TextColumn("가격", width="small"),
                 "Name": "식당 이름",
                 "Cuisine": "음식 종류",
                 "Location": "위치 설명",
                 "Latitude": None, # Hide raw coords
                 "Longitude": None
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("아직 등록된 맛집이 없습니다.")


# --- Sidebar Form (Context Sensitive) ---
st.sidebar.markdown("## 🏘️ 플레이스 정보")

status = st.session_state.selection_status

# Case 1: Existing Restaurant Selected
# Case 1: Existing Restaurant Selected
if status and status.get('type') == 'existing':
    # Back Button at Top
    if st.sidebar.button("⬅️ 뒤로 가기", key="back_btn_existing", use_container_width=True):
        st.session_state.selection_status = None
        st.session_state.selected_lat = None
        st.session_state.selected_lon = None
        st.session_state.selected_name = None
        st.rerun()

    row = status['data']
    st.sidebar.success("✅ **등록된 맛집입니다!**")
    
    st.sidebar.title(f"🍽️ {row['Name']}")
    st.sidebar.caption(f"{row['Cuisine']} | ⭐ {row['Rating']:.1f}점 ({int(row.get('RatingCount', 1))}명 참여)")
    
    st.sidebar.divider()
    
    st.sidebar.markdown(f"**👍 맛있었던 메뉴**\n: {row['BestMenu']}")
    # Price removed
    
    if pd.notna(row.get('Recommender')):
        st.sidebar.markdown(f"**💁‍♂️ 추천인**\n: {row['Recommender']}")
        
    st.sidebar.info(f"🗣️ **의견 (Opinions)**\n\n{row['Review']}")
    
    st.sidebar.divider()
    
    # Add new opinion
    with st.sidebar.expander("✍️ 나도 평가하기 (추가 의견)", expanded=False):
        with st.form("add_review_form"):
            new_rating = st.slider("내 평점", 0, 100, 80)
            new_comment = st.text_area("내 의견 (한줄평)", height=80)
            new_user = st.text_input("내 이름")
            
            submit_review = st.form_submit_button("평가 등록")
            if submit_review:
                if not new_comment or not new_user:
                    st.error("의견과 이름을 모두 입력해주세요.")
                else:
                    # Update Logic
                    df = load_data()
                    # Find index
                    idx = df[df['Name'] == row['Name']].index
                    if not idx.empty:
                        i = idx[0]
                        current_rating = df.at[i, 'Rating']
                        current_count = df.at[i, 'RatingCount'] if pd.notna(df.at[i, 'RatingCount']) else 1
                        current_review = df.at[i, 'Review']
                        current_recommender = df.at[i, 'Recommender']
                        
                        # Calculate New Weighted Average
                        new_total_rating = (current_rating * current_count) + new_rating
                        new_count = current_count + 1
                        updated_rating = new_total_rating / new_count
                        
                        # Append Text
                        updated_review = f"{current_review}\n\n[{new_user}] {new_comment} (⭐{new_rating})"
                        updated_recommender = f"{current_recommender}, {new_user}" if pd.notna(current_recommender) else new_user
                        
                        # Save
                        # Save to Supabase
                        try:
                            row_id = int(df.at[i, 'id'])
                            payload = {
                                'rating': float(updated_rating),
                                'rating_count': int(new_count),
                                'review': updated_review,
                                'recommender': updated_recommender
                            }
                            supabase.table('restaurants').update(payload).eq('id', row_id).execute()
                            
                            # Update local state for immediate feedback
                            updated_row = df.iloc[i].copy()
                            updated_row['Rating'] = updated_rating
                            updated_row['RatingCount'] = new_count
                            updated_row['Review'] = updated_review
                            updated_row['Recommender'] = updated_recommender
                            
                            st.session_state.selection_status['data'] = updated_row
                        except Exception as e:
                            st.error(f"업데이트 실패: {e}")
                            st.stop()
                        st.session_state.search_query = "" # Clear search
                        st.success("소중한 의견이 추가되었습니다!")
                        st.rerun()

    # Old button removed from here

# Case 2: New Location Selected
elif status and status.get('type') == 'new':
    # Back Button at Top
    if st.sidebar.button("⬅️ 뒤로 가기", key="back_btn_new", use_container_width=True):
        st.session_state.selection_status = None
        st.session_state.selected_lat = None
        st.session_state.selected_lon = None
        st.session_state.selected_name = None
        st.rerun()

    place = status['data']
    st.sidebar.markdown(f"### 🏢 {place['place_name']}")
    st.sidebar.caption(place.get('address_name', ''))
    
    st.sidebar.warning(f"🤔 **아직 등록되지 않은 곳입니다! (반경 1km 내)**")
    st.sidebar.info("이곳을 맛집으로 등록하시겠습니까? 👇")
    
    # Old button removed from here

    with st.sidebar.form("add_restaurant_form"):
        col_name, col_cuisine = st.columns(2)
        with col_name:
            name = st.text_input("식당 이름", value=place['place_name'])
        with col_cuisine:
            cuisine = st.selectbox("음식 종류", ["한식", "중식", "일식", "양식", "분식", "술집", "기타"])
        
        # Removed Price
        best_menu = st.text_input("맛있었던 메뉴 (Best Menu)")
        
        rating = st.slider("평점 (0-100)", 0, 100, 80)
        review = st.text_area("의견 (자유롭게 기술)", height=100) # Changed label
        recommender = st.text_input("추천인 이름 (여러 명일 경우 쉼표로 구분)")
        
        submitted = st.form_submit_button("맛집 등록하기", use_container_width=True)
        
        if submitted:
            if not name:
                st.sidebar.error("식당 이름을 입력해주세요.")
            else:
                # Save to Supabase
                db_payload = {
                    'name': name,
                    'cuisine': cuisine,
                    'rating': rating,
                    'rating_count': 1,
                    'review': f"[{recommender}] {review} (⭐{rating})",
                    'location': place.get('address_name', ''),
                    'latitude': float(place['y']),
                    'longitude': float(place['x']),
                    'best_menu': best_menu,
                    'recommender': recommender
                }
                
                try:
                    response = supabase.table('restaurants').insert(db_payload).execute()
                    if response.data:
                        # Construct state data from response (includes ID)
                        inserted = response.data[0]
                        # Map back to App format
                        new_data_state = {
                            'Name': inserted['name'],
                            'Cuisine': inserted['cuisine'],
                            'Rating': inserted['rating'],
                            'RatingCount': inserted['rating_count'],
                            'Review': inserted['review'],
                            'Location': inserted['location'],
                            'Latitude': inserted['latitude'],
                            'Longitude': inserted['longitude'],
                            'BestMenu': inserted['best_menu'],
                            'Recommender': inserted['recommender'],
                            'id': inserted['id']
                        }
                        
                        st.sidebar.success("맛집이 성공적으로 추가되었습니다! 🎉")
                        st.session_state.selection_status = {'type': 'existing', 'data': new_data_state}
                    else:
                        st.error("데이터 저장 실패 (응답 없음)")
                except Exception as e:
                    st.error(f"저장 중 오류가 발생했습니다: {e}")
                    st.stop()
                st.session_state.search_query = "" # Clear search
                st.rerun()

# Case 3: Default (No Selection) -> Search Results OR Stats Summary
else:
    # If search query exists, show the list of results
    if st.session_state.search_query:
        places = search_kakao_place(st.session_state.search_query)
        if places:
            # If ONLY 1 result, auto-select it immediately
            if len(places) == 1:
                selected_place = places[0]
                s_lat = float(selected_place['y'])
                s_lon = float(selected_place['x'])
                
                st.session_state.selected_lat = s_lat
                st.session_state.selected_lon = s_lon
                st.session_state.selected_name = selected_place['place_name']
                
                # Check by Name (Distance check caused errors for neighbors)
                match_found = None
                if not df.empty:
                    matches = df[df['Name'] == selected_place['place_name']]
                    if not matches.empty:
                        match_found = matches.iloc[0]
                
                if match_found is not None:
                     st.session_state.selection_status = {'type': 'existing', 'data': match_found}
                else:
                     st.session_state.selection_status = {'type': 'new', 'data': selected_place}
                
                st.rerun()

            # If multiple results, stick to list
            else:
                st.sidebar.markdown(f"### 🔍 검색 결과: '{st.session_state.search_query}'")
                st.sidebar.caption("아래 목록에서 선택하면 상세 정보를 볼 수 있습니다.")
                
                # Limit to Top 10 results to reduce clutter -> Removed by user request
                # places = places[:10]
                
                for i, p in enumerate(places):
                    # Check registration status for consistent color coding
                    is_registered_sidebar = False
                    if not df.empty:
                         if p['place_name'] in df['Name'].values:
                             is_registered_sidebar = True

                    emoji = "🔵" if is_registered_sidebar else "🔴"
                    
                    # Button for each place (with Index and Color)
                    label = f"{emoji} {i+1}. {p['place_name']} ({p.get('category_group_name', '음식점')})"
                    if st.sidebar.button(label, key=f"sidebar_btn_{i}", use_container_width=True):
                        # --- Same Selection Logic as Dropdown ---
                        selected_place = p
                        s_lat = float(selected_place['y'])
                        s_lon = float(selected_place['x'])
                        
                        st.session_state.selected_lat = s_lat
                        st.session_state.selected_lon = s_lon
                        st.session_state.selected_name = selected_place['place_name']
                        
                        # Check by Name (Distance check caused errors for neighbors)
                        match_found = None
                        if not df.empty:
                            matches = df[df['Name'] == selected_place['place_name']]
                            if not matches.empty:
                                match_found = matches.iloc[0]
                        
                        if match_found is not None:
                            st.session_state.selection_status = {'type': 'existing', 'data': match_found}
                        else:
                            st.session_state.selection_status = {'type': 'new', 'data': selected_place}
                        
                        st.rerun()
        else:
             st.sidebar.warning("검색 결과가 없습니다.")
             if st.sidebar.button("검색 초기화", use_container_width=True):
                st.session_state.search_query = ""
                st.rerun()

    # If no search query, check category filter
    elif st.session_state.selected_category != "전체":
        cat_df = df[df['Cuisine'] == st.session_state.selected_category]
        st.sidebar.markdown(f"### 🥣 {st.session_state.selected_category} 맛집 리스트")
        
        if not cat_df.empty:
            st.sidebar.caption(f"총 {len(cat_df)}곳이 등록되어 있습니다.")
            for i, (idx, row) in enumerate(cat_df.iterrows()):
                # Display average rating and count
                rating_info = f"⭐{row['Rating']:.1f}"
                label = f"{i+1}. {row['Name']} ({rating_info})"
                
                if st.sidebar.button(label, key=f"cat_res_btn_{idx}", use_container_width=True):
                     st.session_state.selection_status = {'type': 'existing', 'data': row}
                     st.session_state.selected_lat = row['Latitude']
                     st.session_state.selected_lon = row['Longitude']
                     st.session_state.selected_name = row['Name']
                     st.rerun()
        else:
            st.sidebar.info("해당 카테고리에 등록된 맛집이 없습니다.")

    # If no search query and no category filter, show stats
    else:
        st.sidebar.markdown("### 📊 현재 등록 현황")
        if not df.empty:
            total_count = len(df)
            st.sidebar.write(f"**총 {total_count}곳**의 맛집이 등록되어 있습니다.")
            
            # Simplified Stats
            cat_counts = df['Cuisine'].value_counts()
            stats_text = []
            st.sidebar.caption(", ".join(stats_text))
            
            st.sidebar.divider()
            st.sidebar.markdown("### 📋 전체 맛집 리스트")
            st.sidebar.caption(f"등록된 모든 맛집을 확인하세요. ({total_count}곳)")
            
            # Sort by name for easier scanning? Or maybe Rating? Name is standard for directory.
            sorted_df = df.sort_values(by='Name')
            
            for i, (idx, row) in enumerate(sorted_df.iterrows()):
                # Display name and rating
                rating_info = f"⭐{row['Rating']:.1f}"
                label = f"{i+1}. {row['Name']} ({row['Cuisine']} | {rating_info})"
                
                # Use original index for key to be safe
                if st.sidebar.button(label, key=f"all_res_btn_{idx}", use_container_width=True):
                     st.session_state.selection_status = {'type': 'existing', 'data': row}
                     st.session_state.selected_lat = row['Latitude']
                     st.session_state.selected_lon = row['Longitude']
                     st.session_state.selected_name = row['Name']
                     st.rerun()

        else:
            st.sidebar.info("아직 등록된 맛집이 없습니다. 첫번째 등록자가 되어주세요!")
