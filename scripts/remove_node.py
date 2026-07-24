#!/usr/bin/env python3
"""Interactively removes a node type - the reverse of scripts/new_node.py.

Refuses to touch the seven node types the app is built around (Hubs,
Projects, Folders, Items, Exchanges, Debug Output, Viewer Output) - anything
else currently registered can be removed. When run with no key argument, the
picker only lists genuinely custom node types (i.e. not ones that shipped
with the app, like Exchange Data/Create Exchange) - pass one of those by key
explicitly if you really do want to remove it. Before deleting anything, it also
checks data/flows/*.json for saved flows that still use the node type
you're removing (loading one afterwards would hit the same "Cannot read
properties of undefined" crash a mismatched/missing registration causes -
see README.md), and it backs up every file it's about to delete under
scripts/.removed_node_backups/ first, since this repo isn't under version
control and a plain rm here would otherwise be unrecoverable.

Run from the repo root:
    uv run python scripts/remove_node.py [key]
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

from _node_scaffold_common import (
    BACKEND_NODES_DIR, BACKEND_INIT, FRONTEND_NODES_DIR, FRONTEND_REGISTRY, REPO_ROOT,
    ask_bool, existing_node_types, remove_from_list_literal, remove_line_matching,
    verify_backend, verify_js_syntax,
)

# Hubs, Projects, Folders, Items, Exchanges, Debug Output, Viewer Output -
# the app doesn't make sense without these, so they're not removable via
# this script, ever.
PROTECTED_KEYS = {'hubs', 'projects', 'folders', 'items', 'exchanges', 'output', 'data'}

# Everything that shipped with the app, including several non-protected
# node types (Exchange Data, Create Exchange, Get Views, Filter, CSV/Excel
# Output) that are still "core" rather than something a user added -
# removable by explicit key, but left out of the interactive picker below
# so it only shows genuinely custom node types.
CORE_KEYS = PROTECTED_KEYS | {'process', 'logic', 'get_views', 'filter', 'csv_output', 'excel_output'}

FLOWS_DIR = REPO_ROOT / 'data' / 'flows'
BACKUP_DIR = Path(__file__).resolve().parent / '.removed_node_backups'


def find_backend_module(key):
    """Returns (module_name, const_name) for the backend/nodes/*.py module
    whose NodeType.key == `key`, by actually importing each module listed in
    __init__.py's imports rather than guessing a filename from the key -
    robust even though e.g. 'process' lives in exchange_data_node.py, not
    process_node.py.
    """
    content = BACKEND_INIT.read_text()
    for module_name, const_name in re.findall(r'from \.(\w+) import (\w+)', content):
        try:
            module = __import__(f'backend.nodes.{module_name}', fromlist=[const_name])
            node_type = getattr(module, const_name)
        except (ImportError, AttributeError):
            continue
        if getattr(node_type, 'key', None) == key:
            return module_name, const_name
    return None


def find_frontend_module(key):
    """Returns (alias, filename) for the frontend/static/js/nodes/*.js
    module registered under NODE_HANDLERS[key], by reading the actual
    key -> alias -> import mapping in registry.js - same reasoning as
    find_backend_module (e.g. 'logic' lives in createExchangeNode.js).
    """
    content = FRONTEND_REGISTRY.read_text()
    handler_match = re.search(rf'^\s*{re.escape(key)}\s*:\s*(\w+)\s*,?\s*$', content, re.MULTILINE)
    if not handler_match:
        return None
    alias = handler_match.group(1)
    import_match = re.search(rf"import \* as {re.escape(alias)} from '\./(\w+)\.js';", content)
    if not import_match:
        return None
    return alias, import_match.group(1)


def flows_using(key):
    """Filenames under data/flows/ whose saved JSON still references
    `key` as a node's `type` - used to warn before removing something
    that's actually in use.
    """
    if not FLOWS_DIR.exists():
        return []
    affected = []
    for path in sorted(FLOWS_DIR.glob('*.json')):
        try:
            text = path.read_text()
        except OSError:
            continue
        # A cheap substring check rather than a full JSON parse per node -
        # good enough to warn with, and can't false-negative.
        if f'"type": "{key}"' in text or f'"type":"{key}"' in text:
            affected.append(path.name)
    return affected


def backup(*paths):
    """Copies whichever of `paths` actually exist into their own
    subfolder under scripts/.removed_node_backups/, named after the first
    path's stem - the only undo available, since this repo isn't under
    version control.
    """
    existing = [p for p in paths if p.exists()]
    if not existing:
        return None
    dest = BACKUP_DIR / paths[0].stem.replace('_node', '').replace('Node', '')
    dest.mkdir(parents=True, exist_ok=True)
    for path in existing:
        shutil.copy2(path, dest / path.name)
    return dest


def remove_backend(key, module_name, const_name):
    """Drops the node type's import + REGISTRY entry from
    backend/nodes/__init__.py, then deletes its backend/nodes/*.py file.
    """
    content = BACKEND_INIT.read_text()
    content = remove_line_matching(content, rf'^from \.{module_name} import {const_name}$')
    content = remove_from_list_literal(content, r'REGISTRY\s*=\s*\[', lambda e: e == const_name)
    BACKEND_INIT.write_text(content)
    (BACKEND_NODES_DIR / f'{module_name}.py').unlink()


def remove_frontend(key, alias, filename):
    """Same as remove_backend, but for registry.js's import + NODE_HANDLERS
    entry and the frontend/static/js/nodes/*.js file.
    """
    content = FRONTEND_REGISTRY.read_text()
    content = remove_line_matching(content, rf"^import \* as {alias} from '\./{filename}\.js';$")
    content = remove_from_list_literal(content, r'NODE_HANDLERS\s*=\s*\{', lambda e: e.split(':')[0].strip() == key)
    FRONTEND_REGISTRY.write_text(content)
    (FRONTEND_NODES_DIR / f'{filename}.js').unlink()


def main():
    print(__doc__.split('\n\n')[0])
    print()

    node_types = existing_node_types()
    removable = {k: v for k, v in node_types.items() if k not in PROTECTED_KEYS}
    custom = {k: v for k, v in node_types.items() if k not in CORE_KEYS}

    if not removable:
        print('Nothing removable - only the protected node types are currently registered.')
        return 0

    key = sys.argv[1] if len(sys.argv) > 1 else None
    if not key:
        if not custom:
            print('No custom node types to remove (only ones that shipped with the app are')
            print('registered right now). Pass one of those by key explicitly if you really')
            print(f'want to remove it: {", ".join(sorted(removable))}')
            return 0
        print('Removable (custom) node types:')
        keys = list(custom)
        for i, k in enumerate(keys, 1):
            print(f'  {i}. {k}  ({custom[k]["name"]})')
        choice = input(f'Which one? [1-{len(keys)}, or type a key]: ').strip()
        key = keys[int(choice) - 1] if choice.isdigit() and 1 <= int(choice) <= len(keys) else choice

    if key in PROTECTED_KEYS:
        print(f'"{key}" is one of the protected node types ({", ".join(sorted(PROTECTED_KEYS))}) - refusing.')
        return 1
    if key not in node_types:
        print(f'"{key}" is not a currently registered node type. Registered: {sorted(node_types)}')
        return 1

    backend_match = find_backend_module(key)
    frontend_match = find_frontend_module(key)
    if not backend_match:
        print(f'Could not find which backend/nodes/*.py module defines key="{key}" - aborting, nothing touched.')
        return 1
    if not frontend_match:
        print(f'Could not find a NODE_HANDLERS["{key}"] entry in registry.js - aborting, nothing touched.')
        return 1
    module_name, const_name = backend_match
    alias, filename = frontend_match

    print()
    print(f'About to remove "{key}" ({node_types[key]["name"]}):')
    print(f'  backend/nodes/{module_name}.py                    (deleted)')
    print(f'  backend/nodes/__init__.py                         (drop import + REGISTRY entry)')
    print(f'  frontend/static/js/nodes/{filename}.js  (deleted)')
    print('  frontend/static/js/nodes/registry.js              (drop import + NODE_HANDLERS entry)')

    affected_flows = flows_using(key)
    if affected_flows:
        print()
        print(f'  WARNING: {len(affected_flows)} saved flow(s) still reference "{key}" and will fail to')
        print(f'  load correctly afterwards: {", ".join(affected_flows)}')

    print()
    print(f'  Backing up the two files above to scripts/.removed_node_backups/ first either way.')
    if not ask_bool('Proceed with removal?', default=False):
        print('Aborted - nothing was removed.')
        return 1

    backup_dir = backup(BACKEND_NODES_DIR / f'{module_name}.py', FRONTEND_NODES_DIR / f'{filename}.js')

    remove_backend(key, module_name, const_name)
    remove_frontend(key, alias, filename)

    print()
    ok, output = verify_backend()
    if ok:
        print(f'Backend OK - node keys now: {output}')
    else:
        print(f'Backend import FAILED after removal:\n{output}')
        return 1

    js_check = verify_js_syntax(FRONTEND_REGISTRY)
    if js_check is None:
        print('(Skipped JS syntax check - `node` not found on PATH.)')
    elif js_check[0]:
        print('Frontend JS syntax OK.')
    else:
        print(f'Frontend JS syntax check FAILED:\n{js_check[1]}')
        return 1

    print()
    print(f'Removed "{key}".')
    if backup_dir:
        print(f'Backed up the deleted files to {backup_dir.relative_to(REPO_ROOT)}/ in case you want them back.')
    if affected_flows:
        print(f'Remember: {", ".join(affected_flows)} still reference "{key}" and will need editing or deleting.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
