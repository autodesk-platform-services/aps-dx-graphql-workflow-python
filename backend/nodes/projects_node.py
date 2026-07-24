"""Projects - the projects a user's hub(s) contain. Fed by Hubs."""

from .base import NodeType

PROJECTS_NODE = NodeType(
    key='projects',
    name='Projects',
    icon='◆',
    description='Projects for selected hubs',
    accent='teal',
    has_input=True,
    has_output=True,
    category='Navigation',
    default_fields={},
    graphql_query_text="""\
# List projects for a hub
query GetProjects($hubId: ID!) {
  projects(hubId: $hubId) {
    results {
      id
      name
    }
  }
}

Variables:
{
  "hubId": "<put_hub_id_here>"
}

Headers:
{
  "Region": "<put_the_hub_region_here>"
}""",
    allowed_source_types=['hubs'],
)
