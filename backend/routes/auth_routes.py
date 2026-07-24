"""The three-step APS sign-in flow's HTTP endpoints - see
backend/services/auth_service.py for what each step actually does; this
module is just the routing and CSRF/session bookkeeping around it.

    /oauth/login    -> redirects to Autodesk's sign-in page (step 1)
    /oauth/callback -> Autodesk redirects back here with a code (steps 2-3)
    /oauth/logout   -> clears the session and its cookie
"""

import hmac
import secrets

from flask import (
    Blueprint,
    current_app,
    make_response,
    redirect,
    request,
    session,
    url_for,
)

from backend.services.auth_service import AuthService

auth_bp = Blueprint('auth', __name__)

# How many in-flight login attempts (i.e. unconsumed CSRF state tokens) to
# remember at once - more than one tab/window mid-login shouldn't break
# either of them, but there's no reason to let this grow unbounded either.
_MAX_PENDING_OAUTH_STATES = 10


def _remember_oauth_state(state):
    """Stores a CSRF state token for later verification in _consume_oauth_state,
    keeping only the _MAX_PENDING_OAUTH_STATES most recent so multi-tab login still works.
    """
    pending = session.setdefault('oauth_states', [])
    pending.append(state)
    session['oauth_states'] = pending[-_MAX_PENDING_OAUTH_STATES:]
    # Flask's session only re-saves the cookie when it detects a change to
    # the session dict itself - mutating a list *inside* it (append, above)
    # doesn't trigger that detection on its own, so this flag has to be set
    # by hand or the updated `oauth_states` list would silently not persist.
    session.modified = True


def _consume_oauth_state(state):
    """True if `state` matches a token _remember_oauth_state stored earlier
    (and removes it, so it can't be replayed) - False otherwise, including
    when `state` is empty.
    """
    if not state:
        return False

    pending = session.get('oauth_states', [])
    matched_index = None
    for index, candidate in enumerate(pending):
        # hmac.compare_digest instead of `==` - a plain string comparison
        # returns as soon as it finds the first mismatched character, which
        # leaks (via how long the comparison took) how many leading
        # characters an attacker's guess got right. compare_digest always
        # takes the same time regardless, which matters here since `state`
        # is a security token, not just any value.
        if hmac.compare_digest(state, candidate):
            matched_index = index
            break

    if matched_index is None:
        return False

    pending.pop(matched_index)
    session['oauth_states'] = pending
    session.modified = True
    return True


@auth_bp.route('/oauth/login')
def login():
    """Step 1: sends the user to Autodesk's sign-in/consent page."""
    state = secrets.token_urlsafe(16)
    _remember_oauth_state(state)
    return redirect(AuthService.build_authorize_url(state))


@auth_bp.route('/oauth/callback')
def callback():
    """Steps 2-3: Autodesk redirects back here with `?code=`/`?state=` (or
    `?error=` if the user declined) after they sign in - verifies `state`,
    trades `code` for an access token, and stores everything the rest of
    the app needs in the session.
    """
    if session.get('access_token'):
        # Already signed in - happens if this callback URL gets loaded
        # twice (common with double page loads), harmless to just move on.
        return redirect(url_for('main.index'))

    error = request.args.get('error')
    if error:
        description = request.args.get('error_description', '')
        return f'Authorization failed: {error} - {description}', 400

    state = request.args.get('state')
    if not _consume_oauth_state(state):
        return 'Invalid state parameter. Possible CSRF attempt.', 400

    code = request.args.get('code')
    if not code:
        return 'No authorization code returned.', 400

    token = AuthService.exchange_code(code)
    session['access_token'] = token.get('access_token')
    session['refresh_token'] = token.get('refresh_token')
    # Used by /api/dx/viewer-token to hand the Viewer SDK a real expiry.
    session['expires_in'] = token.get('expires_in')

    # A failed profile lookup shouldn't block login - the user's name is
    # only cosmetic (shown in the toolbar), everything else already works
    # without it.
    profile = AuthService.get_user_profile(token.get('access_token'))
    if profile:
        session['user_name'] = profile.get('name') or profile.get('email')

    return redirect(url_for('main.index'))


@auth_bp.route('/oauth/logout')
def logout():
    """Clears the session (server-side) and its cookie (browser-side),
    then sends the user back to the landing page.
    """
    session.clear()
    # session.clear() alone empties the session's *contents*, but Flask
    # would still send a (now-empty) session cookie back - explicitly
    # deleting the cookie itself is what actually signs the browser out.
    response = make_response(redirect(url_for('main.index')))
    response.delete_cookie(
        current_app.config.get('SESSION_COOKIE_NAME', 'session'),
        path=current_app.config.get('SESSION_COOKIE_PATH') or '/',
        domain=current_app.config.get('SESSION_COOKIE_DOMAIN'),
    )
    return response
