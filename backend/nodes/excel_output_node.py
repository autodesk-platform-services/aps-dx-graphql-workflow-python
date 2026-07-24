"""Excel Output - same idea as CSV Output, but downloads one Excel workbook
with one sheet per distinct table structure among whatever's connected.
"""

from .base import NodeType

EXCEL_OUTPUT_NODE = NodeType(
    key='excel_output',
    name='Excel Output',
    icon='▩',
    description='Download input table(s) as Excel',
    accent='success',
    has_input=True,
    has_output=False,
    category='Output',
    default_fields={'filepath': ''},
)
