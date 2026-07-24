"""Exchanges - Data Exchange containers sitting inside a folder, alongside
regular Items. Fed by a Project, a Folder, or a Filter narrowing either.
"""

from .base import NodeType

EXCHANGES_NODE = NodeType(
    key='exchanges',
    name='Exchanges',
    icon='▧',
    description='Exchanges in Folders',
    accent='gold',
    has_input=True,
    has_output=True,
    category='Navigation',
    default_fields={},
    graphql_query_text="""\
# List exchanges in a folder
query GetFolderContent($folderId: ID!) {
  folder(folderId: $folderId) {
    exchanges {
      results {
        id
        name
        alternativeIdentifiers {
          fileUrn
          fileVersionUrn
        }
        version {
          id
          versionNumber
          createdOn
        }
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
}""",
    allowed_source_types=['projects', 'folders', 'filter'],
)
