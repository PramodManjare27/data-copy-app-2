"""
Entry point for the PROD -> PREPROD data copy console.

Run: python run_prod_preprod.py
Default port: 5001 (override with the PORT env var).
"""
from app import create_app

app = create_app("prod_preprod")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=app.config["PORT"], debug=True, use_reloader=False)
