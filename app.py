# === Minimal app.py for Vercel Structural Testing ===
from dash import Dash, html
import dash_bootstrap_components as dbc

# --- Data Loading and Filtering are TEMPORARILY REMOVED ---
# --- The goal is to see if the Dash server can start without crashing ---

# App init
app = Dash(__name__, external_stylesheets=[dbc.themes.LUX], suppress_callback_exceptions=True)

# Minimal Layout: This should load if the Vercel/Dash structure is correct.
app.layout = dbc.Container([
    dbc.Row(dbc.Col(html.H1("Empty Test Dashboard", className="text-primary mt-3 mb-3"))),
    dbc.Row(dbc.Col(html.P("If you see this page, the Vercel/Dash connection is working!"))),
    dbc.Row(dbc.Col(html.P("The crash is related to data loading or chart generation.")))
], fluid=True)

# VERCEL DEPLOYMENT ENTRY POINT
# We must expose the server object.
server = app.server

# All callbacks, functions, and app.run_server() are REMOVED for this test.
