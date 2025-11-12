# === app.py: Final Full Version for PythonAnywhere Deployment ===

# 1) Imports
from dash import Dash, dcc, html, Input, Output, State, dash_table
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
import datetime
import plotly.io as pio
import re
import os
import numpy as np # Added numpy for robust data cleaning

# ===============================================
# CONFIGURATION AND DATA LOADING
# ===============================================

# --- DATA PATH for PythonAnywhere Deployment ---
# The file must be in the same directory as app.py
DATA_PATH = "merged_collisions.csv" 
df = pd.DataFrame() # Initialize df to ensure it always exists

try:
    df = pd.read_csv(DATA_PATH, encoding='utf-8') 
    print("SUCCESS: Data loaded successfully.")
except FileNotFoundError:
    print(f"ERROR: Data file '{DATA_PATH}' not found. Check PythonAnywhere file manager.")
except Exception as e:
    print(f"CRITICAL ERROR: Failed to load CSV file due to read error: {e}")

# If data loading failed, the empty DataFrame created above is used.
if df.empty:
    print("Warning: Dashboard running with empty data.")
    
# --- Data Pre-processing (If loading was successful) ---
if not df.empty:
    df.columns = [c.strip() for c in df.columns]
    if 'CRASH DATE' in df.columns:
        # NOTE: Using 'Year' as the column for year in the data processing
        df['Year'] = pd.to_datetime(df['CRASH DATE'], errors='coerce').dt.year.astype('Int64')

# Choose filter columns (fallbacks)
borough_col = 'BOROUGH' if 'BOROUGH' in df.columns else None
year_col = 'Year' if 'Year' in df.columns else None
vehicle_col = 'VEHICLE TYPE CODE 1' if 'VEHICLE TYPE CODE 1' in df.columns else ('VEHICLE TYPE CODE' if 'VEHICLE TYPE CODE' in df.columns else None)
contrib_col = 'CONTRIBUTING_FACTOR_1' if 'CONTRIBUTING_FACTOR_1' in df.columns else ('CONTRIBUTING FACTOR VEHICLE 1' if 'CONTRIBUTING FACTOR VEHICLE 1' in df.columns else None)
injury_col = 'PERSON_INJURY' if 'PERSON_INJURY' in df.columns else None
lat_col = 'LATITUDE' if 'LATITUDE' in df.columns else None
lon_col = 'LONGITUDE' if 'LONGITUDE' in df.columns else None
person_type_col = 'PERSON_TYPE' if 'PERSON_TYPE' in df.columns else None

# ===============================================
# HELPER FUNCTIONS (Standard)
# ===============================================

def uniq_sorted(col):
    if col and col in df.columns:
        temp_df = df[col].dropna()
        if col == year_col:
            vals = temp_df.unique().tolist()
            vals = sorted([v for v in vals if pd.notna(v)])
        else:
            vals = temp_df.astype(str).unique().tolist()
            vals = sorted(vals, key=lambda s: s.lower())
        return [{'label':str(v),'value':v} for v in vals]
    return []

def parse_search(q, df_cols):
    out = {}
    if not q:
        return out
    ql = q.lower()
    m = re.search(r'(20\d{2}|19\d{2})', ql)
    if m:
        out['Year'] = int(m.group(0))
    if 'BOROUGH' in df_cols:
        for b in df['BOROUGH'].dropna().astype(str).unique():
            if b.lower() in ql:
                out['BOROUGH'] = b
                break
    if 'PERSON_TYPE' in df_cols:
        if 'pedestrian' in ql: out['PERSON_TYPE'] = 'Pedestrian'
        elif 'bicyclist' in ql: out['PERSON_TYPE'] = 'Bicyclist'
    return out

def create_html_report(figs: dict, df_filtered: pd.DataFrame):
    html_parts = []
    html_parts.append("<html><head><meta charset='utf-8'><title>Report</title></head><body>")
    html_parts.append(f"<h1>Generated Report — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</h1>")
    html_parts.append(f"<p>Filtered to {len(df_filtered)} records.</p>")
    
    # Sort figures for logical report order
    fig_order = ['Top 10 Factors', 'Incidents by Year', 'Injuries by Borough', 
                 'Killed vs Injured', 'Person Type Distribution', 'Year vs Borough Heatmap']

    for name in fig_order:
        if name in figs:
            html_parts.append(f"<h2>{name}</h2>")
            html_parts.append(pio.to_html(figs[name], include_plotlyjs='cdn', full_html=False))

    html_parts.append("<h2>Filtered Data Sample (First 100 Rows)</h2>")
    html_parts.append(df_filtered.head(100).to_html(index=False))
    html_parts.append("</body></html>")
    return "\n".join(html_parts).encode('utf-8')


# ===============================================
# DASH APPLICATION LAYOUT (UPDATED for 7 charts)
# ===============================================

app = Dash(__name__, external_stylesheets=[dbc.themes.LUX], suppress_callback_exceptions=True)

app.layout = dbc.Container([
    dbc.Row(dbc.Col(html.H2("Interactive Collisions Dashboard", className="text-primary mt-3 mb-3"))),
    dbc.Row([
        # Filter Column (Left)
        dbc.Col([
            html.Div(children=[
                html.Label("Search (e.g., 'Brooklyn 2022 pedestrian crashes')"),
                dcc.Input(id='search-box', type='text', placeholder='Type query and press Generate', debounce=True, style={'width':'100%'}),
            ], className="mb-3"),

            html.Label("Borough"),
            dcc.Dropdown(id='borough-filter', options=uniq_sorted(borough_col), multi=True, placeholder="Select Borough(s)"),
            html.Br(),

            html.Label("Year"),
            dcc.Dropdown(id='year-filter', options=uniq_sorted(year_col), multi=True, placeholder="Select Year(s)"),
            html.Br(),

            html.Label("Vehicle Type"),
            dcc.Dropdown(id='vehicle-filter', options=uniq_sorted(vehicle_col), multi=True, placeholder="Select Vehicle Type(s)"),
            html.Br(),

            html.Label("Contributing Factor"),
            dcc.Dropdown(id='factor-filter', options=uniq_sorted(contrib_col), multi=True, placeholder="Select Factor(s)"),
            html.Br(),

            html.Label("Injury Type"),
            dcc.Dropdown(id='injury-filter', options=uniq_sorted(injury_col), multi=True, placeholder="Select Injury Type(s)"),
            html.Br(),

            dbc.Button("Generate Report", id='generate-btn', color='primary', className="me-2"),
            dbc.Button("Download Report (HTML)", id='download-btn', color='secondary'),
            dcc.Download(id='download-report'),
            html.Div(id='status', style={'marginTop':'10px'})
        ], width=3, className="bg-light p-3"),

        # Visualizations Column (Right)
        dbc.Col([
            dcc.Tabs(id='tabs', value='tab-1', children=[
                dcc.Tab(label='Overview', value='tab-1', children=[
                    # 1. Top 10 Contributing Factors
                    dcc.Loading(dcc.Graph(id='bar-chart', config={'displayModeBar': False}), type='default'),
                    # 2. Total Crashes Over Time
                    dcc.Loading(dcc.Graph(id='line-chart', config={'displayModeBar': False}), type='default'),
                    # 3. Total Injured Persons per Borough (NEW)
                    dcc.Loading(dcc.Graph(id='borough-injuries-chart', config={'displayModeBar': False}), type='default'),
                    # 4. Killed vs. Injured Over Time (NEW)
                    dcc.Loading(dcc.Graph(id='killed-injured-chart', config={'displayModeBar': False}), type='default'),
                ]),
                dcc.Tab(label='Distribution', value='tab-2', children=[
                    # 5. Person Type Distribution (REVISED PIE CHART)
                    dcc.Loading(dcc.Graph(id='pie-chart', config={'displayModeBar': False}), type='default'),
                    # 6. Year vs. Borough Heatmap (Original)
                    dcc.Loading(dcc.Graph(id='heatmap', config={'displayModeBar': False}), type='default'),
                ]),
                dcc.Tab(label='Map & Table', value='tab-3', children=[
                    # 7. Map Chart (ENHANCED/FIXED)
                    dcc.Loading(dcc.Graph(id='map-chart', config={'scrollZoom': True}), type='default'),
                    html.H5("Filtered Data Sample"),
                    dcc.Loading(dash_table.DataTable(
                        id='data-table',
                        columns=[{"name": i, "id": i} for i in df.columns],
                        page_size=10,
                        style_table={'overflowX': 'auto'}
                    ), type='default')
                ])
            ])
        ], width=9)
    ])
], fluid=True)

# ===============================================
# DASH CALLBACKS (UPDATED for 7 charts)
# ===============================================

@app.callback(
    [Output('status', 'children'),
     Output('bar-chart', 'figure'),
     Output('line-chart', 'figure'),
     Output('borough-injuries-chart', 'figure'), # NEW OUTPUT
     Output('killed-injured-chart', 'figure'), # NEW OUTPUT
     Output('pie-chart', 'figure'),
     Output('heatmap', 'figure'),
     Output('map-chart', 'figure'),
     Output('data-table', 'data')],
    [Input('generate-btn', 'n_clicks')],
    [State('search-box', 'value'),
     State('borough-filter', 'value'),
     State('year-filter', 'value'),
     State('vehicle-filter', 'value'),
     State('factor-filter', 'value'),
     State('injury-filter', 'value')],
)
def update_all(n_clicks, search_q, borough_sel, year_sel, vehicle_sel, factor_sel, injury_sel):

    # Define an empty figure for returning on errors
    empty_fig = px.scatter(title="No Data/Error", template='plotly_white')
    
    # Check for data loading issue
    if df.empty:
        empty_map = px.scatter_mapbox(title="Data not loaded.")
        return "Data not loaded.", empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, empty_map, []

    if not n_clicks:
        df_filtered = df.head(500).copy()
        status = "Initial load (showing first 500 rows). Click 'Generate Report' to apply filters."
    else:
        df_filtered = df.copy()
        status_msgs = []

        parsed = parse_search(search_q, df_filtered.columns)

        temp_year_sel = year_sel or []
        if 'Year' in parsed and parsed['Year'] not in temp_year_sel:
            temp_year_sel.append(parsed['Year'])
            status_msgs.append(f"Parsed Year: {parsed['Year']}")

        current_borough_sel = borough_sel or []
        if 'BOROUGH' in parsed and parsed['BOROUGH'] not in current_borough_sel:
             current_borough_sel.append(parsed['BOROUGH'])
             status_msgs.append(f"Parsed Borough: {parsed['BOROUGH']}")

        if current_borough_sel and borough_col:
            df_filtered = df_filtered[df_filtered[borough_col].isin(current_borough_sel)]

        if temp_year_sel and year_col:
            # Note: Ensure year_col is treated as string for isin comparison if necessary
            df_filtered = df_filtered[df_filtered[year_col].astype(str).isin([str(y) for y in temp_year_sel])]

        if vehicle_sel and vehicle_col:
            df_filtered = df_filtered[df_filtered[vehicle_col].isin(vehicle_sel)]

        if factor_sel and contrib_col:
            df_filtered = df_filtered[df_filtered[contrib_col].isin(factor_sel)]

        if injury_sel and injury_col:
            df_filtered = df_filtered[df_filtered[injury_col].isin(injury_sel)]

        if 'PERSON_TYPE' in parsed and person_type_col:
            df_filtered = df_filtered[df_filtered[person_type_col].str.contains(parsed['PERSON_TYPE'], case=False, na=False)]
            status_msgs.append(f"Parsed Person Type: {parsed['PERSON_TYPE']}")

        if df_filtered.empty:
            status = "No data matches the current filters."
            empty_map = px.scatter_mapbox(title="No Data")
            # Return empty figures for all 7 charts
            return status, empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, empty_map, []
        else:
            status = f"✅ {len(df_filtered)} rows matched. " + "; ".join(status_msgs)

    # --- Generate Figures ---
    figures = {}

    # 1. Top 10 Contributing Factors (Bar Chart)
    if contrib_col:
        bar_data = df_filtered[contrib_col].value_counts().nlargest(10).reset_index()
        bar_data.columns = ['factor', 'count']
        figures['bar'] = px.bar(bar_data, x='factor', y='count', title='Top 10 Contributing Factors', template='plotly_white')
    else:
        figures['bar'] = px.bar(title='Contributing Factor data missing')

    # 2. Total Crashes Over Time (Line Chart)
    if year_col:
        # Use only collision-level data for this count
        df_crashes_filtered = df_filtered.drop_duplicates(subset=['COLLISION_ID']).copy()
        line_data = df_crashes_filtered[year_col].value_counts().reset_index(name='count')
        figures['line'] = px.line(line_data, x=year_col, y='count', title='Total Crashes by Year', template='plotly_white')
    else:
        figures['line'] = px.line(title='Year data missing')
        
    # 3. Total Injured Persons per Borough (NEW BAR CHART)
    if borough_col:
        injuries_data = df_filtered.groupby(borough_col)['NUMBER OF PERSONS INJURED'].sum().reset_index()
        injuries_data.columns = [borough_col, 'Total Injured']
        figures['borough-injuries'] = px.bar(injuries_data, x=borough_col, y='Total Injured',
                                             title='Total Injured Persons per Borough (Filtered)',
                                             template='plotly_white')
    else:
        figures['borough-injuries'] = px.bar(title="Error: Borough column not found.", template='plotly_white')

    # 4. Killed vs. Injured Over Time (NEW STACKED AREA CHART)
    if year_col:
        df_collision_level = df_filtered.drop_duplicates(subset=['COLLISION_ID']).copy()

        severity_data = df_collision_level.groupby(year_col)[
            ['NUMBER OF PERSONS KILLED', 'NUMBER OF PERSONS INJURED']
        ].sum().reset_index()

        severity_long = pd.melt(severity_data, id_vars=[year_col], 
                                value_vars=['NUMBER OF PERSONS KILLED', 'NUMBER OF PERSONS INJURED'],
                                var_name='Severity Type', value_name='Count')

        figures['killed-injured'] = px.area(
            severity_long,
            x=year_col,
            y='Count',
            color='Severity Type',
            title='Total Killed vs. Injured Persons Over Time (Filtered)',
            template='plotly_white',
            line_group='Severity Type'
        )
    else:
        figures['killed-injured'] = px.area(title="Error: Year column not found.", template='plotly_white')


    # 5. Person Type Distribution (REVISED PIE CHART)
    if person_type_col:
        # Show the distribution of involved person types (e.g., Driver, Pedestrian)
        pie_data = df_filtered[person_type_col].dropna().value_counts().nlargest(10).reset_index()
        pie_data.columns = [person_type_col, 'count']
        figures['pie'] = px.pie(pie_data, names=person_type_col, values='count', 
                                title='Distribution of Involved Person Types (Filtered)', 
                                hole=0.3, template='plotly_white')
    else:
        figures['pie'] = px.pie(title='Person Type data missing')

    # 6. Year vs. Borough Heatmap (Original)
    if year_col and borough_col:
        heat_data = df_filtered.drop_duplicates(subset=['COLLISION_ID']).groupby([year_col, borough_col]).size().reset_index(name='count')
        figures['heatmap'] = px.density_heatmap(heat_data, x=year_col, y=borough_col, z='count', title='Incidents: Year vs Borough Heatmap', template='plotly_white')
    else:
        figures['heatmap'] = px.density_heatmap(title='Year or Borough data missing')


    # 7. Crash Map (ENHANCED/FIXED)
    if lat_col and lon_col and not df_filtered[[lat_col, lon_col]].dropna().empty:
        # Sample max 2000 points for performance
        df_map = df_filtered.dropna(subset=[lat_col, lon_col]).sample(min(len(df_filtered), 2000)).copy()
        
        # --- FIX: Ensure columns are numeric for calculation ---
        df_map['INJURED'] = pd.to_numeric(df_map['NUMBER OF PERSONS INJURED'], errors='coerce').fillna(0)
        df_map['KILLED'] = pd.to_numeric(df_map['NUMBER OF PERSONS KILLED'], errors='coerce').fillna(0)
        
        df_map['SEVERITY'] = df_map['INJURED'] + df_map['KILLED']
        df_map['SEVERITY_SIZE'] = df_map['SEVERITY'].apply(lambda x: 1 if x == 0 else x) 
        # --- END FIX ---

        figures['map'] = px.scatter_mapbox(df_map,
                                         lat=lat_col, lon=lon_col,
                                         color='SEVERITY', # Color by calculated severity
                                         color_continuous_scale=px.colors.sequential.Inferno,
                                         size='SEVERITY_SIZE', # Size the marker by severity
                                         hover_data=[borough_col, 'SEVERITY'],
                                         zoom=9, height=400,
                                         title='Crash Locations (Sample) - Size/Color by Severity',
                                         mapbox_style="carto-positron")
        figures['map'].update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    else:
        figures['map'] = px.scatter(title='Geolocation data missing')

    table_data = df_filtered.head(1000).to_dict('records')

    # Ensure the return order matches the 9 outputs defined in the callback decorator!
    return (status, 
            figures['bar'], 
            figures['line'], 
            figures['borough-injuries'], 
            figures['killed-injured'], 
            figures['pie'], 
            figures['heatmap'], 
            figures['map'], 
            table_data)

@app.callback(
    Output('download-report', 'data'),
    Input('download-btn', 'n_clicks'),
    [State('search-box', 'value'),
     State('borough-filter', 'value'),
     State('year-filter', 'value'),
     State('vehicle-filter', 'value'),
     State('factor-filter', 'value'),
     State('injury-filter', 'value')],
    prevent_initial_call=True
)
def download_report(n_clicks, search_q, borough_sel, year_sel, vehicle_sel, factor_sel, injury_sel):

    df_filtered = df.copy()

    # Rerun filter logic to create the final data frame
    parsed = parse_search(search_q, df_filtered.columns)
    temp_year_sel = year_sel or []
    if 'Year' in parsed and parsed['Year'] not in temp_year_sel:
        temp_year_sel.append(parsed['Year'])
    current_borough_sel = borough_sel or []
    if 'BOROUGH' in parsed and parsed['BOROUGH'] not in current_borough_sel:
         current_borough_sel.append(parsed['BOROUGH'])
    if current_borough_sel and borough_col:
        df_filtered = df_filtered[df_filtered[borough_col].isin(current_borough_sel)]
    if temp_year_sel and year_col:
        df_filtered = df_filtered[df_filtered[year_col].astype(str).isin([str(y) for y in temp_year_sel])]
    if vehicle_sel and vehicle_col:
        df_filtered = df_filtered[df_filtered[vehicle_col].isin(vehicle_sel)]
    if factor_sel and contrib_col:
        df_filtered = df_filtered[df_filtered[contrib_col].isin(factor_sel)]
    if injury_sel and injury_col:
        df_filtered = df_filtered[df_filtered[injury_col].isin(injury_sel)]
    if 'PERSON_TYPE' in parsed and person_type_col:
        df_filtered = df_filtered[df_filtered[person_type_col].str.contains(parsed['PERSON_TYPE'], case=False, na=False)]

    figs = {}
    
    # Generate charts for the report
    if contrib_col:
        bar_data = df_filtered[contrib_col].value_counts().nlargest(10).reset_index()
        bar_data.columns = ['factor', 'count']
        figs['Top 10 Factors'] = px.bar(bar_data, x='factor', y='count', title='Top 10 Contributing Factors')

    if year_col:
        # Line Chart: Crashes over time
        line_data = df_filtered.drop_duplicates(subset=['COLLISION_ID']).groupby(year_col).size().reset_index(name='count')
        figs['Incidents by Year'] = px.line(line_data, x=year_col, y='count', title='Incidents by Year')

        # Area Chart: Killed vs Injured over time
        df_collision_level = df_filtered.drop_duplicates(subset=['COLLISION_ID']).copy()
        severity_data = df_collision_level.groupby(year_col)[
            ['NUMBER OF PERSONS KILLED', 'NUMBER OF PERSONS INJURED']
        ].sum().reset_index()
        severity_long = pd.melt(severity_data, id_vars=[year_col], 
                                value_vars=['NUMBER OF PERSONS KILLED', 'NUMBER OF PERSONS INJURED'],
                                var_name='Severity Type', value_name='Count')
        figs['Killed vs Injured'] = px.area(severity_long, x=year_col, y='Count', color='Severity Type', title='Total Killed vs. Injured Persons Over Time')
    
    if borough_col:
        # New Bar Chart: Injuries by Borough
        injuries_data = df_filtered.groupby(borough_col)['NUMBER OF PERSONS INJURED'].sum().reset_index()
        injuries_data.columns = [borough_col, 'Total Injured']
        figs['Injuries by Borough'] = px.bar(injuries_data, x=borough_col, y='Total Injured', title='Total Injured Persons per Borough')

    if person_type_col:
        # Revised Pie Chart: Person Type Distribution
        pie_data = df_filtered[person_type_col].dropna().value_counts().nlargest(10).reset_index()
        pie_data.columns = [person_type_col, 'count']
        figs['Person Type Distribution'] = px.pie(pie_data, names=person_type_col, values='count', title='Distribution of Involved Person Types', hole=0.3)

    if year_col and borough_col:
        # Heatmap
        heat_data = df_filtered.drop_duplicates(subset=['COLLISION_ID']).groupby([year_col, borough_col]).size().reset_index(name='count')
        figs['Year vs Borough Heatmap'] = px.density_heatmap(heat_data, x=year_col, y=borough_col, z='count', title='Incidents: Year vs Borough Heatmap')

    html_bytes = create_html_report(figs, df_filtered)
    filename = f"report_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.html"
    return dcc.send_bytes(html_bytes, filename=filename)

# ===============================================
# PYTHONANYWHERE ENTRY POINT (DO NOT DELETE)
# ===============================================

# PythonAnywhere needs the Flask server instance to be exported as 'application' 
# or aliased as 'application' in the WSGI file. Since you are using manual
# configuration, this 'server' object is what you import in your WSGI file.
server = app.server
