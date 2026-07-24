"""The single `/` route - everything else in the app is either an API
route (backend/routes/dx_routes.py, flow_routes.py) or the OAuth flow
(auth_routes.py). This is just the page itself.
"""

from flask import Blueprint, render_template, session

from backend.nodes import NODE_TYPES, grouped_node_types

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """Landing page (with a "Sign In" button) if there's no session yet;
    otherwise the full flow editor, with the node palette's metadata
    injected as template variables (see frontend/templates/index.html).
    """
    if 'access_token' not in session:
        return render_template('landing.html')

    return render_template(
        'index.html',
        user_name=session.get('user_name'),
        node_types=NODE_TYPES,
        node_sections=grouped_node_types(),
    )
