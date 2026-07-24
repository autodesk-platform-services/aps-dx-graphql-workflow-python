"""Entry point for local development.

Run with:
    python run.py

This just builds the Flask app via the factory in backend/__init__.py and
starts Werkzeug's built-in dev server - fine for trying the app out
locally, but see the README before running this anywhere else (the dev
server prints its own warning about that too).
"""

from backend import create_app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=app.config['PORT'], debug=app.config['DEBUG'])
