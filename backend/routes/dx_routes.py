"""The `/api/dx/*` routes - one per node type that talks to the APS Data
Exchange API (or, for Get Views, the Data Management + Model Derivative
REST APIs instead - see model_derivative_service.py). Each route receives
whatever its node's frontend module already resolved as the upstream
selection, runs the relevant query/queries, and hands back plain JSON for
that node's own table.

Rough map of what's in this file, top to bottom:
    - `_resolve_folder_id` / `_aggregate_folder_contents` / `_extract_paginated`
      - shared machinery behind the Folders/Items/Exchanges routes.
    - `/hubs`, `/projects`, `/folders`, `/items`, `/exchanges`
      - the "browse the Data Management hierarchy" routes.
    - `/views`, `/create-exchange`
      - Get Views and Create Exchange.
    - `_fetch_exchange_elements` / `_find_property_value` / `_rows_from_elements`
      - shared machinery behind Get Exchange Data.
    - `/exchange-data`, `/export/csv`, `/export/excel`
      - Get Exchange Data and CSV/Excel download routes (streamed attachments).
"""

from flask import Blueprint, Response, current_app, jsonify, request, session

from backend.services.dx_service import DXQueryError, DXService
from backend.services.dx_queries import (
    GET_HUBS_QUERY,
    GET_PROJECTS_QUERY,
    GET_PROJECT_FOLDERS_QUERY,
    GET_FOLDER_FOLDERS_QUERY,
    GET_FOLDER_ITEMS_QUERY,
    GET_FOLDER_EXCHANGES_QUERY,
    CREATE_EXCHANGE_MUTATION,
    GET_EXCHANGE_ELEMENTS_QUERY,
)
from backend.services.model_derivative_service import get_views_for_item
from backend.services.export_service import build_csv_download, build_excel_download

dx_bp = Blueprint('dx', __name__)

# The folder whose contents populate the Folders/Items/Exchanges nodes - a
# project's other top-level folders (e.g. "For the Field") aren't surfaced today.
TOP_LEVEL_FOLDER_NAME = 'Project Files'

# How many folders/items/exchanges/elements to request per page - see
# _aggregate_folder_contents and _fetch_exchange_elements, the two places
# this drives a pagination-following loop.
PAGE_LIMIT = 200


# --- Folders/Items/Exchanges: shared machinery -----------------------------

def _find_project_files_folder_id(project_id, region, access_token):
    """Returns the id of a project's "Project Files" folder, or None."""
    data = DXService.execute(
        GET_PROJECT_FOLDERS_QUERY,
        access_token,
        variables={'projectId': project_id},
        region=region,
    )
    top_folders = (data.get('project') or {}).get('folders', {}).get('results', [])
    folder = next((f for f in top_folders if f.get('name') == TOP_LEVEL_FOLDER_NAME), None)
    return folder['id'] if folder else None


def _resolve_folder_id(item, access_token):
    """Returns (folder_id, region) to query for one incoming item.

    An item is either a project (its "Project Files" folder is resolved
    first) or an already-resolved folder - e.g. chaining a Folders node's
    output into another Folders/Items/Exchanges node to drill into a
    specific subfolder, rather than always starting back at a project root.
    """
    region = item.get('region', '')
    item_id = item.get('id')
    if not item_id:
        return None, region

    if item.get('kind') == 'folder':
        return item_id, region

    return _find_project_files_folder_id(item_id, region, access_token), region


def _extract_paginated(data, field_name):
    """(results, next-page cursor) for a `folder.<field_name>` selection
    shaped `{ pagination { cursor, pageSize }, results }` - the same
    container shape `folders`/`items`/`exchanges` all share.
    """
    container = ((data.get('folder') or {}).get(field_name)) or {}
    return container.get('results') or [], (container.get('pagination') or {}).get('cursor')


def _aggregate_folder_contents(items_payload, access_token, query, extract_results, result_kind=None):
    """For each incoming item: resolve the folder to query (see
    `_resolve_folder_id`), run `query` against it, and flatten
    `extract_results(data)` from every item into one list. An item that
    errors or has no resolvable folder is skipped.

    `folder.folders`/`.items`/`.exchanges` are all paginated - a folder with
    more than one page's worth was silently truncated to just the first
    page before this followed `pagination.cursor` (the token for the *next*
    page) until a page comes back short of PAGE_LIMIT, same fix as
    Get Exchange Data's element pagination. `extract_results(data)` returns
    `(results, cursor)` rather than just `results` so this can drive that loop.

    When `result_kind` is set (e.g. 'folder' for the /folders route), each
    result is tagged with it plus the region used, so it can itself be fed
    into another Folders/Items/Exchanges node later.
    """
    aggregated = []

    for item in items_payload:
        try:
            folder_id, region = _resolve_folder_id(item, access_token)
        except Exception as exc:  # noqa: BLE001 - external API call boundary, skip and continue
            current_app.logger.warning('Resolving folder failed for %s: %s', item.get('id'), exc)
            continue
        if not folder_id:
            continue

        # `cursor` starts as None (meaning "first page, no cursor yet") -
        # the API rejects an empty-string cursor as malformed, so the
        # 'cursor' key is only added to `pagination` once we actually have
        # a real one from a previous page.
        cursor = None
        while True:
            pagination = {'limit': PAGE_LIMIT}
            if cursor:
                pagination['cursor'] = cursor
            try:
                data = DXService.execute(
                    query,
                    access_token,
                    variables={'folderId': folder_id, 'pagination': pagination},
                    region=region,
                )
            except Exception as exc:  # noqa: BLE001 - external API call boundary, skip and continue
                current_app.logger.warning('GetFolderContent query failed for folder %s: %s', folder_id, exc)
                break

            results, next_cursor = extract_results(data)
            if result_kind:
                for result in results:
                    result['region'] = region
                    result['kind'] = result_kind
            aggregated.extend(results)

            # No cursor for a next page, or a short page (fewer results
            # than we asked for) both mean we've reached the end.
            if not next_cursor or len(results) < PAGE_LIMIT:
                break
            cursor = next_cursor

    return aggregated


@dx_bp.before_request
def require_auth():
    """Runs before every route in this blueprint - gates the whole
    /api/dx/* namespace behind having signed in via /oauth/login first.
    """
    if 'access_token' not in session:
        return jsonify({'error': 'not_authenticated'}), 401


@dx_bp.route('/viewer-token')
def viewer_token():
    """GET /api/dx/viewer-token - hands the current session's APS access
    token to client-side JS for Autodesk.Viewing.Initializer's
    getAccessToken callback. This is the same 3-legged token already used
    for every other /api/dx/* call - it just also needs the
    viewables:read scope (see config.py's APS_SCOPE).
    """
    return jsonify({
        'access_token': session['access_token'],
        'expires_in': session.get('expires_in') or 3600,
    })


@dx_bp.route('/hubs')
def hubs():
    """GET /api/dx/hubs - every hub the signed-in user can see, for the
    Hubs node.
    """
    try:
        data = DXService.execute(GET_HUBS_QUERY, session['access_token'])
    except Exception as exc:  # noqa: BLE001 - external API call boundary
        current_app.logger.warning('GetHubs query failed: %s', exc)
        return jsonify({'error': str(exc)}), 502

    return jsonify(data.get('hubs', {}).get('results', []))


@dx_bp.route('/projects', methods=['POST'])
def projects():
    """POST /api/dx/projects - every project across the Hubs node's
    selected hubs, for the Projects node. One GetProjects call per hub
    (each hub may live in a different Region), aggregated into a single
    flat list.
    """
    payload = request.get_json(force=True) or {}
    hubs_payload = payload.get('hubs') or []

    results = []
    for hub in hubs_payload:
        hub_id = hub.get('id')
        if not hub_id:
            continue
        region = hub.get('region', '')
        try:
            data = DXService.execute(
                GET_PROJECTS_QUERY,
                session['access_token'],
                variables={'hubId': hub_id},
                region=region,
            )
            project_results = data.get('projects', {}).get('results', [])
            # Tag each project with the region of the hub it came from (so a
            # downstream Folders/Items/Exchanges node knows which Region
            # header to send) and its kind (so that node knows to resolve
            # this project's "Project Files" folder rather than treat the
            # id as an already-resolved folder id).
            for project in project_results:
                project['region'] = region
                project['kind'] = 'project'
            results.extend(project_results)
        except Exception as exc:  # noqa: BLE001 - external API call boundary, skip and continue
            current_app.logger.warning('GetProjects query failed for hub %s: %s', hub_id, exc)

    return jsonify(results)


@dx_bp.route('/folders', methods=['POST'])
def folders():
    """POST /api/dx/folders - subfolders of every selected Project/Folder,
    for the Folders node.
    """
    payload = request.get_json(force=True) or {}
    results = _aggregate_folder_contents(
        payload.get('projects') or [],
        session['access_token'],
        GET_FOLDER_FOLDERS_QUERY,
        lambda data: _extract_paginated(data, 'folders'),
        # Tag results as folders so this node's own output can be fed back
        # into another Folders/Items/Exchanges node to drill further in.
        result_kind='folder',
    )
    return jsonify(results)


@dx_bp.route('/items', methods=['POST'])
def items():
    """POST /api/dx/items - items in every selected Project/Folder, for
    the Items node.
    """
    payload = request.get_json(force=True) or {}
    results = _aggregate_folder_contents(
        payload.get('projects') or [],
        session['access_token'],
        GET_FOLDER_ITEMS_QUERY,
        lambda data: _extract_paginated(data, 'items'),
    )
    return jsonify(results)


@dx_bp.route('/exchanges', methods=['POST'])
def exchanges():
    """POST /api/dx/exchanges - exchanges in every selected Project/Folder,
    for the Exchanges node.
    """
    payload = request.get_json(force=True) or {}
    results = _aggregate_folder_contents(
        payload.get('projects') or [],
        session['access_token'],
        GET_FOLDER_EXCHANGES_QUERY,
        lambda data: _extract_paginated(data, 'exchanges'),
        # Tag results with their region - Get Exchange Data needs it for the
        # Region header on its own per-exchange query.
        result_kind='exchange',
    )
    return jsonify(results)


@dx_bp.route('/views', methods=['POST'])
def views():
    """POST /api/dx/views - the named views available in every selected
    Item, for the Get Views node. Each incoming "project" here is actually
    an Item (see selectableProjectFedTable.js's fixed request shape) - one
    Data Management + Model Derivative round trip per item (see
    model_derivative_service.get_views_for_item), aggregated into a single
    flat list of views.
    """
    payload = request.get_json(force=True) or {}
    access_token = session['access_token']

    results = []
    for item in payload.get('projects') or []:
        item_id = item.get('id')
        if not item_id:
            continue
        try:
            results.extend(get_views_for_item(item_id, access_token))
        except Exception as exc:  # noqa: BLE001 - external API call boundary, skip and continue
            current_app.logger.warning('Get views failed for item %s: %s', item_id, exc)
            continue

    return jsonify(results)


@dx_bp.route('/create-exchange', methods=['POST'])
def create_exchange():
    """POST /api/dx/create-exchange - runs the createExchange mutation
    once per selected View, for the Create Exchange node.

    Fed by Create Exchange's two input ports as-is: `views` (Get Views'
    output, each tagged with the id of the item it belongs to - see
    model_derivative_service.get_views_for_item - so no separate Items
    input is needed) and `folders` (only the first one is used as the
    destination, per the node's own "just one folder" rule). Aggregates
    one mutation result per view into a single list - nothing here shapes
    or filters that output, so a failed call shows up as its own raw
    GraphQL error/response too.
    """
    payload = request.get_json(force=True) or {}
    views_payload = payload.get('views') or []
    folders_payload = payload.get('folders') or []

    folder = folders_payload[0] if folders_payload else None
    if not folder or not folder.get('id'):
        return jsonify({'error': 'A destination folder is required'}), 400

    folder_id = folder['id']
    region = folder.get('region', '')
    access_token = session['access_token']

    results = []
    for view in views_payload:
        item_id = view.get('itemId')
        view_name = view.get('name')
        if not item_id or not view_name:
            continue

        variables = {
            'input': {
                'viewName': view_name,
                'source': {'fileId': item_id},
                'target': {'name': view_name, 'folderId': folder_id},
            },
        }
        try:
            data = DXService.execute(CREATE_EXCHANGE_MUTATION, access_token, variables=variables, region=region)
        except DXQueryError as exc:
            data = {'errors': exc.args[0]}
        except Exception as exc:  # noqa: BLE001 - external API call boundary, record and keep going
            current_app.logger.warning('createExchange failed for item %s / view %s: %s', item_id, view_name, exc)
            data = {'error': str(exc)}
        results.append(data)

    return jsonify(results)


# --- Get Exchange Data: shared machinery ------------------------------------

def _fetch_exchange_elements(exchange_id, access_token, region, filter_query):
    """Runs FilterUsingComplexQuery against one exchange, following the
    response's `pagination.cursor` (the token for the *next* page) until a
    page comes back short of PAGE_LIMIT - i.e. fetches every matching
    element rather than just the first page, since omitting pagination
    isn't documented as "return everything" (see PAGE_LIMIT's other use in
    _aggregate_folder_contents, same underlying concern).
    """
    element_filter = {'query': filter_query or ''}
    results = []
    cursor = None

    while True:
        pagination = {'limit': PAGE_LIMIT}
        if cursor:
            pagination['cursor'] = cursor
        variables = {
            'exchangeId': exchange_id,
            'elementFilter': element_filter,
            'elementPagination': pagination,
        }
        data = DXService.execute(GET_EXCHANGE_ELEMENTS_QUERY, access_token, variables=variables, region=region)
        elements = ((data.get('exchange') or {}).get('elements')) or {}
        page = elements.get('results') or []
        results.extend(page)

        cursor = (elements.get('pagination') or {}).get('cursor')
        if not cursor or len(page) < PAGE_LIMIT:
            break

    return results


def _find_property_value(properties, name):
    """The value of the first property in `properties` whose name matches
    `name`, case-insensitively - or None if there isn't one.

    Case-insensitive because the RSQL filter path (`property.name.category`)
    is lowercase, but property.name as actually returned by the API doesn't
    reliably match that casing (or the Revit UI's "Category"/"Type" labels).
    """
    name = name.lower()
    for prop in properties:
        if (prop.get('name') or '').lower() == name:
            return prop.get('value')
    return None


def _rows_from_elements(elements, exchange_name):
    """Flattens a FilterUsingComplexQuery element list into table rows - one
    row per element property. `Category`/`Type` are pulled from whichever
    property in that same element is named "Category"/"Type" (Revit's
    built-in parameters, returned alongside custom ones) and repeated on
    every row for that element, rather than only appearing on their own row.
    `exchange_name` is likewise repeated on every row - it identifies which
    exchange a row came from once several are aggregated into one table.
    """
    rows = []

    for element in elements:
        properties = ((element.get('properties') or {}).get('results')) or []
        category = _find_property_value(properties, 'category')
        type_value = _find_property_value(properties, 'type')

        for prop in properties:
            rows.append({
                'exchangeName': exchange_name,
                'elementId': element.get('id'),
                'category': category,
                'elementName': element.get('name'),
                'type': type_value,
                'keyProperty': prop.get('name'),
                'value': prop.get('value'),
            })

    return rows


@dx_bp.route('/exchange-data', methods=['POST'])
def exchange_data():
    """POST /api/dx/exchange-data - a quantity-takeoff-style table (every
    element and property) for every selected Exchange, for the Get
    Exchange Data node.

    Fed by Get Exchange Data's single input port, which can aggregate
    several Exchanges nodes at once (see core/run.js). `filter` is an
    optional RSQL query string (APS's "Advanced Filtering" syntax, e.g.
    "property.name.category==Walls") applied to every exchange in this
    request; omitted/empty means no filter.
    """
    payload = request.get_json(force=True) or {}
    access_token = session['access_token']
    filter_query = (payload.get('filter') or '').strip()

    rows = []
    for exchange in payload.get('exchanges') or []:
        exchange_id = exchange.get('id')
        if not exchange_id:
            continue
        region = exchange.get('region', '')
        try:
            elements = _fetch_exchange_elements(exchange_id, access_token, region, filter_query)
        except Exception as exc:  # noqa: BLE001 - external API call boundary, skip and continue
            current_app.logger.warning('FilterUsingComplexQuery failed for exchange %s: %s', exchange_id, exc)
            continue

        rows.extend(_rows_from_elements(elements, exchange.get('name')))

    return jsonify(rows)


@dx_bp.route('/export/csv', methods=['POST'])
def export_csv():
    """POST /api/dx/export/csv - builds the CSV Output node's table(s) in
    memory and streams them back as a browser download (one `.csv`, or a
    `.zip` of several when the connected sources have distinct column
    shapes). Fed by tableExport.js's `buildTables()` — see
    export_service.build_csv_download.
    """
    payload = request.get_json(force=True) or {}
    tables = payload.get('tables') or []
    filepath = payload.get('filepath')
    node_id = payload.get('nodeId') or 'export'

    if not tables:
        return jsonify({'error': 'no_rows'}), 400

    try:
        body, filename, mimetype = build_csv_download(tables, filepath, node_id)
    except (ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400

    if not body:
        return jsonify({'error': 'no_rows'}), 400

    return Response(
        body,
        mimetype=mimetype,
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@dx_bp.route('/export/excel', methods=['POST'])
def export_excel():
    """POST /api/dx/export/excel - same as /export/csv, but returns one
    `.xlsx` workbook (see export_service.build_excel_download).
    """
    payload = request.get_json(force=True) or {}
    tables = payload.get('tables') or []
    filepath = payload.get('filepath')
    node_id = payload.get('nodeId') or 'export'

    if not tables:
        return jsonify({'error': 'no_rows'}), 400

    try:
        body, filename, mimetype = build_excel_download(tables, filepath, node_id)
    except (ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400

    if not body:
        return jsonify({'error': 'no_rows'}), 400

    return Response(
        body,
        mimetype=mimetype,
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )
