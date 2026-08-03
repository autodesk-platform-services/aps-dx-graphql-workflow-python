"""Flask configuration for Data Exchange Workflow Bench.

Everything here is read from environment variables (see `.env.example`),
with sensible local-dev defaults so the app still starts without any
configuration - just without a working APS login until you supply real
credentials.
"""

import os
import tomllib

from dotenv import load_dotenv

# Populates os.environ from a `.env` file in the project root, if one
# exists - this is what lets APS_CLIENT_ID etc. below just be a plain
# os.getenv() call instead of the app needing its own .env parsing.
load_dotenv()


def _read_project_version():
    """Reads the manually-bumped version straight from pyproject.toml's
    [project] table - the single place to bump it on each release, mirroring
    the .NET port's <Version> in its .csproj. Lets the UI show a version
    badge so a stale browser tab is easy to spot after a Dokku deploy.
    """
    pyproject_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pyproject.toml')
    with open(pyproject_path, 'rb') as f:
        return tomllib.load(f)['project']['version']


class Config:
    """Flask reads this via `app.config.from_object(Config)` in
    backend/__init__.py - every uppercase class attribute becomes a key in
    `app.config`.
    """

    # --- APS (Autodesk Platform Services) 3-legged OAuth ---
    # "3-legged" means the token is tied to a signed-in Autodesk user (as
    # opposed to a "2-legged" token, which just authenticates the app
    # itself) - required here because every API call needs to act as that
    # specific user (their hubs, their projects, their permissions).
    APS_CLIENT_ID = os.getenv('APS_CLIENT_ID')
    APS_CLIENT_SECRET = os.getenv('APS_CLIENT_SECRET')
    APS_REDIRECT_URI = os.getenv('APS_REDIRECT_URI', 'http://localhost:5000/oauth/callback')
    # The scopes this app requests during login - data:read is needed for
    # every Data Exchange GraphQL call (hubs, projects, folders, ...);
    # viewables:read is needed only by the Viewer Output node, to load a
    # model into the embedded Autodesk Viewer.
    APS_SCOPE = os.getenv('APS_SCOPE', 'user-profile:read data:read viewables:read')

    # Fixed APS Authentication v2 endpoints - see
    # https://aps.autodesk.com/en/docs/oauth/v2/tutorials/get-3-legged-token/
    # for the full OAuth flow these three URLs take part in.
    APS_AUTHORIZE_URL = 'https://developer.api.autodesk.com/authentication/v2/authorize'
    APS_TOKEN_URL = 'https://developer.api.autodesk.com/authentication/v2/token'
    APS_USERINFO_URL = 'https://api.userprofile.autodesk.com/userinfo'

    # The Data Exchange API's GraphQL endpoint - every query/mutation in
    # backend/services/dx_queries.py is sent here, via
    # backend/services/dx_service.py.
    DATA_EXCHANGE_GRAPHQL_URL = 'https://developer.api.autodesk.com/dataexchange/2023-05/graphql'

    # Flask signs the session cookie with this key (it's where the OAuth
    # state and access token get stored) - always override this in a real
    # deployment via FLASK_SECRET_KEY; the default is only safe for local dev.
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-only-insecure-key')

    # APS redirects back to /oauth/callback as a cross-site top-level
    # navigation after login, so the session cookie must still be sent on
    # that request - "Strict" would silently drop it and break login.
    SESSION_COOKIE_SAMESITE = 'Lax'
    # Set SESSION_COOKIE_SECURE=1 on HTTPS deployments (Dokku). When
    # FLASK_DEBUG is off, secure cookies default to on.
    SESSION_COOKIE_SECURE = os.getenv(
        'SESSION_COOKIE_SECURE',
        '0' if os.getenv('FLASK_DEBUG', '1') == '1' else '1',
    ) == '1'

    # Dokku/nginx terminate TLS and forward HTTP to the container — ProxyFix
    # (see backend/__init__.py) needs this so OAuth redirect URLs use https.
    BEHIND_PROXY = os.getenv('BEHIND_PROXY', '0') == '1'

    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

    # Where saved flows live on disk - one JSON file per flow, read/written
    # by backend/services/flow_service.py.
    FLOWS_DIR = os.getenv('FLOWS_DIR', os.path.join(PROJECT_ROOT, 'data', 'flows'))

    PORT = int(os.getenv('PORT', 5000))
    DEBUG = os.getenv('FLASK_DEBUG', '1') == '1'

    APP_VERSION = _read_project_version()
