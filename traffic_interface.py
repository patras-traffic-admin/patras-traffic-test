import streamlit as st
import pandas as pd
import folium
from folium.plugins import PolyLineTextPath
from streamlit_folium import st_folium
import json
import os
import requests
import plotly.express as px
import random
import networkx as nx
import math
from shapely.geometry import LineString
from pyproj import Transformer

# Λίστα με τα κλειδιά σου για το TomTom API
API_KEYS = [
    "I937bOmZ1sU5JIzvVxaXWgyCUa5lPobk", # Βάλε το πραγματικό σου κλειδί μέσα στα εισαγωγικά
]

# 1. Ρυθμίσεις σελίδας - Modern Theme
st.set_page_config(page_title="Patras Traffic Analytics", page_icon="🚦", layout="wide")

# 🔥 CUSTOM CSS
st.markdown("""
<style>
    .stApp { background-color: #0E1117; color: #E0E0E0; }
    h1, h2, h3, h4 { color: #FFFFFF !important; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    [data-testid="stMetricValue"] { font-size: 2.8rem !important; font-weight: 700; color: #00BFFF; }
    [data-testid="stMetricLabel"] { font-size: 1.1rem !important; color: #BDBDBD !important; font-weight: 400 !important; }
    div[data-testid="metric-container"] {
        background-color: #1E1E1E; border-radius: 15px; padding: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3); border: 1px solid #333333;
    }
    [data-testid="stSidebar"] { background-color: #16191F; border-right: 1px solid #333333; }
    button[data-baseweb="tab"] { font-size: 1.1rem; font-weight: 600; color: #BDBDBD; }
    button[data-baseweb="tab"][aria-selected="true"] { color: #00BFFF !important; border-bottom-color: #00BFFF !important; }
    .stDataFrame { border-radius: 15px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3); }
    .stSelectbox, .stSlider { border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# Αφαίρεση του "PRO" από τον τίτλο
st.title("🚦 Patras Traffic Analytics")
st.markdown("---")

if 'start_point' not in st.session_state: st.session_state.start_point = None
if 'end_point' not in st.session_state: st.session_state.end_point = None

# --- 2. Φόρτωση Στατικών & Τύπων από το EXCEL ---
static_data = {}
road_types = {}
if os.path.exists("traffic_patra.xlsx"):
    try:
        df_ex1 = pd.read_excel("traffic_patra.xlsx", sheet_name="Φύλλο1")
        for _, row in df_ex1.iterrows():
            r_name = row['Road_Segment']
            road_types[r_name] = str(row.get('Road type', row.get('Road_type', 'Άγνωστο'))).strip()
            static_data[r_name] = row.get('Static_Speed', 50)
            
        df_ex2 = pd.read_excel("traffic_patra.xlsx", sheet_name="Φύλλο2")
        for _, row in df_ex2.iterrows():
            r_name = row['Road_Segment']
            road_types[r_name] = str(row.get('Road type', row.get('Road_type', 'secondary'))).strip()
            static_data[r_name] = row.get('Static_Speed', 50)
    except Exception as e:
        st.error(f"Σφάλμα ανάγνωσης Excel: {e}")

# --- 3. Φόρτωση Γεωμετρίας & CSV ---
if not os.path.exists("road_geometry.json"):
    st.error("❌ Λείπει το αρχείο 'road_geometry.json'! Τρέξτε πρώτα το setupgeometry.py")
    st.stop()

with open("road_geometry.json", "r", encoding="utf-8") as f:
    geometry_data = json.load(f)

# --- 4. ΦΟΡΤΩΣΗ ΔΕΔΟΜΕΝΩΝ ΚΥΚΛΟΦΟΡΙΑΣ ---
csv_path = "live_traffic_data.csv"
if not os.path.exists(csv_path):
    st.error("⏳ Λείπει το αρχείο δεδομένων (live_traffic_data.csv).")
    st.stop()

df_history = pd.read_csv(csv_path, sep=";")
df_history['Timestamp'] = pd.to_datetime(df_history['Timestamp'], format='mixed', errors='coerce')

df_history['Date'] = df_history['Timestamp'].dt.date
df_history['Time'] = df_history['Timestamp'].dt.strftime('%H:%M')

# --- 5. SIDEBAR (Φίλτρα & Λογότυπο) ---
with st.sidebar:
    # Προσθήκη του λογότυπου στην κορυφή της μπάρας
    if os.path.exists("logo-m.png"):
        st.image("logo-m.png", use_container_width=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
    st.markdown("## ⚙️ Κέντρο Ελέγχου")
    st.markdown("---")
    
    available_dates = sorted(df_history['Date'].dropna().unique())
    if not available_dates:
        st.error("Σφάλμα: Το CSV δεν έχει έγκυρες ημερομηνίες!")
        st.stop()

    selected_date = st.selectbox("📅 Επιλέξτε μέρα:", options=available_dates, index=len(available_dates)-1)
    df_day = df_history[df_history['Date'] == selected_date]
    available_times = sorted(df_day['Time'].dropna().unique())

    if not available_times:
        st.warning("Δεν βρέθηκαν καταγραφές για αυτή τη μέρα.")
        st.stop()

    selected_time = st.selectbox("⏱️ Επιλέξτε ώρα:", options=available_times, index=len(available_times)-1)
    st.markdown("---")
    
    unique_types = ["Όλοι οι Τύποι"] + sorted(list(set(road_types.values()))) if road_types else ["Όλοι οι Τύποι"]
    selected_type = st.selectbox("🛤️ Επιλέξτε τύπο:", options=unique_types, index=0)
    st.markdown("---")

    available_roads_for_step4 = [r for r in geometry_data.keys() if selected_type == "Όλοι οι Τύποι" or road_types.get(r) == selected_type]
    all_roads = ["Όλες οι Οδοί"] + sorted(available_roads_for_step4)
    selected_road = st.selectbox("📍 Επιλέξτε δρόμο:", options=all_roads, index=0)
    st.markdown("---")
    
    past_mask = (df_history['Date'] < selected_date) | ((df_history['Date'] == selected_date) & (df_history['Time'] <= selected_time))
    all_current_df = df_history[past_mask].drop_duplicates(subset=['Road_Segment'], keep='last')
    
    live_speeds = dict(zip(all_current_df['Road_Segment'], all_current_df['Speed_kmh']))
    
    roads_to_remove = []
    for road, speed in live_speeds.items():
        try:
            val = float(speed)
        except:
            val = 0.0
        if val <= 0.5: 
            roads_to_remove.append(road)

    for road in roads_to_remove:
        del live_speeds[road]
        
    def get_center(coords):
        lats = [c[0] for c in coords]
        lons = [c[1] for c in coords]
        return (sum(lats)/len(lats), sum(lons)/len(lons))

    live_centers = {}
    for r_name in live_speeds.keys():
        if r_name in geometry_data:
            live_centers[r_name] = get_center(geometry_data[r_name])

    dynamic_secondary_speeds = {}
    
    for r_name in geometry_data.keys():
        if r_name not in live_speeds:
            static_speed = static_data.get(r_name, 50)
            center_sec = get_center(geometry_data[r_name])
            
            distances = []
            for live_name, center_live in live_centers.items():
                dist_sq = (center_sec[0] - center_live[0])**2 + (center_sec[1] - center_live[1])**2
                distances.append((dist_sq, live_name))
            
            distances.sort()
            
            if "_rev" in str(r_name).lower(): closest_live = distances[:1]
            else: closest_live = distances[:3]
            
            if closest_live:
                local_ratios = []
                for _, l_name in closest_live:
                    l_speed = live_speeds[l_name]
                    l_limit = static_data.get(l_name, 50)
                    if l_limit > 0:
                        local_ratios.append(min(l_speed / l_limit, 1.0))
                local_health_factor = sum(local_ratios) / len(local_ratios)
            else:
                local_health_factor = 1.0 
            
            adjusted_speed = max(static_speed * local_health_factor, 5.0)
            dynamic_secondary_speeds[r_name] = round(adjusted_speed, 1)
            
    all_speeds_map = {**live_speeds, **dynamic_secondary_speeds}
    filtered_view_df = all_current_df.copy()
    if selected_type != "Όλοι οι Τύποι":
        filtered_view_df['Type'] = filtered_view_df['Road_Segment'].map(road_types)
        filtered_view_df = filtered_view_df[filtered_view_df['Type'] == selected_type]
        
    st.metric(label="📊 Ενεργές Μετρήσεις", value=len(filtered_view_df))

# --- ΚΟΙΝΕΣ ΣΥΝΑΡΤΗΣΕΙΣ ---
to_mercator = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
to_wgs84 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

def get_parallel_line(coords, dist_meters=2.0): 
    try:
        xy_pairs = [(c[1], c[0]) for c in coords]
        if len(xy_pairs) < 2: return coords
        projected_xy = [to_mercator.transform(x, y) for x, y in xy_pairs]
        line = LineString(projected_xy)
        offset_line = line.parallel_offset(dist_meters, side='right', join_style=1) 
        
        coords_out_xy = []
        if offset_line.geom_type == 'MultiLineString':
            for sub_line in offset_line.geoms: coords_out_xy.extend(list(sub_line.coords))
        else:
            coords_out_xy = list(offset_line.coords)
        if len(coords_out_xy) < 2: return coords
        unprojected_xy = [to_wgs84.transform(x, y) for x, y in coords_out_xy]
        return [[y, x] for x, y in unprojected_xy]
    except:
        return coords

def get_hybrid_color(speed, road_name):
    if pd.isna(speed) or speed == 0: return "#7f8c8d" 
    r_type = road_types.get(road_name, "").lower()
    if "trunk" in r_type or "motorway" in r_type:
        limit = static_data.get(road_name, 90)
        ratio = speed / limit if limit > 0 else 1
        if ratio < 0.4: return "#EF5350"
        if ratio < 0.75: return "#FFCA28"
        return "#66BB6A"
    else:
        if speed < 15: return "#EF5350"
        if speed < 30: return "#FFCA28"
        return "#66BB6A"

def haversine_dist(coord1, coord2):
    R = 6371000 
    lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
    lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

# --- TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["🗺️ Ανάλυση Δικτύου & Χάρτης", "🔬 Υπολογισμός Διαδρομής", "📅 Εβδομαδιαίο Heatmap", "🔮 Πρόβλεψη Κυκλοφορίας" ])

# ================= TAB 1: LIVE ΧΑΡΤΗΣ =================
with tab1:
    st.markdown(f"### 📍 Αποτύπωση Κυκλοφορίας: {selected_date} στις {selected_time}")

    selected_hour = int(selected_time.split(':')[0])
    is_night_time = (0 <= selected_hour < 6)

    m = folium.Map(
        location=[38.2462, 21.7351], 
        zoom_start=14, 
        tiles='https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}', 
        attr='Google Maps'
    )

    for road_name, coords in geometry_data.items():
        speed = all_speeds_map.get(road_name, 0)
        
        current_coords = coords
        if "_rev" in road_name.lower():
            try: 
                current_coords = get_parallel_line(coords, dist_meters=3.5)
            except: 
                pass

        base_road_name = road_name.replace("_rev", "")
        actual_type = road_types.get(road_name, road_types.get(base_road_name, "Άγνωστο"))
        
        is_type_match = (selected_type == "Όλοι οι Τύποι" or actual_type == selected_type)
        
        clean_selected_road = selected_road.replace("_rev", "")
        is_road_match = (base_road_name == clean_selected_road)

        base_limit = static_data.get(road_name, static_data.get(base_road_name, 50)) 
        speed_limit = base_limit * 0.6 if is_night_time else base_limit
        
        if speed_limit > 0 and speed > 0:
            speed_ratio = speed / speed_limit
            if speed_ratio >= 0.70: traffic_color = "#2ecc71"
            elif speed_ratio >= 0.45: traffic_color = "#f1c40f"
            elif speed_ratio >= 0.25: traffic_color = "#e67e22"
            else: traffic_color = "#e74c3c"
        else:
            traffic_color = "#7f8c8d"

        if selected_road != "Όλες οι Οδοί":
            if is_road_match: 
                color, weight, opacity = traffic_color, 8, 1.0
            else: 
                color, weight, opacity = "#333333", 2, 0.15 
        else:
            if is_type_match: 
                color, weight, opacity = traffic_color, 5, 0.9
            else: 
                color, weight, opacity = "#333333", 2, 0.15

        line = folium.PolyLine(
            locations=current_coords, 
            color=color, 
            weight=weight, 
            opacity=opacity, 
            tooltip=f"{road_name}: {speed} km/h"
        ).add_to(m)

        if selected_road != "Όλες οι Οδοί" and is_road_match:
            PolyLineTextPath(
                line, f'  {road_name}  ', repeat=False, offset=8,
                attributes={'fill': '#000000', 'font-weight': 'bold', 'font-size': '16'}
            ).add_to(m)

    st_folium(m, width=1300, height=550, key="network_map")
    st.markdown("---")

    if selected_road == "Όλες οι Οδοί":
        st.markdown(f"### 📊 Αναλυτική Αναφορά Στιγμής (Φίλτρο: {selected_type})")
        
        if not filtered_view_df.empty:
            filtered_view_df['Type'] = filtered_view_df['Road_Segment'].map(road_types).fillna(
                filtered_view_df['Road_Segment'].apply(lambda x: road_types.get(x.replace("_rev", ""), 'Άγνωστο'))
            )
            filtered_view_df['Limit'] = filtered_view_df['Road_Segment'].apply(
                lambda x: static_data.get(x, static_data.get(x.replace("_rev", ""), 50))
            )

            def is_congested(row):
                r_type = str(row['Type']).lower()
                if "trunk" in r_type or "motorway" in r_type:
                    return (row['Speed_kmh'] / row['Limit']) < 0.4 if row['Limit'] > 0 else False
                else:
                    return row['Speed_kmh'] < 15

            def calc_health_ratio(row):
                r_type = str(row['Type']).lower()
                if "trunk" in r_type or "motorway" in r_type:
                    return row['Speed_kmh'] / row['Limit'] if row['Limit'] > 0 else 1
                else:
                    return row['Speed_kmh'] / 50

            filtered_view_df['Is_Congested'] = filtered_view_df.apply(is_congested, axis=1)
            filtered_view_df['Ratio'] = filtered_view_df.apply(calc_health_ratio, axis=1)

            filtered_view_df['Ratio'] = filtered_view_df.apply(lambda r: r['Speed_kmh'] / r['Limit'] if r['Limit'] > 0 else 1, axis=1)
            avg_speed = round(filtered_view_df['Speed_kmh'].mean(), 1)
            congested_count = filtered_view_df[filtered_view_df['Speed_kmh'] < 15]['Road_Segment'].count()
            total_roads = len(filtered_view_df)
            
            if not filtered_view_df['Ratio'].isna().all():
                worst_road_row = filtered_view_df.loc[filtered_view_df['Ratio'].idxmin()]
                worst_speed = f"{worst_road_row['Speed_kmh']} km/h"
                worst_name = f"{worst_road_row['Road_Segment']}"
            else:
                worst_speed = "N/A"
                worst_name = "Μη διαθέσιμο"
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("🏎️ Μέση Ταχύτητα", f"{avg_speed} km/h")
            c2.metric("🚨 Κόκκινοι Δρόμοι", f"{congested_count} / {total_roads}")
            c3.metric("📉 % Συμφόρησης", f"{round((congested_count/total_roads)*100, 1)}%" if total_roads > 0 else "0%")
            c4.metric("🤯 Χειρότερος Δρόμος", worst_speed, worst_name, delta_color="inverse")

            st.markdown("<br>", unsafe_allow_html=True)
            
            c_left, c_right = st.columns([1, 1])
            
            with c_left:
                st.markdown("#### 🚫 Top 5 Μποτιλιαρίσματα")
                worst_5 = filtered_view_df.nsmallest(5, 'Ratio')[['Road_Segment', 'Speed_kmh', 'Type']].reset_index(drop=True)
                worst_5.columns = ["Όνομα Δρόμου", "Ταχύτητα (km/h)", "Τύπος"]
                st.dataframe(worst_5, use_container_width=True)
                
            with c_right:
                st.markdown("#### 🚦 Κατανομή Κυκλοφορίας")
                def categorize_hybrid(row):
                    speed = row['Speed_kmh']
                    r_type = str(row['Type']).lower()
                    if "trunk" in r_type or "motorway" in r_type:
                        ratio = speed / row['Limit'] if row['Limit'] > 0 else 1
                        if ratio < 0.4: return 'Συμφόρηση'
                        if ratio < 0.75: return 'Μέτρια'
                        return 'Ελεύθερη'
                    else:
                        if speed < 15: return 'Συμφόρηση'
                        if speed < 30: return 'Μέτρια'
                        return 'Ελεύθερη'

                filtered_view_df['Traffic_Level'] = filtered_view_df.apply(categorize_hybrid, axis=1)
                pie_fig = px.pie(
                    filtered_view_df, names='Traffic_Level', hole=0.5, color='Traffic_Level',
                    color_discrete_map={'Συμφόρηση': '#EF5350', 'Μέτρια': '#FFCA28', 'Ελεύθερη': '#66BB6A'}
                )
                pie_fig.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color="white"), 
                    margin=dict(t=10, b=10, l=10, r=10), height=280
                )
                st.plotly_chart(pie_fig, use_container_width=True)

            # 👇 ΕΔΩ ΑΡΧΙΖΕΙ Η ΑΛΛΑΓΗ ΤΟΥ ΝΕΟΥ ΔΙΑΓΡΑΜΜΑΤΟΣ 👇
            st.markdown("---")
            st.markdown("### 🚦 Δείκτης Λειτουργικής Κατάστασης Δικτύου")
            st.caption("Κατάταξη των οδών βάσει της απόκλισης της τρέχουσας ταχύτητας από το όριο (Λόγος Ταχύτητας Ροής).")

            # 1. Νέες κατηγορίες αντί για LOS A-F
            status_order = [
                'Ελεύθερη Ροή (Βέλτιστη)', 
                'Σταθερή Ροή', 
                'Ήπια Επιβάρυνση', 
                'Ασταθής Ροή', 
                'Οριακή Συμφόρηση', 
                'Έντονη Συμφόρηση (Gridlock)'
            ]

            def get_op_status(row):
                limit = row['Limit']
                speed = row['Speed_kmh']
                if limit <= 0: return 'Άγνωστο'
                
                ratio = speed / limit
                if ratio >= 0.85: return status_order[0]
                elif ratio >= 0.70: return status_order[1]
                elif ratio >= 0.50: return status_order[2]
                elif ratio >= 0.40: return status_order[3]
                elif ratio >= 0.33: return status_order[4]
                else: return status_order[5]

            filtered_view_df['Status'] = filtered_view_df.apply(get_op_status, axis=1)

            def get_tooltip_roads(df_group):
                roads = df_group['Road_Segment'].tolist()
                if len(roads) > 6:
                    return "<br>".join(roads[:6]) + f"<br><i>...και άλλοι {len(roads)-6}</i>"
                return "<br>".join(roads)

            status_hover_data = filtered_view_df.groupby('Status').apply(get_tooltip_roads).reset_index(name='Ενδεικτικές Οδοί')
            status_counts = filtered_view_df['Status'].value_counts().reset_index()
            status_counts.columns = ['Λειτουργική Κατάσταση', 'Πλήθος Οδών']

            status_counts = pd.merge(status_counts, status_hover_data, left_on='Λειτουργική Κατάσταση', right_on='Status', how='left')

            status_counts['Λειτουργική Κατάσταση'] = pd.Categorical(status_counts['Λειτουργική Κατάσταση'], categories=status_order, ordered=True)
            status_counts = status_counts.sort_values('Λειτουργική Κατάσταση').dropna()

            status_color_map = {
                status_order[0]: '#2ecc71', 
                status_order[1]: '#82e0aa', 
                status_order[2]: '#f1c40f', 
                status_order[3]: '#e67e22', 
                status_order[4]: '#e74c3c', 
                status_order[5]: '#8b0000'
            }

            fig_status = px.bar(
                status_counts, 
                x='Λειτουργική Κατάσταση', 
                y='Πλήθος Οδών', 
                color='Λειτουργική Κατάσταση',
                color_discrete_map=status_color_map,
                text='Πλήθος Οδών',
                custom_data=['Ενδεικτικές Οδοί']
            )

            fig_status.update_traces(
                textposition='outside',
                hovertemplate="<b>%{x}</b><br>Πλήθος: %{y}<br><br><b>Οδοί:</b><br>%{customdata[0]}<extra></extra>"
            )
            
            fig_status.update_layout(
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(10,10,10,0.5)', font=dict(color="white"),
                xaxis=dict(title="Βαθμίδα Λειτουργικότητας", showgrid=False),
                yaxis=dict(title="Αριθμός Δρόμων", showgrid=True, gridcolor='rgba(255,255,255,0.1)'),
                showlegend=False, height=400, margin=dict(t=20, b=20, l=10, r=10)
            )

            st.plotly_chart(fig_status, use_container_width=True)

            with st.expander("📋 Προβολή Αναλυτικής Λίστας Οδών ανά Κατάσταση"):
                # Το index=5 προεπιλέγει την Έντονη Συμφόρηση (τη χειρότερη κατάσταση)
                selected_status = st.selectbox("Επιλέξτε Κατηγορία για προβολή οδών:", status_order, index=5)
                
                df_selected_status = filtered_view_df[filtered_view_df['Status'] == selected_status][
                    ['Road_Segment', 'Speed_kmh', 'Limit', 'Ratio', 'Type']
                ].sort_values('Ratio')
                
                df_selected_status.columns = ['Όνομα Οδού', 'Ταχύτητα (km/h)', 'Όριο (km/h)', 'Δείκτης (Ratio)', 'Τύπος Οδού']
                
                if df_selected_status.empty:
                    st.info(f"Δεν υπάρχουν δρόμοι σε αυτή την κατηγορία ({selected_status}) για την επιλεγμένη ώρα.")
                else:
                    st.dataframe(df_selected_status, use_container_width=True)
            # 👆 ΤΕΛΟΣ ΕΝΣΩΜΑΤΩΣΗΣ ΝΕΟΥ ΔΙΑΓΡΑΜΜΑΤΟΣ 👆

        else:
            st.warning("⚠️ Δεν υπάρχουν διαθέσιμα τρέχοντα δεδομένα κυκλοφορίας.")

    else:
        st.markdown(f"### 📊 Λεπτομερής Ανάλυση: `{selected_road}`")
        df_road_day = df_day[df_day['Road_Segment'] == selected_road].sort_values('Time')

        if not df_road_day.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("⏱️ Ταχύτητα τώρα", f"{live_speeds.get(selected_road, 'N/A')} km/h")
            c2.metric("📈 Μέγιστη Σήμερα", f"{df_road_day['Speed_kmh'].max()} km/h")
            c3.metric("📉 Ελάχιστη Σήμερα", f"{df_road_day['Speed_kmh'].min()} km/h")

            st.markdown("<br>", unsafe_allow_html=True)

            city_avg = df_day.groupby('Time')['Speed_kmh'].mean().reset_index()
            city_avg.rename(columns={'Speed_kmh': 'Μέσος Όρος Πόλης'}, inplace=True)

            plot_df = pd.merge(df_road_day[['Time', 'Speed_kmh']], city_avg, on='Time', how='outer').sort_values('Time')
            plot_df.rename(columns={'Speed_kmh': f'Επιλεγμένη Οδός'}, inplace=True)

            plot_df_melted = plot_df.melt(
                id_vars=['Time'], value_vars=[f'Επιλεγμένη Οδός', 'Μέσος Όρος Πόλης'],
                var_name='Δείκτης', value_name='Ταχύτητα (km/h)'
            )

            fig_road_line = px.line(
                plot_df_melted, x='Time', y='Ταχύτητα (km/h)', color='Δείκτης', markers=True,
                color_discrete_map={f'Επιλεγμένη Οδός': '#00BFFF', 'Μέσος Όρος Πόλης': '#7f8c8d'}
            )
            fig_road_line.update_traces(marker=dict(size=6))
            fig_road_line.update_layout(
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(10,10,10,0.5)', font=dict(color="white"),
                xaxis=dict(gridcolor="#333"), yaxis=dict(gridcolor="#333"),
                legend=dict(title="", orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_road_line, use_container_width=True)
        else:
            st.warning("⚠️ Δεν υπάρχουν επαρκή δεδομένα για αυτή την οδό σήμερα.")
# ================= TAB 2 =================
with tab2:
    st.markdown("### 🔬 Επιλογή Διαδρομής & Live Κίνηση")
    st.caption("💡 Οδηγός: Κλικάρετε πάνω στις διακριτικές γαλάζιες γραμμές για να επιλέξετε Αφετηρία και Προορισμό.")
    
    c_btn, c_inf = st.columns([1, 4])
    with c_btn:
        if st.button("🔄 Καθαρισμός Σημείων"):
            st.session_state.start_point = None
            st.session_state.end_point = None
            st.rerun()
        
    # Αλλαγή χάρτη σε Google Maps style
    m_click = folium.Map(
        location=[38.2462, 21.7351], 
        zoom_start=14, 
        tiles='https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}', 
        attr='Google Maps'
    )
    
    for road_name, coords in geometry_data.items():
        folium.PolyLine(locations=coords, color="#0088CC", weight=4, opacity=0.5, tooltip=f"Άξονας: {road_name}").add_to(m_click)
    
    if st.session_state.start_point:
        folium.Marker(st.session_state.start_point, popup="Αφετηρία", icon=folium.Icon(color="green", icon="play")).add_to(m_click)
    if st.session_state.end_point:
        folium.Marker(st.session_state.end_point, popup="Προορισμός", icon=folium.Icon(color="red", icon="stop")).add_to(m_click)
        
    map_data = st_folium(m_click, width=1300, height=500, key="click_selector_map")
    
    if map_data and map_data.get("last_clicked"):
        clicked_coords = [map_data["last_clicked"]["lat"], map_data["last_clicked"]["lng"]]
        if st.session_state.start_point is None:
            st.session_state.start_point = clicked_coords
            st.rerun()
        elif st.session_state.end_point is None and clicked_coords != st.session_state.start_point:
            st.session_state.end_point = clicked_coords
            st.rerun()
            
    c_out1, c_out2 = st.columns(2)
    with c_out1:
        st.markdown(f"<div style='background-color: #1E1E1E; padding: 15px; border-radius: 10px; border-left: 5px solid #66BB6A;'>🟢 <b>Αφετηρία:</b> {st.session_state.start_point if st.session_state.start_point else 'Εκκρεμεί...'}</div>", unsafe_allow_html=True)
    with c_out2:
        st.markdown(f"<div style='background-color: #1E1E1E; padding: 15px; border-radius: 10px; border-left: 5px solid #EF5350;'>🔴 <b>Προορισμός:</b> {st.session_state.end_point if st.session_state.end_point else 'Εκκρεμεί...'}</div>", unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)

    if st.session_state.start_point and st.session_state.end_point:
        s_str = f"{st.session_state.start_point[0]},{st.session_state.start_point[1]}"
        e_str = f"{st.session_state.end_point[0]},{st.session_state.end_point[1]}"
        
        url = f"https://api.tomtom.com/routing/1/calculateRoute/{s_str}:{e_str}/json"
        params = {'key': random.choice(API_KEYS), 'traffic': 'true', 'routeType': 'fastest', 'travelMode': 'car', 'sectionType': 'traffic'}
        
        try:
            with st.spinner('🔭 Υπολογισμός διαδρομής με βάση την κίνηση...'):
                response = requests.get(url, params=params, timeout=10)
                res_data = response.json()
                
            if response.status_code == 200 and 'routes' in res_data:
                summary = res_data['routes'][0]['summary']
                points = res_data['routes'][0]['legs'][0]['points']
                sections = res_data['routes'][0].get('sections', [])
                
                time_min = round(summary.get('travelTimeInSeconds', 0) / 60, 1)
                distance_km = round(summary.get('lengthInMeters', 0) / 1000, 2)
                delay_sec = summary.get('trafficDelayInSeconds', 0)
                calc_speed = round((summary.get('lengthInMeters', 0) / 1000) / (summary.get('travelTimeInSeconds', 1) / 3600), 1)
                
                st.markdown("---")
                st.markdown("#### 🔭 Αποτελέσματα Βέλτιστης Διαδρομής")
                
                res_col1, res_col2, res_col3, res_col4 = st.columns(4)
                res_col1.metric("⏱️ Χρόνος", f"{time_min} λεπτά")
                res_col2.metric("🏎️ Ταχύτητα", f"{calc_speed} km/h")
                res_col3.metric("📏 Απόσταση", f"{distance_km} km")
                res_col4.metric("🚨 Καθυστέρηση", f"{delay_sec} δευτ.")
                
                route_coords = [[p['latitude'], p['longitude']] for p in points]
                
                # Αλλαγή χάρτη αποτελεσμάτων σε Google Maps style
                m_res = folium.Map(
                    location=route_coords[0], 
                    zoom_start=14, 
                    tiles='https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}', 
                    attr='Google Maps'
                )
                
                for road_name, coords in geometry_data.items():
                    speed = live_speeds.get(road_name, static_data.get(road_name, 0))
                    c = get_hybrid_color(speed, road_name)
                    folium.PolyLine(locations=coords, color=c, weight=3, opacity=0.4).add_to(m_res)

                folium.PolyLine(locations=route_coords, color="#00BFFF", weight=7, opacity=0.8).add_to(m_res)
                
                for sec in sections:
                    if sec.get('sectionType') == 'TRAFFIC':
                        s_idx = sec.get('startPointIndex', 0)
                        e_idx = sec.get('endPointIndex', len(route_coords)-1)
                        mag = sec.get('magnitudeOfDelay', 0)
                        
                        if mag >= 3: t_color = "#EF5350"
                        elif mag > 0: t_color = "#FFCA28"
                        else: t_color = "#66BB6A"
                        
                        sec_coords = route_coords[s_idx:e_idx+1]
                        folium.PolyLine(locations=sec_coords, color=t_color, weight=7, opacity=1.0).add_to(m_res)

                folium.Marker(location=route_coords[0], icon=folium.Icon(color="green", icon="play")).add_to(m_res)
                folium.Marker(location=route_coords[-1], icon=folium.Icon(color="red", icon="stop")).add_to(m_res)
                st_folium(m_res, width=1300, height=450, key="result_route_map")
            else:
                st.error("Σφάλμα API: Δεν βρέθηκε διαδρομή. Δοκιμάστε να κάνετε κλικ πιο κοντά στο δίκτυο.")
        except Exception as e:
            st.error(f"Αποτυχία σύνδεσης: {e}")

# ================= TAB 3: HEATMAP (ΑΝΑΛΥΣΗ ΚΥΚΛΟΦΟΡΙΑΣ) =================
with tab3:
    st.markdown("### 📅 Εβδομαδιαία Ανάλυση (Heatmaps)")
    
    metric_choice = st.radio(
        "Επιλέξτε Μετρική Απεικόνισης:", 
        ["Δείκτης Συμφόρησης (85th Percentile)", "Χρόνος Ταξιδιού (Λεπτά)"], 
        horizontal=True
    )
    st.markdown("---")
    
    df_heat = df_history.copy()
    
    df_heat['Speed_kmh'] = pd.to_numeric(df_heat['Speed_kmh'], errors='coerce')
    df_heat = df_heat[df_heat['Speed_kmh'] >= 4.0]
    
    bad_data_mask = (
        (df_heat['Timestamp'].dt.strftime('%Y-%m-%d') == '2026-05-19') & 
        (df_heat['Timestamp'].dt.strftime('%H:%M') >= '11:00') & 
        (df_heat['Timestamp'].dt.strftime('%H:%M') <= '14:00') 
    )
    df_heat = df_heat[~bad_data_mask]
    
    if selected_type != "Όλοι οι Τύποι":
        df_heat['Type'] = df_heat['Road_Segment'].map(road_types)
        df_heat = df_heat[df_heat['Type'] == selected_type]
    if selected_road != "Όλες οι Οδοί":
        df_heat = df_heat[df_heat['Road_Segment'] == selected_road]
        
    if not df_heat.empty:
        df_heat['Date_Only'] = pd.to_datetime(df_heat['Timestamp'].dt.date)
        df_heat['Μισάωρο'] = df_heat['Timestamp'].dt.floor('30min').dt.strftime('%H:%M')
        df_heat['DayOrder'] = df_heat['Timestamp'].dt.dayofweek 
        day_map = {0: 'Δευ', 1: 'Τρι', 2: 'Τετ', 3: 'Πεμ', 4: 'Παρ', 5: 'Σαβ', 6: 'Κυρ'}
        df_heat['Ημέρα'] = df_heat['DayOrder'].map(day_map)
        
        fig_heat = None
        
        if metric_choice == "Δείκτης Συμφόρησης (85th Percentile)":
            st.caption("💡 Μέθοδος: Σύγκριση με το 95ο Εκατοστημόριο Ταχύτητας (Free Flow). Όταν βλέπετε 'Όλες οι Οδοί', εστιάζουμε στις πιο επιβαρυμένες αρτηρίες (85th percentile).")
            
            ffs_df = df_heat.groupby('Road_Segment')['Speed_kmh'].quantile(0.95).reset_index()
            ffs_df.rename(columns={'Speed_kmh': 'Limit'}, inplace=True)
            df_heat = df_heat.merge(ffs_df, on='Road_Segment', how='left')
            df_heat['Limit'] = df_heat['Limit'].replace(0, 30.0) 
            
            df_heat['Road_Congestion'] = ((df_heat['Limit'] - df_heat['Speed_kmh']) / df_heat['Limit']) * 100
            df_heat['Road_Congestion'] = df_heat['Road_Congestion'].clip(lower=0, upper=100)
            
            if selected_road == "Όλες οι Οδοί":
                heatmap_data = df_heat.groupby(['Date_Only', 'Ημέρα', 'Μισάωρο'])['Road_Congestion'].quantile(0.85).reset_index()
            else:
                heatmap_data = df_heat.groupby(['Date_Only', 'Ημέρα', 'Μισάωρο'])['Road_Congestion'].mean().reset_index()
            heatmap_data.rename(columns={'Road_Congestion': 'Congestion'}, inplace=True)
            
            heatmap_data = heatmap_data.sort_values('Date_Only')
            heatmap_data['Date_Label'] = heatmap_data['Date_Only'].dt.strftime('%d/%m') + " " + heatmap_data['Ημέρα']
            
            pivot_df = heatmap_data.pivot(index='Μισάωρο', columns='Date_Label', values='Congestion')
            ordered_cols = heatmap_data.drop_duplicates('Date_Only').sort_values('Date_Only')['Date_Label'].unique()
            pivot_df = pivot_df[ordered_cols]
            
            all_half_hours = [f"{h:02d}:{m:02d}" for h in range(24) for m in [0, 30]]
            pivot_df = pivot_df.reindex(all_half_hours).astype(float)
            
            pivot_df = pivot_df.interpolate(method='linear', axis=0, limit_area='inside')
            pivot_df = pivot_df.interpolate(method='linear', axis=1, limit_area='inside')
            
            if not pivot_df.empty:
                st.markdown("#### 🏆 Στατιστικά Επιβάρυνσης Δικτύου")
                c1, c2, c3 = st.columns(3)
                peak_row = heatmap_data.loc[heatmap_data['Congestion'].idxmax()]
                c1.metric("🔥 Μέγιστη Συμφόρηση", f"{peak_row['Congestion']:.0f}%", f"Στις {peak_row['Μισάωρο']} ({peak_row['Date_Label']})", delta_color="inverse")
                c2.metric("📊 Μέση Εβδομαδιαία", f"{heatmap_data['Congestion'].mean():.0f}%")
                c3.metric("✅ Ελάχιστη (Νύχτα)", f"{heatmap_data['Congestion'].min():.0f}%")
                st.markdown("<br>", unsafe_allow_html=True)
                
                traffic_scale = [[0.0, "#2ecc71"], [0.2, "#2ecc71"], [0.4, "#f1c40f"], [0.6, "#e67e22"], [0.8, "#e74c3c"], [1.0, "#78281f"]]
                fig_heat = px.imshow(pivot_df, labels=dict(x="Ημερομηνία", y="Ώρα", color="Συμφόρηση (%)"),
                                    color_continuous_scale=traffic_scale, range_color=[0, 80], text_auto=".0f", aspect="auto", height=900)
                fig_heat.update_traces(xgap=2, ygap=2, texttemplate="%{z:.0f}%", textfont=dict(color="white", size=10))

        else:
            st.caption("💡 Δείχνει τον πραγματικό μέσο χρόνο ταξιδιού σε λεπτά. Πράσινο=Ταχύτερα, Μπορντό=Καθυστερήσεις.")
            if 'Travel_Time_sec' in df_heat.columns:
                df_heat['Travel_Time_min'] = df_heat['Travel_Time_sec'] / 60.0
                heatmap_data = df_heat.groupby(['Date_Only', 'Ημέρα', 'Μισάωρο'])['Travel_Time_min'].mean().reset_index()
                
                heatmap_data = heatmap_data.sort_values('Date_Only')
                heatmap_data['Date_Label'] = heatmap_data['Date_Only'].dt.strftime('%d/%m') + " " + heatmap_data['Ημέρα']
                
                pivot_df = heatmap_data.pivot(index='Μισάωρο', columns='Date_Label', values='Travel_Time_min')
                ordered_cols = heatmap_data.drop_duplicates('Date_Only').sort_values('Date_Only')['Date_Label'].unique()
                pivot_df = pivot_df[ordered_cols]
                
                all_half_hours = [f"{h:02d}:{m:02d}" for h in range(24) for m in [0, 30]]
                pivot_df = pivot_df.reindex(all_half_hours).astype(float)
                
                pivot_df = pivot_df.interpolate(method='linear', axis=0, limit_area='inside')
                pivot_df = pivot_df.interpolate(method='linear', axis=1, limit_area='inside')
                
                if not pivot_df.empty:
                    st.markdown("#### 🏆 Στατιστικά Χρόνου Μετάβασης")
                    c1, c2, c3 = st.columns(3)
                    peak_row = heatmap_data.loc[heatmap_data['Travel_Time_min'].idxmax()]
                    best_row = heatmap_data.loc[heatmap_data['Travel_Time_min'].idxmin()]
                    avg_time = heatmap_data['Travel_Time_min'].mean()
                    
                    c1.metric("🔥 Μέγιστος Χρόνος (Αιχμή)", f"{peak_row['Travel_Time_min']:.1f} λ", f"Στις {peak_row['Μισάωρο']} ({peak_row['Date_Label']})", delta_color="inverse")
                    c2.metric("📊 Μέσος Χρόνος Ημέρας", f"{avg_time:.1f} λ")
                    c3.metric("✅ Ελάχιστος Χρόνος (Νύχτα)", f"{best_row['Travel_Time_min']:.1f} λ", "Ελεύθερη Ροή")
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    time_scale = [[0.0, "#2ecc71"], [0.3, "#f1c40f"], [0.6, "#e67e22"], [0.8, "#e74c3c"], [1.0, "#78281f"]]
                    fig_heat = px.imshow(pivot_df, labels=dict(x="Ημερομηνία", y="Ώρα", color="Χρόνος (Λεπτά)"),
                                        color_continuous_scale=time_scale, text_auto=".1f", aspect="auto", height=900)
                    fig_heat.update_traces(xgap=2, ygap=2, texttemplate="%{z:.1f} λ", textfont=dict(color="white", size=10))
            else:
                st.warning("⚠️ Λείπει η στήλη 'Travel_Time_sec' από το CSV.")

        if fig_heat is not None:
            fig_heat.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(10,10,10,0.5)', font=dict(color="white"), xaxis=dict(side="top"), yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig_heat, use_container_width=True)
    else:
        st.warning("⚠️ Δεν βρέθηκαν καταγραφές.")

# ================= TAB 4: ΠΡΟΒΛΕΨΗ (FORECASTING) =================
with tab4:
    st.markdown("### 🔮 Πρόβλεψη Κυκλοφορίας (Historical Profiling)")
    st.caption("💡 Υπολογισμός αναμενόμενης κυκλοφορίας βάσει ιστορικών μοτίβων. Εφαρμόζεται χωρική παρεμβολή (spatial interpolation) για τις οδούς χωρίς ιστορικά δεδομένα.")
    
    c_date, c_time, c_type, c_road = st.columns(4)
    
    with c_date:
        import datetime
        today = datetime.date.today()
        future_date = st.date_input("📅 Επιλέξτε Ημερομηνία:", min_value=today)
        
    with c_time:
        future_time = st.time_input("⏱️ Επιλέξτε Ώρα:", value=datetime.time(14, 00))
        
    with c_type:
        unique_types_tab4 = ["Όλοι οι Τύποι"] + sorted(list(set(road_types.values()))) if road_types else ["Όλοι οι Τύποι"]
        selected_type_tab4 = st.selectbox("🛤️ Επιλέξτε Τύπο (Πρόβλεψη):", options=unique_types_tab4, index=0)
        
    with c_road:
        available_roads_tab4 = [
            r for r in geometry_data.keys() 
            if selected_type_tab4 == "Όλοι οι Τύποι" or road_types.get(r, road_types.get(r.replace("_rev", ""), "Άγνωστο")) == selected_type_tab4
        ]
        all_roads_tab4 = ["Όλες οι Οδοί"] + sorted(available_roads_tab4)
        selected_road_tab4 = st.selectbox("📍 Επιλέξτε Δρόμο (Πρόβλεψη):", options=all_roads_tab4, index=0)
        
    st.markdown("---")
    
    target_weekday = future_date.weekday() 
    minute_binned = 30 if future_time.minute >= 15 and future_time.minute < 45 else 0
    hour_binned = future_time.hour if future_time.minute < 45 else (future_time.hour + 1) % 24
    target_time_str = f"{hour_binned:02d}:{minute_binned:02d}"
    
    df_pred = df_history.copy()
    df_pred['Weekday'] = df_pred['Timestamp'].dt.weekday
    df_pred['Time_Bin'] = df_pred['Timestamp'].dt.floor('30min').dt.strftime('%H:%M')
    
    mask_prediction = (df_pred['Weekday'] == target_weekday) & (df_pred['Time_Bin'] == target_time_str)
    df_future_profile = df_pred[mask_prediction]
    
    if df_future_profile.empty:
        st.warning(f"⚠️ Δεν υπάρχουν ιστορικά δεδομένα για την ημέρα {future_date.strftime('%A')} στις {target_time_str}.")
    else:
        predicted_speeds = df_future_profile.groupby('Road_Segment')['Speed_kmh'].mean().to_dict()
        
        forecast_centers = {}
        for r_name in predicted_speeds.keys():
            if r_name in geometry_data:
                forecast_centers[r_name] = get_center(geometry_data[r_name])
                
        dynamic_forecast_speeds = {}
        for r_name in geometry_data.keys():
            if r_name not in predicted_speeds:
                static_speed = static_data.get(r_name, 50)
                center_sec = get_center(geometry_data[r_name])
                
                distances = []
                for h_name, h_center in forecast_centers.items():
                    dist_sq = (center_sec[0] - h_center[0])**2 + (center_sec[1] - h_center[1])**2
                    distances.append((dist_sq, h_name))
                distances.sort()
                
                closest_hist = distances[:1] if "_rev" in str(r_name).lower() else distances[:3]
                
                if closest_hist:
                    local_ratios = []
                    for _, h_name in closest_hist:
                        h_speed = predicted_speeds[h_name]
                        h_limit = static_data.get(h_name, 50)
                        if h_limit > 0:
                            local_ratios.append(min(h_speed / h_limit, 1.0))
                    local_health_factor = sum(local_ratios) / len(local_ratios) if local_ratios else 1.0
                else:
                    local_health_factor = 1.0 
                    
                adjusted_speed = max(static_speed * local_health_factor, 5.0)
                dynamic_forecast_speeds[r_name] = round(adjusted_speed, 1)
        
        all_forecast_speeds = {**predicted_speeds, **dynamic_forecast_speeds}
        
        c_msg, c_metric = st.columns([3, 1])
        with c_msg:
            st.success(f"✅ Η πρόβλεψη βασίστηκε σε {len(df_future_profile['Date'].unique())} ιστορικές καταγραφές για αυτή την ημέρα και ώρα.")
        with c_metric:
            if selected_road_tab4 != "Όλες οι Οδοί":
                specific_speed = all_forecast_speeds.get(selected_road_tab4, 0)
                st.metric(f"Ταχύτητα ({selected_road_tab4})", f"{round(specific_speed, 1)} km/h")

        # Αλλαγή χάρτη πρόβλεψης σε Google Maps style
        m_forecast = folium.Map(
            location=[38.2462, 21.7351], 
            zoom_start=14, 
            tiles='https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}', 
            attr='Google Maps'
        )
        
        for road_name, coords in geometry_data.items():
            speed = all_forecast_speeds.get(road_name, 0)
            
            base_road_name = road_name.replace("_rev", "")
            actual_type = road_types.get(road_name, road_types.get(base_road_name, "Άγνωστο"))
            base_limit = static_data.get(road_name, static_data.get(base_road_name, 50))
            
            if selected_road_tab4 != "Όλες οι Οδοί":
                is_targeted = (road_name == selected_road_tab4)
            elif selected_type_tab4 != "Όλοι οι Τύποι":
                is_targeted = (actual_type == selected_type_tab4)
            else:
                is_targeted = True
            
            current_coords = coords
            if "_rev" in road_name.lower():
                try: 
                    current_coords = get_parallel_line(coords, dist_meters=3.5)
                except: 
                    pass
            
            if is_targeted:
                if speed > 0:
                    ratio = speed / base_limit if base_limit > 0 else 1
                    if ratio >= 0.70: t_color = "#2ecc71"
                    elif ratio >= 0.45: t_color = "#f1c40f"
                    elif ratio >= 0.25: t_color = "#e67e22"
                    else: t_color = "#e74c3c"
                    
                    folium.PolyLine(
                        locations=current_coords, color=t_color, weight=6, opacity=1.0, 
                        tooltip=f"{road_name}<br>Αναμενόμενη Ταχύτητα: {round(speed, 1)} km/h"
                    ).add_to(m_forecast)
                else:
                    folium.PolyLine(locations=current_coords, color="#bdc3c7", weight=4, opacity=0.8).add_to(m_forecast)
            else:
                folium.PolyLine(locations=current_coords, color="#333333", weight=2, opacity=0.2).add_to(m_forecast)
                
        st_folium(m_forecast, width=1300, height=550, key="forecast_map")
