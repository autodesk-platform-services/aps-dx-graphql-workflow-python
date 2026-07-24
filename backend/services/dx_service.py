"""Thin wrapper around one HTTP call: POSTing a GraphQL query/mutation to
the APS Data Exchange API. Every route in backend/routes/dx_routes.py goes
through this instead of calling `requests` directly, so error handling
(see DXService.execute below) and the auth header are only written once.
"""

import requests
from flask import current_app


class DXQueryError(Exception):
    """Raised when the APS GraphQL API responds with `errors` and no
    usable `data` at all - see DXService.execute for when partial errors
    are tolerated instead of raising.
    """


class DXService:
    """Executes GraphQL queries against the APS Data Exchange API."""

    @staticmethod
    def execute(query, access_token, variables=None, region=''):
        """Runs one GraphQL request and returns its `data` object.

        Args:
            query: Raw GraphQL query/mutation text (see dx_queries.py).
            access_token: A 3-legged APS access token for the signed-in user.
            variables: Dict of GraphQL variables the query expects, if any.
            region: Value for the `Region` header - required by the Data
                Exchange API for any call scoped to a hub/project/folder
                that isn't in the default region (US).

        Returns:
            The response's `data` dict (or `{}` if there was none).

        Raises:
            DXQueryError: If the response had `errors` and no usable `data`
                to fall back on - e.g. an expired token, or a request for
                something that doesn't exist.
        """
        response = requests.post(
            current_app.config['DATA_EXCHANGE_GRAPHQL_URL'],
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
                'Region': region,
            },
            json={'query': query, 'variables': variables or {}},
        )
        response.raise_for_status()

        payload = response.json()
        data = payload.get('data')
        errors = payload.get('errors')

        if errors:
            # GraphQL supports partial success: one bad field (e.g. an
            # exchange whose version reference 404s, null-bubbling up to
            # that one result) can sit alongside otherwise-good `data` for
            # everything else in the same response. Only raise when there's
            # no usable data at all - discarding a whole page over one bad
            # element would be worse than just missing that one field.
            current_app.logger.warning('DX GraphQL query returned partial errors: %s', errors)
            if not data:
                raise DXQueryError(errors)

        return data or {}
