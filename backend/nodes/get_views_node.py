"""Get Views - looks up the named views (floor plans, 3D views, ...)
available in a Revit item's latest version, via the Data Management and
Model Derivative REST APIs rather than the Data Exchange GraphQL API - see
backend/services/model_derivative_service.py for why (the GraphQL schema
has no way to list a Revit file's views).
"""

from .base import NodeType

GET_VIEWS_NODE = NodeType(
    key='get_views',
    name='Get Views',
    icon='#',
    description='Get Views of the given Item',
    accent='gold',
    has_input=True,
    has_output=True,
    category='Tools',
    default_fields={},
    # Only makes sense fed by an Item (a Revit file) - views are looked up
    # for its underlying Data Management item id.
    allowed_source_types=['items'],
)
