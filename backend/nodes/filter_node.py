"""Filter - narrows an already-fetched list (from any of the node types
below) down to elements whose name contains a given substring. Doesn't
call the Data Exchange API itself - it just filters, client-side, whatever
its upstream node already fetched.

Not given an explicit `category` here, so it defaults to 'Other' (see
NodeType.category in base.py) - it doesn't fit neatly into
Navigation/Output/Tools the way the API-calling node types do.
"""

from .base import NodeType

FILTER_NODE = NodeType(
    key='filter',
    name='Filter',
    icon='▽',
    description='Keep only elements whose name contains the given text',
    accent='primary',
    has_input=True,
    has_output=True,
    default_fields={'filterText': ''},
    allowed_source_types=['hubs', 'projects', 'folders', 'items', 'exchanges', 'get_views'],
)
