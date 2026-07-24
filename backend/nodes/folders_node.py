"""Folders - subfolders of a project or of another folder. Chaining a
Folders node's own output back into another Folders/Items/Exchanges node
drills into a specific subfolder, rather than always starting back at a
project's root - see backend/routes/dx_routes.py's `_resolve_folder_id`
for how that resolution actually happens.
"""

from .base import NodeType

FOLDERS_NODE = NodeType(
    key='folders',
    name='Folders',
    icon='▤',
    description='Folders and Subfolders',
    accent='magenta',
    has_input=True,
    has_output=True,
    category='Navigation',
    default_fields={},
    graphql_query_text="""\
# List subfolders of a folder
query GetFolderContent($folderId: ID!) {
  folder(folderId: $folderId) {
    folders {
      results {
        id
        name
        __typename
      }
    }
  }
}

Variables:
{
  "folderId": "<put_folder_id_here>"
}

Headers:
{
  "Region": "<put_the_region_here>"
}

# Only if the input is a project (not yet resolved to a folder) - resolve its "Project Files" folder first
query GetProjectFolders($projectId: ID!) {
  project(projectId: $projectId) {
    id
    name
    folders {
      results {
        id
        name
      }
    }
  }
}

Variables:
{
  "projectId": "<put_project_id_here>"
}

Headers:
{
  "Region": "<put_the_project_region_here>"
}""",
    allowed_source_types=['projects', 'folders', 'filter'],
)
