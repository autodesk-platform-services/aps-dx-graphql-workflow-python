"""Raw GraphQL query/mutation text against the APS Data Exchange API,
executed by backend/routes/dx_routes.py via DXService.execute.

Each node type's "Get the GraphQL query" popup text (backend/nodes/*.py)
is defined separately and inline in that node's own file, even where it
documents the same query as one of these - that's a deliberate choice so
each node type stays independently editable, rather than sharing text
that changing one node type could silently affect another. The constants
here are the ones actually sent over the wire; the popup text is a
human-readable copy for the UI.
"""

# Every hub (BIM 360/ACC account, or personal hub) the signed-in user can see.
GET_HUBS_QUERY = """
query GetHubs {
  hubs {
    results {
      name
      id
      region
    }
  }
}
"""

# Every project within one hub.
GET_PROJECTS_QUERY = """
query GetProjects($hubId: ID!) {
  projects(hubId: $hubId) {
    results {
      id
      name
    }
  }
}
"""

# A project's top-level folders - used only to find the "Project Files"
# folder by name (see dx_routes.py's `_find_project_files_folder_id`),
# never paginated since a project has few enough top-level folders that
# the API doesn't require it here.
GET_PROJECT_FOLDERS_QUERY = """
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
"""

# One folder's subfolders. Paginated ($pagination) - see
# dx_routes.py's `_aggregate_folder_contents` for why that matters (a
# folder with more subfolders than one page would otherwise be truncated).
GET_FOLDER_FOLDERS_QUERY = """
query GetFolderContent($folderId: ID!, $pagination: PaginationInput) {
  folder(folderId: $folderId) {
    folders(pagination: $pagination) {
      pagination {
        pageSize
        cursor
      }
      results {
        id
        name
        __typename
      }
    }
  }
}
"""

# One folder's items (Revit models, drawings, etc. - anything that isn't
# itself an Exchange). Paginated, same reasoning as GET_FOLDER_FOLDERS_QUERY.
GET_FOLDER_ITEMS_QUERY = """
query GetFolderContent($folderId: ID!, $pagination: PaginationInput) {
  folder(folderId: $folderId) {
    items(pagination: $pagination) {
      pagination {
        pageSize
        cursor
      }
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
"""

# One folder's exchanges. Paginated, same reasoning as GET_FOLDER_FOLDERS_QUERY.
GET_FOLDER_EXCHANGES_QUERY = """
query GetFolderContent($folderId: ID!, $pagination: PaginationInput) {
  folder(folderId: $folderId) {
    exchanges(pagination: $pagination) {
      pagination {
        pageSize
        cursor
      }
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
"""

# Creates a new Exchange from a Revit item's tip version, using one of its
# views as the reference - see the Create Exchange node.
CREATE_EXCHANGE_MUTATION = """
mutation CreateExchange($input: CreateExchangeInput!) {
  createExchange(input: $input) {
    exchange {
      id
      name
    }
    error {
      exchangeId
      code
      message
    }
  }
}
"""

# Every element and property in one Exchange, optionally narrowed by an
# RSQL filter string ($elementFilter) - see the Get Exchange Data node.
# Paginated, same reasoning as GET_FOLDER_FOLDERS_QUERY.
GET_EXCHANGE_ELEMENTS_QUERY = """
query FilterUsingComplexQuery($exchangeId: ID!, $elementFilter: ElementFilterInput, $elementPagination: PaginationInput) {
  exchange(exchangeId: $exchangeId) {
    id
    name
    elements(filter: $elementFilter, pagination: $elementPagination) {
      pagination {
        pageSize
        cursor
      }
      results {
        id
        name
        properties {
          results {
            name
            value
          }
        }
      }
    }
  }
}
"""
