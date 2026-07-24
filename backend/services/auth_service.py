"""Implements the APS 3-legged OAuth (Authorization Code) flow, in three
steps that map 1:1 onto the three methods below:

1. Send the user to Autodesk's sign-in/consent page (build_authorize_url).
2. Autodesk redirects back to us with a one-time `code`
   (backend/routes/auth_routes.py's /oauth/callback handles that redirect).
3. Exchange that `code` for a real access token (exchange_code), then
   optionally fetch the user's profile to show their name in the UI
   (get_user_profile).

See https://aps.autodesk.com/en/docs/oauth/v2/tutorials/get-3-legged-token/
for the full walkthrough this mirrors.
"""

import base64
from urllib.parse import urlencode

import requests
from flask import current_app


class AuthService:
    """Implements the APS 3-legged OAuth (Authorization Code) flow."""

    @staticmethod
    def build_authorize_url(state):
        """Step 1: the URL to redirect the user's browser to. `state` is a
        random value auth_routes.py generates and stores in the session,
        then checks again on the callback - a CSRF guard that makes sure
        the callback we receive actually came from an authorize request we
        started, not a forged one.
        """
        params = {
            'response_type': 'code',
            'client_id': current_app.config['APS_CLIENT_ID'],
            'redirect_uri': current_app.config['APS_REDIRECT_URI'],
            'scope': current_app.config['APS_SCOPE'],
            'state': state,
        }
        return f"{current_app.config['APS_AUTHORIZE_URL']}?{urlencode(params)}"

    @staticmethod
    def exchange_code(code):
        """Step 3: trades the one-time authorization `code` from the
        callback for a real access token. Authenticated as the app itself
        (not the user) via HTTP Basic auth built from the client
        id/secret - this is why APS_CLIENT_SECRET must stay server-side
        and never reach the browser.
        """
        client_id = current_app.config['APS_CLIENT_ID']
        client_secret = current_app.config['APS_CLIENT_SECRET']
        basic = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()

        headers = {
            'Authorization': f'Basic {basic}',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': current_app.config['APS_REDIRECT_URI'],
        }
        response = requests.post(
            current_app.config['APS_TOKEN_URL'],
            headers=headers,
            data=data,
        )
        response.raise_for_status()
        # {'access_token': ..., 'refresh_token': ..., 'expires_in': ...} -
        # auth_routes.py stores what it needs from this straight into the
        # session.
        return response.json()

    @staticmethod
    def get_user_profile(access_token):
        """Fetches the signed-in user's name/email (requires the
        user-profile:read scope) - used only to show a friendly name in
        the toolbar, so a failure here isn't fatal to logging in.
        """
        response = requests.get(
            current_app.config['APS_USERINFO_URL'],
            headers={'Authorization': f'Bearer {access_token}'},
        )
        if response.status_code == 200:
            return response.json()
        return None
