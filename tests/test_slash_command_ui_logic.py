from __future__ import annotations

import pathlib
import shutil
import subprocess
import textwrap

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_JS_PATH = REPO_ROOT / "static" / "app.js"
TEMPLATE_PATH = REPO_ROOT / "templates" / "index.html"
STYLE_CSS_PATH = REPO_ROOT / "static" / "style.css"
SLASH_HELPERS_START_MARKER = "const SLASH_COMMAND_MENU_MAX_VISIBLE_ITEMS"
SLASH_HELPERS_END_MARKER = "function sanitizeEditedUserMetadata"


def _load_app_js_source() -> str:
    return APP_JS_PATH.read_text(encoding="utf-8")


def _load_slash_helper_source() -> str:
    source = _load_app_js_source()
    start = source.find(SLASH_HELPERS_START_MARKER)
    end = source.find(SLASH_HELPERS_END_MARKER, start)
    assert start != -1 and end != -1, "Slash command helpers were not found in static/app.js"
    return source[start:end]


def _run_node_assertions(script_body: str) -> None:
    node_path = shutil.which("node")
    if not node_path:
        pytest.skip("node is not installed")

    helper_source = _load_slash_helper_source()
    node_script = textwrap.dedent(
        f"""
        {helper_source}

        const assert = (condition, message) => {{
          if (!condition) {{
            throw new Error(message);
          }}
        }};

        {script_body}
        """
    )
    result = subprocess.run(
        [node_path, "-e", node_script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "Node slash-command assertions failed.\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )


def test_parse_composer_slash_command_supports_check() -> None:
    _run_node_assertions(
        """
        const parsed = parseComposerSlashCommand('/check Verify the migration plan');

        assert(parsed.requested === true, 'Expected /check to be recognized as a registered slash command');
        assert(parsed.command && parsed.command.name === 'check', 'Expected the check command definition');
        assert(parsed.text === 'Verify the migration plan', `Unexpected normalized text: ${parsed.text}`);
        assert(parsed.query === 'Verify the migration plan', `Unexpected query: ${parsed.query}`);
        assert(parsed.requestPayload && parsed.requestPayload.double_check === true, 'Expected double_check payload flag');
        assert(parsed.metadata && parsed.metadata.double_check_query === 'Verify the migration plan', 'Expected query metadata to survive parsing');
        """
    )


def test_parse_composer_slash_command_leaves_unknown_commands_as_plain_text() -> None:
    _run_node_assertions(
        """
        const parsed = parseComposerSlashCommand('/unknown-command keep this literal');

        assert(parsed.requested === false, 'Unknown slash commands must not be treated as registered commands');
        assert(parsed.command === null, 'Unknown slash commands must not resolve to a command definition');
        assert(parsed.text === '/unknown-command keep this literal', 'Unknown slash commands should remain literal user text');
        """
    )


def test_get_slash_command_autocomplete_state_filters_only_command_token() -> None:
    _run_node_assertions(
        """
        const allCommands = getSlashCommandAutocompleteState('/');
        const filtered = getSlashCommandAutocompleteState('/ch');
        const withArgs = getSlashCommandAutocompleteState('/check verify this');

        assert(allCommands.active === true, 'Typing / should open the slash command menu');
        assert(allCommands.matches.some((command) => command.name === 'check'), 'The check command must be listed for a bare slash');
        assert(filtered.active === true, 'Partial command tokens should keep the slash menu active');
        assert(filtered.matches.length === 1 && filtered.matches[0].name === 'check', 'The slash menu should filter registered commands by token');
        assert(withArgs.active === false, 'Once arguments start, the autocomplete list should close');
        """
    )


def test_build_composer_slash_command_metadata_clears_stale_command_flags() -> None:
    _run_node_assertions(
        """
        const parsed = parseComposerSlashCommand('/check Verify the release notes');
        const merged = buildComposerSlashCommandMetadata({ attachments: [{ kind: 'document', file_name: 'notes.md' }] }, parsed);
        const cleared = buildComposerSlashCommandMetadata({ double_check: true, double_check_query: 'old query' }, null);

        assert(Array.isArray(merged.attachments) && merged.attachments.length === 1, 'Existing attachment metadata must be preserved');
        assert(merged.double_check === true, 'Slash command metadata must be merged into the outgoing user metadata');
        assert(merged.double_check_query === 'Verify the release notes', 'Slash command query metadata must be updated');
        assert(cleared === null, 'Clearing slash command metadata should drop stale command fields when nothing else remains');
        """
    )


def test_template_contains_slash_command_menu_shell() -> None:
    template_source = TEMPLATE_PATH.read_text(encoding="utf-8")

    assert 'id="slash-command-menu"' in template_source
    assert 'aria-controls="slash-command-menu"' in template_source
    assert 'aria-autocomplete="list"' in template_source
    assert 'Type a message or / for commands…' in template_source


def test_styles_define_slash_command_menu_states() -> None:
    style_source = STYLE_CSS_PATH.read_text(encoding="utf-8")

    assert '.slash-command-menu {' in style_source
    assert '.slash-command-menu__item.is-active {' in style_source
    assert '.slash-command-menu__footer {' in style_source
