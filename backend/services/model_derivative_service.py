"""Looks up the named views (floor plans, 3D views, ...) available in a
Revit file - for the Get Views node.

The Data Exchange GraphQL API has no way to list a Revit file's views -
per the DX GraphQL tutorial's "[Optional] Getting the View names from a
Revit model" section, that requires decoding the item's id back into a
plain Data Management project/item id, then going through the Data
Management and Model Derivative REST APIs instead. See:
https://autodesk-platform-services.github.io/aps-dx-graphql-tutorial/mutation/home/#optional-getting-the-view-names-from-a-revit-model
"""

import base64
import binascii

import requests

DATA_MANAGEMENT_ITEM_URL = 'https://developer.api.autodesk.com/data/v1/projects/{project_id}/items/{item_id}'
MODEL_DERIVATIVE_METADATA_URL = 'https://developer.api.autodesk.com/modelderivative/v2/designdata/{urn}/metadata'


class ViewsLookupError(Exception):
    """Raised when an item's id can't be decoded, or it has no derivative to read views from."""


def _decode_item_id(encoded_item_id):
    """Decodes a Data Exchange GraphQL item id into (project_id, item_id).

    The id is base64 of `item~<hub>~<project>~<folder>~<item>` (tilde
    separated); the project and item ids are the 3rd and last segments.

    Args:
        encoded_item_id: The `id` field as returned by the Items node's
            GraphQL query - still base64-encoded, not yet split apart.

    Returns:
        (project_id, item_id) - both plain Data Management ids, ready to
        use directly in a Data Management REST API URL.

    Raises:
        ViewsLookupError: If the id isn't valid base64, or decodes to
            something that doesn't have the expected 5 tilde-separated parts.
    """
    # base64 requires the input length be a multiple of 4, padded with
    # '=' - GraphQL ids are sometimes returned without that padding, so
    # add it back before decoding rather than let b64decode raise on it.
    padded = encoded_item_id + '=' * (-len(encoded_item_id) % 4)
    try:
        decoded = base64.b64decode(padded).decode('utf-8')
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ViewsLookupError(f'Could not decode item id {encoded_item_id!r}: {exc}') from exc

    parts = decoded.split('~')
    if len(parts) < 5:
        raise ViewsLookupError(f'Unexpected decoded item id shape: {decoded!r}')

    return parts[2], parts[-1]


def _find_derivative_urn(item_payload, tip_version_id):
    """Digs the Model Derivative "derivative" urn out of a Data Management
    item response's `included` section - the one entry there whose type is
    "versions" and whose id matches the item's own tip version.

    Args:
        item_payload: The raw JSON body from GET .../items/{item_id}.
        tip_version_id: The version id to match against (from
            item_payload['data']['relationships']['tip']).

    Returns:
        The derivative urn string, or None if no matching version (or no
        derivative on it) was found.
    """
    for included in item_payload.get('included') or []:
        if included.get('type') == 'versions' and included.get('id') == tip_version_id:
            derivatives = (included.get('relationships') or {}).get('derivatives') or {}
            return (derivatives.get('data') or {}).get('id')
    return None


def get_views_for_item(encoded_item_id, access_token):
    """Looks up every named view in the latest version of one Revit item.

    Three steps: decode the item id back into plain Data Management ids
    (_decode_item_id), fetch that item to find its tip version's
    derivative urn (_find_derivative_urn), then ask the Model Derivative
    API for that derivative's metadata - the `metadata` array in that
    response is the file's list of views.

    Args:
        encoded_item_id: The Items node's `id` field for one Revit item.
        access_token: A 3-legged APS access token with the data:read and
            viewables:read scopes.

    Returns:
        A list of `{id, name, derivative_urn, itemId}` dicts, one per view.
        `id` is the view's guid; `derivative_urn` is already
        base64-encoded exactly as the Model Derivative REST paths above
        need it (the Viewer needs it prefixed with "urn:" as-is, not
        re-encoded like an Exchange's fileUrn/fileVersionUrn); `itemId` is
        the same (still-encoded) id passed in, carried on each view so a
        downstream node (Create Exchange) can match a view back to the
        item it came from.

    Raises:
        ViewsLookupError: If the item id can't be decoded, or the item has
            no tip version or no derivative on it.
    """
    project_id, item_id = _decode_item_id(encoded_item_id)

    item_response = requests.get(
        DATA_MANAGEMENT_ITEM_URL.format(project_id=project_id, item_id=item_id),
        headers={'Authorization': f'Bearer {access_token}'},
    )
    item_response.raise_for_status()
    item_payload = item_response.json()

    tip = (item_payload.get('data') or {}).get('relationships', {}).get('tip') or {}
    tip_version_id = (tip.get('data') or {}).get('id')
    if not tip_version_id:
        raise ViewsLookupError(f'Item {item_id} has no tip version')

    derivative_urn = _find_derivative_urn(item_payload, tip_version_id)
    if not derivative_urn:
        raise ViewsLookupError(f'Tip version {tip_version_id} has no derivative')

    metadata_response = requests.get(
        MODEL_DERIVATIVE_METADATA_URL.format(urn=derivative_urn),
        headers={'Authorization': f'Bearer {access_token}'},
    )
    metadata_response.raise_for_status()
    metadata_payload = metadata_response.json()

    # derivative_urn is included on every view (not just returned once) so
    # the frontend can load either one directly - each view is otherwise a
    # self-contained {id, name} row, same as an Item/Exchange element.
    views = (metadata_payload.get('data') or {}).get('metadata') or []
    return [
        {'id': view['guid'], 'name': view['name'], 'derivative_urn': derivative_urn, 'itemId': encoded_item_id}
        for view in views
    ]
