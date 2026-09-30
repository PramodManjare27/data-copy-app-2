"""
Entry point for the PREPROD -> DEV (DEV_env1..4) data copy console.

Run: python run_preprod_dev.py
Default port: 5002 (override with the PORT env var).
"""
from app import create_app

app = create_app("preprod_dev")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=app.config["PORT"], debug=True, use_reloader=False)
