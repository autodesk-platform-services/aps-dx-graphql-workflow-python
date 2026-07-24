"""Items - files (Revit models, drawings, etc.) sitting inside a folder.
Fed by a Project, a Folder, or a Filter narrowing either of those.
"""

from .base import NodeType

ITEMS_NODE = NodeType(
    key='items',
    name='Items',
    icon='▥',
    description='Items in Folders',
    accent='slate',
    has_input=True,
    has_output=True,
    category='Navigation',
    default_fields={},
    graphql_query_text="""\
# List items in a folder
query GetFolderContent($folderId: ID!) {
  folder(folderId: $folderId) {
    items {
      ... on Items {
        results {
          id
          name
          extensionType
          ... on BasicItem {
            tipVersion {
              id
              versionNumber
              createdOn
            }
          }
        }
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
}""",
    allowed_source_types=['projects', 'folders', 'filter'],
)
