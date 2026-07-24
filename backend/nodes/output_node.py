"""Debug Output - a plain data sink for inspecting whatever value reaches
it, whether that's a single value, a list, or a whole nested object.
"""

from .base import NodeType

OUTPUT_NODE = NodeType(
    key='output',
    name='Debug Output',
    icon='⇤',
    description='Data sink',
    accent='tertiary',
    has_input=True,
    has_output=False,
    category='Output',
    default_fields={},
)
