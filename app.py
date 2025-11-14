# app.py - Unified dashboard for Colab (inline) and PythonAnywhere deployment
# - supports inline JupyterDash if available, otherwise normal Dash
# - auto-normalizes multiple common CSV column names
# - produces 7 charts + table, creates downloadable HTML report
# - export `server = app.server` for PythonAnywhere WSGI

import os
import sys
import re
import datetime
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.io as pio

# Try to import JupyterDash for inline notebook support
try:
    from jupyter_dash import JupyterDash
    JUPYTER_AVAILABLE = True
except Exception:
    JUPYTER_AVAILABLE = False

from dash import Dash, dcc, html, Input, Output, State, dash_table
import dash_bootstrap_components as dbc

# -------------------------
# Configuration / Data Load
# -------------------------
DATA_PATH = "merged_collisions.csv"

# Initialize empty df to avoid NameErrors
df = pd.DataFrame()

if os.path.exists(DATA_PATH):
    try:
        df = pd.read_csv(DATA_PATH, encoding='utf-8')
        print("SUCCESS: loaded", DATA_PATH)
    except Exception as e:
        print("ERROR: failed to read CSV:", e)
else:
    print(f"WARNING: {DATA_PATH} not found. Dashboard will start with empty dataset.")

# Normalize column names: strip and uppercase for matching
if not df.empty:
    df.columns = [c.strip() for c in df.columns]

# -------------------------
# Canonical column mapping
# -------------------------
# We will try multiple common names and create canonical names used by the app.
def _first_existing(col_candidates, df_cols):
    for c in col_candidates:
        if c in df_cols:
            return c
    return None

# Potential column name candidates
candidates = {
    "CRASH_DATE": ["CRASH DATE", "CRASH_DATE", "DATE"],
    "COLLISION_ID": ["COLLISION_ID", "CRASH_ID", "UNIQUE_ID", "COLLISION ID"],
    "BOROUGH": ["BOROUGH"],
    "YEAR": ["YEAR", "Year", "CRASH YEAR"],
    "CONTRIBUTING_FACTOR": ["CONTRIBUTING_FACTOR_1", "CONTRIBUTING FACTOR VEHICLE 1", "CONTRIBUTING FACTOR"],
    "VEHICLE": ["VEHICLE TYPE CODE 1", "VEHICLE TYPE CODE", "VEHICLE"],
    "PERSON_TYPE": ["PERSON_TYPE", "PERSON TYPE"],
    "NUM_INJURED": ["NUMBER OF PERSONS INJURED", "PERSONS INJURED", "PERSON_INJURY", "INJURED"],
    "NUM_KILLED": ["NUMBER OF PERSONS KILLED", "PERSONS KILLED", "PERSON_KILLED", "KILLED"],
    "LAT": ["LATITUDE", "LAT"],
    "LON": ["LONGITUDE", "LON", "LONG"]
}

# Map detected column names to canonical names used below
col_map = {}
if not df.empty:
    for canon, cand_list in candidates.items():
        found = _first_existing(cand_list, df.columns)
        if found:
            col_map[canon] = found

    # If we have CRASH_DATE but not YEAR, try to create YEAR
    if "YEAR" not in col_map and "CRASH_DATE" in col_map:
        try:
            df["YEAR"] = pd.to_datetime(df[col_map["CRASH_DATE"]], errors="coerce").dt.year
            col_map["YEAR"] = "YEAR"
            print("INFO: created YEAR from", col_map["CRASH_DATE"])
        except Exception as e:
            print("WARN: couldn't parse CRASH_DATE -> YEAR:", e)

    # Create numeric injury/killed columns from available names; ensure canonical names exist in df
    if "NUM_INJURED" in col_map:
        df["NUM_INJURED"] = pd.to_numeric(df[col_map["NUM_INJURED"]], errors="coerce").fillna(0).astype(int)
    else:
        # try alternative common name PERSON_INJURY
        alt = _first_existing(["PERSON_INJURY", "PERSON INJURY"], df.columns)
        if alt:
            df["NUM_INJURED"] = pd.to_numeric(df[alt], errors="coerce").fillna(0).astype(int)
            col_map["NUM_INJURED"] = "NUM_INJURED"

    if "NUM_KILLED" in col_map:
        df["NUM_KILLED"] = pd.to_numeric(df[col_map["NUM_KILLED"]], errors="coerce").fillna(0).astype(int)
    else:
        alt = _first_existing(["PERSON_KILLED", "PERSON KILLED"], df.columns)
        if alt:
            df["NUM_KILLED"] = pd.to_numeric(df[alt], errors="coerce").fillna(0).astype(int)
            col_map["NUM_KILLED"] = "NUM_KILLED"

    # Ensure LAT/LON canonical columns exist (copy if detected)
    if "LAT" in col_map and col_map["LAT"] != "LAT":
        df["LAT"] = pd.to_numeric(df[col_map["LAT"]], errors="coerce")
    if "LON" in col_map and col_map["LON"] != "LON":
        df["LON"] = pd.to_numeric(df[col_map["LON"]], errors="coerce")

# Fallback canonical names (even if not in col_map)
BOROUGH_COL = col_map.get("BOROUGH", "BOROUGH")
YEAR_COL = col_map.get("YEAR", "YEAR")
CONTRIB_COL = col_map.get("CONTRIBUTING_FACTOR", "CONTRIBUTING FACTOR")
VEHICLE_COL = col_map.get("VEHICLE", "VEHICLE")
PERSON_TYPE_COL = col_map.get("PERSON_TYPE", "PERSON_TYPE")
NUM_INJURED_COL = "NUM_INJURED" if "NUM_INJURED" in df.columns else (col_map.get("NUM_INJURED", None))
NUM_KILLED_COL = "NUM_KILLED" if "NUM_KILLED" in df.columns else (col_map.get("NUM_KILLED", None))
LAT_COL = "LAT" if "LAT" in df.columns else col_map.get("LAT", None)
LON_COL = "LON" if "LON" in df.columns else col_map.get("LON", None)
COLLISION_ID_COL = col_map.get("COLLISION_ID", None)

# Some helpful prints for debugging (will appear in logs)
print("Detected column mapping (col_map):", col_map)
print("Canonical columns used:", {
    "BOROUGH": BOROUGH_COL,
    "YEAR": YEAR_COL,
    "CONTRIBUTION": CONTRIB_COL,
    "VEHICLE": VEHICLE_COL,
    "PERSON_TYPE": PERSON_TYPE_COL,
    "NUM_INJURED": NUM_INJURED_COL,
    "NUM_KILLED": NUM_KILLED_COL,
    "LAT": LAT_COL,
    "LON": LON_COL,
    "COLLISION_ID": COLLISION_ID_COL
})

# -------------------------
# Helper functions
# -------------------------
def uniq_sorted_options(colname):
    """Return dropdown options list of dicts [{'label','value'}, ...] or empty list."""
    if df.empty or not colname:
        return []
    if colname not in df.columns:
        return []
    vals = df[colname].dropna().astype(str).unique().tolist()
    vals = sorted([v for v in vals if v not in ("", "nan", "NaN")], key=lambda s: s.lower())
    return [{"label": v, "value": v} for v in vals]

def uniq_sorted_values(colname):
    """Return simple list of values (for range marks etc.)."""
    if df.empty or not colname or colname not in df.columns:
        return []
    vals = pd.to_numeric(df[colname], errors="coerce").dropna().unique().tolist()
    vals = sorted([int(v) for v in vals])
    return vals

def parse_search(q):
    """Basic parser: extracts year, borough, person type keywords."""
    out = {}
    if not q or not isinstance(q, str):
        return out
    ql = q.lower()
    m = re.search(r'(20\d{2}|19\d{2})', ql)
    if m:
        out["YEAR"] = int(m.group(0))
    # borough names: check known borough list
    if BOROUGH_COL in df.columns:
        for b in df[BOROUGH_COL].dropna().astype(str).unique():
            if b.lower() in ql:
                out["BOROUGH"] = b
                break
    # person types
    if "pedestrian" in ql:
        out["PERSON_TYPE"] = "Pedestrian"
    elif "bicyclist" in ql or "bicycle" in ql:
        out["PERSON_TYPE"] = "Bicyclist"
    return out

def create_html_report(figs: dict, df_filtered: pd.DataFrame):
    """Return bytes (utf-8) of a full HTML report with embedded plotly charts (CDN)."""
    parts = []
    parts.append("<html><head><meta charset='utf-8'><title>Collisions Report</title></head><body>")
    parts.append(f"<h1>Generated Report — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</h1>")
    parts.append(f"<p>Filtered records: {len(df_filtered)}</p>")

    # Order of sections - attempt to include only those present
    order = [
        ("Top 10 Factors", "Top 10 Contributing Factors"),
        ("Incidents by Year", "Incidents by Year"),
        ("Injuries by Borough", "Injuries by Borough"),
        ("Killed vs Injured", "Killed vs Injured"),
        ("Person Type Distribution", "Person Type Distribution"),
        ("Year vs Borough Heatmap", "Year vs Borough Heatmap")
    ]
    for key, title in order:
        if key in figs:
            parts.append(f"<h2>{title}</h2>")
            parts.append(pio.to_html(figs[key], include_plotlyjs="cdn", full_html=False))

    parts.append("<h2>Sample Data (first 100 rows)</h2>")
    parts.append(df_filtered.head(100).to_html(index=False))
    parts.append("</body></html>")
    return "\n".join(parts).encode("utf-8")

# -------------------------
# App creation (choose JupyterDash in notebooks)
# -------------------------
USE_JUPYTER = ("ipykernel" in sys.modules) and JUPYTER_AVAILABLE

AppClass = JupyterDash if USE_JUPYTER else Dash
app = AppClass(__name__, external_stylesheets=[dbc.themes.LUX], suppress_callback_exceptions=True)
server = app.server  # for WSGI (PythonAnywhere)

# -------------------------
# Layout
# -------------------------
# Prepare dropdown options
borough_opts = uniq_sorted_options(BOROUGH_COL)
year_values = uniq_sorted_values(YEAR_COL)
min_year = min(year_values) if year_values else 2020
max_year = max(year_values) if year_values else datetime.datetime.utcnow().year
contrib_opts = uniq_sorted_options(CONTRIB_COL)
injury_opts = uniq_sorted_options(PERSON_TYPE_COL)  # person type dropdown
vehicle_opts = uniq_sorted_options(VEHICLE_COL)

app.layout = dbc.Container([
    dbc.Row(dbc.Col(html.H2("Interactive Collisions Dashboard", className="text-primary mt-3 mb-3"))),
    dbc.Row([
        dbc.Col([
            html.Div([
                html.Label("Search (e.g., 'Brooklyn 2022 pedestrian crashes')"),
                dcc.Input(id='search-box', type='text', placeholder='Type query and press Generate', debounce=True, style={'width':'100%'}),
            ], className="mb-3"),
            html.Label("Borough"),
            dcc.Dropdown(id='borough-filter', options=borough_opts, multi=True, placeholder="Select Borough(s)"),
            html.Br(),
            html.Label("Year (range)"),
            dcc.RangeSlider(
                id='year-range',
                min=min_year,
                max=max_year,
                step=1,
                value=[min_year, max_year],
                marks={y: str(y) for y in year_values} if year_values else None
            ),
            html.Br(),
            html.Label("Vehicle Type"),
            dcc.Dropdown(id='vehicle-filter', options=vehicle_opts, multi=True, placeholder="Select Vehicle Type(s)"),
            html.Br(),
            html.Label("Contributing Factor"),
            dcc.Dropdown(id='factor-filter', options=contrib_opts, multi=True, placeholder="Select Factor(s)"),
            html.Br(),
            html.Label("Person Type (role)"),
            dcc.Dropdown(id='person-type-filter', options=injury_opts, multi=True, placeholder="Select Person Type(s)"),
            html.Br(),
            dbc.Button("Generate Report", id='generate-btn', color='primary', className="me-2"),
            dbc.Button("Download Report (HTML)", id='download-btn', color='secondary'),
            dcc.Download(id='download-report'),
            html.Div(id='status', style={'marginTop':'10px'})
        ], width=3, className="bg-light p-3"),
        dbc.Col([
            dcc.Tabs(id='tabs', value='tab-1', children=[
                dcc.Tab(label='Overview', value='tab-1', children=[
                    dcc.Loading(dcc.Graph(id='bar-chart', config={'displayModeBar': False}), type='default'),
                    dcc.Loading(dcc.Graph(id='line-chart', config={'displayModeBar': False}), type='default'),
                    dcc.Loading(dcc.Graph(id='borough-injuries-chart', config={'displayModeBar': False}), type='default'),
                    dcc.Loading(dcc.Graph(id='killed-injured-chart', config={'displayModeBar': False}), type='default'),
                ]),
                dcc.Tab(label='Distribution', value='tab-2', children=[
                    dcc.Loading(dcc.Graph(id='pie-chart', config={'displayModeBar': False}), type='default'),
                    dcc.Loading(dcc.Graph(id='heatmap', config={'displayModeBar': False}), type='default'),
                ]),
                dcc.Tab(label='Map & Table', value='tab-3', children=[
                    dcc.Loading(dcc.Graph(id='map-chart', config={'scrollZoom': True}), type='default'),
                    html.H5("Filtered Data Sample"),
                    dcc.Loading(dash_table.DataTable(
                        id='data-table',
                        columns=[{"name": i, "id": i} for i in (df.columns.tolist() if not df.empty else [])],
                        page_size=10,
                        style_table={'overflowX': 'auto'}
                    ), type='default')
                ])
            ])
        ], width=9)
    ])
], fluid=True)

# -------------------------
# Main callback: update all charts + table
# -------------------------
@app.callback(
    [Output('status', 'children'),
     Output('bar-chart', 'figure'),
     Output('line-chart', 'figure'),
     Output('borough-injuries-chart', 'figure'),
     Output('killed-injured-chart', 'figure'),
     Output('pie-chart', 'figure'),
     Output('heatmap', 'figure'),
     Output('map-chart', 'figure'),
     Output('data-table', 'data')],
    [Input('generate-btn', 'n_clicks')],
    [State('search-box', 'value'),
     State('borough-filter', 'value'),
     State('year-range', 'value'),
     State('vehicle-filter', 'value'),
     State('factor-filter', 'value'),
     State('person-type-filter', 'value')],
)
def update_all(n_clicks, search_q, borough_sel, year_range, vehicle_sel, factor_sel, person_type_sel):
    # empty/default figures
    empty_fig = px.scatter(title="No Data", template='plotly_white')
    empty_map = px.scatter_mapbox(title="No Data")
    if df.empty:
        return "Data not loaded.", empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, empty_map, []

    # default initial load (no click) -> show sample
    if not n_clicks:
        df_filtered = df.head(500).copy()
        status = "Initial load (first 500 rows). Click Generate to apply filters."
    else:
        df_filtered = df.copy()
        msgs = []

        parsed = parse_search(search_q)
        # year filtering from range slider
        if year_range and len(year_range) == 2:
            start_year, end_year = int(year_range[0]), int(year_range[1])
            if YEAR_COL in df_filtered.columns:
                df_filtered = df_filtered[(pd.to_numeric(df_filtered[YEAR_COL], errors="coerce") >= start_year) & (pd.to_numeric(df_filtered[YEAR_COL], errors="coerce") <= end_year)]
                msgs.append(f"Years: {start_year}-{end_year}")

        if borough_sel:
            if BOROUGH_COL in df_filtered.columns:
                df_filtered = df_filtered[df_filtered[BOROUGH_COL].isin(borough_sel)]
                msgs.append(f"Boroughs: {', '.join([str(b) for b in borough_sel])}")

        if factor_sel and CONTRIB_COL in df_filtered.columns:
            df_filtered = df_filtered[df_filtered[CONTRIB_COL].isin(factor_sel)]
            msgs.append(f"Factors: {', '.join([str(f) for f in factor_sel])}")

        if vehicle_sel and VEHICLE_COL in df_filtered.columns:
            df_filtered = df_filtered[df_filtered[VEHICLE_COL].isin(vehicle_sel)]
            msgs.append(f"Vehicles: {', '.join([str(v) for v in vehicle_sel])}")

        if person_type_sel and PERSON_TYPE_COL in df_filtered.columns:
            df_filtered = df_filtered[df_filtered[PERSON_TYPE_COL].isin(person_type_sel)]
            msgs.append(f"Person types: {', '.join([str(p) for p in person_type_sel])}")

        # parse_search outputs
        if parsed.get("YEAR") and YEAR_COL in df_filtered.columns:
            df_filtered = df_filtered[pd.to_numeric(df_filtered[YEAR_COL], errors="coerce") == parsed["YEAR"]]
            msgs.append(f"Parsed year: {parsed['YEAR']}")
        if parsed.get("BOROUGH") and BOROUGH_COL in df_filtered.columns:
            df_filtered = df_filtered[df_filtered[BOROUGH_COL] == parsed["BOROUGH"]]
            msgs.append(f"Parsed borough: {parsed['BOROUGH']}")
        if parsed.get("PERSON_TYPE") and PERSON_TYPE_COL in df_filtered.columns:
            df_filtered = df_filtered[df_filtered[PERSON_TYPE_COL].str.contains(parsed["PERSON_TYPE"], case=False, na=False)]
            msgs.append(f"Parsed person_type: {parsed['PERSON_TYPE']}")

        status = f"✅ {len(df_filtered)} rows matched. " + "; ".join(msgs) if msgs else f"✅ {len(df_filtered)} rows matched."

    # --- Build figures ---
    figs = {}

    # 1) Top 10 contributing factors
    if CONTRIB_COL in df_filtered.columns:
        bar_data = df_filtered[CONTRIB_COL].fillna("Unknown").astype(str).value_counts().nlargest(10).reset_index()
        bar_data.columns = ['factor', 'count']
        figs['bar'] = px.bar(bar_data, x='factor', y='count', title='Top 10 Contributing Factors', template='plotly_white')
    else:
        figs['bar'] = px.bar(title="Contributing Factor data missing", template='plotly_white')

    # 2) Crashes over time (line)
    if YEAR_COL in df_filtered.columns:
        # try use collision-level if COLLISION_ID exists
        if COLLISION_ID_COL and COLLISION_ID_COL in df_filtered.columns:
            crash_df = df_filtered.drop_duplicates(subset=[COLLISION_ID_COL]).copy()
            line_counts = pd.to_numeric(crash_df[YEAR_COL], errors="coerce").dropna().astype(int).value_counts().reset_index()
            line_counts.columns = [YEAR_COL, 'count']
            line_counts = line_counts.sort_values(by=YEAR_COL)
        else:
            line_counts = pd.to_numeric(df_filtered[YEAR_COL], errors="coerce").dropna().astype(int).value_counts().reset_index()
            line_counts.columns = [YEAR_COL, 'count']
            line_counts = line_counts.sort_values(by=YEAR_COL)
        figs['line'] = px.line(line_counts, x=YEAR_COL, y='count', title='Total Crashes by Year', template='plotly_white')
    else:
        figs['line'] = px.line(title="Year data missing", template='plotly_white')

    # 3) Injuries by borough
    if BOROUGH_COL in df_filtered.columns and NUM_INJURED_COL:
        temp = df_filtered.copy()
        # ensure numeric column exists
        if NUM_INJURED_COL not in temp.columns:
            temp["NUM_INJURED"] = pd.to_numeric(temp.get(col_map.get("NUM_INJURED", ""), 0), errors="coerce").fillna(0)
        agg = temp.groupby(BOROUGH_COL)["NUM_INJURED"].sum().reset_index()
        agg.columns = [BOROUGH_COL, "Total Injured"]
        figs['borough_injuries'] = px.bar(agg, x=BOROUGH_COL, y="Total Injured", title='Total Injured Persons per Borough', template='plotly_white')
    else:
        figs['borough_injuries'] = px.bar(title="Injury or Borough data missing", template='plotly_white')

    # 4) Killed vs Injured area chart
    if YEAR_COL in df_filtered.columns and (NUM_INJURED_COL or NUM_KILLED_COL):
        # build severity by year
        temp = df_filtered.copy()
        if NUM_INJURED_COL not in temp.columns:
            temp["NUM_INJURED"] = pd.to_numeric(temp.get(col_map.get("NUM_INJURED", ""), 0), errors="coerce").fillna(0)
        if NUM_KILLED_COL not in temp.columns:
            temp["NUM_KILLED"] = pd.to_numeric(temp.get(col_map.get("NUM_KILLED", ""), 0), errors="coerce").fillna(0)
        if COLLISION_ID_COL and COLLISION_ID_COL in temp.columns:
            temp = temp.drop_duplicates(subset=[COLLISION_ID_COL])
        severity = temp.groupby(YEAR_COL)[["NUM_KILLED","NUM_INJURED"]].sum().reset_index()
        severity_long = pd.melt(severity, id_vars=[YEAR_COL], value_vars=["NUM_KILLED","NUM_INJURED"], var_name="Severity Type", value_name="Count")
        figs['killed_injured'] = px.area(severity_long, x=YEAR_COL, y='Count', color='Severity Type', title='Killed vs Injured Over Time', template='plotly_white', line_group='Severity Type')
    else:
        figs['killed_injured'] = px.area(title="Killed/Injured or Year data missing", template='plotly_white')

    # 5) Person type distribution (pie)
    if PERSON_TYPE_COL in df_filtered.columns:
        pie_data = df_filtered[PERSON_TYPE_COL].dropna().astype(str).value_counts().nlargest(10).reset_index()
        pie_data.columns = [PERSON_TYPE_COL, 'count']
        figs['pie'] = px.pie(pie_data, names=PERSON_TYPE_COL, values='count', title='Distribution of Involved Person Types', hole=0.3, template='plotly_white')
    else:
        figs['pie'] = px.pie(title="Person type data missing", template='plotly_white')

    # 6) Year vs Borough heatmap
    if YEAR_COL in df_filtered.columns and BOROUGH_COL in df_filtered.columns:
        heat = df_filtered.copy()
        if COLLISION_ID_COL and COLLISION_ID_COL in heat.columns:
            heat = heat.drop_duplicates(subset=[COLLISION_ID_COL])
        heat_group = heat.groupby([YEAR_COL, BOROUGH_COL]).size().reset_index(name='count')
        figs['heatmap'] = px.density_heatmap(heat_group, x=YEAR_COL, y=BOROUGH_COL, z='count', title='Incidents: Year vs Borough Heatmap', template='plotly_white')
    else:
        figs['heatmap'] = px.density_heatmap(title="Year/Borough data missing", template='plotly_white')

    # 7) Map
    if LAT_COL and LON_COL and LAT_COL in df_filtered.columns and LON_COL in df_filtered.columns and not df_filtered[[LAT_COL, LON_COL]].dropna().empty:
        df_map = df_filtered.dropna(subset=[LAT_COL, LON_COL]).copy()
        # sample for performance
        n_sample = min(len(df_map), 2000)
        df_map = df_map.sample(n_sample) if len(df_map) > n_sample else df_map
        # ensure numeric severity columns
        if "NUM_INJURED" not in df_map.columns:
            df_map["NUM_INJURED"] = pd.to_numeric(df_map.get(col_map.get("NUM_INJURED", ""), 0), errors="coerce").fillna(0)
        if "NUM_KILLED" not in df_map.columns:
            df_map["NUM_KILLED"] = pd.to_numeric(df_map.get(col_map.get("NUM_KILLED", ""), 0), errors="coerce").fillna(0)
        df_map["SEVERITY"] = df_map["NUM_INJURED"] + df_map["NUM_KILLED"]
        df_map["SEVERITY_SIZE"] = df_map["SEVERITY"].apply(lambda x: 1 if x == 0 else x)
        figs['map'] = px.scatter_mapbox(df_map, lat=LAT_COL, lon=LON_COL, color='SEVERITY', size='SEVERITY_SIZE', hover_data=[BOROUGH_COL, YEAR_COL] if BOROUGH_COL in df_map.columns else [YEAR_COL], zoom=9, height=400, title='Crash Locations (sample)', mapbox_style='carto-positron', template='plotly_white')
        figs['map'].update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    else:
        figs['map'] = px.scatter(title="Geolocation data missing")

    table_data = df_filtered.head(1000).to_dict('records')

    return status, figs['bar'], figs['line'], figs['borough_injuries'], figs['killed_injured'], figs['pie'], figs['heatmap'], figs['map'], table_data

# -------------------------
# Report download callback
# -------------------------
@app.callback(
    Output('download-report', 'data'),
    Input('download-btn', 'n_clicks'),
    [State('search-box', 'value'),
     State('borough-filter', 'value'),
     State('year-range', 'value'),
     State('vehicle-filter', 'value'),
     State('factor-filter', 'value'),
     State('person-type-filter', 'value')],
    prevent_initial_call=True
)
def download_report(n_clicks, search_q, borough_sel, year_range, vehicle_sel, factor_sel, person_type_sel):
    # Re-run same filtering as update_all (simplified)
    if df.empty:
        return dcc.send_bytes(b"","report.html")

    df_filtered = df.copy()

    parsed = parse_search(search_q)
    if year_range and len(year_range) == 2 and YEAR_COL in df_filtered.columns:
        start_year, end_year = int(year_range[0]), int(year_range[1])
        df_filtered = df_filtered[(pd.to_numeric(df_filtered[YEAR_COL], errors="coerce") >= start_year) & (pd.to_numeric(df_filtered[YEAR_COL], errors="coerce") <= end_year)]
    if borough_sel and BOROUGH_COL in df_filtered.columns:
        df_filtered = df_filtered[df_filtered[BOROUGH_COL].isin(borough_sel)]
    if factor_sel and CONTRIB_COL in df_filtered.columns:
        df_filtered = df_filtered[df_filtered[CONTRIB_COL].isin(factor_sel)]
    if vehicle_sel and VEHICLE_COL in df_filtered.columns:
        df_filtered = df_filtered[df_filtered[VEHICLE_COL].isin(vehicle_sel)]
    if person_type_sel and PERSON_TYPE_COL in df_filtered.columns:
        df_filtered = df_filtered[df_filtered[PERSON_TYPE_COL].isin(person_type_sel)]
    if parsed.get("YEAR") and YEAR_COL in df_filtered.columns:
        df_filtered = df_filtered[pd.to_numeric(df_filtered[YEAR_COL], errors="coerce") == parsed["YEAR"]]
    if parsed.get("BOROUGH") and BOROUGH_COL in df_filtered.columns:
        df_filtered = df_filtered[df_filtered[BOROUGH_COL] == parsed["BOROUGH"]]
    if parsed.get("PERSON_TYPE") and PERSON_TYPE_COL in df_filtered.columns:
        df_filtered = df_filtered[df_filtered[PERSON_TYPE_COL].str.contains(parsed["PERSON_TYPE"], case=False, na=False)]

    figs = {}
    # build minimal set of figures for the report (reuse patterns from update_all)
    try:
        if CONTRIB_COL in df_filtered.columns:
            bar_data = df_filtered[CONTRIB_COL].fillna("Unknown").astype(str).value_counts().nlargest(10).reset_index()
            bar_data.columns = ['factor', 'count']
            figs['Top 10 Factors'] = px.bar(bar_data, x='factor', y='count', title='Top 10 Contributing Factors')

        if YEAR_COL in df_filtered.columns:
            line_counts = pd.to_numeric(df_filtered[YEAR_COL], errors="coerce").dropna().astype(int).value_counts().reset_index()
            line_counts.columns = [YEAR_COL, 'count']
            line_counts = line_counts.sort_values(by=YEAR_COL)
            figs['Incidents by Year'] = px.line(line_counts, x=YEAR_COL, y='count', title='Incidents by Year')

            # killed vs injured
            temp = df_filtered.copy()
            temp["NUM_INJURED"] = pd.to_numeric(temp.get("NUM_INJURED", 0), errors="coerce").fillna(0)
            temp["NUM_KILLED"] = pd.to_numeric(temp.get("NUM_KILLED", 0), errors="coerce").fillna(0)
            if COLLISION_ID_COL and COLLISION_ID_COL in temp.columns:
                temp = temp.drop_duplicates(subset=[COLLISION_ID_COL])
            severity = temp.groupby(YEAR_COL)[["NUM_KILLED","NUM_INJURED"]].sum().reset_index()
            severity_long = pd.melt(severity, id_vars=[YEAR_COL], value_vars=["NUM_KILLED","NUM_INJURED"], var_name="Severity Type", value_name="Count")
            figs['Killed vs Injured'] = px.area(severity_long, x=YEAR_COL, y='Count', color='Severity Type', title='Killed vs Injured')

        if BOROUGH_COL in df_filtered.columns and ("NUM_INJURED" in df_filtered.columns or NUM_INJURED_COL):
            temp = df_filtered.copy()
            if "NUM_INJURED" not in temp.columns:
                temp["NUM_INJURED"] = pd.to_numeric(temp.get(col_map.get("NUM_INJURED", ""), 0), errors="coerce").fillna(0)
            agg = temp.groupby(BOROUGH_COL)["NUM_INJURED"].sum().reset_index()
            agg.columns = [BOROUGH_COL, "Total Injured"]
            figs['Injuries by Borough'] = px.bar(agg, x=BOROUGH_COL, y='Total Injured', title='Injuries by Borough')

        if PERSON_TYPE_COL in df_filtered.columns:
            pie_data = df_filtered[PERSON_TYPE_COL].dropna().astype(str).value_counts().nlargest(10).reset_index()
            pie_data.columns = [PERSON_TYPE_COL, 'count']
            figs['Person Type Distribution'] = px.pie(pie_data, names=PERSON_TYPE_COL, values='count', title='Person Type Distribution', hole=0.3)

        if YEAR_COL in df_filtered.columns and BOROUGH_COL in df_filtered.columns:
            heat = df_filtered.copy()
            if COLLISION_ID_COL and COLLISION_ID_COL in heat.columns:
                heat = heat.drop_duplicates(subset=[COLLISION_ID_COL])
            heat_group = heat.groupby([YEAR_COL, BOROUGH_COL]).size().reset_index(name='count')
            figs['Year vs Borough Heatmap'] = px.density_heatmap(heat_group, x=YEAR_COL, y=BOROUGH_COL, z='count', title='Year vs Borough Heatmap')

    except Exception as e:
        print("WARN: error creating report figures:", e)

    html_bytes = create_html_report(figs, df_filtered)
    filename = f"collision_report_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.html"
    return dcc.send_bytes(html_bytes, filename=filename)

# -------------------------
# Run behavior: inline if Jupyter, otherwise don't auto-run (WSGI expects external runner)
# -------------------------
if __name__ == "__main__":
    if USE_JUPYTER:
        # JupyterDash supports run_server with mode='inline'
        app.run_server(mode='inline', port=8051)
    else:
        # normal Dash; useful for local dev (not used by PythonAnywhere WSGI)
        app.run(port=8051, debug=False)
