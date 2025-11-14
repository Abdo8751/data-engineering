# === Paste this whole cell into your Colab notebook and run ===

# 1) Install libs (first time)
!pip install -q dash==2.11.0 dash-bootstrap-components pandas plotly dash-table

# 2) App code
from dash import Dash, dcc, html, Input, Output, State, callback_context, dash_table
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
import numpy as np
import datetime
import io
import plotly.io as pio
import re
import os

# ===============================================
# CONFIGURATION
# ===============================================

# --- CORRECTED DATA PATH ---
DATA_PATH = "/content/merged_collisions.csv"
if not os.path.exists(DATA_PATH) and os.path.exists("/content/dataset.csv"):
    DATA_PATH = "/content/dataset.csv"
# ===============================================

try:
    df = pd.read_csv(DATA_PATH)
except FileNotFoundError:
    print(f"Error: Could not find '{DATA_PATH}'. Please ensure the file is uploaded to the Colab environment.")
    df = pd.DataFrame()

if df.empty:
    print("Dashboard will run with empty data and show an error message.")

# Normalize column names
df.columns = [c.strip() for c in df.columns]

# Extract Year from CRASH DATE and apply stronger type conversion
if 'CRASH DATE' in df.columns:
    df['CRASH DATE'] = pd.to_datetime(df['CRASH DATE'], errors='coerce')
    df['Year'] = df['CRASH DATE'].dt.year.astype('Int64')

# --- CORE COLUMN DEFINITIONS (FORCED to use your exact names) ---
borough_col = 'BOROUGH'
year_col = 'Year' # This is the unified column created above
vehicle_col = 'VEHICLE TYPE CODE 1'
contrib_col = 'CONTRIBUTING FACTOR VEHICLE 1'
injury_col = 'PERSON_INJURY'
lat_col = 'LATITUDE'
lon_col = 'LONGITUDE'
person_type_col = 'PERSON_TYPE'
injured_col = 'NUMBER OF PERSONS INJURED'
killed_col = 'NUMBER OF PERSONS KILLED'
collision_id_col = 'COLLISION_ID'

# --- CRITICAL: Numeric Type Conversion for Key Plotting Columns ---
if injured_col in df.columns:
    df[injured_col] = pd.to_numeric(df[injured_col], errors='coerce').fillna(0)
if killed_col in df.columns:
    df[killed_col] = pd.to_numeric(df[killed_col], errors='coerce').fillna(0)
if lat_col in df.columns:
    df[lat_col] = pd.to_numeric(df[lat_col], errors='coerce')
if lon_col in df.columns:
    df[lon_col] = pd.to_numeric(df[lon_col], errors='coerce')


# Helper functions
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
    if borough_col and borough_col in df_cols:
        for b in df[borough_col].dropna().astype(str).unique():
            if b.lower() in ql:
                out[borough_col] = b
                break
    if person_type_col and person_type_col in df_cols:
        if 'pedestrian' in ql: out[person_type_col] = 'Pedestrian'
        elif 'bicyclist' in ql: out[person_type_col] = 'Bicyclist'
    return out

def create_html_report(figs: dict, df_filtered: pd.DataFrame):
    html_parts = []
    html_parts.append("<html><head><meta charset='utf-8'><title>Report</title></head><body>")
    html_parts.append(f"<h1>Generated Report — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</h1>")
    html_parts.append(f"<p>Filtered to {len(df_filtered)} records.</p>")
    for name, fig in figs.items():
        html_parts.append(f"<h2>{name}</h2>")
        html_parts.append(pio.to_html(fig, include_plotlyjs='cdn', full_html=False))
    html_parts.append("<h2>Filtered Data Sample (First 100 Rows)</h2>")
    html_parts.append(df_filtered.head(100).to_html(index=False))
    html_parts.append("</body></html>")
    return "\n".join(html_parts).encode('utf-8')


# App init
app = Dash(__name__, external_stylesheets=[dbc.themes.LUX], suppress_callback_exceptions=True)

# Layout setup 
app.layout = dbc.Container([
    dbc.Row(dbc.Col(html.H2("Interactive Collisions Dashboard (Standard Dash)", className="text-primary mt-3 mb-3"))),
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
                        columns=[{"name": i, "id": i} for i in df.columns],
                        page_size=10,
                        style_table={'overflowX': 'auto'}
                    ), type='default')
                ])
            ])
        ], width=9)
    ])
], fluid=True)

# Callbacks - Updated Output for all 8 plots
@app.callback(
    Output('status', 'children'),
    Output('bar-chart', 'figure'),
    Output('line-chart', 'figure'),
    Output('pie-chart', 'figure'),
    Output('heatmap', 'figure'), # This will now be the Grouped Bar Chart
    Output('map-chart', 'figure'),
    Output('data-table', 'data'),
    Output('borough-injuries-chart', 'figure'), 
    Output('killed-injured-chart', 'figure'), 
    Input('generate-btn', 'n_clicks'),
    State('search-box', 'value'),
    State('borough-filter', 'value'),
    State('year-filter', 'value'),
    State('vehicle-filter', 'value'),
    State('factor-filter', 'value'),
    State('injury-filter', 'value'),
)
def update_all(n_clicks, search_q, borough_sel, year_sel, vehicle_sel, factor_sel, injury_sel):

    # Define an empty figure for error handling
    empty_fig = px.scatter(title="Data not loaded or filtered data is empty.", template='plotly_white')

    if df.empty:
        # Return empty figures for all 8 charts
        return "Data not loaded.", empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, [], empty_fig, empty_fig

    if not n_clicks:
        # Initial load condition: show a filtered sample to prevent crashing on large datasets
        df_filtered = df.head(500).copy()
        status = "Initial load (showing first 500 rows). Click 'Generate Report' to apply filters."
    else:
        df_filtered = df.copy()
        status_msgs = []

        # --- Filtering Logic ---
        parsed = parse_search(search_q, df_filtered.columns)

        temp_year_sel = year_sel or []
        if 'Year' in parsed and parsed['Year'] not in temp_year_sel:
            temp_year_sel.append(parsed['Year'])

        current_borough_sel = borough_sel or []
        if borough_col and borough_col in parsed and parsed[borough_col] not in current_borough_sel:
             current_borough_sel.append(parsed[borough_col])

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

        if person_type_col and person_type_col in parsed:
            df_filtered = df_filtered[df_filtered[person_type_col].str.contains(parsed[person_type_col], case=False, na=False)]
        # --- End Filtering Logic ---

    if df_filtered.empty:
        status = "No data matches the current filters."
        # Return empty figures for all 8 charts
        return status, empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, [], empty_fig, empty_fig

    status = f"✅ {len(df_filtered)} rows matched."
    
    # --- Generate Figures ---
    figures = {}

    # 1. Bar Chart (Top 10 Contributing Factors)
    if contrib_col in df_filtered.columns:
        bar_data = df_filtered[contrib_col].value_counts().nlargest(10).reset_index()
        bar_data.columns = ['factor', 'count']
        figures['bar'] = px.bar(bar_data, x='factor', y='count', title='Top 10 Contributing Factors', template='plotly_white')
    else:
        figures['bar'] = px.bar(title='Contributing Factor data missing')

    # 2. Line Chart (Total Crashes Over Time)
    if year_col in df_filtered.columns and collision_id_col in df_filtered.columns:
        df_crashes_filtered = df_filtered.drop_duplicates(subset=[collision_id_col]).copy()
        line_data = df_crashes_filtered.groupby(year_col).size().reset_index(name='count')
        figures['line'] = px.line(line_data, x=year_col, y='count', title='Total Crashes Over Time (Filtered)', template='plotly_white')
    else:
        figures['line'] = px.line(title='Year or Collision ID data missing')

    # 3. Pie Chart (Person Type Distribution)
    if person_type_col in df_filtered.columns:
        pie_data = df_filtered[person_type_col].dropna().value_counts().nlargest(10).reset_index()
        pie_data.columns = [person_type_col, 'count']
        figures['pie'] = px.pie(pie_data, names=person_type_col, values='count', title='Distribution of Involved Person Types (Top 10)', hole=0.3, template='plotly_white')
    else:
        figures['pie'] = px.pie(title='Person Type data missing')

    # 4. Heatmap changed to Grouped Bar Chart (Year vs Borough) for better readability
    if year_col in df_filtered.columns and borough_col in df_filtered.columns:
        # Data aggregation: count incidents by Year and Borough
        heat_data = df_filtered.groupby([year_col, borough_col]).size().reset_index(name='count')
        
        figures['heatmap'] = px.bar(
            heat_data, 
            x=borough_col, 
            y='count',
            color=year_col, 
            barmode='group', # Use grouped bars for easy comparison
            title='Incidents by Borough and Year (Grouped Bar Chart)', 
            template='plotly_white',
            labels={'count': 'Number of Incidents', year_col: 'Year', borough_col: 'Borough'}
        )
        # Apply slight x-axis rotation for borough names
        figures['heatmap'].update_xaxes(tickangle=30)
    else:
        figures['heatmap'] = px.bar(title='Year or Borough data missing')

    # 5. Map Chart (Geographical Distribution)
    if lat_col in df_filtered.columns and lon_col in df_filtered.columns and injured_col in df_filtered.columns and killed_col in df_filtered.columns and not df_filtered[[lat_col, lon_col]].dropna().empty:
        df_map = df_filtered.dropna(subset=[lat_col, lon_col]).copy()
        
        # Recalculate Severity (just in case)
        df_map['SEVERITY'] = df_map[injured_col] + df_map[killed_col]
        df_map['SEVERITY_SIZE'] = df_map['SEVERITY'].apply(lambda x: 1 if x == 0 else (x * 2)) 
        
        figures['map'] = px.scatter_mapbox(df_map.head(5000), 
                                          lat=lat_col, lon=lon_col,
                                          color='SEVERITY', 
                                          size='SEVERITY_SIZE', 
                                          color_continuous_scale=px.colors.sequential.Inferno,
                                          hover_data=[borough_col, year_col, contrib_col, 'SEVERITY'],
                                          zoom=9, height=400,
                                          title='Crash Locations (Sample) - Size/Color by Severity',
                                          mapbox_style="carto-positron")
        figures['map'].update_layout(margin={"r":0,"t":40,"l":0,"b":0})
    else:
        figures['map'] = px.scatter(title='Geolocation data missing or missing injured/killed counts')

    # 6. Total Injured Persons per Borough
    if borough_col in df_filtered.columns and injured_col in df_filtered.columns and collision_id_col in df_filtered.columns:
        df_collision_level = df_filtered.drop_duplicates(subset=[collision_id_col]).copy()
        # Ensure sum uses the cleaned numeric column
        injuries_data = df_collision_level.groupby(borough_col)[injured_col].sum().reset_index(name='Total Injured')
        
        figures['borough_injuries'] = px.bar(injuries_data, x=borough_col, y='Total Injured',
                                             title='Total Injured Persons per Borough (Filtered)',
                                             template='plotly_white')
    else:
        figures['borough_injuries'] = px.bar(title="Borough or Injury Count data missing")

    # 7. Killed vs. Injured Over Time
    if year_col in df_filtered.columns and killed_col in df_filtered.columns and injured_col in df_filtered.columns and collision_id_col in df_filtered.columns:
        df_collision_level = df_filtered.drop_duplicates(subset=[collision_id_col]).copy()
        # Ensure sum uses the cleaned numeric columns
        severity_data = df_collision_level.groupby(year_col)[[killed_col, injured_col]].sum().reset_index()

        severity_long = pd.melt(severity_data, id_vars=[year_col], 
                                value_vars=[killed_col, injured_col],
                                var_name='Severity Type', value_name='Count')

        figures['killed_injured'] = px.area(
            severity_long,
            x=year_col,
            y='Count',
            color='Severity Type',
            title='Total Killed vs. Injured Persons Over Time (Filtered)',
            template='plotly_white',
            line_group='Severity Type'
        )
    else:
        figures['killed_injured'] = px.area(title='Year or Severity Count data missing')


    table_data = df_filtered.head(1000).to_dict('records')

    # Ensure the return order matches the Output order! (8 outputs now)
    return status, figures['bar'], figures['line'], figures['pie'], figures['heatmap'], figures['map'], table_data, figures['borough_injuries'], figures['killed_injured']

@app.callback(
    Output('download-report', 'data'),
    Input('download-btn', 'n_clicks'),
    State('search-box', 'value'),
    State('borough-filter', 'value'),
    State('year-filter', 'value'),
    State('vehicle-filter', 'value'),
    State('factor-filter', 'value'),
    State('injury-filter', 'value'),
    prevent_initial_call=True
)
def download_report(n_clicks, search_q, borough_sel, year_sel, vehicle_sel, factor_sel, injury_sel):

    df_filtered = df.copy()

    # --- Filtering Logic for Download (reused) ---
    parsed = parse_search(search_q, df_filtered.columns)
    temp_year_sel = year_sel or []
    if 'Year' in parsed and parsed['Year'] not in temp_year_sel:
        temp_year_sel.append(parsed['Year'])
    current_borough_sel = borough_sel or []
    if borough_col and borough_col in parsed and parsed[borough_col] not in current_borough_sel:
         current_borough_sel.append(parsed[borough_col])
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
    if person_type_col and person_type_col in parsed:
        df_filtered = df_filtered[df_filtered[person_type_col].str.contains(parsed[person_type_col], case=False, na=False)]
    # --- End Filtering Logic ---

    figs = {}
    
    # 1. Top 10 Factors
    if contrib_col in df_filtered.columns:
        bar_data = df_filtered[contrib_col].value_counts().nlargest(10).reset_index()
        bar_data.columns = ['factor', 'count']
        figs['Top 10 Factors'] = px.bar(bar_data, x='factor', y='count', title='Top 10 Contributing Factors')

    # 2. Total Crashes Over Time
    if year_col in df_filtered.columns and collision_id_col in df_filtered.columns:
        df_crashes_filtered = df_filtered.drop_duplicates(subset=[collision_id_col]).copy()
        line_data = df_crashes_filtered.groupby(year_col).size().reset_index(name='count')
        figs['Incidents by Year'] = px.line(line_data, x=year_col, y='count', title='Total Crashes Over Time')
        
    # 3. Total Injured Persons per Borough
    if borough_col in df_filtered.columns and injured_col in df_filtered.columns and collision_id_col in df_filtered.columns:
        df_collision_level = df_filtered.drop_duplicates(subset=[collision_id_col]).copy()
        injuries_data = df_collision_level.groupby(borough_col)[injured_col].sum().reset_index(name='Total Injured')
        figs['Total Injured Persons per Borough'] = px.bar(injuries_data, x=borough_col, y='Total Injured',
                                             title='Total Injured Persons per Borough')

    # 4. Heatmap changed to Grouped Bar Chart (Year vs Borough)
    if year_col in df_filtered.columns and borough_col in df_filtered.columns:
        heat_data = df_filtered.groupby([year_col, borough_col]).size().reset_index(name='count')
        figs['Incidents by Borough and Year (Grouped Bar Chart)'] = px.bar(
            heat_data, 
            x=borough_col, 
            y='count',
            color=year_col, 
            barmode='group',
            title='Incidents by Borough and Year (Grouped Bar Chart)',
            labels={'count': 'Number of Incidents', year_col: 'Year', borough_col: 'Borough'}
        )
        figs['Incidents by Borough and Year (Grouped Bar Chart)'].update_xaxes(tickangle=30)


    html_bytes = create_html_report(figs, df_filtered)
    filename = f"report_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.html"
    return dcc.send_bytes(html_bytes, filename=filename)

# Run the app
app.run_server(mode='jupyterlab', host='0.0.0.0', port=8051)
