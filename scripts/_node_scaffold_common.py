"""Shared plumbing for scripts/new_node.py and scripts/remove_node.py -
path constants, small interactive-prompt helpers, and the text-surgery
helpers both scripts use to edit backend/nodes/__init__.py and
frontend/static/js/nodes/registry.js without needing a real Python/JS
parser for what are, structurally, just two small lists.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

BACKEND_NODES_DIR = REPO_ROOT / 'backend' / 'nodes'
BACKEND_INIT = BACKEND_NODES_DIR / '__init__.py'
FRONTEND_NODES_DIR = REPO_ROOT / 'frontend' / 'static' / 'js' / 'nodes'
FRONTEND_REGISTRY = FRONTEND_NODES_DIR / 'registry.js'

ACCENTS = ['primary', 'success', 'tertiary', 'warning', 'info', 'teal', 'magenta', 'slate', 'gold']

KEY_RE = re.compile(r'^[a-z][a-z0-9_]*$')


def ask(prompt, default=None):
    """Prompts until a non-blank answer is given, or returns `default`
    immediately on a blank answer if one was provided.
    """
    suffix = f' [{default}]' if default is not None else ''
    while True:
        value = input(f'{prompt}{suffix}: ').strip()
        if value:
            return value
        if default is not None:
            return default
        print('  (required)')


def ask_bool(prompt, default=True):
    """Yes/no prompt - a blank answer takes `default`; otherwise True only
    for an answer starting with 'y'.
    """
    default_label = 'Y/n' if default else 'y/N'
    value = input(f'{prompt} [{default_label}]: ').strip().lower()
    if not value:
        return default
    return value in ('y', 'yes')


def ask_choice(prompt, choices, default):
    """Prints a numbered menu of `choices` and returns whichever one the
    user picked - by number, by typing the choice's name verbatim, or
    `default` on a blank answer (or an unrecognized one, after a warning).
    """
    print(f'{prompt}')
    for i, choice in enumerate(choices, 1):
        marker = ' (default)' if choice == default else ''
        print(f'  {i}. {choice}{marker}')
    value = input(f'Choice [1-{len(choices)}, or type a name] [{default}]: ').strip()
    if not value:
        return default
    if value.isdigit() and 1 <= int(value) <= len(choices):
        return choices[int(value) - 1]
    if value in choices:
        return value
    print(f'  Not a valid choice, using default: {default}')
    return default


def to_camel(key):
    """snake_case -> camelCase - e.g. 'get_views' -> 'getViews', matching
    the frontend's <camelKey>Node.js filename convention.
    """
    parts = key.split('_')
    return parts[0] + ''.join(p.capitalize() for p in parts[1:])


def existing_node_types():
    """{key: asdict(NodeType)} for every currently-registered node type, or
    {} if backend/nodes doesn't even import cleanly right now (best-effort -
    the calling script's own verify_backend() step will catch that properly).
    """
    try:
        from backend.nodes import NODE_TYPES
        return dict(NODE_TYPES)
    except Exception as exc:  # noqa: BLE001 - best-effort validation, don't block on it
        print(f'Warning: could not inspect existing node types ({exc}) - proceeding without that check.')
        return {}


def insert_after_last_match(text, pattern, new_line):
    """Inserts `new_line` right after the last line in `text` matching
    `pattern` - used to add one more `from .x import Y` (or `import * as x
    from ...`) right after the existing block of them, rather than at some
    arbitrary fixed position.
    """
    matches = list(re.finditer(pattern, text, re.MULTILINE))
    if not matches:
        raise ValueError(f'Could not find a line matching {pattern!r} to insert after.')
    insert_at = matches[-1].end()
    return text[:insert_at] + '\n' + new_line + text[insert_at:]


def remove_line_matching(text, pattern):
    """Drops every line in `text` matching `pattern` - the inverse of
    insert_after_last_match, for undoing exactly what it added.
    """
    lines = text.split('\n')
    kept = [line for line in lines if not re.match(pattern, line)]
    return '\n'.join(kept)


def _list_literal_bounds(text, open_pattern):
    """(start, end) character offsets of the *contents* of the first [...]
    or {...} literal whose opening is matched by `open_pattern` - i.e. just
    inside the brackets, not including them. Which closing bracket to look
    for is inferred from whether the opening match itself contains `[` or `{`.
    """
    open_match = re.search(open_pattern, text)
    if not open_match:
        raise ValueError(f'Could not find {open_pattern!r}.')
    close_char = ']' if '[' in open_match.group() else '}'
    close_index = text.index(close_char, open_match.end())
    return open_match.end(), close_index


def insert_into_list_literal(text, open_pattern, new_entry):
    """Appends `new_entry` into the first [...] or {...} literal whose
    opening is matched by `open_pattern`, normalizing whatever trailing
    comma situation is already there.
    """
    start, end = _list_literal_bounds(text, open_pattern)
    stripped = text[start:end].rstrip()
    if stripped.endswith(','):
        stripped = stripped[:-1]
    new_inner = f'{stripped},\n    {new_entry},\n'
    return text[:start] + new_inner + text[end:]


def remove_from_list_literal(text, open_pattern, matches_entry):
    """Removes whichever comma-separated entry in the first [...] or {...}
    literal (matched the same way as insert_into_list_literal) satisfies
    `matches_entry(entry_text)`, and rebuilds the literal's formatting from
    the remaining entries rather than trying to surgically patch around a
    regex match - simplest way to not leave a dangling comma either way.
    """
    start, end = _list_literal_bounds(text, open_pattern)
    entries = [e.strip() for e in text[start:end].split(',')]
    kept = [e for e in entries if e and not matches_entry(e)]
    new_inner = ('\n    ' + ',\n    '.join(kept) + ',\n') if kept else '\n'
    return text[:start] + new_inner + text[end:]


def verify_backend():
    """Sanity-checks that `backend.nodes` still imports cleanly (in a
    fresh subprocess, not this one, so a broken import can't just crash
    the scaffolding script itself) after either script edits it.

    Returns:
        (True, sorted list of node keys) on success, or (False, combined
        stdout+stderr) if the import failed.
    """
    result = subprocess.run(
        [sys.executable, '-c', 'from backend.nodes import NODE_TYPES; print(sorted(NODE_TYPES.keys()))'],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def verify_js_syntax(*paths):
    """Runs `node --check` on each of `paths` - a syntax-only sanity check
    (no imports actually resolved/run), skipped entirely if `node` isn't
    on PATH since it's a nice-to-have, not a hard requirement to run these
    scripts at all.

    Returns:
        None if `node` isn't available, else (True, '') on success or
        (False, the failing file's stderr) on the first syntax error found.
    """
    node = subprocess.run(['which', 'node'], capture_output=True, text=True)
    if node.returncode != 0:
        return None  # node isn't available - skip, not a hard requirement
    for path in paths:
        result = subprocess.run(['node', '--check', str(path)], capture_output=True, text=True)
        if result.returncode != 0:
            return False, f'{path}:\n{result.stderr}'
    return True, ''
