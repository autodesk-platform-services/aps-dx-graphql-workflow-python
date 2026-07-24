"""CSV Output - downloads whatever table(s) reach it as a `.csv` file (or a
`.zip` of several CSVs when connected sources have distinct column shapes).
See frontend/static/js/nodes/tableExport.js.
"""

from .base import NodeType

CSV_OUTPUT_NODE = NodeType(
    key='csv_output',
    name='CSV Output',
    icon='▦',
    description='Download input table(s) as CSV',
    accent='teal',
    has_input=True,
    has_output=False,
    category='Output',
    default_fields={'filepath': ''},
)
