"""Plain CRUD over saved flows (backend/services/flow_service.py), plus
one extra route that isn't CRUD at all: /export-script, which turns a flow
into a standalone Python script instead of just returning its JSON.

Registered under /api/flows (see backend/__init__.py's
`register_blueprint(flow_bp, url_prefix='/api/flows')`), and gated behind
login same as every /api/dx/* route - a flow graph isn't sensitive data
exactly, but there's no reason to expose it to a signed-out visitor either.
"""

from flask import Blueprint, Response, jsonify, request, session

from backend.services import flow_codegen
from backend.services.flow_service import FlowService

flow_bp = Blueprint('flows', __name__)


@flow_bp.before_request
def require_auth():
    """Runs before every route in this blueprint - Flask's per-blueprint
    hook for "gate the whole thing behind one check" without repeating it
    in each route function.
    """
    if 'access_token' not in session:
        return jsonify({'error': 'not_authenticated'}), 401


@flow_bp.route('', methods=['GET'])
def list_flows():
    """GET /api/flows - every saved flow's `{id, name, updated_at}`, for
    the toolbar's "Saved flows" dropdown.
    """
    return jsonify(FlowService.list_flows())


@flow_bp.route('', methods=['POST'])
def create_flow():
    """POST /api/flows - saves a new flow, returning its full record
    (including the server-generated id) with a 201 Created status.
    """
    payload = request.get_json(force=True) or {}
    record = FlowService.save_flow(payload.get('name'), payload.get('flow'))
    return jsonify(record), 201


@flow_bp.route('/<flow_id>', methods=['GET'])
def get_flow(flow_id):
    """GET /api/flows/<flow_id> - one flow's full saved record, or 404 if
    no flow with that id exists.
    """
    record = FlowService.load_flow(flow_id)
    if record is None:
        return jsonify({'error': 'not_found'}), 404
    return jsonify(record)


@flow_bp.route('/<flow_id>', methods=['PUT'])
def update_flow(flow_id):
    """PUT /api/flows/<flow_id> - overwrites an existing flow's name/graph
    in place, keeping its id and original created_at.
    """
    payload = request.get_json(force=True) or {}
    record = FlowService.save_flow(payload.get('name'), payload.get('flow'), flow_id=flow_id)
    return jsonify(record)


@flow_bp.route('/<flow_id>', methods=['DELETE'])
def delete_flow(flow_id):
    """DELETE /api/flows/<flow_id> - always returns 204, whether or not a
    flow with that id actually existed (deleting something already gone
    isn't an error from the caller's point of view either).
    """
    FlowService.delete_flow(flow_id)
    return '', 204


@flow_bp.route('/export-script', methods=['POST'])
def export_script():
    """POST /api/flows/export-script - repurposes the toolbar's "Export"
    button: rather than downloading the flow's own JSON, this generates a
    standalone Python script that re-runs the same API pipeline outside
    the browser. See flow_codegen.py for how that script is actually built.

    Unlike the other routes here, this doesn't touch FlowService at all -
    the flow graph to export comes straight from the request body (the
    canvas's current in-memory state), not a previously-saved file, so
    exporting works even for a flow that was never saved.
    """
    payload = request.get_json(force=True) or {}
    name = payload.get('name') or 'flow'
    flow = payload.get('flow') or {'nodes': [], 'connections': []}

    filename = flow_codegen.filename_for(name)
    script = flow_codegen.generate_script(flow, name=name, filename=filename)

    return Response(
        script,
        mimetype='text/x-python',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )
