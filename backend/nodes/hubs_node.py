"""Hubs - the entry point of every flow. A "hub" is Autodesk's term for one
account/team's top-level workspace (a BIM 360/ACC account, or a personal
hub) - everything else (Projects, Folders, Items, Exchanges) lives inside one.
"""

from .base import NodeType

HUBS_NODE = NodeType(
    key='hubs',
    name='Hubs',
    icon='⬢',
    description='Autodesk hubs',
    accent='success',
    has_input=False,
    has_output=True,
    category='Navigation',
    default_fields={},
    graphql_query_text="""\
# List hubs the current user has access to
query GetHubs {
  hubs {
    results {
      name
      id
      region
    }
  }
}""",
)
