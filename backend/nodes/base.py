"""The `NodeType` dataclass - the single schema every node type in
backend/nodes/*_node.py is declared against.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NodeType:
    """Canonical metadata for one node type in the flow editor.

    This is the single source of truth for a node type's identity (name,
    icon, accent color, port shape, default field values) - both the
    palette/canvas rendering and the flow-execution engine on the frontend
    read this via the JSON blob injected into the page template. Frozen
    (immutable) because these are fixed, shared definitions loaded once at
    startup, not per-instance state - see backend/nodes/__init__.py for
    where all of them get collected into NODE_TYPES.
    """

    key: str
    name: str
    icon: str
    description: str
    accent: str
    has_input: bool
    has_output: bool

    # Which palette section this node type is grouped under - see
    # NODE_SECTION_ORDER in backend/nodes/__init__.py for the fixed display
    # order. Defaults to 'Other', the catch-all for anything not explicitly
    # placed in Navigation/Output/Tools (including any newly added node type
    # that hasn't been sorted into a section yet).
    category: str = 'Other'

    default_fields: dict = field(default_factory=dict)

    # Verbatim text shown in the node's "Get the GraphQL query" popup -
    # written out by hand exactly as it should appear (comment, query, and
    # any Variables/Headers sections). Empty for node types that don't call
    # the Data Exchange API directly.
    #
    # This is plain text, not structured data assembled at render time - and
    # it belongs entirely in the node type's own file, even when it
    # documents the same underlying query as another node type. Each node
    # type must stay independently editable without touching (or
    # accidentally affecting) any other node type's popup.
    graphql_query_text: str = ''

    # Restricts what can be connected into this node's input port to just
    # these upstream node type keys - e.g. Folders only makes sense fed by a
    # Project or another Folder, not a Hub or an Exchange. Empty means
    # unrestricted (the default for most node types, including any new one).
    allowed_source_types: list = field(default_factory=list)

    # Same restriction, but keyed by input port index - for a node type with
    # several distinct input ports where each one accepts a different
    # upstream type (e.g. Create Exchange: port 0 only from Get Views, port
    # 1 only from Folders). Takes precedence over `allowed_source_types` for
    # whichever port index has an entry here; ports with no entry fall back
    # to `allowed_source_types`. Empty (the default) means every port just
    # uses `allowed_source_types` uniformly.
    allowed_source_types_by_port: dict = field(default_factory=dict)
