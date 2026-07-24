#!/usr/bin/env python3
"""Interactively scaffolds a new node type - both halves of it.

Adding a node type by hand means touching four places (backend/nodes/<key>_
node.py, backend/nodes/__init__.py, frontend/static/js/nodes/<key>Node.js,
frontend/static/js/nodes/registry.js), and it's easy to get one of them
wrong - a forgotten registration, or a key that doesn't match between the
Python NodeType.key and the JS registry.js entry, both fail silently until
you actually try to use the node. This asks a few questions, then writes
and wires up all four consistently from the same answers.

Run from the repo root:
    uv run python scripts/new_node.py

To remove a node type again, see scripts/remove_node.py.

See README.md's "Adding a new node type" section for what each generated
file actually needs to do beyond this starting skeleton.
"""

import re
import sys

from _node_scaffold_common import (
    ACCENTS, BACKEND_NODES_DIR, BACKEND_INIT, FRONTEND_NODES_DIR, FRONTEND_REGISTRY, KEY_RE,
    ask, ask_bool, ask_choice, existing_node_types, insert_after_last_match, insert_into_list_literal,
    to_camel, verify_backend, verify_js_syntax,
)


def write_backend_node_file(key, const_name, name, icon, description, accent, has_input, has_output, graphql, allowed_source_types):
    """Writes backend/nodes/<key>_node.py - a single `NodeType(...)` call
    built from the interactive answers, with a TODO placeholder query if
    `graphql` was requested.
    """
    path = BACKEND_NODES_DIR / f'{key}_node.py'
    graphql_field = ''
    if graphql:
        graphql_field = (
            "\n    graphql_query_text=\"\"\"\\\n"
            "# TODO: describe the query this node runs\n"
            "query TODO {\n"
            "  TODO\n"
            "}\"\"\","
        )
    restriction_field = f'\n    allowed_source_types={allowed_source_types!r},' if allowed_source_types else ''
    content = (
        "from .base import NodeType\n\n"
        f"{const_name} = NodeType(\n"
        f"    key='{key}',\n"
        f"    name='{name}',\n"
        f"    icon='{icon}',\n"
        f"    description='{description}',\n"
        f"    accent='{accent}',\n"
        f"    has_input={has_input},\n"
        f"    has_output={has_output},\n"
        f"    default_fields={{}},{graphql_field}{restriction_field}\n"
        ")\n"
    )
    path.write_text(content)
    return path


def update_backend_init(key, const_name):
    """Adds the new module's import and REGISTRY entry to
    backend/nodes/__init__.py, so NODE_TYPES actually picks it up.
    """
    content = BACKEND_INIT.read_text()
    content = insert_after_last_match(
        content, r'^from \.\w+ import \w+$',
        f'from .{key}_node import {const_name}',
    )
    content = insert_into_list_literal(content, r'REGISTRY\s*=\s*\[', const_name)
    BACKEND_INIT.write_text(content)


def write_frontend_node_file(key, camel_key, has_input, has_output, graphql):
    """Writes frontend/static/js/nodes/<camelKey>Node.js - a minimal
    module with just enough (ports, an identity-passthrough execute())
    for the node to show up and do *something* immediately; the caller
    strips the execute() stub afterward if `custom_execution` was requested.
    """
    path = FRONTEND_NODES_DIR / f'{camel_key}Node.js'

    if graphql:
        body_row = "${renderGraphqlButtonRow('__KEY__')}"
        imports = "import { renderGraphqlButtonRow, bindGraphqlButton } from './graphqlButton.js';\n\n"
        attach_events = (
            "export function attachEvents(node) {\n"
            "    bindGraphqlButton(node);\n"
            "}\n\n"
        )
    else:
        in_label = "<span class=\"port-label\">in</span>" if has_input else '<span></span>'
        out_label = "<span class=\"port-label\">out</span>" if has_output else '<span></span>'
        body_row = f'<div class="node-row">{in_label}{out_label}</div>'
        imports = ''
        attach_events = ''

    ports = []
    if has_input:
        ports.append('<div class="port port-input" data-port="input" data-port-index="0" data-node="__ID__"></div>')
    if has_output:
        ports.append('<div class="port port-output" data-port="output" data-port-index="0" data-node="__ID__"></div>')
    ports_html = '\n        '.join(ports)

    execute_block = ''
    if has_input or has_output:
        execute_block = (
            "\n// TODO: implement this node's actual behavior. This identity\n"
            "// passthrough just wires it into core/run.js's generic execute\n"
            "// fallback so the node does *something* visible immediately - see\n"
            "// README.md's \"Adding a new node type\" section (in particular,\n"
            "// whether you need something richer than a single value in/out).\n"
            "export function execute(id, nodeData, value) {\n"
            "    return value;\n"
            "}\n"
        )

    content = (
        f"{imports}export const key = '__KEY__';\n\n"
        "export function createFields() {}\n\n"
        "export function renderBody() {\n"
        f"    return `{body_row}`;\n"
        "}\n\n"
        "export function renderPorts(id) {\n"
        f"    return `\n        {ports_html}\n    `;\n"
        "}\n\n"
        f"{attach_events}"
        "export function serialize() {\n"
        "    return {};\n"
        "}\n"
        f"{execute_block}"
    )
    content = content.replace('__KEY__', key).replace('__ID__', '${id}')
    path.write_text(content)
    return path


def update_frontend_registry(key, camel_key):
    """Adds the new module's import and NODE_HANDLERS entry to
    frontend/static/js/nodes/registry.js, so core/run.js can actually
    dispatch to it.
    """
    content = FRONTEND_REGISTRY.read_text()
    content = insert_after_last_match(
        content, r"^import \* as \w+ from '\./\w+\.js';$",
        f"import * as {camel_key}Node from './{camel_key}Node.js';",
    )
    content = insert_into_list_literal(content, r'NODE_HANDLERS\s*=\s*\{', f'{key}: {camel_key}Node')
    FRONTEND_REGISTRY.write_text(content)


def main():
    print(__doc__.split('\n\n')[0])
    print()

    known = set(existing_node_types().keys())

    key = ask('Node key (snake_case, e.g. exchange_filter)')
    while not KEY_RE.match(key) or key in known or (BACKEND_NODES_DIR / f'{key}_node.py').exists():
        if not KEY_RE.match(key):
            print('  Must be lowercase letters/digits/underscores, starting with a letter.')
        elif key in known or (BACKEND_NODES_DIR / f'{key}_node.py').exists():
            print(f'  "{key}" is already used by an existing node type.')
        key = ask('Node key (snake_case, e.g. exchange_filter)')

    name = ask('Display name (e.g. "Exchange Filter")')
    icon = ask('Icon (a single glyph, shown in the palette)', default='●')
    description = ask('Short description (shown under the name in the palette)')
    accent = ask_choice('Accent color:', ACCENTS, default='primary')
    has_input = ask_bool('Has an input port?', default=True)
    has_output = ask_bool('Has an output port?', default=True)

    allowed_source_types = []
    if has_input:
        raw = ask(
            'Restrict which node types can connect into it? (comma-separated keys, e.g. '
            '"projects,folders" - blank = any)',
            default='',
        )
        allowed_source_types = [k.strip() for k in raw.split(',') if k.strip()]
        unknown = [k for k in allowed_source_types if k not in known]
        if unknown:
            print(f'  Note: {", ".join(unknown)} not a currently registered key - allowed anyway (e.g. if you add it next).')

    graphql = ask_bool('Calls the Data Exchange GraphQL API directly (adds a "Get the GraphQL query" button)?', default=False)
    custom_execution = ask_bool(
        'Needs multiple simultaneous inputs, or multi-connection aggregation into one port '
        '(like Exchange Data or Viewer Output)?',
        default=False,
    )

    const_name = f'{key.upper()}_NODE'
    camel_key = to_camel(key)

    print()
    print('About to create/modify:')
    print(f'  backend/nodes/{key}_node.py                 (new)')
    print('  backend/nodes/__init__.py                    (add import + REGISTRY entry)')
    print(f'  frontend/static/js/nodes/{camel_key}Node.js  (new)')
    print('  frontend/static/js/nodes/registry.js         (add import + NODE_HANDLERS entry)')
    if allowed_source_types:
        print(f'  (input restricted to: {", ".join(allowed_source_types)})')
    if custom_execution:
        print()
        print('  NOTE: you asked for richer execution semantics - this script will NOT')
        print('  generate an execute() for you (a wrong one is worse than none - see the')
        print('  README section on this). You will need to add a dispatch branch in')
        print('  frontend/static/js/core/run.js yourself.')
    if not ask_bool('Proceed?', default=True):
        print('Aborted - nothing was written.')
        return 1

    write_backend_node_file(key, const_name, name, icon, description, accent, has_input, has_output, graphql, allowed_source_types)
    update_backend_init(key, const_name)

    frontend_path = write_frontend_node_file(
        key, camel_key, has_input, has_output, graphql,
    )
    if custom_execution:
        # Strip the identity-passthrough execute() stub - see the note above.
        frontend_path.write_text(re.sub(r'\n// TODO:.*?\nexport function execute.*?\n\}\n', '\n', frontend_path.read_text(), flags=re.DOTALL))
    update_frontend_registry(key, camel_key)

    print()
    ok, output = verify_backend()
    if ok:
        print(f'Backend OK - node keys now: {output}')
    else:
        print(f'Backend import FAILED after generation:\n{output}')
        return 1

    js_check = verify_js_syntax(frontend_path, FRONTEND_REGISTRY)
    if js_check is None:
        print('(Skipped JS syntax check - `node` not found on PATH.)')
    elif js_check[0]:
        print('Frontend JS syntax OK.')
    else:
        print(f'Frontend JS syntax check FAILED:\n{js_check[1]}')
        return 1

    print()
    print(f'Done. Next steps for "{key}":')
    print(f'  - Implement the real behavior in frontend/static/js/nodes/{camel_key}Node.js')
    if graphql:
        print(f'  - Fill in the real query text in backend/nodes/{key}_node.py\'s graphql_query_text')
    print('  - Restart the Flask dev server and drag it out of the palette to try it')
    return 0


if __name__ == '__main__':
    sys.exit(main())
