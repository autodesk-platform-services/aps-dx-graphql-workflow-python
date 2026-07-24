"""Generates a standalone Python script that re-runs a saved flow outside the
browser — the same GraphQL/REST calls the live app makes, in dependency order.

Supported node types mirror the reference workflows under data/flows/:
navigation (Hubs through Exchanges), Get Views, Create Exchange, Get Exchange
Data, Filter, CSV/Excel Output, Debug Output, and a headless stand-in for
Viewer Output (prints connected exchange JSON instead of loading the Viewer).
"""

import re

from backend.nodes import NODE_TYPES
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

SUPPORTED_TYPES = {
    'hubs', 'projects', 'folders', 'items', 'exchanges', 'output',
    'get_views', 'logic', 'process', 'filter', 'data',
    'csv_output', 'excel_output',
}

PROJECT_FED_TYPES = {'projects', 'folders', 'items', 'exchanges', 'get_views'}

FETCH_FN_BY_TYPE = {
    'projects': 'get_projects',
    'folders': 'get_folders',
    'items': 'get_items',
    'exchanges': 'get_exchanges',
}

MULTI_INPUT_PORT0 = {'filter', 'process', 'data', 'csv_output', 'excel_output', 'logic'}

PRELUDE = '''#!/usr/bin/env python3
"""
Auto-generated from the Data Exchange Workflow Bench flow "__FLOW_NAME__" -
re-runs the same API pipeline headlessly.

Setup:
    pip install requests openpyxl
    export APS_ACCESS_TOKEN=<a 3-legged access token with the data:read scope>

    Tip: while logged into Data Exchange Workflow Bench in your browser, GET
    /api/dx/viewer-token returns your current session's access token.

Run:
    python __SCRIPT_FILENAME__

Viewer Output nodes print connected exchange data as JSON (the Viewer SDK is
browser-only). CSV/Excel Output writes files next to this script under
./output/ when no path is set, or to the path saved on the node.
"""
import base64
import binascii
import csv
import json
import os
import re
import sys

import requests
from openpyxl import Workbook

DATA_EXCHANGE_GRAPHQL_URL = 'https://developer.api.autodesk.com/dataexchange/2023-05/graphql'
DATA_MANAGEMENT_ITEM_URL = 'https://developer.api.autodesk.com/data/v1/projects/{project_id}/items/{item_id}'
MODEL_DERIVATIVE_METADATA_URL = 'https://developer.api.autodesk.com/modelderivative/v2/designdata/{urn}/metadata'
TOP_LEVEL_FOLDER_NAME = 'Project Files'
PAGE_LIMIT = 200
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'output')

ACCESS_TOKEN = os.environ.get('APS_ACCESS_TOKEN')
if not ACCESS_TOKEN:
    sys.exit('Set the APS_ACCESS_TOKEN environment variable before running this script (see the module docstring).')


def graphql_request(query, variables=None, region=''):
    """POSTs one GraphQL query/mutation to the Data Exchange API."""
    response = requests.post(
        DATA_EXCHANGE_GRAPHQL_URL,
        headers={
            'Authorization': f'Bearer {ACCESS_TOKEN}',
            'Content-Type': 'application/json',
            'Region': region,
        },
        json={'query': query, 'variables': variables or {}},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get('errors') and not payload.get('data'):
        raise RuntimeError(payload['errors'])
    return payload.get('data') or {}


def rest_get(url):
    response = requests.get(url, headers={'Authorization': f'Bearer {ACCESS_TOKEN}'})
    response.raise_for_status()
    return response.json()


GET_HUBS_QUERY = """__GET_HUBS_QUERY_BODY__"""
GET_PROJECTS_QUERY = """__GET_PROJECTS_QUERY_BODY__"""
GET_PROJECT_FOLDERS_QUERY = """__GET_PROJECT_FOLDERS_QUERY_BODY__"""
GET_FOLDER_FOLDERS_QUERY = """__GET_FOLDER_FOLDERS_QUERY_BODY__"""
GET_FOLDER_ITEMS_QUERY = """__GET_FOLDER_ITEMS_QUERY_BODY__"""
GET_FOLDER_EXCHANGES_QUERY = """__GET_FOLDER_EXCHANGES_QUERY_BODY__"""
CREATE_EXCHANGE_MUTATION = """__CREATE_EXCHANGE_MUTATION_BODY__"""
GET_EXCHANGE_ELEMENTS_QUERY = """__GET_EXCHANGE_ELEMENTS_QUERY_BODY__"""


def get_hubs():
    data = graphql_request(GET_HUBS_QUERY)
    return data.get('hubs', {}).get('results', [])


def get_projects(hubs):
    results = []
    for hub in hubs:
        region = hub.get('region', '')
        data = graphql_request(GET_PROJECTS_QUERY, {'hubId': hub['id']}, region=region)
        for project in data.get('projects', {}).get('results', []):
            project['region'] = region
            project['kind'] = 'project'
            results.append(project)
    return results


def _find_project_files_folder_id(project_id, region):
    data = graphql_request(GET_PROJECT_FOLDERS_QUERY, {'projectId': project_id}, region=region)
    top_folders = (data.get('project') or {}).get('folders', {}).get('results', [])
    folder = next((f for f in top_folders if f.get('name') == TOP_LEVEL_FOLDER_NAME), None)
    return folder['id'] if folder else None


def _resolve_folder_id(item):
    region = item.get('region', '')
    item_id = item.get('id')
    if not item_id:
        return None, region
    if item.get('kind') == 'folder':
        return item_id, region
    return _find_project_files_folder_id(item_id, region), region


def _aggregate_folder_contents(items_payload, query, extract_results, result_kind=None):
    aggregated = []
    for item in items_payload:
        folder_id, region = _resolve_folder_id(item)
        if not folder_id:
            continue
        cursor = None
        while True:
            pagination = {'limit': PAGE_LIMIT}
            if cursor:
                pagination['cursor'] = cursor
            data = graphql_request(query, {'folderId': folder_id, 'pagination': pagination}, region=region)
            results, next_cursor = extract_results(data)
            if result_kind:
                for result in results:
                    result['region'] = region
                    result['kind'] = result_kind
            aggregated.extend(results)
            if not next_cursor or len(results) < PAGE_LIMIT:
                break
            cursor = next_cursor
    return aggregated


def _extract_paginated(data, field_name):
    container = ((data.get('folder') or {}).get(field_name)) or {}
    return container.get('results') or [], (container.get('pagination') or {}).get('cursor')


def get_folders(projects):
    return _aggregate_folder_contents(
        projects, GET_FOLDER_FOLDERS_QUERY,
        lambda data: _extract_paginated(data, 'folders'),
        result_kind='folder',
    )


def get_items(projects):
    return _aggregate_folder_contents(
        projects, GET_FOLDER_ITEMS_QUERY,
        lambda data: _extract_paginated(data, 'items'),
    )


def get_exchanges(projects):
    return _aggregate_folder_contents(
        projects, GET_FOLDER_EXCHANGES_QUERY,
        lambda data: _extract_paginated(data, 'exchanges'),
    )


def filter_selected(items, selected_ids):
    selected_ids = set(selected_ids)
    return [item for item in items if item.get('id') in selected_ids]


def filter_by_name(elements, needle):
    """Client-side name filter — mirrors the Filter node in the live app."""
    needle = (needle or '').strip().lower()
    if not needle:
        return elements or []
    return [el for el in (elements or []) if needle in (el.get('name') or '').lower()]


def _decode_item_id(encoded_item_id):
    padded = encoded_item_id + '=' * (-len(encoded_item_id) % 4)
    try:
        decoded = base64.b64decode(padded).decode('utf-8')
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise RuntimeError(f'Could not decode item id {encoded_item_id!r}: {exc}') from exc
    parts = decoded.split('~')
    if len(parts) < 5:
        raise RuntimeError(f'Unexpected decoded item id shape: {decoded!r}')
    return parts[2], parts[-1]


def _find_derivative_urn(item_payload, tip_version_id):
    for included in item_payload.get('included') or []:
        if included.get('type') == 'versions' and included.get('id') == tip_version_id:
            derivatives = (included.get('relationships') or {}).get('derivatives') or {}
            return (derivatives.get('data') or {}).get('id')
    return None


def get_views_for_items(items):
    """Named views for each Revit item — Data Management + Model Derivative REST."""
    results = []
    for item in items or []:
        item_id = item.get('id')
        if not item_id:
            continue
        try:
            project_id, plain_item_id = _decode_item_id(item_id)
            item_payload = rest_get(DATA_MANAGEMENT_ITEM_URL.format(project_id=project_id, item_id=plain_item_id))
            tip = (item_payload.get('data') or {}).get('relationships', {}).get('tip') or {}
            tip_version_id = (tip.get('data') or {}).get('id')
            if not tip_version_id:
                continue
            derivative_urn = _find_derivative_urn(item_payload, tip_version_id)
            if not derivative_urn:
                continue
            metadata_payload = rest_get(MODEL_DERIVATIVE_METADATA_URL.format(urn=derivative_urn))
            views = (metadata_payload.get('data') or {}).get('metadata') or []
            for view in views:
                results.append({
                    'id': view['guid'],
                    'name': view['name'],
                    'derivative_urn': derivative_urn,
                    'itemId': item_id,
                })
        except (RuntimeError, requests.RequestException) as exc:
            print(f'Warning: get views failed for item {item_id}: {exc}', file=sys.stderr)
    return results


def _fetch_exchange_elements(exchange_id, region, filter_query):
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
        data = graphql_request(GET_EXCHANGE_ELEMENTS_QUERY, variables, region=region)
        elements = ((data.get('exchange') or {}).get('elements')) or {}
        page = elements.get('results') or []
        results.extend(page)
        cursor = (elements.get('pagination') or {}).get('cursor')
        if not cursor or len(page) < PAGE_LIMIT:
            break
    return results


def _find_property_value(properties, name):
    name = name.lower()
    for prop in properties:
        if (prop.get('name') or '').lower() == name:
            return prop.get('value')
    return None


def _rows_from_elements(elements, exchange_name):
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


def get_exchange_data(exchanges, filter_query=''):
    """Quantity-takeoff rows for each exchange — mirrors Get Exchange Data."""
    rows = []
    for exchange in exchanges or []:
        exchange_id = exchange.get('id')
        if not exchange_id:
            continue
        region = exchange.get('region', '')
        try:
            elements = _fetch_exchange_elements(exchange_id, region, filter_query)
            rows.extend(_rows_from_elements(elements, exchange.get('name')))
        except (RuntimeError, requests.RequestException) as exc:
            print(f'Warning: exchange data failed for {exchange_id}: {exc}', file=sys.stderr)
    return rows


def create_exchanges(views, folders):
    """Runs createExchange once per view into the first selected folder."""
    folder = (folders or [None])[0]
    if not folder or not folder.get('id'):
        return [{'error': 'A destination folder is required'}]

    folder_id = folder['id']
    region = folder.get('region', '')
    results = []
    for view in views or []:
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
            data = graphql_request(CREATE_EXCHANGE_MUTATION, variables, region=region)
            results.append(data)
        except (RuntimeError, requests.RequestException) as exc:
            results.append({'error': str(exc)})
    return results


def _format_date_only(iso_string):
    return iso_string.split('T')[0] if iso_string else ''


def _stringify_cell(value):
    if value is None:
        return ''
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


def _export_row(element):
    if 'tipVersion' in element:
        return [
            element.get('name', ''),
            (element.get('tipVersion') or {}).get('versionNumber', ''),
            _format_date_only((element.get('tipVersion') or {}).get('createdOn', '')),
        ]
    if 'alternativeIdentifiers' in element or 'version' in element:
        return [
            element.get('name', ''),
            (element.get('version') or {}).get('versionNumber', ''),
            _format_date_only((element.get('version') or {}).get('createdOn', '')),
        ]
    if 'keyProperty' in element:
        return [
            element.get('exchangeName', ''),
            element.get('elementId', ''),
            element.get('category', ''),
            element.get('elementName', ''),
            element.get('type', ''),
            element.get('keyProperty', ''),
            element.get('value', ''),
        ]
    return [element.get('name', '')]


def _export_columns(element):
    if 'tipVersion' in element:
        return ['Name', 'Version', 'Created']
    if 'alternativeIdentifiers' in element or 'version' in element:
        return ['Name', 'Version', 'Created']
    if 'keyProperty' in element:
        return [
            'Exchange Name', 'Element ID', 'Category', 'Element Name',
            'Type', 'Key Property', 'Value',
        ]
    return ['Name']


def build_export_tables(groups):
    """Builds [{name, columns, rows}, ...] — mirrors tableExport.js."""
    buckets = {}
    shape_names = {
        'Name Version Created': 'items_exchanges',
        'Exchange Name Element ID Category Element Name Type Key Property Value': 'exchange_elements',
        'Name': 'table',
    }
    for group in groups or []:
        for element in group or []:
            columns = _export_columns(element)
            signature = ' '.join(columns)
            if signature not in buckets:
                buckets[signature] = {
                    'name': shape_names.get(signature, 'table'),
                    'columns': columns,
                    'rows': [],
                }
            buckets[signature]['rows'].append(
                [_stringify_cell(v) for v in _export_row(element)]
            )
    return list(buckets.values())


def _safe_filename_part(text):
    return re.sub(r'[^a-zA-Z0-9_-]', '', text or '') or 'export'


def _default_export_path(node_id, extension):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return os.path.join(OUTPUT_DIR, f'{_safe_filename_part(node_id)}{extension}')


def _resolve_export_path(filepath, extension):
    if filepath:
        path = filepath if os.path.isabs(filepath) else os.path.join(SCRIPT_DIR, filepath)
    else:
        path = _default_export_path('export', extension)
    if not path.lower().endswith(extension):
        path += extension
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    return path


def _insert_suffix(path, suffix):
    base, ext = os.path.splitext(path)
    return f'{base}_{_safe_filename_part(suffix)}{ext}'


def write_csv_tables(tables, filepath, node_id):
    if not tables:
        return []
    base_path = _resolve_export_path(filepath, '.csv') if filepath else _default_export_path(node_id, '.csv')
    paths = []
    for table in tables:
        path = base_path if len(tables) == 1 else _insert_suffix(base_path, table['name'])
        with open(path, 'w', newline='', encoding='utf-8') as handle:
            writer = csv.writer(handle)
            writer.writerow(table['columns'])
            writer.writerows(table['rows'])
        paths.append(path)
    return paths


def _sheet_name(name, used_names):
    cleaned = re.sub(r'[\\[\\]:*?/\\\\]', '_', name or 'Sheet')[:31] or 'Sheet'
    candidate = cleaned
    index = 2
    while candidate in used_names:
        candidate = f'{cleaned[:28]}_{index}'
        index += 1
    used_names.add(candidate)
    return candidate


def write_excel_tables(tables, filepath, node_id):
    if not tables:
        return None
    path = _resolve_export_path(filepath, '.xlsx') if filepath else _default_export_path(node_id, '.xlsx')
    workbook = Workbook()
    workbook.remove(workbook.active)
    used_names = set()
    for table in tables:
        sheet = workbook.create_sheet(title=_sheet_name(table['name'], used_names))
        sheet.append(table['columns'])
        for row in table['rows']:
            sheet.append(row)
    workbook.save(path)
    return path

'''


def _node_label(node_type):
    return NODE_TYPES.get(node_type, {}).get('name', node_type)


def _topological_order(node_ids, connections):
    id_set = set(node_ids)
    incoming_count = {nid: 0 for nid in node_ids}
    outgoing = {nid: [] for nid in node_ids}
    for conn in connections:
        if conn['from'] in id_set and conn['to'] in id_set:
            outgoing[conn['from']].append(conn['to'])
            incoming_count[conn['to']] += 1

    ready = [nid for nid in node_ids if incoming_count[nid] == 0]
    ordered = []
    seen = set()
    while ready:
        nid = ready.pop(0)
        if nid in seen:
            continue
        seen.add(nid)
        ordered.append(nid)
        for nxt in outgoing[nid]:
            incoming_count[nxt] -= 1
            if incoming_count[nxt] == 0:
                ready.append(nxt)

    ordered.extend(nid for nid in node_ids if nid not in seen)
    return ordered


def _incoming_connections(connections, supported):
    port0 = {}
    port1 = {}
    for conn in connections:
        target = conn['to']
        source = conn['from']
        if target not in supported or source not in supported:
            continue
        port_index = conn.get('toPortIndex', 0)
        if port_index == 0:
            port0.setdefault(target, []).append(source)
        elif port_index == 1:
            port1[target] = source
    return port0, port1


def _merge_lists_expr(source_ids, var_of):
    if not source_ids:
        return '[]'
    if len(source_ids) == 1:
        return var_of[source_ids[0]]
    return '(' + ' + '.join(f'({var_of[source_id]} or [])' for source_id in source_ids) + ')'


def _export_groups_expr(source_ids, var_of):
    if not source_ids:
        return '[]'
    if len(source_ids) == 1:
        return f'[{var_of[source_ids[0]]}]'
    return '[' + ', '.join(var_of[source_id] for source_id in source_ids) + ']'


def _header_line(node_type, node_id, upstream_labels):
    header = f'# --- {_node_label(node_type)} ({node_id})'
    if upstream_labels:
        header += ', fed by ' + ', '.join(upstream_labels)
    else:
        header += ' ---' if node_type == 'hubs' else ' - nothing connected ---'
    header += ' ---'
    return header


def generate_script(flow, name='flow', filename='flow.py'):
    """Turns one saved flow into a complete, runnable Python script."""
    all_nodes = {n['id']: n for n in (flow.get('nodes') or [])}
    connections = flow.get('connections') or []

    supported = {nid: n for nid, n in all_nodes.items() if n.get('type') in SUPPORTED_TYPES}
    order = _topological_order(list(supported.keys()), connections)
    port0_in, port1_in = _incoming_connections(connections, supported)

    var_of = {}
    lines = []

    for nid in order:
        node = supported[nid]
        node_type = node['type']
        var_name = nid.replace('-', '_')

        upstream_p0 = port0_in.get(nid, [])
        upstream_p1 = port1_in.get(nid)
        upstream_labels = []
        for source_id in upstream_p0:
            upstream_labels.append(
                f'{_node_label(supported[source_id]["type"])} ({source_id})'
            )
        if upstream_p1 and node_type == 'logic':
            upstream_labels.append(
                f'{_node_label(supported[upstream_p1]["type"])} ({upstream_p1}) on port 1'
            )

        lines.append(_header_line(node_type, nid, upstream_labels))

        if node_type == 'hubs':
            lines.append(
                f'{var_name} = filter_selected(get_hubs(), {node.get("selectedIds") or []!r})'
            )
        elif node_type == 'output':
            upstream_var = var_of.get(upstream_p0[0]) if upstream_p0 else None
            lines.append(
                f'print(json.dumps({upstream_var}, indent=2))' if upstream_var else "print('No value')"
            )
        elif node_type in PROJECT_FED_TYPES:
            source_expr = _merge_lists_expr(upstream_p0, var_of) if upstream_p0 else '[]'
            if (
                len(upstream_p0) == 1
                and supported[upstream_p0[0]]['type'] == 'filter'
                and node_type in {'folders', 'items', 'exchanges'}
            ):
                lines.append(
                    f'{var_name} = filter_selected({source_expr}, {node.get("selectedIds") or []!r})'
                )
            elif node_type == 'get_views':
                lines.append(
                    f'{var_name} = filter_selected(get_views_for_items({source_expr}), '
                    f'{node.get("selectedIds") or []!r})'
                )
            else:
                fetch_fn = FETCH_FN_BY_TYPE[node_type]
                lines.append(
                    f'{var_name} = filter_selected({fetch_fn}({source_expr}), '
                    f'{node.get("selectedIds") or []!r})'
                )
        elif node_type == 'filter':
            source_expr = _merge_lists_expr(upstream_p0, var_of)
            lines.append(f'{var_name} = filter_by_name({source_expr}, {node.get("filterText") or ""!r})')
        elif node_type == 'process':
            source_expr = _merge_lists_expr(upstream_p0, var_of)
            lines.append(
                f'{var_name} = get_exchange_data({source_expr}, {node.get("filterQuery") or ""!r})'
            )
        elif node_type == 'logic':
            views_expr = _merge_lists_expr(upstream_p0, var_of)
            folder_var = var_of.get(upstream_p1, '[]') if upstream_p1 else '[]'
            lines.append(f'{var_name} = create_exchanges({views_expr}, {folder_var})')
            lines.append(f'print(json.dumps({var_name}, indent=2))')
        elif node_type == 'data':
            source_expr = _merge_lists_expr(upstream_p0, var_of)
            lines.append(
                '# Viewer Output is browser-only — headless replay prints connected exchange data instead.'
            )
            lines.append(f'print(json.dumps({source_expr}, indent=2))')
            var_of[nid] = source_expr
            lines.append('')
            continue
        elif node_type == 'csv_output':
            groups_expr = _export_groups_expr(upstream_p0, var_of)
            tables_var = f'{var_name}_tables'
            filepath = node.get('filepath') or None
            lines.append(f'{tables_var} = build_export_tables({groups_expr})')
            lines.append(
                f'{var_name}_paths = write_csv_tables({tables_var}, {filepath!r}, {nid!r})'
            )
            lines.append(f'print("CSV exported to", {var_name}_paths)')
            lines.append('')
            continue
        elif node_type == 'excel_output':
            groups_expr = _export_groups_expr(upstream_p0, var_of)
            tables_var = f'{var_name}_tables'
            filepath = node.get('filepath') or None
            lines.append(f'{tables_var} = build_export_tables({groups_expr})')
            lines.append(
                f'{var_name}_path = write_excel_tables({tables_var}, {filepath!r}, {nid!r})'
            )
            lines.append(f'print("Excel exported to", {var_name}_path)')
            lines.append('')
            continue
        else:
            lines.append(f'# Unsupported node type in export: {node_type!r}')

        var_of[nid] = var_name
        lines.append('')

    prelude = PRELUDE.replace('__FLOW_NAME__', name).replace('__SCRIPT_FILENAME__', filename)
    for token, query in (
        ('__GET_HUBS_QUERY_BODY__', GET_HUBS_QUERY),
        ('__GET_PROJECTS_QUERY_BODY__', GET_PROJECTS_QUERY),
        ('__GET_PROJECT_FOLDERS_QUERY_BODY__', GET_PROJECT_FOLDERS_QUERY),
        ('__GET_FOLDER_FOLDERS_QUERY_BODY__', GET_FOLDER_FOLDERS_QUERY),
        ('__GET_FOLDER_ITEMS_QUERY_BODY__', GET_FOLDER_ITEMS_QUERY),
        ('__GET_FOLDER_EXCHANGES_QUERY_BODY__', GET_FOLDER_EXCHANGES_QUERY),
        ('__CREATE_EXCHANGE_MUTATION_BODY__', CREATE_EXCHANGE_MUTATION),
        ('__GET_EXCHANGE_ELEMENTS_QUERY_BODY__', GET_EXCHANGE_ELEMENTS_QUERY),
    ):
        prelude = prelude.replace(token, query)

    return prelude + '\n# --- Flow ---\n\n' + '\n'.join(lines)


def filename_for(name):
    slug = re.sub(r'[^a-zA-Z0-9_-]+', '_', name or '').strip('_') or 'flow'
    return f'{slug}.py'
