import re
from datetime import date, timedelta
import streamlit as st
import pandas as pd
import urllib.parse
from geopy.geocoders import Nominatim
from sqlalchemy import text
from database_manager import SessionLocal, Municipality, URLSubmission, Feedback
from config import APP_NAME, APP_TAGLINE, MASTER_TAGS, AUDIENCE_TAGS, DEFAULT_ZIP

st.set_page_config(page_title=f"{APP_NAME} Explorer", page_icon="🌀", layout="wide")

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

#MainMenu, footer {visibility: hidden;}

/* ---- Sidebar ---- */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #f0f2ff 0%, #e8eafc 50%, #f5f6ff 100%) !important;
    border-right: 2px solid #667eea30;
}
section[data-testid="stSidebar"] h3 {
    color: #1a1a2e !important;
}

/* ---- Accent pills (selected state) ---- */
button[data-testid="stBaseButton-pills"][aria-checked="true"] {
    background: #667eea !important;
    color: #fff !important;
    border-color: #667eea !important;
}
button[data-testid="stBaseButton-pills"] {
    border-radius: 20px !important;
    font-size: 0.82rem !important;
    padding: 4px 14px !important;
}

/* ---- Hero banner ---- */
.hero-banner {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 16px;
    padding: 1.6rem 2.5rem;
    margin-bottom: 1rem;
    color: white;
}
.hero-banner h1 {
    font-size: 2.4rem;
    font-weight: 700;
    margin: 0 0 0.25rem 0;
    letter-spacing: -0.5px;
}
.hero-banner p {
    font-size: 1.05rem;
    opacity: 0.9;
    margin: 0;
}

/* ---- Filter bar ---- */
.filter-bar {
    background: white;
    border-radius: 14px;
    padding: 1rem 1.2rem 0.6rem 1.2rem;
    margin-bottom: 1rem;
    box-shadow: 0 2px 12px rgba(0,0,0,0.05);
    border: 1px solid #f0f0f0;
}
.filter-label {
    font-size: 0.75rem;
    font-weight: 600;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
}

/* ---- Metric cards row ---- */
.metric-row {
    display: flex;
    gap: 1rem;
    margin-bottom: 1rem;
}
.metric-card {
    flex: 1;
    background: white;
    border-radius: 14px;
    padding: 1rem 1.2rem;
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
    font-size: 0.82rem;
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
    flex-wrap: wrap;
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
.btn-directions { background: #667eea; color: white !important; }
.btn-source    { background: #f0f0f0; color: #444 !important; }
.btn-signup    { background: #28a745; color: white !important; }

/* ---- Badges ---- */
.badge-free {
    display: inline-block;
    background: #d4edda; color: #155724;
    font-size: 0.75rem; font-weight: 600;
    padding: 2px 10px; border-radius: 12px; margin-right: 6px;
}
.badge-paid {
    display: inline-block;
    background: #fff3cd; color: #856404;
    font-size: 0.75rem; font-weight: 600;
    padding: 2px 10px; border-radius: 12px; margin-right: 6px;
}
.badge-recurring {
    display: inline-block;
    background: #e2e3f1; color: #5a4fcf;
    font-size: 0.72rem; font-weight: 500;
    padding: 2px 8px; border-radius: 12px; margin-right: 6px;
}

/* ---- Empty state ---- */
.empty-state {
    text-align: center;
    padding: 3rem 1rem;
    color: #999;
}
.empty-state .empty-icon { font-size: 3rem; margin-bottom: 0.5rem; }
.empty-state p { font-size: 1rem; }

/* ---- Mobile responsive ---- */
@media (max-width: 768px) {
    .hero-banner { padding: 1.2rem 1rem; }
    .hero-banner h1 { font-size: 1.6rem; }
    .metric-row { flex-wrap: wrap; }
    .metric-card { min-width: 45%; }
    .event-card { padding: 1rem; }
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
                e.event_date_start, e.cost_text, e.cost_cents,
                e.registration_url, e.is_recurring, e.recurrence_pattern,
                v.name as location_name, v.address, e.source_url,
                ST_Y(v.location::geometry) as latitude,
                ST_X(v.location::geometry) as longitude,
                (ST_Distance(v.location, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) / 1609.34) as distance_miles
            FROM events e
            JOIN venues v ON e.venue_id = v.id
            WHERE v.location IS NOT NULL
              AND ST_DWithin(v.location, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius_meters)
              AND (e.event_date_start >= CURRENT_DATE - INTERVAL '1 day' OR e.event_date_start IS NULL)
              AND e.parent_event_id IS NULL
            ORDER BY distance_miles ASC, e.event_date_start ASC NULLS LAST
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

    cost_badge = ""
    if pd.notnull(row.get('cost_cents')):
        if row['cost_cents'] == 0:
            cost_badge = '<span class="badge-free">FREE</span>'
        else:
            dollars = f"${row['cost_cents'] / 100:.0f}" if row['cost_cents'] % 100 == 0 else f"${row['cost_cents'] / 100:.2f}"
            cost_badge = f'<span class="badge-paid">{dollars}</span>'

    recurring_badge = ""
    if row.get('is_recurring'):
        pattern = row.get('recurrence_pattern', '') or 'Repeating'
        recurring_badge = f'<span class="badge-recurring">{pattern}</span>'

    tags_html = ""
    if pd.notnull(row['tags']) and str(row['tags']).strip():
        for tag in str(row['tags']).split(','):
            tag = tag.strip()
            if tag and tag != "Free":
                tags_html += f'<span class="event-tag">{tag}</span>'

    actions = ""
    if pd.notnull(row.get('registration_url')) and str(row.get('registration_url', '')).strip():
        actions += f'<a href="{row["registration_url"]}" target="_blank" class="btn-signup">Sign Up</a>'
    if pd.notnull(row.get('address')) and str(row.get('address', '')).strip():
        maps_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(str(row['address']))}"
        actions += f'<a href="{maps_url}" target="_blank" class="btn-directions">Directions</a>'
    if pd.notnull(row.get('source_url')) and str(row.get('source_url', '')).strip():
        actions += f'<a href="{row["source_url"]}" target="_blank" class="btn-source">Source</a>'

    return f"""
    <div class="event-card">
        <div class="event-title">{cost_badge}{recurring_badge}{title}</div>
        <div class="event-meta">
            {date_str} at {time_str} &nbsp;&bull;&nbsp; {location} &nbsp;&bull;&nbsp; {dist} mi away
        </div>
        <div>{tags_html}</div>
        <div class="event-desc">{desc_snippet}</div>
        <div class="event-actions">{actions}</div>
    </div>
    """


# ---------------------------------------------------------------------------
# Sidebar — location + utility forms only
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Find Events")
    zip_code = st.text_input("ZIP Code", value=DEFAULT_ZIP, label_visibility="collapsed",
                              placeholder="Enter ZIP code...")
    radius = st.slider("Radius (miles)", min_value=1, max_value=50, value=15)

    st.markdown("---")

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
        f"{APP_NAME} v1.1 &bull; Rhode Island</div>",
        unsafe_allow_html=True
    )


# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------

# Hero banner
st.markdown(f"""
<div class="hero-banner">
    <h1>{APP_NAME}</h1>
    <p>{APP_TAGLINE} — discover events near you across Rhode Island</p>
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

# ---------------------------------------------------------------------------
# Filter bar
# ---------------------------------------------------------------------------
st.markdown('<div class="filter-bar">', unsafe_allow_html=True)

# Row 1: Mode | Sort | Cost
r1a, r1b, r1c, r1d = st.columns([2, 1.5, 2, 1.5])
with r1a:
    st.markdown('<div class="filter-label">Mode</div>', unsafe_allow_html=True)
    mode = st.pills("Mode", ["🏠 Family", "🌐 All Events"], default="🏠 Family",
                    label_visibility="collapsed")
with r1b:
    st.markdown('<div class="filter-label">Sort by</div>', unsafe_allow_html=True)
    sort_option = st.radio("Sort", ["Closest", "Soonest"], horizontal=True,
                           label_visibility="collapsed")
with r1c:
    st.markdown('<div class="filter-label">When</div>', unsafe_allow_html=True)
    date_filter = st.pills("When", ["Any", "Today", "This Weekend", "Next 7 Days", "Next 30 Days"],
                           default="Any", label_visibility="collapsed")
with r1d:
    st.markdown('<div class="filter-label">Cost</div>', unsafe_allow_html=True)
    cost_filter = st.pills("Cost", ["All", "Free", "Paid"],
                           default="All", label_visibility="collapsed")

# Row 2: Category
st.markdown('<div class="filter-label" style="margin-top:0.7rem;">Category</div>', unsafe_allow_html=True)
selected_tags = st.pills("Category", MASTER_TAGS, selection_mode="multi", default=[],
                          label_visibility="collapsed")

# Row 3: Audience
st.markdown('<div class="filter-label" style="margin-top:0.5rem;">Audience</div>', unsafe_allow_html=True)
selected_ages = st.pills("Audience", AUDIENCE_TAGS, selection_mode="multi", default=[],
                          label_visibility="collapsed")

st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Apply filters
# ---------------------------------------------------------------------------
filtered = df.copy()

# Mode filter — Family hides Adults (18+) and Nightlife
family_mode = mode and "Family" in mode
if family_mode:
    adult_mask = filtered['tags'].fillna('').str.contains(
        r'Adults \(18\+\)|Nightlife', case=False, regex=True
    )
    filtered = filtered[~adult_mask]

# Category filter
if selected_tags:
    pattern = '|'.join([re.escape(t.strip()) for t in selected_tags])
    filtered = filtered[filtered['tags'].fillna('').str.contains(pattern, case=False, regex=True)]

# Audience filter
if selected_ages:
    age_pattern = '|'.join([re.escape(a.strip()) for a in selected_ages])
    filtered = filtered[filtered['tags'].fillna('').str.contains(age_pattern, case=False, regex=True)]

# Date filter
if date_filter and date_filter != "Any":
    today = date.today()
    filtered['_date_parsed'] = pd.to_datetime(filtered['event_date_start'], errors='coerce')
    if date_filter == "Today":
        filtered = filtered[filtered['_date_parsed'].dt.date == today]
    elif date_filter == "This Weekend":
        days_until_sat = (5 - today.weekday()) % 7
        sat = today + timedelta(days=days_until_sat)
        sun = sat + timedelta(days=1)
        filtered = filtered[filtered['_date_parsed'].dt.date.isin([sat, sun])]
    elif date_filter == "Next 7 Days":
        end = today + timedelta(days=7)
        filtered = filtered[(filtered['_date_parsed'].dt.date >= today) &
                            (filtered['_date_parsed'].dt.date <= end)]
    elif date_filter == "Next 30 Days":
        end = today + timedelta(days=30)
        filtered = filtered[(filtered['_date_parsed'].dt.date >= today) &
                            (filtered['_date_parsed'].dt.date <= end)]
    if '_date_parsed' in filtered.columns:
        filtered = filtered.drop(columns=['_date_parsed'])

# Cost filter
if cost_filter == "Free":
    filtered = filtered[filtered['cost_cents'] == 0]
elif cost_filter == "Paid":
    filtered = filtered[filtered['cost_cents'] > 0]

# Sort
if sort_option == "Soonest":
    filtered = filtered.sort_values(
        by=['event_date_start', 'distance_miles'], ascending=[True, True], na_position='last'
    ).reset_index(drop=True)
else:
    filtered = filtered.sort_values(
        by=['distance_miles', 'event_date_start'], ascending=[True, True], na_position='last'
    ).reset_index(drop=True)

# ---------------------------------------------------------------------------
# Metric row
# ---------------------------------------------------------------------------
unique_venues = filtered['location_name'].nunique()
free_count = int((filtered['cost_cents'] == 0).sum()) if 'cost_cents' in filtered.columns else 0
mode_label = "Family" if family_mode else "All"

st.markdown(f"""
<div class="metric-row">
    <div class="metric-card">
        <div class="metric-value">{len(filtered)}</div>
        <div class="metric-label">Events</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">{unique_venues}</div>
        <div class="metric-label">Venues</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">{free_count}</div>
        <div class="metric-label">Free</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">{radius} mi</div>
        <div class="metric-label">Radius</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">{mode_label}</div>
        <div class="metric-label">Mode</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Tabs: List | Map | Coverage
# ---------------------------------------------------------------------------
tab_list, tab_map, tab_coverage = st.tabs(["📋 Events", "🗺️ Map", "📊 Coverage"])

with tab_list:
    if df.empty:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">🔍</div>
            <p>No events found within that radius. Try increasing the distance.</p>
        </div>
        """, unsafe_allow_html=True)
    elif filtered.empty:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">🏷️</div>
            <p>No events match those filters. Try adjusting them above.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        for _, row in filtered.iterrows():
            st.markdown(render_event_card(row), unsafe_allow_html=True)

with tab_map:
    if filtered.empty:
        st.info("No events to show on map with current filters.")
    else:
        map_data = filtered[['latitude', 'longitude']].rename(
            columns={'latitude': 'lat', 'longitude': 'lon'}
        )
        st.map(map_data, use_container_width=True)

with tab_coverage:
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
            active_count = len(cov_df[
                (cov_df['library_status'] == 'active') |
                (cov_df['recreation_status'] == 'active')
            ])
            total = len(cov_df)
            st.progress(active_count / total,
                        text=f"{active_count}/{total} municipalities with active sources")

            def status_icon(s):
                return {"active": "🟢", "scouted": "🟡",
                        "not_scouted": "🔴", "unreachable": "⚫"}.get(s, "⚪")

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
