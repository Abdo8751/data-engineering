# wsgi.py

# Explicitly import the server object defined in app.py
from app import server as application

# This file acts as the bridge that Vercel needs
# to reliably start the Flask/Dash application.
