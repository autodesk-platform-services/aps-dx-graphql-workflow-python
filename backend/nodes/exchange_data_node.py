"""Get Exchange Data - a per-element, per-property "quantity takeoff" for
one or more Exchanges, optionally narrowed by an RSQL filter string (APS's
"Advanced Filtering" syntax - see the tutorial series linked from the
node's Filter field in the UI). Paginated server-side (see
backend/routes/dx_routes.py's `_fetch_exchange_elements`) so a large
exchange's element list isn't silently truncated to one page.
"""

from .base import NodeType

EXCHANGE_DATA_NODE = NodeType(
    key='process',
    name='Get Exchange Data',
    icon='⚙',
    description='Quantity takeoff: every element and property in an Exchange',
    accent='primary',
    has_input=True,
    has_output=True,
    category='Tools',
    default_fields={'filterQuery': ''},
    graphql_query_text="""\
# Quantity takeoff - every element and property for one exchange, optionally
# narrowed by an RSQL filter string, e.g.
# "property.name.category==Walls and property.name.Area>10.0".
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

Variables:
{
  "exchangeId": "<put_the_exchange_id_here>",
  "elementFilter": { "query": "<empty string, or an RSQL filter>" },
  "elementPagination": { "limit": 200, "cursor": "<omit for the first page>" }
}

Headers:
{
  "Region": "<put_the_exchange_region_here>"
}""",
    # Only makes sense fed by an Exchange - runs FilterUsingComplexQuery
    # against each one's own id.
    allowed_source_types=['exchanges'],
)
