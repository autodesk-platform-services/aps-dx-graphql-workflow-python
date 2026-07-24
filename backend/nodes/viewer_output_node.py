"""Viewer Output - embeds a headless Autodesk Viewer and renders whichever
model element (an Item or an Exchange) is selected. A pure display sink
like Debug Output - no output port, since there's no meaningful value to
chain further downstream from "a 3D view was shown."
"""

from .base import NodeType

VIEWER_OUTPUT_NODE = NodeType(
    key='data',
    name='Viewer Output',
    icon='⬡',
    description='View the item or exchange in Viewer',
    accent='info',
    has_input=True,
    has_output=False,
    category='Output',
    default_fields={},
    # Only makes sense fed by a model-bearing element - an Exchange (has
    # alternativeIdentifiers.fileUrn) or an Item.
    allowed_source_types=['exchanges', 'items'],
)
