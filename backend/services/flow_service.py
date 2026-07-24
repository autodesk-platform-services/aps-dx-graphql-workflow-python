"""Saves/loads flow graphs as one JSON file per flow under
Config.FLOWS_DIR (see backend/routes/flow_routes.py for the CRUD routes
that call this).

A "flow" here is just the node/connection graph the frontend canvas
serializes - this module doesn't know or care what's inside it, only how
to get a named blob of JSON on and off disk.
"""

import json
import os
import re
import uuid
from datetime import datetime, timezone

from flask import current_app


class FlowService:
    """Saves/loads flow graphs as one JSON file per flow under FLOWS_DIR."""

    @staticmethod
    def _flows_dir():
        """Returns Config.FLOWS_DIR, creating it on first use so callers
        never have to check it exists themselves.
        """
        flows_dir = current_app.config['FLOWS_DIR']
        os.makedirs(flows_dir, exist_ok=True)
        return flows_dir

    @staticmethod
    def _path_for(flow_id):
        """Path to one flow's JSON file on disk.

        `flow_id` ends up in a filename, and it can come from a URL
        (backend/routes/flow_routes.py's <flow_id> route parameter) - so it
        has to be sanitized first, or a crafted id like `../../etc/passwd`
        could read/write outside FLOWS_DIR entirely (a path traversal
        attack). Stripping everything except letters/digits/`_`/`-` makes
        that impossible, at the cost of flow ids only ever looking like the
        uuid.uuid4().hex[:12] save_flow() below actually generates.
        """
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '', flow_id)
        return os.path.join(FlowService._flows_dir(), f'{safe_id}.json')

    @staticmethod
    def list_flows():
        """Returns `[{id, name, updated_at}, ...]` for every saved flow,
        sorted by filename - just enough to populate the "Saved flows"
        dropdown without loading each flow's full node graph.
        """
        flows = []
        for filename in sorted(os.listdir(FlowService._flows_dir())):
            if not filename.endswith('.json'):
                continue
            with open(os.path.join(FlowService._flows_dir(), filename)) as f:
                record = json.load(f)
            flows.append({
                'id': record['id'],
                'name': record.get('name', record['id']),
                'updated_at': record.get('updated_at'),
            })
        return flows

    @staticmethod
    def load_flow(flow_id):
        """Returns the full saved record for one flow (id/name/flow/
        created_at/updated_at), or None if no such flow exists.
        """
        path = FlowService._path_for(flow_id)
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)

    @staticmethod
    def save_flow(name, flow, flow_id=None):
        """Creates a new flow (when `flow_id` is None) or overwrites an
        existing one, preserving its original `created_at` and its name if
        a new one wasn't given. Returns the saved record.
        """
        flow_id = flow_id or uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        existing = FlowService.load_flow(flow_id)
        record = {
            'id': flow_id,
            'name': name or (existing['name'] if existing else flow_id),
            'flow': flow or {'nodes': [], 'connections': []},
            'created_at': existing['created_at'] if existing else now,
            'updated_at': now,
        }
        with open(FlowService._path_for(flow_id), 'w') as f:
            json.dump(record, f, indent=2)
        return record

    @staticmethod
    def delete_flow(flow_id):
        """Removes a flow's JSON file, if it exists - a no-op otherwise
        (deleting something already gone isn't an error here).
        """
        path = FlowService._path_for(flow_id)
        if os.path.exists(path):
            os.remove(path)
