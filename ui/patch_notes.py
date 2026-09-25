from __future__ import annotations

import ast
import re
import textwrap
import tokenize
from pathlib import Path


def latest_patch_notes(repo_path: str) -> tuple[str, list[str]]:
    """Read the highest-version patch entry in a repository's GUI.py."""
    gui_path = Path(repo_path) / "GUI.py"
    try:
        with tokenize.open(gui_path) as source:
            lines = source.readlines()
    except (OSError, SyntaxError, UnicodeError, LookupError):
        return "", []

    latest_version = ""
    latest_key: tuple[int, ...] = ()
    latest_patches: list[str] = []

    for index, line in enumerate(lines):
        match = re.match(r"^([ \t]*)def _seed_patch_notes\s*\(", line)
        if not match:
            continue

        indent = len(match.group(1).expandtabs())
        end = index + 1
        while end < len(lines):
            next_line = lines[end]
            if next_line.strip() and not next_line.lstrip().startswith("#"):
                next_indent = len(next_line[: len(next_line) - len(next_line.lstrip())].expandtabs())
                if next_indent <= indent:
                    break
            end += 1
        try:
            tree = ast.parse(textwrap.dedent("".join(lines[index:end])), filename=str(gui_path))
        except SyntaxError:
            continue
        function = tree.body[0]

        patch_list: list[str] = []
        for statement in function.body:
            if isinstance(statement, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "patch_list"
                for target in statement.targets
            ):
                try:
                    value = ast.literal_eval(statement.value)
                except (ValueError, TypeError, SyntaxError):
                    patch_list = []
                    continue
                patch_list = (
                    [note for note in value if isinstance(note, str)]
                    if isinstance(value, (list, tuple)) else []
                )
                continue

            if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
                continue
            call = statement.value
            if not (
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "add_patch"
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "self"
            ):
                continue

            arguments = {keyword.arg: keyword.value for keyword in call.keywords}
            try:
                version = ast.literal_eval(arguments["version"])
            except (KeyError, ValueError, TypeError, SyntaxError):
                continue
            if not isinstance(version, str) or not re.fullmatch(r"\d+(?:\.\d+)*", version.strip()):
                continue

            patches = arguments.get("patches")
            if isinstance(patches, ast.Name) and patches.id == "patch_list":
                notes = patch_list
            else:
                try:
                    value = ast.literal_eval(patches)
                except (ValueError, TypeError, SyntaxError):
                    continue
                notes = (
                    [note for note in value if isinstance(note, str)]
                    if isinstance(value, (list, tuple)) else []
                )

            key = tuple(int(part) for part in version.split("."))
            if notes and key >= latest_key:
                latest_version, latest_key, latest_patches = version, key, notes

    return latest_version, latest_patches
