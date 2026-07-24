"""Flask application factory.

Using a factory function (rather than a module-level `app = Flask(...)`)
means tests or other entry points can create independent app instances
with different config, instead of always sharing one global app object.
`run.py` is the only thing that actually calls this today, but the
pattern costs nothing and is the standard Flask way to structure a
multi-blueprint app.
"""

from flask import Flask
from flask_cors import CORS

from config import Config


def create_app(config_class=Config):
    """Builds and returns a fully configured Flask app - static/template
    folders pointed at frontend/, config loaded from `config_class`, CORS
    enabled, and every route blueprint registered under its URL prefix.
    """
    app = Flask(
        __name__,
        template_folder='../frontend/templates',
        static_folder='../frontend/static',
    )
    app.config.from_object(config_class)

    # Not strictly needed for the app to serve its own frontend (same
    # origin), but harmless and convenient if you ever want to call these
    # routes from a different origin during development.
    CORS(app)

    # Imported here rather than at module level so nothing under
    # backend/routes/ loads until create_app() actually runs - handy if
    # you ever add tests that build an app instance without needing every
    # blueprint, though today all four are always registered anyway.
    from backend.routes.auth_routes import auth_bp
    from backend.routes.dx_routes import dx_bp
    from backend.routes.flow_routes import flow_bp
    from backend.routes.main_routes import main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(flow_bp, url_prefix='/api/flows')
    app.register_blueprint(dx_bp, url_prefix='/api/dx')

    if app.config.get('BEHIND_PROXY'):
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    return app
