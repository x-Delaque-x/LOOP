import re
import streamlit as st
import pandas as pd
import urllib.parse
from geopy.geocoders import Nominatim
from sqlalchemy import text
from database_manager import SessionLocal, Municipality, URLSubmission, Feedback
from config import APP_NAME, APP_TAGLINE, MASTER_TAGS, AGE_TAGS, DEFAULT_ZIP

st.set_page_config(page_title=f"{APP_NAME} Explorer", page_icon="🌀", layout="wide")

# ---------------------------------------------------------------------------
# Custom CSS — modern glass UI
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* ---- Global ---- */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Hide default Streamlit chrome */
#MainMenu, footer {visibility: hidden;}

/* ---- Sidebar ---- */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%) !important;
}
section[data-testid="stSidebar"] * {
    color: #e0e0e0 !important;
}
section[data-testid="stSidebar"] .stTextInput > div > div > input {
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 10px;
    color: #fff !important;
}
section[data-testid="stSidebar"] .stSlider [data-testid="stThumbValue"] {
    color: #fff !important;
}

/* ---- Hero banner ---- */
.hero-banner {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 16px;
    padding: 2rem 2.5rem;
    margin-bottom: 1.5rem;
    color: white;
}
.hero-banner h1 {
    font-size: 2.4rem;
    font-weight: 700;
    margin: 0 0 0.25rem 0;
    letter-spacing: -0.5px;
}
.hero-banner p {
    font-size: 1.1rem;
    opacity: 0.9;
    margin: 0;
}

/* ---- Metric cards row ---- */
.metric-row {
    display: flex;
    gap: 1rem;
    margin-bottom: 1.5rem;
}
.metric-card {
    flex: 1;
    background: white;
    border-radius: 14px;
    padding: 1.2rem 1.4rem;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    border: 1px solid #f0f0f0;
    text-align: center;
}
.metric-card .metric-value {
    font-size: 1.8rem;
    font-weight: 700;
    color: #333;
}
.metric-card .metric-label {
    font-size: 0.85rem;
    color: #888;
    margin-top: 2px;
}

/* ---- Event cards ---- */
.event-card {
    background: white;
    border-radius: 14px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 0.9rem;
    box-shadow: 0 2px 12px rgba(0,0,0,0.05);
    border: 1px solid #f0f0f0;
    transition: box-shadow 0.2s ease, transform 0.2s ease;
}
.event-card:hover {
    box-shadow: 0 6px 24px rgba(0,0,0,0.1);
    transform: translateY(-1px);
}
.event-card .event-title {
    font-size: 1.15rem;
    font-weight: 600;
    color: #1a1a2e;
    margin: 0 0 0.4rem 0;
}
.event-card .event-meta {
    font-size: 0.85rem;
    color: #777;
    margin-bottom: 0.5rem;
}
.event-card .event-desc {
    font-size: 0.9rem;
    color: #555;
    line-height: 1.5;
    margin-bottom: 0.6rem;
}
.event-tag {
    display: inline-block;
    background: linear-gradient(135deg, #667eea22, #764ba222);
    color: #5a4fcf;
    font-size: 0.75rem;
    font-weight: 500;
    padding: 3px 10px;
    border-radius: 20px;
    margin-right: 4px;
    margin-bottom: 4px;
}
.event-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.8rem;
}
.event-actions a {
    display: inline-block;
    font-size: 0.82rem;
    font-weight: 500;
    padding: 6px 14px;
    border-radius: 8px;
    text-decoration: none;
    transition: opacity 0.2s;
}
.event-actions a:hover { opacity: 0.85; }
.btn-directions {
    background: #667eea;
    color: white !important;
}
.btn-source {
    background: #f0f0f0;
    color: #444 !important;
}

/* ---- Section headers ---- */
.section-header {
    font-size: 1.3rem;
    font-weight: 600;
    color: #1a1a2e;
    margin: 1.5rem 0 1rem 0;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid #667eea;
    display: inline-block;
}

/* ---- Empty state ---- */
.empty-state {
    text-align: center;
    padding: 3rem 1rem;
    color: #999;
}
.empty-state .empty-icon { font-size: 3rem; margin-bottom: 0.5rem; }
.empty-state p { font-size: 1rem; }

/* ---- Map container ---- */
.map-container {
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    margin-bottom: 1.5rem;
}

/* Pills styling */
button[data-testid="stBaseButton-pills"] {
    border-radius: 20px !important;
    font-size: 0.82rem !important;
    padding: 4px 14px !important;
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------
@st.cache_data
def geocode_zip(zip_code):
    geolocator = Nominatim(user_agent=f"{APP_NAME.lower()}_streamlit_app")
    try:
        location = geolocator.geocode(f"{zip_code}, USA")
        if location:
            return location.latitude, location.longitude
    except Exception:
        pass
    return None, None


def load_data_spatial(lat, lon, radius_miles):
    try:
        session = SessionLocal()
        radius_meters = radius_miles * 1609.34
        query = text('''
            SELECT
                e.id, e.title, e.event_date, e.event_time, e.description, e.tags,
                v.name as location_name, v.address, e.source_url,
                ST_Y(v.location::geometry) as latitude,
                ST_X(v.location::geometry) as longitude,
                (ST_Distance(v.location, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) / 1609.34) as distance_miles
            FROM events e
            JOIN venues v ON e.venue_id = v.id
            WHERE v.location IS NOT NULL
              AND ST_DWithin(v.location, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius_meters)
            ORDER BY distance_miles ASC, e.event_date ASC
        ''')
        result = session.execute(query, {"lat": lat, "lon": lon, "radius_meters": radius_meters})
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
        session.close()
        return df
    except Exception as e:
        st.error(f"Database offline — {e}")
        return pd.DataFrame()


def render_event_card(row):
    """Render a single event as a styled HTML card."""
    title = row['title']
    time_str = row['event_time'] if pd.notnull(row['event_time']) else "TBD"
    date_str = row['event_date'] if pd.notnull(row['event_date']) else ""
    location = row['location_name'] if pd.notnull(row['location_name']) else ""
    dist = round(row['distance_miles'], 1)
    desc = str(row['description']) if pd.notnull(row['description']) else ""
    desc_snippet = desc[:200] + "..." if len(desc) > 200 else desc

    # Build tag pills
    tags_html = ""
    if pd.notnull(row['tags']) and str(row['tags']).strip():
        for tag in str(row['tags']).split(','):
            tag = tag.strip()
            if tag:
                tags_html += f'<span class="event-tag">{tag}</span>'

    # Build action buttons
    actions = ""
    if pd.notnull(row['address']) and str(row['address']).strip():
        maps_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(str(row['address']))}"
        actions += f'<a href="{maps_url}" target="_blank" class="btn-directions">Get Directions</a>'
    if pd.notnull(row['source_url']) and str(row['source_url']).strip():
        actions += f'<a href="{row["source_url"]}" target="_blank" class="btn-source">View Source</a>'

    return f"""
    <div class="event-card">
        <div class="event-title">{title}</div>
        <div class="event-meta">
            {date_str} at {time_str} &nbsp;&bull;&nbsp; {location} &nbsp;&bull;&nbsp; {dist} mi away
        </div>
        <div>{tags_html}</div>
        <div class="event-desc">{desc_snippet}</div>
        <div class="event-actions">{actions}</div>
    </div>
    """


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Search")
    zip_code = st.text_input("ZIP Code", value=DEFAULT_ZIP, label_visibility="collapsed",
                              placeholder="Enter ZIP code...")
    radius = st.slider("Radius (miles)", min_value=1, max_value=50, value=15)

    st.markdown("---")
    st.markdown("### Filter by Category")
    selected_tags = st.pills("Categories", MASTER_TAGS, selection_mode="multi", default=[],
                              label_visibility="collapsed")

    st.markdown("### Filter by Age")
    selected_ages = st.pills("Ages", AGE_TAGS, selection_mode="multi", default=[],
                              label_visibility="collapsed")

    st.markdown("---")

    # URL Submission Form
    with st.expander("Submit a Source URL"):
        try:
            session = SessionLocal()
            munis = session.query(Municipality).order_by(Municipality.name).all()
            muni_names = [m.name for m in munis]
            session.close()
        except Exception:
            muni_names = []

        if muni_names:
            sub_town = st.selectbox("Municipality", muni_names, key="sub_town")
            sub_url = st.text_input("Calendar/Events URL", key="sub_url")
            sub_type = st.radio("Type", ["library", "recreation"], key="sub_type")
            sub_note = st.text_area("Notes (optional)", key="sub_note")
            if st.button("Submit URL"):
                if sub_url:
                    try:
                        session = SessionLocal()
                        muni = session.query(Municipality).filter_by(name=sub_town).first()
                        session.add(URLSubmission(
                            municipality_id=muni.id if muni else None,
                            url=sub_url,
                            source_type=sub_type,
                            submitter_note=sub_note,
                        ))
                        session.commit()
                        session.close()
                        st.success("Submitted! We'll review it soon.")
                    except Exception as e:
                        st.error(f"Submission failed: {e}")
                else:
                    st.warning("Please enter a URL.")
        else:
            st.info("Municipality data not loaded.")

    # Feedback Form
    with st.expander("Give Feedback"):
        fb_name = st.text_input("Your name (optional)", key="fb_name")
        fb_text = st.text_area("What's on your mind?", key="fb_text",
                               placeholder="Found a bug? Missing your town? Have an idea?")
        if st.button("Send Feedback"):
            if fb_text.strip():
                try:
                    session = SessionLocal()
                    session.add(Feedback(name=fb_name.strip() or None, feedback=fb_text.strip()))
                    session.commit()
                    session.close()
                    st.success("Thanks for your feedback!")
                except Exception as e:
                    st.error(f"Could not save feedback: {e}")
            else:
                st.warning("Please enter some feedback.")

    st.markdown("---")
    st.markdown(
        f"<div style='text-align:center; font-size:0.75rem; opacity:0.5; padding-top:1rem;'>"
        f"{APP_NAME} v1.0 &bull; Rhode Island</div>",
        unsafe_allow_html=True
    )


# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------

# Hero banner
st.markdown(f"""
<div class="hero-banner">
    <h1>{APP_NAME}</h1>
    <p>{APP_TAGLINE} — find family-friendly events near you across Rhode Island</p>
</div>
""", unsafe_allow_html=True)

if not zip_code:
    st.markdown("""
    <div class="empty-state">
        <div class="empty-icon">📍</div>
        <p>Enter a ZIP code in the sidebar to discover events near you.</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

home_lat, home_lon = geocode_zip(zip_code)

if not home_lat:
    st.error("Could not find that ZIP code. Please try another.")
    st.stop()

df = load_data_spatial(home_lat, home_lon, radius)

if df.empty:
    st.markdown("""
    <div class="empty-state">
        <div class="empty-icon">🔍</div>
        <p>No events found within that radius. Try increasing the distance.</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# Apply tag filters
filtered = df.copy()
if selected_tags:
    pattern = '|'.join([t.strip() for t in selected_tags])
    mask = filtered['tags'].fillna('').str.contains(pattern, case=False, regex=True)
    filtered = filtered[mask]

if selected_ages:
    age_pattern = '|'.join([re.escape(a.strip()) for a in selected_ages])
    age_mask = filtered['tags'].fillna('').str.contains(age_pattern, case=False, regex=True)
    filtered = filtered[age_mask]

if filtered.empty:
    st.markdown("""
    <div class="empty-state">
        <div class="empty-icon">🏷️</div>
        <p>No events match those filters. Try removing some tags.</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# Metric cards
unique_venues = filtered['location_name'].nunique()
tag_counts = filtered['tags'].fillna('').str.split(',').explode().str.strip()
top_tag = tag_counts[tag_counts.isin(MASTER_TAGS)].mode().iloc[0] if not tag_counts.empty else "—"

st.markdown(f"""
<div class="metric-row">
    <div class="metric-card">
        <div class="metric-value">{len(filtered)}</div>
        <div class="metric-label">Events Found</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">{unique_venues}</div>
        <div class="metric-label">Venues</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">{radius} mi</div>
        <div class="metric-label">Search Radius</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">{top_tag}</div>
        <div class="metric-label">Top Category</div>
    </div>
</div>
""", unsafe_allow_html=True)

# Map + Events in two columns
col_map, col_events = st.columns([1, 1], gap="large")

with col_map:
    st.markdown('<div class="section-header">Event Map</div>', unsafe_allow_html=True)
    map_data = filtered[['latitude', 'longitude']].rename(columns={'latitude': 'lat', 'longitude': 'lon'})
    st.map(map_data, use_container_width=True)

with col_events:
    st.markdown(f'<div class="section-header">Events ({len(filtered)})</div>', unsafe_allow_html=True)

    # Scrollable event list — render each card individually
    for _, row in filtered.iterrows():
        st.markdown(render_event_card(row), unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Coverage Dashboard
# ---------------------------------------------------------------------------
with st.expander("RI Municipality Coverage"):
    try:
        session = SessionLocal()
        coverage_query = text('''
            SELECT m.name, m.county, m.library_status, m.recreation_status,
                   COUNT(DISTINCT s.id) as source_count
            FROM municipalities m
            LEFT JOIN sources s ON s.municipality_id = m.id AND s.is_active = true
            GROUP BY m.id, m.name, m.county, m.library_status, m.recreation_status
            ORDER BY m.name
        ''')
        result = session.execute(coverage_query)
        cov_df = pd.DataFrame(result.fetchall(), columns=result.keys())
        session.close()

        if not cov_df.empty:
            active_count = len(cov_df[(cov_df['library_status'] == 'active') | (cov_df['recreation_status'] == 'active')])
            total = len(cov_df)
            st.progress(active_count / total, text=f"{active_count}/{total} municipalities with active sources")

            # Color-code statuses
            def status_icon(status):
                return {"active": "🟢", "scouted": "🟡", "not_scouted": "🔴", "unreachable": "⚫"}.get(status, "⚪")

            display = cov_df.copy()
            display['Library'] = display['library_status'].apply(status_icon) + ' ' + display['library_status']
            display['Recreation'] = display['recreation_status'].apply(status_icon) + ' ' + display['recreation_status']
            display = display.rename(columns={'name': 'Municipality', 'county': 'County', 'source_count': 'Sources'})
            st.dataframe(display[['Municipality', 'County', 'Library', 'Recreation', 'Sources']],
                        use_container_width=True, hide_index=True)
        else:
            st.info("No municipality data. Run migrate_municipalities.py first.")
    except Exception as e:
        st.info(f"Coverage data unavailable: {e}")
