"""Create Exchange - triggers the createExchange mutation for one Revit
item + view (from Get Views) into a destination folder. See:
https://autodesk-platform-services.github.io/aps-dx-graphql-tutorial/mutation/home/#creating-exchanges-from-revit-file
"""

from .base import NodeType

CREATE_EXCHANGE_NODE = NodeType(
    key='logic',
    name='Create Exchange',
    icon='◇',
    description='Create an Exchange from a view, in a folder',
    accent='warning',
    has_input=True,
    has_output=True,
    category='Tools',
    default_fields={},
    graphql_query_text="""\
# Create an exchange from a Revit item's tip version, using one of its views
# as the reference.
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

Variables:
{
  "input": {
    "viewName": "<the view's name>",
    "source": { "fileId": "<id of the Revit item the view belongs to>" },
    "target": { "name": "<name for the new exchange>", "folderId": "<destination folder id>" }
  }
}

Headers:
{
  "Region": "<the destination folder's region>"
}""",
    # Ports: 0 = Get Views (one or more, aggregated - each view already
    # carries the id of the item it belongs to, so there's no separate Items
    # port), 1 = Folder (the exchange's destination, only the first one used
    # if more than one comes through) - see allowed_source_types_by_port
    # below for which upstream type each one accepts.
    allowed_source_types_by_port={
        0: ['get_views'],
        1: ['folders'],
    },
)
