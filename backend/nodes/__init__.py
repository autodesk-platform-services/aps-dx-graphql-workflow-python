"""Collects every node type's `NodeType` definition (backend/nodes/*_node.py)
into two things the rest of the app actually uses:

- `NODE_TYPES`: a flat {key: dict} lookup, injected into the page template
  as JSON so the frontend can read each node type's metadata (name, icon,
  allowed_source_types, ...) without duplicating it in JavaScript.
- `grouped_node_types()`: the same data, grouped and ordered for the
  node palette specifically - see backend/routes/main_routes.py.
"""

from dataclasses import asdict

from .create_exchange_node import CREATE_EXCHANGE_NODE
from .csv_output_node import CSV_OUTPUT_NODE
from .excel_output_node import EXCEL_OUTPUT_NODE
from .exchange_data_node import EXCHANGE_DATA_NODE
from .exchanges_node import EXCHANGES_NODE
from .folders_node import FOLDERS_NODE
from .hubs_node import HUBS_NODE
from .items_node import ITEMS_NODE
from .output_node import OUTPUT_NODE
from .projects_node import PROJECTS_NODE
from .viewer_output_node import VIEWER_OUTPUT_NODE
from .get_views_node import GET_VIEWS_NODE
from .filter_node import FILTER_NODE

# Order here defines each node type's order within its palette section - see
# NODE_SECTION_ORDER/grouped_node_types below for how sections themselves
# are ordered.
REGISTRY = [
    HUBS_NODE,
    PROJECTS_NODE,
    FOLDERS_NODE,
    ITEMS_NODE,
    EXCHANGES_NODE,
    EXCHANGE_DATA_NODE,
    OUTPUT_NODE,
    CREATE_EXCHANGE_NODE,
    VIEWER_OUTPUT_NODE,
    GET_VIEWS_NODE,
    FILTER_NODE,
    CSV_OUTPUT_NODE,
    EXCEL_OUTPUT_NODE,
]

# `asdict` turns each frozen dataclass into a plain dict - plain dicts are
# what `flask.jsonify`/Jinja's `tojson` filter know how to serialize, a
# dataclass instance isn't JSON-serializable as-is.
NODE_TYPES = {node_type.key: asdict(node_type) for node_type in REGISTRY}

# Fixed palette section display order. A category not listed here (there
# isn't one today) would just be appended after these, rather than dropped -
# see grouped_node_types.
NODE_SECTION_ORDER = ['Navigation', 'Output', 'Tools', 'Other']


def grouped_node_types():
    """NODE_TYPES grouped into palette sections, in NODE_SECTION_ORDER, each
    as (section_name, [(key, node_type_dict), ...]) - empty sections
    omitted, node order within a section follows REGISTRY order.
    """
    by_section = {}
    for key, node in NODE_TYPES.items():
        by_section.setdefault(node['category'], []).append((key, node))

    section_names = [name for name in NODE_SECTION_ORDER if name in by_section]
    section_names += [name for name in by_section if name not in NODE_SECTION_ORDER]
    return [(name, by_section[name]) for name in section_names]
