"""Tree-sitter based multi-language code parser.

Extracts structural nodes (classes, functions, imports, types) and edges
(calls, inheritance, contains) from source files.
"""

from __future__ import annotations

import ast
import hashlib
import html
import importlib
import json
import logging
import math
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path, PurePath
from typing import Any, NamedTuple, Optional

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]

from .custom_languages import CustomLanguage, load_custom_languages

try:
    import yaml as _yaml  # type: ignore[import-untyped]
    from yaml import MappingNode as _YamlMapping
    from yaml import ScalarNode as _YamlScalar
    from yaml import SequenceNode as _YamlSequence
except ImportError:
    _yaml = None  # type: ignore[assignment]
    _YamlMapping = _YamlSequence = _YamlScalar = None  # type: ignore[assignment,misc]

from .tsconfig_resolver import TsconfigResolver


class CellInfo(NamedTuple):
    """Represents a single cell in a notebook with its language."""
    cell_index: int
    language: str
    source: str


_SQL_TABLE_RE = re.compile(
    r"(?:FROM|JOIN|INTO|CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW)|INSERT\s+OVERWRITE)"
    r"\s+((?:`[^`]+`|\w+)(?:\.(?:`[^`]+`|\w+))*)",
    re.IGNORECASE,
)

_PYTHON_STAR_CACHE_MAX = 15_000
_PYTHON_STAR_EXPORT_CACHE: dict[tuple[str, int, int], dict[str, str]] = {}
_PYTHON_STAR_EXPORT_CACHE_LOCK = threading.RLock()


@lru_cache(maxsize=512)
def _read_cargo_manifest(
    manifest_path: str, _mtime_ns: int, _size: int,
) -> dict[str, Any]:
    """Read one Cargo manifest, keyed by immutable file identity metadata."""
    try:
        parsed = tomllib.loads(
            Path(manifest_path).read_text(encoding="utf-8", errors="replace"),
        )
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _load_cargo_manifest(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
        resolved = path.resolve()
    except (OSError, RuntimeError, ValueError):
        return {}
    return _read_cargo_manifest(str(resolved), stat.st_mtime_ns, stat.st_size)


class _PythonScopeBindingVisitor(ast.NodeVisitor):
    """Collect names bound in one Python lexical scope."""

    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names.add(node.id)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self.names.add(node.name)

    def visit_AsyncFunctionDef(  # noqa: N802
        self,
        node: ast.AsyncFunctionDef,
    ) -> None:
        self.names.add(node.name)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self.names.add(node.name)

    def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802
        return

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            self.names.add(alias.asname or alias.name.split(".", 1)[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        for alias in node.names:
            if alias.name != "*":
                self.names.add(alias.asname or alias.name)


def _python_type_checking_aliases(
    tree: ast.Module,
) -> tuple[frozenset[str], frozenset[str]]:
    """Return unshadowed aliases for ``typing.TYPE_CHECKING``."""
    names: set[str] = set()
    modules: set[str] = set()
    shadowed: set[str] = set()
    for statement in tree.body:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                if alias.name == "typing":
                    modules.add(alias.asname or "typing")
                else:
                    shadowed.add(
                        alias.asname or alias.name.split(".", 1)[0],
                    )
        elif isinstance(statement, ast.ImportFrom) and statement.module == "typing":
            for alias in statement.names:
                if alias.name == "TYPE_CHECKING":
                    names.add(alias.asname or alias.name)
                elif alias.name != "*":
                    shadowed.add(alias.asname or alias.name)
        else:
            bindings = _PythonScopeBindingVisitor()
            bindings.visit(statement)
            shadowed.update(bindings.names)
    return frozenset(names - shadowed), frozenset(modules - shadowed)


def _python_static_truth(
    node: ast.expr,
    type_checking_names: frozenset[str] = frozenset(),
    typing_modules: frozenset[str] = frozenset(),
) -> Optional[bool]:
    """Return a truth value for the small constant subset we can prove."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (bool, int)):
        return bool(node.value)
    if isinstance(node, ast.Name) and node.id in type_checking_names:
        return False
    if (
        isinstance(node, ast.Attribute)
        and node.attr == "TYPE_CHECKING"
        and isinstance(node.value, ast.Name)
        and node.value.id in typing_modules
    ):
        return False
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        value = _python_static_truth(
            node.operand,
            type_checking_names,
            typing_modules,
        )
        return None if value is None else not value
    if isinstance(node, ast.BoolOp):
        values = [
            _python_static_truth(
                value,
                type_checking_names,
                typing_modules,
            )
            for value in node.values
        ]
        if isinstance(node.op, ast.And):
            if False in values:
                return False
            return True if all(value is True for value in values) else None
        if isinstance(node.op, ast.Or):
            if True in values:
                return True
            return False if all(value is False for value in values) else None
    return None


class _PythonUnreachableCallVisitor(ast.NodeVisitor):
    """Collect calls inside branches whose condition is statically false."""

    def __init__(
        self,
        type_checking_names: frozenset[str],
        typing_modules: frozenset[str],
    ) -> None:
        self._dead = False
        self.positions: set[tuple[int, int]] = set()
        self._type_checking_names = type_checking_names
        self._typing_modules = typing_modules

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if self._dead:
            self.positions.add((node.lineno, node.col_offset))
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:  # noqa: N802
        self.visit(node.test)
        truth = _python_static_truth(
            node.test,
            self._type_checking_names,
            self._typing_modules,
        )
        self._visit_statements(node.body, dead=truth is False)
        self._visit_statements(node.orelse, dead=truth is True)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def visit_AsyncFunctionDef(  # noqa: N802
        self,
        node: ast.AsyncFunctionDef,
    ) -> None:
        self._visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)

        bindings = _PythonScopeBindingVisitor()
        for statement in node.body:
            bindings.visit(statement)
        outer_names = self._type_checking_names
        outer_modules = self._typing_modules
        self._type_checking_names = outer_names - bindings.names
        self._typing_modules = outer_modules - bindings.names
        self._visit_statements(node.body, dead=False)
        self._type_checking_names = outer_names
        self._typing_modules = outer_modules

    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)
        all_args = (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        )
        for argument in all_args:
            if argument.annotation is not None:
                self.visit(argument.annotation)
        for optional_argument in (node.args.vararg, node.args.kwarg):
            if (
                optional_argument is not None
                and optional_argument.annotation is not None
            ):
                self.visit(optional_argument.annotation)
        if node.returns is not None:
            self.visit(node.returns)

        bindings = _PythonScopeBindingVisitor()
        for statement in node.body:
            bindings.visit(statement)
        bindings.names.update(argument.arg for argument in all_args)
        bindings.names.update(
            argument.arg
            for argument in (node.args.vararg, node.args.kwarg)
            if argument is not None
        )

        outer_names = self._type_checking_names
        outer_modules = self._typing_modules
        self._type_checking_names = outer_names - bindings.names
        self._typing_modules = outer_modules - bindings.names
        self._visit_statements(node.body, dead=False)
        self._type_checking_names = outer_names
        self._typing_modules = outer_modules

    def _visit_statements(
        self,
        statements: list[ast.stmt],
        *,
        dead: bool,
    ) -> None:
        outer_dead = self._dead
        self._dead = outer_dead or dead
        for statement in statements:
            self.visit(statement)
        self._dead = outer_dead


@lru_cache(maxsize=128)
def _python_unreachable_call_positions(
    source: bytes,
) -> frozenset[tuple[int, int]]:
    """Return one-based line/byte-column positions of proven-dead calls."""
    try:
        tree = ast.parse(source.decode("utf-8"))
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return frozenset()
    type_checking_names, typing_modules = _python_type_checking_aliases(tree)
    visitor = _PythonUnreachableCallVisitor(
        type_checking_names,
        typing_modules,
    )
    visitor.visit(tree)
    return frozenset(visitor.positions)


# ---------------------------------------------------------------------------
# Non-Python static dead-guard detection (tree-sitter ancestor walk).
#
# ``_python_unreachable_call_positions`` above uses the ``ast`` module and so
# only covers Python.  The helpers below cover languages ``ast`` cannot parse,
# walking the tree-sitter ancestor chain of a call node:
#
#   * TypeScript / JavaScript:  ``if false { ... }`` / ``if (0) { ... }``
#   * C / C++:                       ``#if 0`` / ``#elif 0`` preprocessor blocks
#
# Only the consequence (true branch) is dead; ``else`` / ``#else`` / ``#elif``
# branches stay live.
# ---------------------------------------------------------------------------


def _node_is_in_child(node, child_node) -> bool:
    """Return True if *node* is *child_node* or one of its descendants.

    Compares byte ranges because the tree-sitter Python bindings create a
    fresh ``Node`` object on every ``child_by_field_name`` call, so ``is``
    identity fails even when both sides refer to the same tree node.
    """
    start_byte, end_byte = child_node.start_byte, child_node.end_byte
    cursor = node
    while cursor is not None:
        if cursor.start_byte == start_byte and cursor.end_byte == end_byte:
            return True
        cursor = cursor.parent
    return False


def _is_statically_false_condition(cond) -> bool:
    """Return True if *cond* is a statically-false literal (non-Python).

    * ``parenthesized_expression`` (TS/JS wrap ``if (expr)``) is unwrapped.
    * ``false`` -- TS/JS boolean literal.
    * ``number`` equal to ``0`` -- TS/JS ``if (0)``.
    """
    if cond.type == "parenthesized_expression":
        inner = cond.named_children
        return _is_statically_false_condition(inner[0]) if inner else False
    if cond.type == "false":
        return True
    # Literal ``0`` only. ``0x0`` / ``0.0`` are equally falsy but are left
    # undetected on purpose: missing one is a dropped suppression, never a
    # wrongly-suppressed live call, and evaluating arbitrary numeric literals
    # invites its own bugs. Python's ``if 0:`` is handled by the ast path.
    if cond.type == "number" and cond.text == b"0":
        return True
    return False


def _is_in_static_dead_guard(node) -> bool:
    """Return True if *node* sits in a statically-dead branch (non-Python).

    Two independent ancestor walks:

    * A walk for TS / JS ``if false`` / ``if (0)``.
    * A walk for C/C++ ``#if 0`` / ``#elif 0``.

    Neither walk stops at a function or class boundary. A declaration
    nested inside a dead branch is never evaluated, so calls in its body
    are dead too -- matching what the Python ``ast`` path above already
    does for a ``def`` or ``class`` under ``if False:``. Unlike Python,
    JS/TS class declarations are not hoisted, so there is no reachable
    symbol to preserve either.
    """
    # TS / JS: ``if`` with a statically-false condition.
    cursor = node.parent
    while cursor is not None:
        node_type = cursor.type
        if node_type == "if_statement":
            condition = cursor.child_by_field_name("condition")
            consequence = cursor.child_by_field_name("consequence")
            if (
                condition is not None
                and consequence is not None
                and _is_statically_false_condition(condition)
                and _node_is_in_child(node, consequence)
            ):
                return True
        cursor = cursor.parent

    # C / C++: ``#if 0`` / ``#elif 0`` preprocessor block.
    preproc = node.parent
    while preproc is not None:
        if preproc.type in ("preproc_if", "preproc_elif"):
            condition = preproc.child_by_field_name("condition")
            if (
                condition is not None
                and condition.type == "number_literal"
                and condition.text == b"0"
            ):
                alternative = preproc.child_by_field_name("alternative")
                if not (
                    alternative is not None
                    and _node_is_in_child(node, alternative)
                ):
                    return True
        preproc = preproc.parent

    return False

logger = logging.getLogger(__name__)

_DEFAULT_PARSER_LOAD_TIMEOUT_SECONDS = 5.0
_PARSER_PROBE_RESULTS: dict[str, bool] = {}
_PARSER_PROBE_FAILURE_DETAILS: dict[str, str] = {}
_PARSER_PROBE_LOCK = threading.Lock()
_EXPECTED_PARSER_LOAD_ERRORS = (ImportError, LookupError, OSError, ValueError)


def _parser_load_timeout_seconds() -> float:
    """Return a safe positive timeout for native grammar probes."""
    raw = os.environ.get(
        "CRG_PARSER_LOAD_TIMEOUT_SECONDS",
        str(_DEFAULT_PARSER_LOAD_TIMEOUT_SECONDS),
    )
    try:
        timeout = float(raw)
    except ValueError:
        timeout = _DEFAULT_PARSER_LOAD_TIMEOUT_SECONDS
    if not math.isfinite(timeout) or timeout <= 0:
        timeout = _DEFAULT_PARSER_LOAD_TIMEOUT_SECONDS
    return timeout


def _run_parser_load_probe(grammar: str, timeout_seconds: float) -> bool:
    """Probe one native grammar in a disposable interpreter process."""
    code = (
        "from tree_sitter_language_pack import get_parser\n"
        "import sys\n"
        "get_parser(sys.argv[1])\n"
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-c", code, grammar],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _PARSER_PROBE_FAILURE_DETAILS[grammar] = str(exc)
        logger.debug("tree-sitter parser probe failed for %s: %s", grammar, exc)
        return False
    if completed.returncode == 0:
        _PARSER_PROBE_FAILURE_DETAILS.pop(grammar, None)
        return True

    raw_stderr = getattr(completed, "stderr", b"")
    if isinstance(raw_stderr, bytes):
        stderr = raw_stderr.decode("utf-8", errors="replace")
    else:
        stderr = str(raw_stderr)
    detail = next(
        (line.strip() for line in reversed(stderr.splitlines()) if line.strip()),
        f"probe exited with status {completed.returncode}",
    )
    _PARSER_PROBE_FAILURE_DETAILS[grammar] = detail[:500]
    return False


def _parser_load_probe_succeeds(
    grammar: str,
    timeout_seconds: float | None = None,
) -> bool:
    """Return a process-cached result for one bounded grammar probe.

    The lock deliberately covers the subprocess call: parallel parser users
    must not start duplicate probes for the same grammar while the first one
    is still running.
    """
    with _PARSER_PROBE_LOCK:
        cached = _PARSER_PROBE_RESULTS.get(grammar)
        if cached is not None:
            return cached
        timeout = (
            _parser_load_timeout_seconds()
            if timeout_seconds is None
            else timeout_seconds
        )
        result = _run_parser_load_probe(grammar, timeout)
        _PARSER_PROBE_RESULTS[grammar] = result
        if not result:
            detail = _PARSER_PROBE_FAILURE_DETAILS.get(grammar)
            if detail:
                logger.warning(
                    "Skipping unavailable tree-sitter parser for %s: %s",
                    grammar,
                    detail,
                )
            else:
                logger.warning(
                    "Skipping unavailable tree-sitter parser for %s",
                    grammar,
                )
        return result


def _mark_parser_unavailable(grammar: str) -> None:
    """Prevent repeated parent-process loads after an expected failure."""
    with _PARSER_PROBE_LOCK:
        _PARSER_PROBE_RESULTS[grammar] = False


def _clear_parser_probe_cache() -> None:
    """Clear process-level probe state (used by focused tests)."""
    with _PARSER_PROBE_LOCK:
        _PARSER_PROBE_RESULTS.clear()
        _PARSER_PROBE_FAILURE_DETAILS.clear()


def _load_tree_sitter_parser(grammar: str):
    """Load a probed grammar, suppressing only known availability errors."""
    if not _parser_load_probe_succeeds(grammar):
        return None
    try:
        language_pack = importlib.import_module("tree_sitter_language_pack")
        return language_pack.get_parser(grammar)  # type: ignore[attr-defined]
    except _EXPECTED_PARSER_LOAD_ERRORS as exc:
        _mark_parser_unavailable(grammar)
        logger.debug("tree-sitter parser unavailable for %s: %s", grammar, exc)
        return None


def _path_is_within(path: Path, root: Path) -> bool:
    """Return whether *path* is inside *root* after both are resolved."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True



# ---------------------------------------------------------------------------
# Data models for extracted entities
# ---------------------------------------------------------------------------


def normalize_file_path(path: "str | PurePath") -> str:
    """Return *path* as a forward-slash (POSIX) string for graph identity.

    ``file_path`` values and the path component of qualified names are graph
    identity: they must be separator-stable across operating systems so a
    graph built on Windows produces the same identifiers as one built on
    Linux/macOS, and so consumers that reconstruct identifiers from ``Path``
    objects always agree with the parser. See issue #774.

    Only apply this to file *paths* — never to symbol names: qualified
    identifiers legitimately contain backslashes.
    """
    if isinstance(path, PurePath):
        return path.as_posix()
    return str(path).replace("\\", "/")


@dataclass
class NodeInfo:
    kind: str  # File, Class, Function, Type, Test
    name: str
    file_path: str
    line_start: int
    line_end: int
    language: str = ""
    parent_name: Optional[str] = None  # enclosing class/module
    params: Optional[str] = None
    return_type: Optional[str] = None
    modifiers: Optional[str] = None
    is_test: bool = False
    extra: dict = field(default_factory=dict)
    identity_name: Optional[str] = None

    def __post_init__(self) -> None:
        # Identity invariant (#774): file paths always use POSIX separators.
        # File nodes carry their path in ``name`` as well.
        self.file_path = normalize_file_path(self.file_path)
        if self.kind == "File":
            self.name = normalize_file_path(self.name)


@dataclass
class EdgeInfo:
    # CALLS, IMPORTS_FROM, INHERITS, IMPLEMENTS, CONTAINS,
    # TESTED_BY, DEPENDS_ON, REFERENCES
    kind: str
    source: str  # qualified name or path
    target: str  # qualified name or path
    file_path: str
    line: int = 0
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Identity invariant (#774): file paths always use POSIX separators.
        # ``source``/``target`` are left alone — they may contain qualified
        # names whose symbol part legitimately embeds backslashes.
        self.file_path = normalize_file_path(self.file_path)


# ---------------------------------------------------------------------------
# Language extension mapping
# ---------------------------------------------------------------------------

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".rs": "rust",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".mjs": "javascript",
    ".astro": "typescript",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".ksh": "bash",  # Korn shell — close enough to bash for tree-sitter-bash (#235)
    ".ipynb": "notebook",
    # SystemVerilog/Verilog
    ".sv": "verilog",
    ".svh": "verilog",
    ".v": "verilog",
    ".vh": "verilog",
    ".properties": "properties",
    ".yml": "yaml",
    ".yaml": "yaml",
}

# ``.h`` is shared by C and C++. Keep C as the extension default, then promote
# a header only when the C++ grammar finds syntax that C cannot express. Weak
# compatibility markers such as ``__cplusplus`` and ``extern "C"`` are
# deliberately excluded because they are common in otherwise-C headers.
_CPP_HEADER_EVIDENCE_TYPES = frozenset({
    "access_specifier",
    "alias_declaration",
    "base_class_clause",
    "class_specifier",
    "concept_definition",
    "lambda_expression",
    "namespace_definition",
    "noexcept",
    "template_declaration",
    "trailing_return_type",
    "using_declaration",
})

_CPP_HEADER_EVIDENCE_QUALIFIERS = frozenset({b"consteval", b"constinit"})

_CPP_QT_STRUCTURAL_MACRO_REPLACEMENTS = {
    b"QT_BEGIN_NAMESPACE": b" " * len(b"QT_BEGIN_NAMESPACE"),
    b"QT_END_NAMESPACE": b" " * len(b"QT_END_NAMESPACE"),
    b"Q_OBJECT": b" " * len(b"Q_OBJECT"),
    b"Q_SIGNALS": b"public" + b" " * (len(b"Q_SIGNALS") - len(b"public")),
    b"Q_SLOTS": b" " * len(b"Q_SLOTS"),
    b"Q_EMIT": b" " * len(b"Q_EMIT"),
}

# Shebang interpreter → language mapping for extension-less Unix scripts.
# Each key is the **basename** of the interpreter path as it appears after
# ``#!`` (or after ``#!/usr/bin/env``).  Only languages already registered
# above are listed — this file strictly routes extension-less scripts, it
# does NOT introduce new languages on its own.  See issue #237.
SHEBANG_INTERPRETER_TO_LANGUAGE: dict[str, str] = {
    # POSIX / bash-compatible shells — all routed through tree-sitter-bash
    "bash": "bash",
    "sh": "bash",
    "zsh": "bash",
    "ksh": "bash",
    "dash": "bash",
    "ash": "bash",
    # Python (every common variant)
    "python": "python",
    "python2": "python",
    "python3": "python",
    "pypy": "python",
    "pypy3": "python",
    # JavaScript via Node
    "node": "javascript",
    "nodejs": "javascript",
}

# Maximum bytes to read from the head of a file when probing for a shebang.
# 256 is enough for any reasonable shebang line (``#!/usr/bin/env python3 -u\n``
# is ~30 chars) while keeping the worst-case read tiny even on fat binaries.
_SHEBANG_PROBE_BYTES = 256

# ---------------------------------------------------------------------------
# Ansible YAML constants
# ---------------------------------------------------------------------------

# Path components that strongly suggest an Ansible project layout
_ANSIBLE_PATH_COMPONENTS: frozenset[str] = frozenset({
    "playbooks", "roles", "tasks", "handlers", "group_vars", "host_vars",
})

# Common top-level playbook filenames (still require content confirmation)
_ANSIBLE_PLAYBOOK_NAMES: frozenset[str] = frozenset({
    "site.yml", "site.yaml", "main.yml", "main.yaml",
    "install.yml", "install.yaml", "deploy.yml", "deploy.yaml",
})

# Play-level keys that are ONLY valid in Ansible plays.
# `hosts:` alone is not sufficient to identify a play — require at least one of these.
_ANSIBLE_PLAY_KEYS: frozenset[str] = frozenset({
    "tasks", "handlers", "pre_tasks", "post_tasks", "roles",
    "gather_facts", "become", "become_user", "become_method",
    "serial", "strategy", "vars_files", "vars_prompt",
    "any_errors_fatal", "max_fail_percentage", "ignore_errors",
})

# Bare module names for content sniffing; also used after FQCN prefix strip
_ANSIBLE_MODULE_KEYS: frozenset[str] = frozenset({
    "apt", "yum", "dnf", "package", "pip", "copy", "template", "file",
    "service", "systemd", "command", "shell", "raw", "git", "user", "stat",
    "include_tasks", "import_tasks", "include_role", "import_role",
    "set_fact", "debug", "fail", "assert", "wait_for", "pause",
    "lineinfile", "blockinfile", "get_url", "uri", "unarchive",
    "add_host", "group_by", "include_vars",
})

# Task mapping keys that are metadata, NOT module invocations
_TASK_META_KEYS: frozenset[str] = frozenset({
    "name", "when", "loop", "loop_control",
    "with_items", "with_first_found", "with_fileglob", "with_dict",
    "with_subelements", "with_nested", "with_sequence", "with_indexed_items",
    "register", "notify", "tags", "become", "become_user", "become_method",
    "ignore_errors", "vars", "no_log", "check_mode", "environment",
    "any_errors_fatal", "run_once", "delegate_to", "delegate_facts",
    "block", "rescue", "always",
    "changed_when", "failed_when", "retries", "delay", "until",
    "listen", "connection", "timeout",
})

# Tree-sitter node type mappings per language
# Maps (language) -> dict of semantic role -> list of TS node types
_CLASS_TYPES: dict[str, list[str]] = {
    "python": ["class_definition"],
    "javascript": ["class_declaration", "class"],
    # TS types are declarations, not just runtime classes: an interface or type
    # alias is the thing callers depend on, so it needs a node of its own the way
    # interface declarations do. Without them a types-only module (types.ts,
    # *.d.ts) contributes zero symbol nodes and its blast radius collapses to
    # whole-file IMPORTS_FROM fan-out. See: #737
    "typescript": [
        "class_declaration", "class",
        "interface_declaration", "type_alias_declaration", "enum_declaration",
    ],
    "tsx": [
        "class_declaration", "class",
        "interface_declaration", "type_alias_declaration", "enum_declaration",
    ],
    # impl_item is a scope for methods, not a second type definition. It is
    # dispatched separately so repeated impl blocks cannot overwrite structs.
    "rust": ["struct_item", "enum_item", "trait_item"],
    "c": ["struct_specifier", "type_definition"],
    "cpp": ["class_specifier", "struct_specifier"],
    "bash": [],  # Shell has no classes
    "verilog": [
        "module_declaration",
        "interface_declaration",
        "class_declaration",
        "package_declaration",
    ],
}

# TS/TSX heritage clauses. Classes wrap theirs in class_heritage; interfaces use
# extends_type_clause. A type_identifier inside one is already covered by an
# INHERITS edge, so it must not also emit REFERENCES.
_TS_HERITAGE_CLAUSES = frozenset({
    "extends_clause", "implements_clause", "extends_type_clause",
})

# TS/TSX declarations whose ``name`` field is a type_identifier. That occurrence
# is the definition site, not a use of the type.
_TS_TYPE_DECLARATIONS = frozenset({
    "class_declaration", "abstract_class_declaration", "interface_declaration",
    "type_alias_declaration", "enum_declaration",
})

_FUNCTION_TYPES: dict[str, list[str]] = {
    "python": ["function_definition"],
    "javascript": ["function_declaration", "method_definition", "arrow_function"],
    "typescript": ["function_declaration", "method_definition", "arrow_function"],
    "tsx": ["function_declaration", "method_definition", "arrow_function"],
    "rust": ["function_item", "function_signature_item"],
    "c": ["function_definition"],
    "cpp": ["function_definition", "declaration", "field_declaration"],
    # Bash: only function_definition; everything else is a command.
    "bash": ["function_definition"],
    "verilog": ["task_declaration", "function_declaration", "always_construct"],
}

_IMPORT_TYPES: dict[str, list[str]] = {
    "python": ["import_statement", "import_from_statement"],
    "javascript": ["import_statement"],
    "typescript": ["import_statement"],
    "tsx": ["import_statement"],
    "rust": ["use_declaration"],
    "c": ["preproc_include"],
    "cpp": ["preproc_include"],
    # Bash: source / . <file> is a command — handled in _extract_bash_source below.
    "bash": [],
    "verilog": ["package_import_declaration"],
}

_CALL_TYPES: dict[str, list[str]] = {
    "python": ["call"],
    "javascript": ["call_expression", "new_expression"],
    "typescript": ["call_expression", "new_expression"],
    "tsx": ["call_expression", "new_expression"],
    "rust": ["call_expression", "macro_invocation"],
    "c": ["call_expression"],
    "cpp": ["call_expression"],
    # Bash: every command invocation is a "command" node.
    "bash": ["command"],
    "verilog": [
        "module_instantiation",
        "interface_instantiation",
        "function_subroutine_call",
        "subroutine_call",
        "system_tf_call",
    ],
}


def _builtin_language_names() -> frozenset[str]:
    """All built-in language identifiers.

    Used to stop config-driven custom languages (languages.toml) from
    shadowing a built-in language name — built-ins always win.
    """
    return (
        frozenset(EXTENSION_TO_LANGUAGE.values())
        | frozenset(_CLASS_TYPES)
        | frozenset(_FUNCTION_TYPES)
        | frozenset(_IMPORT_TYPES)
        | frozenset(_CALL_TYPES)
    )


# Patterns that indicate a test function
_TEST_PATTERNS = [
    re.compile(r"^test_"),
    re.compile(r"^Test"),
    re.compile(r"_test$"),
    re.compile(r"\.test\."),
    re.compile(r"\.spec\."),
    re.compile(r"_spec$"),
]

_TEST_FILE_PATTERNS = [
    re.compile(r"test_.*\.py$"),
    re.compile(r".*_test\.py$"),
    re.compile(r".*\.test\.[jt]sx?$"),
    re.compile(r".*\.spec\.[jt]sx?$"),
    re.compile(r"tests?/"),
    re.compile(r"[\\/]__tests__[\\/]"),
]

_TEST_RUNNER_NAMES = frozenset({
    "describe", "it", "test", "beforeEach", "afterEach",
    "beforeAll", "afterAll",
    # Mocha TDD interface: `suite` is the describe-equivalent.
    # `test`, the it-equivalent, is already covered above.
    "suite",
})

# Annotations/decorators that mark test methods
_TEST_ANNOTATIONS = frozenset({
    # Rust: built-in `#[test]` plus common async-runtime + framework
    # variants. Stripped of the `#[ ]` wrapper before lookup.
    "test", "tokio::test", "async_std::test",
    "rstest", "rstest::rstest", "proptest",
})

_JS_IMPORT_ORIGINAL_PREFIX_KEY = "__crg_js_import_original__:"
_HTTP_REQUEST_METHODS = frozenset({
    "CONNECT", "DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE",
})


def _is_test_file(path: str) -> bool:
    return any(p.search(path) for p in _TEST_FILE_PATTERNS)


def _is_test_function(
    name: str, file_path: str, decorators: tuple[str, ...] = (),
) -> bool:
    """A function is a test if its name matches test patterns, it lives
    in a test file and has a test-runner name, or it has a @Test annotation.
    """
    if any(p.search(name) for p in _TEST_PATTERNS):
        return True
    if _is_test_file(file_path) and name in _TEST_RUNNER_NAMES:
        return True
    if decorators and any(d in _TEST_ANNOTATIONS for d in decorators):
        return True
    return False


# Documentation summaries are stored in ``NodeInfo.extra`` so the graph
# schema remains backward compatible.  A hard cap keeps parser metadata and
# semantic-search input bounded even when a source file contains a very long
# API reference as its docstring.
_MAX_DOCSTRING_CHARS = 400
_DOC_COMMENT_NODE_TYPES = frozenset({
    "comment",
    "block_comment",
    "line_comment",
    "doc_comment",
})
_DOC_COMMENT_SKIP_TYPES = frozenset({"attribute_item", "decorator"})
_DOC_COMMENT_WRAPPER_TYPES = frozenset({
    "export_statement",
    "template_declaration",
})
_XML_TAG_RE = re.compile(r"<[^>]+>")
_DOC_PARAGRAPH_TAG_RE = re.compile(
    r"</?(?:p|para)(?:\s[^>]*)?>",
    re.IGNORECASE,
)
_DOC_INLINE_TAG_RE = re.compile(
    r"\{@(?:code|literal|link)\s+([^}]+)\}",
    re.IGNORECASE,
)
_DOC_BRIEF_RE = re.compile(r"^\s*[@\\]brief\s+", re.IGNORECASE)


def _clean_docstring_summary(raw: str, language: str) -> str:
    """Return a whitespace-stable, first-paragraph documentation summary."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    if language != "python":
        text = _DOC_PARAGRAPH_TAG_RE.sub("\n\n", text)
        text = _DOC_INLINE_TAG_RE.sub(r"\1", text)
        text = _XML_TAG_RE.sub(" ", text)
        text = html.unescape(text)
        text = _DOC_BRIEF_RE.sub("", text)

    lines = [line.strip() for line in text.splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    paragraph: list[str] = []
    for line in lines:
        if not line:
            break
        if paragraph and line.startswith(("@param", "@return", "\\param", "\\return")):
            break
        paragraph.append(line)
    return " ".join(" ".join(paragraph).split())[:_MAX_DOCSTRING_CHARS]


def _strip_block_doc_comment(text: str) -> str:
    """Remove a Doxygen/Javadoc-style wrapper and per-line ``*`` prefix."""
    if text.startswith(("/**", "/*!")):
        text = text[3:]
    elif text.startswith("/*"):
        text = text[2:]
    if text.endswith("*/"):
        text = text[:-2]

    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("*"):
            stripped = stripped[1:]
            if stripped.startswith(" "):
                stripped = stripped[1:]
        lines.append(stripped)
    return "\n".join(lines)


def _modifier_annotation_names(node) -> list[str]:
    """Return annotation names from a ``modifiers`` child of *node*.

    Annotations live inside a ``modifiers`` node as ``annotation`` /
    ``marker_annotation`` children. The leading ``@`` is stripped. See: #295
    """
    names: list[str] = []
    for sub in node.children:
        if sub.type == "modifiers":
            for mod in sub.children:
                if mod.type in ("annotation", "marker_annotation"):
                    text = mod.text.decode("utf-8", errors="replace")
                    names.append(text.lstrip("@").strip())
    return names


def _python_decorator_names(node) -> list[str]:
    """Return decorators wrapping a Python definition in source order."""
    parent = node.parent
    if parent is None or parent.type != "decorated_definition":
        return []

    names: list[str] = []
    for sibling in parent.children:
        if sibling.type != "decorator":
            continue
        text = sibling.text.decode("utf-8", errors="replace")
        names.append(text.lstrip("@").strip())
    return names


def file_hash(path: Path) -> str:
    """SHA-256 hash of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Ansible YAML helpers (module-level so tests can import them directly)
# ---------------------------------------------------------------------------


def _is_ansible_path(path: Path) -> bool:
    """Return True if the path suggests an Ansible YAML file by directory convention."""
    parts = {p.lower() for p in path.parts}
    return bool(parts & _ANSIBLE_PATH_COMPONENTS) or path.name.lower() in _ANSIBLE_PLAYBOOK_NAMES


def _is_ansible_content(source: bytes) -> bool:
    """Lightweight byte-scan: does this YAML look like an Ansible file?

    Checks that the file is a top-level list and contains at least one
    Ansible-specific structural marker (hosts, tasks, handlers, import_playbook,
    or a known module key / FQCN pattern).
    """
    try:
        text = source.decode("utf-8", errors="replace")
    except Exception:
        return False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped == "---":
            continue  # skip blank lines, comments, and YAML document markers
        if not (line.startswith("- ") or line == "-"):
            return False
        break
    else:
        return False
    has_hosts = bool(re.search(r"^\s+hosts\s*:", text, re.MULTILINE))
    has_tasks = bool(re.search(r"^\s+tasks\s*:", text, re.MULTILINE))
    has_handlers = bool(re.search(r"^\s+handlers\s*:", text, re.MULTILINE))
    has_import_pb = bool(re.search(r"^\s+import_playbook\s*:", text, re.MULTILINE))
    has_name = bool(re.search(r"^\s+-?\s*name\s*:", text, re.MULTILINE))
    has_module = any(
        re.search(rf"^\s+{re.escape(k)}\s*:", text, re.MULTILINE)
        for k in _ANSIBLE_MODULE_KEYS
    ) or bool(re.search(r"^\s+ansible\.\w+\.\w+\s*:", text, re.MULTILINE))
    return has_hosts or has_import_pb or has_tasks or has_handlers or (has_name and has_module)


def _ansible_file_type(path: Path) -> str:
    """Classify an Ansible file by path convention.

    Returns one of: 'playbook', 'tasks', 'handlers', 'meta', 'vars', 'unknown'.
    """
    parts_lower = [p.lower() for p in path.parts]
    name_lower = path.name.lower()
    if "meta" in parts_lower and name_lower in ("main.yml", "main.yaml"):
        return "meta"
    if "handlers" in parts_lower:
        return "handlers"
    if "tasks" in parts_lower:
        return "tasks"
    if any(p in parts_lower for p in ("group_vars", "host_vars", "vars", "defaults")):
        return "vars"
    if "playbooks" in parts_lower or name_lower in _ANSIBLE_PLAYBOOK_NAMES:
        return "playbook"
    return "unknown"


def _ansible_fqcn_short(key: str) -> str:
    """Strip FQCN prefix: 'ansible.builtin.include_tasks' → 'include_tasks'."""
    return key.rsplit(".", 1)[-1]


def _yaml_line(node: object) -> int:
    return node.start_mark.line + 1  # type: ignore[attr-defined]


def _yaml_end_line(node: object) -> int:
    return node.end_mark.line + 1  # type: ignore[attr-defined]


def _yaml_get_key(mapping_node: object, key: str) -> Optional[object]:
    for k_node, v_node in mapping_node.value:  # type: ignore[attr-defined]
        if isinstance(k_node, _YamlScalar) and k_node.value == key:
            return v_node
    return None


def _yaml_scalar(node: object) -> Optional[str]:
    if isinstance(node, _YamlScalar):
        return node.value  # type: ignore[attr-defined]
    return None


def _ansible_is_play_item(item: object) -> bool:
    """True if this top-level sequence item is a definitive Ansible play or playbook import.

    Requires EITHER:
    - ``import_playbook:`` key (unambiguous), OR
    - ``hosts:`` key AND at least one key from ``_ANSIBLE_PLAY_KEYS``.

    A bare ``hosts: all`` without any other play key is too generic and is rejected.
    """
    if not isinstance(item, _YamlMapping):
        return False
    keys: set[Optional[str]] = {
        _yaml_scalar(k)
        for k, _ in item.value  # type: ignore[attr-defined]
        if isinstance(k, _YamlScalar)
    }
    if "import_playbook" in keys:
        return True
    return "hosts" in keys and bool(keys & _ANSIBLE_PLAY_KEYS)

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class CodeParser:
    """Parses source files using Tree-sitter and extracts structural information."""

    _MODULE_CACHE_MAX = 15_000  # Evict cache to cap memory on huge monorepos

    def __init__(self, repo_root: Optional[Path] = None) -> None:
        self._repo_root = Path(repo_root).resolve() if repo_root is not None else None
        self._parsers: dict[str, object] = {}
        self._module_file_cache: dict[str, Optional[str]] = {}
        # Absolute file paths to treat as absent during import resolution.
        # ``forget`` sets this (via :meth:`exclude_files`) so a re-parsed
        # referrer resolves exactly as it would in a build where the forgotten
        # files never existed on disk. See ``forget.forget_files``.
        self._excluded_files: set[str] = set()
        self._export_symbol_cache: dict[str, Optional[str]] = {}
        self._tsconfig_resolver = TsconfigResolver()
        # Cargo discovery is shared by every Rust import/call in a source file.
        self._rust_project_cache: dict[
            str, tuple[Path, Path, Path, dict[str, Path], Path]
        ] = {}
        # Config-driven custom languages (.code-review-graph/languages.toml).
        # The built-in tables stay shared module-level constants; only when a
        # repo defines custom languages does this parser switch to merged
        # copies, so other CodeParser instances (multi-repo registry, worker
        # processes for other repos) are never affected.  See #320.
        self._extension_map: dict[str, str] = EXTENSION_TO_LANGUAGE
        self._class_types: dict[str, list[str]] = _CLASS_TYPES
        self._function_types: dict[str, list[str]] = _FUNCTION_TYPES
        self._import_types: dict[str, list[str]] = _IMPORT_TYPES
        self._call_types: dict[str, list[str]] = _CALL_TYPES
        self._custom_languages: dict[str, CustomLanguage] = {}
        if repo_root is not None:
            self._custom_languages = load_custom_languages(
                Path(repo_root),
                builtin_extensions=EXTENSION_TO_LANGUAGE,
                builtin_languages=_builtin_language_names(),
            )
        if self._custom_languages:
            self._extension_map = dict(EXTENSION_TO_LANGUAGE)
            self._class_types = dict(_CLASS_TYPES)
            self._function_types = dict(_FUNCTION_TYPES)
            self._import_types = dict(_IMPORT_TYPES)
            self._call_types = dict(_CALL_TYPES)
            for custom in self._custom_languages.values():
                for ext in custom.extensions:
                    self._extension_map[ext] = custom.name
                self._class_types[custom.name] = list(custom.class_node_types)
                self._function_types[custom.name] = list(custom.function_node_types)
                self._import_types[custom.name] = list(custom.import_node_types)
                self._call_types[custom.name] = list(custom.call_node_types)

    def _get_parser(self, language: str):  # type: ignore[arg-type]
        if language not in self._parsers:
            # Custom languages map their name onto a packaged grammar.
            custom = self._custom_languages.get(language)
            grammar = custom.grammar if custom is not None else language
            parser = _load_tree_sitter_parser(grammar)
            if parser is None:
                return None
            self._parsers[language] = parser
        return self._parsers[language]

    def detect_language(self, path: Path, source: Optional[bytes] = None) -> Optional[str]:
        """Map a file path to its language name.

        Extension-based lookup is tried first.  For extension-less files
        (typical for Unix scripts like ``bin/myapp`` or ``.git/hooks/pre-commit``)
        we fall back to reading the first line for a shebang.  Files that
        already have a known extension are never re-read — shebang probing
        only runs when the extension lookup returns ``None`` **and** the path
        has no suffix at all.  See issue #237.

        When *source* is provided, the shebang is sniffed from those bytes
        instead of re-reading the file.  Callers that hash-and-parse one byte
        snapshot MUST pass it: a separate disk read can race a concurrent
        save, mis-detect the language, and store a wrong parse under the
        snapshot's hash (issue #746).
        """
        suffix = path.suffix.lower()
        lang = self._extension_map.get(suffix)
        if lang == "yaml" and _is_ansible_path(path):
            return "ansible"
        if lang == "properties":
            return None
        if lang is not None:
            return lang
        # Only probe shebang for files without any extension — "README", "LICENSE",
        # and other extension-less text files also fall here, but the probe is a
        # cheap 256-byte read that returns None when no shebang is found.
        if suffix == "":
            head = source[:_SHEBANG_PROBE_BYTES] if source is not None else None
            return self._detect_language_from_shebang(path, head)
        return None

    @staticmethod
    def _detect_language_from_shebang(
        path: Path,
        head: Optional[bytes] = None,
    ) -> Optional[str]:
        """Inspect the first line of ``path`` for a shebang interpreter.

        When *head* is given it is used as the first bytes of the file and
        the file is not read from disk (TOCTOU-safe for callers that already
        hold the byte snapshot being parsed, see issue #746).

        Returns the mapped language name or ``None`` if the file has no
        shebang, is unreadable, or names an interpreter we don't map.

        Accepted shapes::

            #!/bin/bash
            #!/usr/bin/env python3
            #!/usr/bin/env -S node --experimental-vm-modules
            #!/usr/bin/bash -e

        Only the basename of the interpreter is consulted.  Trailing flags
        after the interpreter are ignored.  Windows-style ``\r\n`` line
        endings are handled.  Binary files read as garbage bytes simply
        fail the ``#!`` prefix check and return ``None``.
        """
        if head is None:
            try:
                with path.open("rb") as fh:
                    head = fh.read(_SHEBANG_PROBE_BYTES)
            except (OSError, PermissionError):
                return None
        if not head.startswith(b"#!"):
            return None

        # Take just the first line, stripped of leading "#!" and any
        # surrounding whitespace.  Split on NUL to defend against accidental
        # binary content following a ``#!`` prefix.
        first_line = head.split(b"\n", 1)[0].split(b"\0", 1)[0]
        try:
            line = first_line[2:].decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError:
            return None
        if not line:
            return None

        tokens = line.split()
        if not tokens:
            return None

        first = tokens[0]
        # `/usr/bin/env` indirection: the interpreter is the next token.
        # `/usr/bin/env -S node --flag` is also valid — skip any leading
        # ``-`` options after env.
        if first.endswith("/env") or first == "env":
            interpreter_token: Optional[str] = None
            for tok in tokens[1:]:
                if tok.startswith("-"):
                    # ``-S`` takes no argument in most envs; skip and continue.
                    continue
                interpreter_token = tok
                break
            if interpreter_token is None:
                return None
            interpreter = interpreter_token.rsplit("/", 1)[-1]
        else:
            # Direct form: ``#!/bin/bash`` or ``#!/usr/local/bin/python3``.
            interpreter = first.rsplit("/", 1)[-1]

        return SHEBANG_INTERPRETER_TO_LANGUAGE.get(interpreter)

    def parse_file(self, path: Path) -> tuple[list[NodeInfo], list[EdgeInfo]]:
        """Parse a single file and return extracted nodes and edges."""
        try:
            source = path.read_bytes()
        except (OSError, PermissionError):
            return [], []
        return self.parse_bytes(path, source)

    def parse_bytes(self, path: Path, source: bytes) -> tuple[list[NodeInfo], list[EdgeInfo]]:
        """Parse pre-read bytes and return extracted nodes and edges.

        This avoids re-reading the file from disk, eliminating TOCTOU gaps
        when the caller has already read the bytes (e.g. for hashing): every
        parse decision, including shebang language detection, derives from
        *source* so the stored file hash always describes the bytes that were
        actually parsed (issue #746).
        """
        language = self.detect_language(path, source)
        if not language:
            return [], []

        parser = None
        tree = None
        parse_source = source
        if language == "c" and path.suffix.lower() == ".h":
            cpp_parser = self._get_parser("cpp")
            if cpp_parser is not None:
                cpp_source = self._mask_cpp_qt_macros(source)
                cpp_tree = cpp_parser.parse(cpp_source)
                if self._has_cpp_header_evidence(cpp_tree.root_node):
                    language = "cpp"
                    parser = cpp_parser
                    tree = cpp_tree
                    parse_source = cpp_source
        elif language == "cpp":
            parse_source = self._mask_cpp_qt_macros(source)

        # Jupyter notebooks: extract code cells and parse as Python
        if language == "notebook":
            return self._parse_notebook(path, source)

        # Databricks .py notebook exports.  The header is ALWAYS the very
        # first line, but the file may have CRLF line endings on Windows
        # (git's core.autocrlf=true default).  Match the first line robustly
        # after stripping any trailing ``\r`` so the detection works on both
        # platforms.  See issue #239.
        if language == "python":
            first_newline = source.find(b"\n")
            first_line = (
                source[:first_newline].rstrip(b"\r")
                if first_newline != -1
                else source.rstrip(b"\r")
            )
            if first_line == b"# Databricks notebook source":
                return self._parse_databricks_py_notebook(path, source)

        # Ansible YAML: path heuristic promoted to "ansible".
        if language == "ansible":
            if _yaml is None:
                return [], []
            file_type = _ansible_file_type(path)
            # Variable and role-metadata files are identified by Ansible's
            # directory contract. Task/handler paths are not sufficient on
            # their own: generic YAML repositories commonly contain those
            # directory names, so require Ansible content evidence there.
            if file_type in ("vars", "meta") or _is_ansible_content(source):
                return self._parse_ansible(path, source)
            return [], []

        # Generic YAML: no tree-sitter grammar bundled; skip.
        if language == "yaml":
            return [], []

        if parser is None:
            parser = self._get_parser(language)
        if not parser:
            return [], []

        if tree is None:
            tree = parser.parse(parse_source)
        nodes: list[NodeInfo] = []
        edges: list[EdgeInfo] = []
        file_path_str = normalize_file_path(path)

        # File node
        test_file = _is_test_file(file_path_str)
        file_extra: dict = {}
        nodes.append(NodeInfo(
            kind="File",
            name=file_path_str,
            file_path=file_path_str,
            line_start=1,
            line_end=source.count(b"\n") + 1,
            language=language,
            is_test=test_file,
            extra=file_extra,
        ))

        # Pre-scan for import mappings and defined names
        import_map, defined_names = self._collect_file_scope(
            tree.root_node, language, source,
        )
        if language == "python":
            self._expand_python_star_imports(
                tree.root_node, file_path_str, import_map,
            )

        typed_call_targets = self._collect_typed_call_targets(
            tree.root_node,
            language,
            file_path_str,
            import_map,
            defined_names,
        )

        # Walk the tree
        self._extract_from_tree(
            tree.root_node, source, language, file_path_str, nodes, edges,
            import_map=import_map, defined_names=defined_names,
        )

        edges = self._apply_typed_call_targets(edges, typed_call_targets, language)

        # Resolve bare call targets to qualified names using same-file definitions
        edges = self._resolve_call_targets(nodes, edges, file_path_str)

        # Generate TESTED_BY edges: when a test function calls a production
        # function, create an edge from the production function back to the test.
        test_qnames = set()
        for n in nodes:
            if n.is_test:
                qn = self._node_qualified(n)
                test_qnames.add(qn)
        if test_qnames:
            for edge in list(edges):
                if edge.kind == "CALLS" and edge.source in test_qnames:
                    edges.append(EdgeInfo(
                        kind="TESTED_BY",
                        source=edge.target,
                        target=edge.source,
                        file_path=edge.file_path,
                        line=edge.line,
                        extra=edge.extra.copy(),
                    ))

        return nodes, edges

    @staticmethod
    def _has_cpp_header_evidence(root) -> bool:
        """Return whether a parsed ``.h`` tree contains C++-only syntax."""
        pending = [root]
        while pending:
            node = pending.pop()
            if node.type == "ERROR" or _is_in_static_dead_guard(node):
                continue

            previous = node.prev_named_sibling
            recovered_after_error = (
                previous is not None
                and previous.type == "ERROR"
                and previous.end_byte == node.start_byte
            )
            if recovered_after_error:
                continue

            if node.type in _CPP_HEADER_EVIDENCE_TYPES:
                return True
            if (
                node.type == "enum_specifier"
                and any(child.type in ("class", "struct") for child in node.children)
            ):
                return True
            if (
                node.type == "type_qualifier"
                and node.text in _CPP_HEADER_EVIDENCE_QUALIFIERS
            ):
                return True
            pending.extend(node.named_children)
        return False

    @staticmethod
    def _mask_cpp_qt_macros(source: bytes) -> bytes:
        """Shield structural Qt macros without changing byte or line offsets."""
        masked = bytearray(source)
        length = len(source)
        index = 0
        line_has_code = False

        def skip_quoted(start: int, quote: int) -> int:
            cursor = start + 1
            while cursor < length:
                if source[cursor] == ord("\\"):
                    cursor += 2
                elif source[cursor] == quote:
                    return cursor + 1
                else:
                    cursor += 1
            return length

        def raw_string_end(start: int) -> Optional[int]:
            for prefix in (b'u8R"', b'LR"', b'UR"', b'uR"', b'R"'):
                if not source.startswith(prefix, start):
                    continue
                delimiter_start = start + len(prefix)
                opening = source.find(b"(", delimiter_start, delimiter_start + 17)
                if opening == -1:
                    return None
                delimiter = source[delimiter_start:opening]
                if any(byte in b" ()\\\t\r\n" for byte in delimiter):
                    return None
                closing = source.find(b")" + delimiter + b'"', opening + 1)
                return length if closing == -1 else closing + len(delimiter) + 2
            return None

        while index < length:
            byte = source[index]
            if byte == ord("\n"):
                line_has_code = False
                index += 1
                continue

            if source.startswith(b"//", index):
                newline = source.find(b"\n", index + 2)
                index = length if newline == -1 else newline
                continue
            if source.startswith(b"/*", index):
                closing = source.find(b"*/", index + 2)
                comment_end = length if closing == -1 else closing + 2
                if b"\n" in source[index:comment_end]:
                    line_has_code = False
                index = comment_end
                continue

            if byte == ord("#") and not line_has_code:
                cursor = index
                while cursor < length:
                    newline = source.find(b"\n", cursor)
                    if newline == -1:
                        cursor = length
                        break
                    previous = newline - 1
                    if previous >= cursor and source[previous] == ord("\r"):
                        previous -= 1
                    if previous < cursor or source[previous] != ord("\\"):
                        cursor = newline
                        break
                    cursor = newline + 1
                index = cursor
                continue

            raw_end = raw_string_end(index)
            if raw_end is not None:
                line_has_code = True
                index = raw_end
                continue
            if byte in (ord('"'), ord("'")):
                line_has_code = True
                index = skip_quoted(index, byte)
                continue

            if byte == ord("_") or chr(byte).isalpha():
                end = index + 1
                while end < length:
                    candidate = source[end]
                    if candidate != ord("_") and not chr(candidate).isalnum():
                        break
                    end += 1
                token = source[index:end]
                replacement = _CPP_QT_STRUCTURAL_MACRO_REPLACEMENTS.get(token)
                if replacement is not None:
                    masked[index:end] = replacement
                line_has_code = True
                index = end
                continue

            if byte not in b" \t\v\f\r":
                line_has_code = True
            index += 1

        return bytes(masked)

    def _parse_notebook(
        self, path: Path, source: bytes,
    ) -> tuple[list[NodeInfo], list[EdgeInfo]]:
        """Parse a Jupyter notebook by extracting code cells."""
        try:
            nb = json.loads(source)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return [], []

        # Determine kernel language
        kernel_lang = (
            nb.get("metadata", {}).get("kernelspec", {}).get("language")
            or nb.get("metadata", {}).get("language_info", {}).get("name")
            or "python"
        ).lower()

        # Only parse supported languages
        supported = {"python"}
        if kernel_lang not in supported:
            return [], []

        # Build CellInfo list from code cells
        cells: list[CellInfo] = []
        magic_lang_map = {
            "%python": "python",
            "%sql": "sql",
        }
        skip_magics = {"%md", "%sh"}

        for cell_idx, cell in enumerate(nb.get("cells", [])):
            if cell.get("cell_type") != "code":
                continue
            lines = cell.get("source", [])
            if isinstance(lines, str):
                lines = lines.splitlines(keepends=True)
            if not lines:
                continue

            # Check first line for language-switching magic
            first_line = lines[0].strip()
            cell_lang = kernel_lang
            cell_lines = lines

            for magic, lang in magic_lang_map.items():
                if first_line == magic or first_line.startswith(magic + " "):
                    cell_lang = lang
                    cell_lines = lines[1:]  # strip magic line
                    break
            else:
                # Check for skip magics
                for skip in skip_magics:
                    if first_line == skip or first_line.startswith(skip + " "):
                        cell_lines = []
                        break

            # Filter %pip, ! lines from Python content (not SQL)
            if cell_lang == "python":
                filtered = [
                    ln for ln in cell_lines
                    if not ln.lstrip().startswith(("%", "!"))
                ]
            else:
                filtered = cell_lines
            if not filtered:
                continue

            cell_source = "".join(filtered)
            cells.append(CellInfo(cell_index=cell_idx, language=cell_lang, source=cell_source))

        if not cells:
            file_path_str = normalize_file_path(path)
            return [NodeInfo(
                kind="File",
                name=file_path_str,
                file_path=file_path_str,
                line_start=1,
                line_end=1,
                language=kernel_lang,
                is_test=_is_test_file(file_path_str),
            )], []

        return self._parse_notebook_cells(path, cells, kernel_lang)

    def _parse_notebook_cells(
        self,
        path: Path,
        cells: list[CellInfo],
        default_language: str,
    ) -> tuple[list[NodeInfo], list[EdgeInfo]]:
        """Parse notebook cells grouped by language.

        Args:
            path: Notebook file path.
            cells: List of CellInfo with index, language, and source.
            default_language: Default language for the File node.
        """
        file_path_str = normalize_file_path(path)
        test_file = _is_test_file(file_path_str)

        # Group cells by language
        lang_cells: dict[str, list[CellInfo]] = {}
        for cell in cells:
            lang_cells.setdefault(cell.language, []).append(cell)

        all_nodes: list[NodeInfo] = []
        all_edges: list[EdgeInfo] = []

        # Track offsets per language for cell_index tagging.
        # Each language group is parsed independently by Tree-sitter,
        # so line numbers restart at 1 for each group.
        all_cell_offsets: list[tuple[int, int, int]] = []
        max_line = 1

        for lang, lang_group in lang_cells.items():
            if lang == "sql":
                # SQL: regex-based table extraction
                for cell in lang_group:
                    for match in _SQL_TABLE_RE.finditer(cell.source):
                        table_name = match.group(1).replace("`", "")
                        all_edges.append(EdgeInfo(
                            kind="IMPORTS_FROM",
                            source=file_path_str,
                            target=table_name,
                            file_path=file_path_str,
                            line=1,
                        ))
                continue

            if lang != "python":
                continue

            ts_parser = self._get_parser(lang)
            if not ts_parser:
                continue

            # Concatenate cells of this language.
            # Line numbers start at 1 for each language group because
            # Tree-sitter parses each concatenation independently.
            code_chunks: list[str] = []
            cell_offsets: list[tuple[int, int, int]] = []
            current_line = 1

            for cell in lang_group:
                cell_line_count = cell.source.count("\n") + (
                    1 if not cell.source.endswith("\n") else 0
                )
                cell_offsets.append((
                    cell.cell_index, current_line, current_line + cell_line_count - 1,
                ))
                code_chunks.append(cell.source)
                current_line += cell_line_count + 1

            concatenated = "\n".join(code_chunks)
            concat_bytes = concatenated.encode("utf-8")

            tree = ts_parser.parse(concat_bytes)

            import_map, defined_names = self._collect_file_scope(
                tree.root_node, lang, concat_bytes,
            )
            if lang == "python":
                self._expand_python_star_imports(
                    tree.root_node, file_path_str, import_map,
                )
            self._extract_from_tree(
                tree.root_node, concat_bytes, lang,
                file_path_str, all_nodes, all_edges,
                import_map=import_map, defined_names=defined_names,
            )

            all_cell_offsets.extend(cell_offsets)
            max_line = max(max_line, current_line)

        # Create File node
        file_node = NodeInfo(
            kind="File",
            name=file_path_str,
            file_path=file_path_str,
            line_start=1,
            line_end=max_line,
            language=default_language,
            is_test=test_file,
        )
        all_nodes.insert(0, file_node)

        # Resolve call targets
        all_edges = self._resolve_call_targets(
            all_nodes, all_edges, file_path_str,
        )

        # Tag nodes with cell_index
        for node in all_nodes:
            if node.kind == "File":
                continue
            for cell_idx, start, end in all_cell_offsets:
                if start <= node.line_start <= end:
                    node.extra["cell_index"] = cell_idx
                    break

        # Generate TESTED_BY edges
        if test_file:
            test_qnames = set()
            for n in all_nodes:
                if n.is_test:
                    qn = self._qualify(n.name, n.file_path, n.parent_name)
                    test_qnames.add(qn)
            for edge in list(all_edges):
                if edge.kind == "CALLS" and edge.source in test_qnames:
                    all_edges.append(EdgeInfo(
                        kind="TESTED_BY",
                        source=edge.target,
                        target=edge.source,
                        file_path=edge.file_path,
                        line=edge.line,
                    ))

        return all_nodes, all_edges

    def _parse_databricks_py_notebook(
        self, path: Path, source: bytes,
    ) -> tuple[list[NodeInfo], list[EdgeInfo]]:
        """Parse a Databricks .py notebook export."""
        text = source.decode("utf-8", errors="replace")

        # Strip the header line
        lines = text.split("\n")
        if lines and lines[0].strip() == "# Databricks notebook source":
            lines = lines[1:]

        # Split on COMMAND delimiters
        cell_chunks: list[list[str]] = [[]]
        for line in lines:
            if re.match(r"^# COMMAND\s*-+\s*$", line):
                cell_chunks.append([])
            else:
                cell_chunks[-1].append(line)

        # Classify each cell
        cells: list[CellInfo] = []
        magic_lang_map = {
            "# MAGIC %sql": "sql",
        }
        skip_prefixes = ("# MAGIC %md", "# MAGIC %sh")

        for cell_idx, chunk in enumerate(cell_chunks):
            non_empty = [ln for ln in chunk if ln.strip()]
            if not non_empty:
                continue

            first_line = non_empty[0]

            # Check if all non-empty lines are MAGIC lines
            all_magic = all(ln.startswith("# MAGIC ") for ln in non_empty)

            # Detect language from the first MAGIC line (e.g. "# MAGIC %sql")
            cell_lang = None
            if all_magic:
                for prefix, lang in magic_lang_map.items():
                    if first_line.startswith(prefix):
                        cell_lang = lang
                        break

            if cell_lang:
                # Strip "# MAGIC " prefix (8 chars) then skip the %lang directive line
                stripped = [
                    ln[8:] if ln.startswith("# MAGIC ") else ln
                    for ln in chunk
                ]
                # Remove the first non-empty line if it's just the %lang directive
                stripped_non_empty = [ln for ln in stripped if ln.strip()]
                if stripped_non_empty and stripped_non_empty[0].strip().startswith("%"):
                    # Drop the directive line from the source
                    first_directive = stripped_non_empty[0]
                    stripped = [ln for ln in stripped if ln != first_directive]
                cell_source = "\n".join(stripped)
                cells.append(CellInfo(
                    cell_index=cell_idx, language=cell_lang, source=cell_source,
                ))
                continue

            # Check for skip prefixes (md, sh)
            if all_magic and first_line.startswith(skip_prefixes):
                continue

            # Default: Python cell (mixed or no MAGIC)
            py_lines = [ln for ln in chunk if not ln.startswith("# MAGIC ")]
            cell_source = "\n".join(py_lines)
            cells.append(CellInfo(
                cell_index=cell_idx, language="python", source=cell_source,
            ))

        if not cells:
            file_path_str = normalize_file_path(path)
            file_node = NodeInfo(
                kind="File",
                name=file_path_str,
                file_path=file_path_str,
                line_start=1,
                line_end=1,
                language="python",
                is_test=_is_test_file(file_path_str),
            )
            file_node.extra["notebook_format"] = "databricks_py"
            return [file_node], []

        nodes, edges = self._parse_notebook_cells(path, cells, "python")

        # Tag File node with notebook_format
        for node in nodes:
            if node.kind == "File":
                node.extra["notebook_format"] = "databricks_py"
                break

        return nodes, edges

    def _resolve_call_targets(
        self,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        file_path: str,
    ) -> list[EdgeInfo]:
        """Resolve bare call targets to qualified names using same-file definitions.

        After parsing, CALLS edges store bare function names (e.g. ``FirebaseAuth``)
        as targets. This method builds a symbol table from the parsed nodes and
        qualifies any bare target that matches a local definition, so that
        ``callers_of`` / ``callees_of`` queries produce correct results.

        External calls (names not defined in this file) remain bare.
        """

        is_cpp = any(node.language == "cpp" for node in nodes)

        def cpp_resolution_extra(
            extra: dict,
            resolution: str,
            candidates: list[str],
        ) -> dict:
            limit = 20
            return {
                **extra,
                f"{resolution}_targets": candidates[:limit],
                f"{resolution}_target_count": len(candidates),
                f"{resolution}_targets_truncated": len(candidates) > limit,
            }

        # Build symbol table: bare_name -> qualified names. Most languages
        # retain their established first-definition behavior; C++ needs all
        # candidates so an overloaded call is never silently bound to one.
        symbols: dict[str, list[tuple[str, Optional[str]]]] = {}
        callable_symbols: dict[str, list[tuple[str, Optional[str]]]] = {}
        source_scopes: dict[str, Optional[str]] = {}
        for node in nodes:
            if node.kind in ("Function", "Class", "Type", "Test"):
                bare = node.name
                qualified = self._node_qualified(node)
                entry = (qualified, node.parent_name)
                if entry not in symbols.setdefault(bare, []):
                    symbols[bare].append(entry)
                if (
                    node.kind in ("Function", "Test")
                    and entry not in callable_symbols.setdefault(bare, [])
                ):
                    callable_symbols[bare].append(entry)
                source_scopes[qualified] = node.parent_name

        def candidate_entries(
            target: str,
            edge_kind: str,
        ) -> list[tuple[str, Optional[str]]]:
            entries = symbols.get(target, [])
            if is_cpp and edge_kind == "CALLS":
                return callable_symbols.get(target) or entries
            return entries

        resolved: list[EdgeInfo] = []
        for edge in edges:
            receiver = edge.extra.get("receiver")
            has_receiver = bool(receiver)
            if edge.kind in ("CALLS", "REFERENCES") and "::" not in edge.target:
                # JS/TS calls retain their full member expression as evidence
                # (``app.handle``) while keeping the method name (``handle``)
                # as the fallback target for external calls. Prefer the full
                # expression when it identifies a same-file member-assigned
                # function; otherwise preserve the existing bare-name
                # resolution behavior.
                member_call = edge.extra.get("member_call")
                member_candidates = symbols.get(member_call, [])
                if member_candidates:
                    edge = EdgeInfo(
                        kind=edge.kind,
                        source=edge.source,
                        target=member_candidates[0][0],
                        file_path=edge.file_path,
                        line=edge.line,
                        extra=edge.extra,
                    )
                    resolved.append(edge)
                    continue
            cpp_lexical_receiver = is_cpp and receiver == "this"
            if (
                is_cpp
                and has_receiver
                and not cpp_lexical_receiver
                and edge.kind in ("CALLS", "REFERENCES")
                and "::" not in edge.target
            ):
                receiver_candidates = [
                    qualified
                    for qualified, _ in candidate_entries(edge.target, edge.kind)
                ]
                edge = EdgeInfo(
                    kind=edge.kind,
                    source=edge.source,
                    target=edge.target,
                    file_path=edge.file_path,
                    line=edge.line,
                    extra=cpp_resolution_extra(
                        edge.extra,
                        "unresolved",
                        receiver_candidates,
                    ),
                )
                resolved.append(edge)
                continue
            if (
                is_cpp
                and edge.kind in ("CALLS", "REFERENCES")
                and "::" in edge.target
                and not edge.target.startswith(f"{file_path}::")
            ):
                explicit_scope, bare_target = edge.target.rsplit("::", 1)
                global_scope = edge.target.startswith("::")
                explicit_scope = explicit_scope.lstrip(":").replace("::", ".")
                scoped_entries = candidate_entries(bare_target, edge.kind)
                if explicit_scope:
                    explicit_preferred_scopes: list[str] = []
                    source_scope = source_scopes.get(edge.source)
                    if not global_scope:
                        while source_scope:
                            explicit_preferred_scopes.append(
                                f"{source_scope}.{explicit_scope}",
                            )
                            source_scope = (
                                source_scope.rsplit(".", 1)[0]
                                if "." in source_scope
                                else None
                            )
                    explicit_preferred_scopes.append(explicit_scope)
                    matching_entries = []
                    for preferred_scope in explicit_preferred_scopes:
                        matching_entries = [
                            (qualified, parent_scope)
                            for qualified, parent_scope in scoped_entries
                            if parent_scope == preferred_scope
                        ]
                        if matching_entries:
                            break
                else:
                    matching_entries = [
                        (qualified, parent_scope)
                        for qualified, parent_scope in scoped_entries
                        if parent_scope is None
                    ]
                scoped_candidates = [
                    qualified for qualified, _ in matching_entries
                ]
                if scoped_candidates:
                    if len(scoped_candidates) > 1:
                        edge = EdgeInfo(
                            kind=edge.kind,
                            source=edge.source,
                            target=edge.target,
                            file_path=edge.file_path,
                            line=edge.line,
                            extra=cpp_resolution_extra(
                                edge.extra,
                                "ambiguous",
                                scoped_candidates,
                            ),
                        )
                    else:
                        edge = EdgeInfo(
                            kind=edge.kind,
                            source=edge.source,
                            target=scoped_candidates[0],
                            file_path=edge.file_path,
                            line=edge.line,
                            extra=edge.extra,
                        )
                    resolved.append(edge)
                    continue
            if (
                edge.kind in ("CALLS", "REFERENCES")
                and "::" not in edge.target
                and (not has_receiver or cpp_lexical_receiver)
            ):
                entries = candidate_entries(edge.target, edge.kind)
                candidates = [qualified for qualified, _ in entries]
                if is_cpp and entries:
                    source_scope = source_scopes.get(edge.source)
                    preferred_scopes: list[Optional[str]] = []
                    while source_scope:
                        preferred_scopes.append(source_scope)
                        source_scope = (
                            source_scope.rsplit(".", 1)[0]
                            if "." in source_scope
                            else None
                        )
                    preferred_scopes.append(None)
                    candidates = []
                    for preferred_scope in preferred_scopes:
                        candidates = [
                            qualified
                            for qualified, parent_scope in entries
                            if parent_scope == preferred_scope
                        ]
                        if candidates:
                            break
                    if not candidates:
                        edge = EdgeInfo(
                            kind=edge.kind,
                            source=edge.source,
                            target=edge.target,
                            file_path=edge.file_path,
                            line=edge.line,
                            extra=cpp_resolution_extra(
                                edge.extra,
                                "unresolved",
                                [qualified for qualified, _ in entries],
                            ),
                        )
                        resolved.append(edge)
                        continue
                if candidates:
                    if is_cpp and len(candidates) > 1:
                        edge = EdgeInfo(
                            kind=edge.kind,
                            source=edge.source,
                            target=edge.target,
                            file_path=edge.file_path,
                            line=edge.line,
                            extra=cpp_resolution_extra(
                                edge.extra,
                                "ambiguous",
                                candidates,
                            ),
                        )
                        resolved.append(edge)
                        continue
                    edge = EdgeInfo(
                        kind=edge.kind,
                        source=edge.source,
                        target=candidates[0],
                        file_path=edge.file_path,
                        line=edge.line,
                        extra=edge.extra,
                    )
            resolved.append(edge)
        return resolved


    _TYPED_CALL_LANGUAGES = frozenset({
        "python", "javascript", "typescript", "tsx",
    })
    _TRANSPARENT_TYPE_WRAPPERS = frozenset({"Annotated", "Optional", "Type"})
    _NON_RECEIVER_TYPE_NAMES = frozenset({
        "Array", "Collection", "Dict", "Iterable", "List", "Map", "Mapping",
        "MutableList", "MutableMap", "MutableMapping", "ReadonlyArray",
        "Sequence", "Set", "Tuple", "Union", "dict", "frozenset", "list",
        "set", "tuple",
    })

    def _collect_typed_call_targets(
        self,
        root,
        language: str,
        file_path: str,
        import_map: dict[str, str],
        defined_names: set[str],
    ) -> dict[tuple[int, str, str], tuple[str, str, str]]:
        """Collect evidence-backed targets for calls on typed receivers.

        The result is keyed by source line, receiver, and method so the normal
        call extractor remains the single producer of CALLS edges. Statically
        typed receivers resolve directly when their class is repository-local.
        Unknown or ambiguous types keep their existing bare targets.
        """
        if language not in self._TYPED_CALL_LANGUAGES:
            return {}

        class_types = set(self._class_types.get(language, []))
        function_types = set(self._function_types.get(language, []))
        call_types = set(self._call_types.get(language, []))
        block_types = {
            "javascript": {"statement_block"},
            "typescript": {"statement_block"},
            "tsx": {"statement_block"},
        }.get(language, set())
        targets: dict[tuple[int, str, str], tuple[str, str, str]] = {}

        def walk(
            node,
            bindings: dict[str, str],
            class_fields: dict[str, str],
            depth: int = 0,
        ) -> None:
            if depth > self._MAX_AST_DEPTH:
                return
            if node.type in class_types:
                fields = self._collect_class_typed_fields(
                    node, language, function_types, class_types,
                )
                class_bindings = dict(bindings)
                class_bindings.update(fields)
                for child in node.children:
                    walk(child, class_bindings, fields, depth + 1)
                return

            if node.type in function_types:
                scoped = dict(bindings)
                scoped.update(class_fields)
                scoped.update(self._collect_function_typed_parameters(node, language))
                for child in node.children:
                    walk(child, scoped, class_fields, depth + 1)
                return

            if node.type in block_types:
                scoped = dict(bindings)
                for child in node.children:
                    walk(child, scoped, class_fields, depth + 1)
                return

            new_bindings = self._typed_bindings_from_node(node, language)
            if new_bindings:
                # Initializers are evaluated before their declaration becomes
                # visible, so visit children with the previous environment.
                for child in node.children:
                    walk(child, bindings, class_fields, depth + 1)
                bindings.update(new_bindings)
                return

            if node.type in call_types:
                receiver, method = self._get_member_call_receiver_method(
                    node, language,
                )
                if receiver and method:
                    type_name = bindings.get(receiver)
                    evidence = "typed_receiver"
                    if type_name is None and receiver[:1].isupper():
                        if (
                            receiver in import_map
                            or receiver in defined_names
                        ):
                            type_name = receiver
                            evidence = "class_receiver"
                    if type_name:
                        target = self._resolve_typed_method_target(
                            type_name,
                            method,
                            file_path,
                            language,
                            import_map,
                            defined_names,
                        )
                        if target:
                            key = (node.start_point[0] + 1, receiver, method)
                            targets[key] = (target, type_name, evidence)

            for child in node.children:
                walk(child, bindings, class_fields, depth + 1)

        walk(root, {}, {})
        return targets

    def _collect_class_typed_fields(
        self,
        class_node,
        language: str,
        function_types: set[str],
        class_types: set[str],
    ) -> dict[str, str]:
        """Return declared instance-field types for one class."""
        fields: dict[str, str] = {}

        def visit(node, depth: int = 0) -> None:
            if depth > self._MAX_AST_DEPTH:
                return
            if node is not class_node and node.type in class_types:
                return
            if node is not class_node and node.type in function_types:
                if language in ("javascript", "typescript", "tsx"):
                    name = node.child_by_field_name("name")
                    if name is not None and name.text == b"constructor":
                        fields.update(self._collect_ts_parameter_properties(node))
                return
            fields.update(self._typed_bindings_from_node(node, language))
            for child in node.children:
                visit(child, depth + 1)

        visit(class_node)
        return fields

    def _collect_function_typed_parameters(
        self,
        function_node,
        language: str,
    ) -> dict[str, str]:
        """Return typed parameters declared directly by one function."""
        bindings: dict[str, str] = {}
        parameter_types = {
            "python": {"typed_parameter", "typed_default_parameter"},
            "javascript": {"required_parameter", "optional_parameter"},
            "typescript": {"required_parameter", "optional_parameter"},
            "tsx": {"required_parameter", "optional_parameter"},
        }.get(language, set())

        def visit(node, depth: int = 0) -> None:
            if depth > self._MAX_AST_DEPTH:
                return
            if node is not function_node and node.type in self._function_types.get(
                language, []
            ):
                return
            if node.type in parameter_types:
                bindings.update(self._typed_bindings_from_node(node, language))
                return
            # Function bodies cannot contain parameters of this function.
            if node.type in ("block", "statement_block", "function_body"):
                return
            for child in node.children:
                visit(child, depth + 1)

        visit(function_node)
        return bindings

    def _collect_ts_parameter_properties(self, constructor_node) -> dict[str, str]:
        """Return TypeScript constructor parameters that declare fields."""
        bindings: dict[str, str] = {}

        def visit(node, depth: int = 0) -> None:
            if depth > self._MAX_AST_DEPTH:
                return
            if node.type in ("required_parameter", "optional_parameter"):
                has_field_modifier = any(
                    child.type in (
                        "accessibility_modifier", "override_modifier", "readonly",
                    )
                    for child in node.children
                )
                if has_field_modifier:
                    bindings.update(
                        self._typed_bindings_from_node(node, "typescript"),
                    )
                return
            if node.type == "statement_block":
                return
            for child in node.children:
                visit(child, depth + 1)

        visit(constructor_node)
        return bindings

    def _typed_bindings_from_node(
        self,
        node,
        language: str,
    ) -> dict[str, str]:
        """Extract typed variable declarations from one AST node."""
        result: dict[str, str] = {}

        if language == "python" and node.type in (
            "assignment", "typed_parameter", "typed_default_parameter",
        ):
            name_node = node.child_by_field_name("left")
            if name_node is None:
                name_node = next(
                    (child for child in node.children if child.type == "identifier"),
                    None,
                )
            type_node = node.child_by_field_name("type")
            self._store_typed_binding(result, name_node, type_node)

        elif language in ("javascript", "typescript", "tsx") and node.type in (
            "required_parameter", "optional_parameter", "variable_declarator",
            "public_field_definition",
        ):
            name_node = (
                node.child_by_field_name("name")
                or node.child_by_field_name("pattern")
            )
            if name_node is None:
                name_node = next(
                    (child for child in node.children if child.type == "identifier"),
                    None,
                )
            self._store_typed_binding(
                result,
                name_node,
                node.child_by_field_name("type"),
            )

        return result

    @classmethod
    def _store_typed_binding(cls, result: dict[str, str], name_node, type_node) -> None:
        if name_node is None or type_node is None:
            return
        name = name_node.text.decode("utf-8", errors="replace")
        type_name = cls._base_type_name(
            type_node.text.decode("utf-8", errors="replace"),
        )
        if name and type_name:
            result[name] = type_name

    @classmethod
    def _base_type_name(cls, annotation: str) -> Optional[str]:
        """Return the receiver class from a generic/nullable annotation."""
        current = annotation.strip()
        for _ in range(4):
            match = re.search(r"[\"']?([A-Za-z_][A-Za-z0-9_.]*)", current)
            if match is None:
                return None
            outer = match.group(1).rsplit(".", 1)[-1]
            remainder = current[match.end():].lstrip()
            if remainder.startswith("[]"):
                return None
            if outer in cls._TRANSPARENT_TYPE_WRAPPERS:
                openings = [
                    index for index in (current.find("["), current.find("<"))
                    if index >= 0
                ]
                if not openings:
                    return None
                current = current[min(openings) + 1:].lstrip()
                continue
            if outer in cls._NON_RECEIVER_TYPE_NAMES:
                return None
            if outer in (
                "None", "bool", "boolean", "float", "int", "number", "str",
                "string", "unknown", "void",
            ):
                return None
            return outer
        return None

    def _resolve_typed_method_target(
        self,
        type_name: str,
        method: str,
        file_path: str,
        language: str,
        import_map: dict[str, str],
        defined_names: set[str],
    ) -> Optional[str]:
        base_type = self._base_type_name(type_name)
        if not base_type:
            return None
        if base_type in import_map:
            resolved = self._resolve_imported_symbol(
                self._js_imported_symbol_name(base_type, import_map),
                import_map[base_type],
                file_path,
                language,
            )
            if resolved:
                return f"{resolved}.{method}"
        if base_type in defined_names:
            return f"{file_path}::{base_type}.{method}"
        return None

    @staticmethod
    def _apply_typed_call_targets(
        edges: list[EdgeInfo],
        targets: dict[tuple[int, str, str], tuple[str, str, str]],
        language: str,
    ) -> list[EdgeInfo]:
        if not targets:
            return edges
        resolved: list[EdgeInfo] = []
        for edge in edges:
            receiver = edge.extra.get("receiver")
            method = edge.target.rsplit(".", 1)[-1].rsplit("::", 1)[-1]
            evidence = targets.get((edge.line, receiver, method)) if receiver else None
            if edge.kind == "CALLS" and evidence:
                target, type_name, evidence_kind = evidence
                extra = dict(edge.extra)
                extra.update({
                    "receiver_type": type_name,
                    "receiver_resolution": evidence_kind,
                })
                resolved_target = target
                edge = EdgeInfo(
                    kind=edge.kind,
                    source=edge.source,
                    target=resolved_target,
                    file_path=edge.file_path,
                    line=edge.line,
                    extra=extra,
                )
            resolved.append(edge)
        return resolved

    _MAX_AST_DEPTH = 180  # Guard against pathologically nested source files
    _MAX_TEST_DESCRIPTION_LEN = 200  # Cap test description length in node names

    def _get_test_description(self, call_node, source: bytes) -> Optional[str]:
        """Extract the first string argument from a test runner call node."""
        for child in call_node.children:
            if child.type == "arguments":
                for arg in child.children:
                    if arg.type in ("string", "template_string"):
                        raw = arg.text.decode("utf-8", errors="replace")
                        stripped = raw.strip("'\"`")
                        normalized = re.sub(r"\s+", " ", stripped).strip()
                        if len(normalized) > self._MAX_TEST_DESCRIPTION_LEN:
                            normalized = normalized[: self._MAX_TEST_DESCRIPTION_LEN]
                        return normalized
        return None


    # -----------------------------------------------------------------------
    # Ansible YAML parser
    # -----------------------------------------------------------------------

    def _parse_ansible(
        self, path: Path, source: bytes,
    ) -> tuple[list[NodeInfo], list[EdgeInfo]]:
        """Parse an Ansible YAML file using PyYAML's compose() node tree.

        Dispatches to sub-parsers based on the file's classified role:
        playbook, tasks, handlers, meta, or vars (vars emits File node only).
        """
        try:
            root = _yaml.compose(source.decode("utf-8", errors="replace"))
        except _yaml.YAMLError as exc:
            logger.debug("Ansible YAML parse error in %s: %s", path, exc)
            return [], []
        if root is None:
            return [], []

        file_path_str = normalize_file_path(path)
        line_count = source.count(b"\n") + 1
        nodes: list[NodeInfo] = [NodeInfo(
            kind="File",
            name=file_path_str,
            file_path=file_path_str,
            line_start=1,
            line_end=line_count,
            language="ansible",
        )]
        edges: list[EdgeInfo] = []

        file_type = _ansible_file_type(path)
        if file_type == "vars":
            return nodes, edges

        # Content-based override: require strong evidence for "playbook" vs "tasks".
        # hosts: alone is not sufficient — require at least one _ANSIBLE_PLAY_KEYS member
        # or an import_playbook: key (which is unambiguously Ansible).
        if file_type in ("unknown", "playbook"):
            if isinstance(root, _YamlSequence) and root.value:
                is_pb = any(_ansible_is_play_item(item) for item in root.value)
                file_type = "playbook" if is_pb else "tasks"
            else:
                file_type = "unknown"

        if file_type == "playbook":
            self._parse_ansible_playbook(root, file_path_str, nodes, edges)
        elif file_type in ("tasks", "handlers"):
            self._parse_ansible_tasks(
                root, file_path_str, nodes, edges,
                is_handler=(file_type == "handlers"),
                parent_play=None,
            )
        elif file_type == "meta":
            self._parse_ansible_meta(root, file_path_str, nodes, edges)

        return nodes, self._resolve_ansible_notify_targets(nodes, edges)

    @staticmethod
    def _ansible_unique_name(
        nodes: list[NodeInfo],
        file_path: str,
        parent_name: Optional[str],
        requested: str,
        line: int,
    ) -> str:
        """Return a stable node name without collapsing repeated task labels."""
        used = {
            node.name
            for node in nodes
            if node.file_path == file_path and node.parent_name == parent_name
        }
        if requested not in used:
            return requested
        candidate = f"{requested}@line{line}"
        suffix = 2
        while candidate in used:
            candidate = f"{requested}@line{line}.{suffix}"
            suffix += 1
        return candidate

    def _resolve_ansible_notify_targets(
        self,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
    ) -> list[EdgeInfo]:
        """Qualify notify targets when one same-scope handler matches."""
        node_by_qn = {
            self._qualify(node.name, node.file_path, node.parent_name): node
            for node in nodes
        }
        handlers: dict[tuple[Optional[str], str], list[str]] = {}
        for node in nodes:
            if node.extra.get("ansible_kind") != "handler":
                continue
            qn = self._qualify(node.name, node.file_path, node.parent_name)
            labels = {
                node.name,
                str(node.extra.get("ansible_name") or node.name),
            }
            listen = node.extra.get("ansible_listen")
            if isinstance(listen, str) and listen:
                labels.add(listen)
            for label in labels:
                handlers.setdefault((node.parent_name, label), []).append(qn)

        resolved: list[EdgeInfo] = []
        for edge in edges:
            if edge.extra.get("ansible_kind") != "notify" or "::" in edge.target:
                resolved.append(edge)
                continue
            source = node_by_qn.get(edge.source)
            scope = source.parent_name if source is not None else None
            candidates = handlers.get((scope, edge.target), [])
            if len(candidates) != 1:
                resolved.append(edge)
                continue
            resolved.append(EdgeInfo(
                kind=edge.kind,
                source=edge.source,
                target=candidates[0],
                file_path=edge.file_path,
                line=edge.line,
                extra=edge.extra,
            ))
        return resolved

    def _parse_ansible_playbook(
        self,
        root: object,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
    ) -> None:
        """Extract plays and import_playbook references from a top-level SequenceNode."""
        if not isinstance(root, _YamlSequence):
            return

        for item in root.value:
            if not isinstance(item, _YamlMapping):
                continue

            # import_playbook: is unambiguously Ansible; emit IMPORTS_FROM and skip
            import_pb_node = _yaml_get_key(item, "import_playbook")
            if import_pb_node is not None:
                target = _yaml_scalar(import_pb_node)
                if target:
                    edges.append(EdgeInfo(
                        kind="IMPORTS_FROM",
                        source=file_path,
                        target=target,
                        file_path=file_path,
                        line=_yaml_line(item),
                        extra={"ansible_kind": "import_playbook"},
                    ))
                continue

            if not _ansible_is_play_item(item):
                continue

            # Derive play name
            name_node = _yaml_get_key(item, "name")
            hosts_node = _yaml_get_key(item, "hosts")
            if name_node and _yaml_scalar(name_node):
                play_name = _yaml_scalar(name_node)
            elif hosts_node and _yaml_scalar(hosts_node):
                play_name = f"play[{_yaml_scalar(hosts_node)}]"
            else:
                play_name = f"play@line{_yaml_line(item)}"

            play_line_start = _yaml_line(item)
            play_line_end = _yaml_end_line(item)
            play_name = self._ansible_unique_name(
                nodes,
                file_path,
                None,
                str(play_name),
                play_line_start,
            )
            play_qn = self._qualify(play_name, file_path, None)

            nodes.append(NodeInfo(
                kind="Class",
                name=play_name,
                file_path=file_path,
                line_start=play_line_start,
                line_end=play_line_end,
                language="ansible",
                extra={"ansible_kind": "play"},
            ))
            edges.append(EdgeInfo(
                kind="CONTAINS",
                source=file_path,
                target=play_qn,
                file_path=file_path,
                line=play_line_start,
            ))

            # vars_files: → IMPORTS_FROM
            vars_files_node = _yaml_get_key(item, "vars_files")
            if isinstance(vars_files_node, _YamlSequence):
                for vf in vars_files_node.value:
                    vf_path = _yaml_scalar(vf)
                    if vf_path:
                        edges.append(EdgeInfo(
                            kind="IMPORTS_FROM",
                            source=play_qn,
                            target=vf_path,
                            file_path=file_path,
                            line=_yaml_line(vf),
                            extra={"ansible_kind": "vars_files"},
                        ))

            # roles: list → IMPORTS_FROM (roles are not tasks)
            roles_node = _yaml_get_key(item, "roles")
            if isinstance(roles_node, _YamlSequence):
                for role_item in roles_node.value:
                    role_name = self._ansible_extract_role_name(role_item)
                    if role_name:
                        edges.append(EdgeInfo(
                            kind="IMPORTS_FROM",
                            source=play_qn,
                            target=role_name,
                            file_path=file_path,
                            line=_yaml_line(role_item),
                            extra={"ansible_kind": "role_reference"},
                        ))

            # pre_tasks, tasks, post_tasks, handlers → task extraction
            for section_key, is_handler in (
                ("pre_tasks", False),
                ("tasks", False),
                ("post_tasks", False),
                ("handlers", True),
            ):
                section_node = _yaml_get_key(item, section_key)
                if isinstance(section_node, _YamlSequence):
                    self._parse_ansible_tasks(
                        section_node, file_path, nodes, edges,
                        is_handler=is_handler,
                        parent_play=play_name,
                    )

    def _parse_ansible_tasks(
        self,
        tasks_node: object,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        is_handler: bool,
        parent_play: Optional[str],
    ) -> None:
        """Extract task/handler Function nodes from a SequenceNode of task mappings."""
        if not isinstance(tasks_node, _YamlSequence):
            return

        for task_node in tasks_node.value:
            if not isinstance(task_node, _YamlMapping):
                continue

            # Find the module key: first key that is not task metadata or a with_* loop
            module_key: Optional[str] = None
            module_short: Optional[str] = None
            module_args_node: Optional[object] = None
            for k_node, v_node in task_node.value:
                k_str = _yaml_scalar(k_node)
                if not k_str:
                    continue
                if k_str in _TASK_META_KEYS or k_str.startswith("with_"):
                    continue
                module_key = k_str
                module_short = _ansible_fqcn_short(k_str)
                module_args_node = v_node
                break

            # Derive task name with fallback chain
            name_node = _yaml_get_key(task_node, "name")
            name_raw = _yaml_scalar(name_node) if name_node is not None else None
            if name_raw:
                requested_name = name_raw
            elif module_short or module_key:
                requested_name = f"{module_short or module_key}@line{_yaml_line(task_node)}"
            else:
                requested_name = f"task@line{_yaml_line(task_node)}"

            task_name = self._ansible_unique_name(
                nodes,
                file_path,
                parent_play,
                requested_name,
                _yaml_line(task_node),
            )
            task_qn = self._qualify(task_name, file_path, parent_play)

            task_extra: dict = {
                "ansible_kind": "handler" if is_handler else "task",
                "ansible_module": module_key or "",
                "ansible_name": requested_name,
            }

            # handler listen: alias
            if is_handler:
                listen_node = _yaml_get_key(task_node, "listen")
                listen_val = _yaml_scalar(listen_node) if listen_node is not None else None
                if listen_val:
                    task_extra["ansible_listen"] = listen_val

            nodes.append(NodeInfo(
                kind="Function",
                name=task_name,
                file_path=file_path,
                line_start=_yaml_line(task_node),
                line_end=_yaml_end_line(task_node),
                language="ansible",
                parent_name=parent_play,
                extra=task_extra,
            ))

            # CONTAINS edge: parent play → task, or file → task for standalone files
            edges.append(EdgeInfo(
                kind="CONTAINS",
                source=(
                    self._qualify(parent_play, file_path, None)
                    if parent_play is not None
                    else file_path
                ),
                target=task_qn,
                file_path=file_path,
                line=_yaml_line(task_node),
            ))

            # notify: → CALLS
            notify_node = _yaml_get_key(task_node, "notify")
            if notify_node is not None:
                for handler_name in self._ansible_extract_notify_targets(notify_node):
                    edges.append(EdgeInfo(
                        kind="CALLS",
                        source=task_qn,
                        target=handler_name,
                        file_path=file_path,
                        line=_yaml_line(notify_node),
                        extra={"ansible_kind": "notify"},
                    ))

            # include_tasks / import_tasks → IMPORTS_FROM (filename)
            if module_short in ("include_tasks", "import_tasks"):
                target_file = self._ansible_module_arg_str(module_args_node)
                if target_file:
                    edges.append(EdgeInfo(
                        kind="IMPORTS_FROM",
                        source=task_qn,
                        target=target_file,
                        file_path=file_path,
                        line=_yaml_line(task_node),
                        extra={"ansible_kind": module_short},
                    ))

            # include_role / import_role → IMPORTS_FROM (role name)
            if module_short in ("include_role", "import_role"):
                role_name = self._ansible_role_from_module_args(module_args_node)
                if role_name:
                    edges.append(EdgeInfo(
                        kind="IMPORTS_FROM",
                        source=task_qn,
                        target=role_name,
                        file_path=file_path,
                        line=_yaml_line(task_node),
                        extra={"ansible_kind": module_short},
                    ))

            # include_vars → IMPORTS_FROM (file or dir)
            if module_short == "include_vars":
                var_target = self._ansible_module_arg_str(module_args_node)
                if var_target:
                    edges.append(EdgeInfo(
                        kind="IMPORTS_FROM",
                        source=task_qn,
                        target=var_target,
                        file_path=file_path,
                        line=_yaml_line(task_node),
                        extra={"ansible_kind": "include_vars"},
                    ))

            # block / rescue / always → recurse with same parent
            for block_key in ("block", "rescue", "always"):
                block_node = _yaml_get_key(task_node, block_key)
                if block_node is not None:
                    self._parse_ansible_tasks(
                        block_node, file_path, nodes, edges,
                        is_handler=is_handler,
                        parent_play=parent_play,
                    )

    def _parse_ansible_meta(
        self,
        root: object,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
    ) -> None:
        """Extract role dependencies from a role meta/main.yml."""
        if not isinstance(root, _YamlMapping):
            return
        deps_node = _yaml_get_key(root, "dependencies")
        if not isinstance(deps_node, _YamlSequence):
            return
        for dep_item in deps_node.value:
            dep_name = self._ansible_extract_role_name(dep_item)
            if dep_name:
                edges.append(EdgeInfo(
                    kind="DEPENDS_ON",
                    source=file_path,
                    target=dep_name,
                    file_path=file_path,
                    line=_yaml_line(dep_item),
                    extra={"ansible_kind": "role_dependency"},
                ))

    def _ansible_extract_role_name(self, item: object) -> Optional[str]:
        """Extract a role name from a roles-list item.

        Handles: plain string, ``{role: name}`` dict, ``{name: ns.role}`` dict.
        """
        if isinstance(item, _YamlScalar):
            return item.value or None  # type: ignore[attr-defined]
        if isinstance(item, _YamlMapping):
            for key in ("role", "name"):
                v = _yaml_get_key(item, key)
                val = _yaml_scalar(v)
                if val:
                    return val
        return None

    def _ansible_extract_notify_targets(self, notify_node: object) -> list[str]:
        """Extract handler names from a notify: value (scalar or sequence)."""
        if isinstance(notify_node, _YamlScalar):
            return [notify_node.value] if notify_node.value else []  # type: ignore[attr-defined]
        if isinstance(notify_node, _YamlSequence):
            return [
                item.value  # type: ignore[attr-defined]
                for item in notify_node.value  # type: ignore[attr-defined]
                if isinstance(item, _YamlScalar) and item.value  # type: ignore[attr-defined]
            ]
        return []

    def _ansible_module_arg_str(self, args_node: Optional[object]) -> Optional[str]:
        """Extract a simple string argument from a module args node.

        Handles: bare scalar (``include_tasks: db.yml``) or mapping with ``file:`` key.
        Jinja2 expressions are returned as-is.
        """
        if args_node is None:
            return None
        if isinstance(args_node, _YamlScalar):
            return args_node.value or None  # type: ignore[attr-defined]
        if isinstance(args_node, _YamlMapping):
            for key in ("file", "_raw_params"):
                v = _yaml_get_key(args_node, key)
                val = _yaml_scalar(v)
                if val:
                    return val
        return None

    def _ansible_role_from_module_args(self, args_node: Optional[object]) -> Optional[str]:
        """Extract role name from include_role/import_role module args."""
        if args_node is None:
            return None
        if isinstance(args_node, _YamlScalar):
            return args_node.value or None  # type: ignore[attr-defined]
        if isinstance(args_node, _YamlMapping):
            v = _yaml_get_key(args_node, "name")
            return _yaml_scalar(v)
        return None

    def _extract_from_tree(
        self,
        root,
        source: bytes,
        language: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        enclosing_class: Optional[str] = None,
        enclosing_func: Optional[str] = None,
        import_map: Optional[dict[str, str]] = None,
        defined_names: Optional[set[str]] = None,
        _depth: int = 0,
    ) -> None:
        """Recursively walk the AST and extract nodes/edges."""
        if _depth > self._MAX_AST_DEPTH:
            return
        class_types = set(self._class_types.get(language, []))
        func_types = set(self._function_types.get(language, []))
        import_types = set(self._import_types.get(language, []))
        call_types = set(self._call_types.get(language, []))

        for child in root.children:
            node_type = child.type

            # --- Bash-specific constructs ---
            # ``source ./foo.sh`` and ``. ./foo.sh`` are commands in
            # tree-sitter-bash; re-interpret them as IMPORTS_FROM edges so
            # cross-script wiring works the same as in other languages.
            if language == "bash" and node_type == "command":
                if self._extract_bash_source_command(
                    child, file_path, edges,
                ):
                    continue

            # --- Verilog/SystemVerilog structural declarations ---
            if language == "verilog" and self._extract_verilog_constructs(
                child,
                node_type,
                file_path,
                nodes,
                edges,
                enclosing_class,
                enclosing_func,
            ):
                continue

            if language == "rust" and node_type == "impl_item":
                self._extract_rust_impl(
                    child,
                    source,
                    file_path,
                    nodes,
                    edges,
                    import_map or {},
                    defined_names or set(),
                    _depth,
                )
                continue

            # --- JS/TS static CommonJS and dynamic imports ---
            # Treat only literal module specifiers as definite dependencies.
            # Dynamic templates and path.join/path.resolve expressions are
            # intentionally left unresolved rather than guessed.
            if (
                language in ("javascript", "typescript", "tsx")
                and node_type == "call_expression"
            ):
                self._extract_js_module_call(child, file_path, language, edges)

            # --- JS/TS variable-assigned functions (const foo = () => {}) ---
            if (
                language in ("javascript", "typescript", "tsx")
                and node_type in ("lexical_declaration", "variable_declaration")
                and self._extract_js_var_functions(
                    child, source, language, file_path, nodes, edges,
                    enclosing_class, enclosing_func,
                    import_map, defined_names, _depth,
                )
            ):
                continue

            # --- Classes ---
            if node_type in class_types and self._extract_classes(
                child, source, language, file_path, nodes, edges,
                enclosing_class, import_map, defined_names,
                _depth,
            ):
                continue

            # --- JS/TS class field arrow functions (handler = () => {}) ---
            if (
                language in ("javascript", "typescript", "tsx")
                and node_type == "public_field_definition"
                and self._extract_js_field_function(
                    child, source, language, file_path, nodes, edges,
                    enclosing_class, enclosing_func,
                    import_map, defined_names, _depth,
                )
            ):
                continue

            # --- JS/TS member-assigned functions (app.handle = function () {}) ---
            if (
                language in ("javascript", "typescript", "tsx")
                and node_type == "expression_statement"
                and self._extract_js_member_functions(
                    child, source, language, file_path, nodes, edges,
                    enclosing_class, enclosing_func,
                    import_map, defined_names, _depth,
                )
            ):
                continue

            # --- Functions ---
            if node_type in func_types and self._extract_functions(
                child, source, language, file_path, nodes, edges,
                enclosing_class, import_map, defined_names,
                _depth, enclosing_func,
            ):
                continue

            # --- Imports ---
            if node_type in import_types:
                if self._extract_imports(
                    child, language, source, file_path, edges,
                ):
                    continue
                # A node type can be shared between imports and calls (e.g.
                # a custom language mapping one node type to both). If it was
                # not an import, fall through to call extraction below rather
                # than dropping it.

            # --- Calls ---
            if node_type in call_types:
                if self._extract_calls(
                    child, source, language, file_path, nodes, edges,
                    enclosing_class, enclosing_func,
                    import_map, defined_names, _depth,
                ):
                    continue

            # --- JSX component invocations ---
            if (
                language in ("javascript", "typescript", "tsx")
                and node_type in ("jsx_opening_element", "jsx_self_closing_element")
            ):
                self._extract_jsx_component_call(
                    child, language, file_path, edges,
                    enclosing_class, enclosing_func,
                    import_map, defined_names,
                )

            # --- TS type-position references ---
            if language in ("typescript", "tsx") and node_type == "type_identifier":
                self._extract_ts_type_reference(
                    child, language, file_path, edges,
                    enclosing_class, enclosing_func,
                    import_map, defined_names,
                )

            # --- Value references (function-as-value in maps, arrays, args) ---
            self._extract_value_references(
                child, node_type, source, language, file_path, edges,
                enclosing_class, enclosing_func,
                import_map, defined_names,
            )

            # Recurse for other node types
            self._extract_from_tree(
                child, source, language, file_path, nodes, edges,
                enclosing_class=enclosing_class,
                enclosing_func=enclosing_func,
                import_map=import_map, defined_names=defined_names,
                _depth=_depth + 1,
            )

    def _extract_bash_source_command(
        self,
        node,
        file_path: str,
        edges: list[EdgeInfo],
    ) -> bool:
        """Detect ``source foo.sh`` / ``. foo.sh`` and emit an IMPORTS_FROM
        edge. Returns True if handled (so the main loop skips recursing
        into this command). See: #197
        """
        command_name: Optional[str] = None
        args: list[str] = []
        for sub in node.children:
            if sub.type == "command_name":
                command_name = sub.text.decode("utf-8", errors="replace").strip()
            elif sub.type in ("word", "string", "raw_string") and command_name:
                txt = sub.text.decode("utf-8", errors="replace").strip()
                # Strip surrounding quotes if present
                if len(txt) >= 2 and txt[0] in ("'", '"') and txt[-1] == txt[0]:
                    txt = txt[1:-1]
                if txt:
                    args.append(txt)
        if command_name in ("source", ".") and args:
            target = args[0]
            # Try to resolve relative paths to real files
            resolved = self._resolve_module_to_file(target, file_path, "bash")
            edges.append(EdgeInfo(
                kind="IMPORTS_FROM",
                source=file_path,
                target=resolved if resolved else target,
                file_path=file_path,
                line=node.start_point[0] + 1,
            ))
            return True
        return False


    # ------------------------------------------------------------------
    # JS/TS: variable-assigned functions  (const foo = () => {})
    # ------------------------------------------------------------------

    _JS_FUNC_VALUE_TYPES = frozenset(
        {"arrow_function", "function_expression", "function"},
    )

    def _extract_js_var_functions(
        self,
        child,
        source: bytes,
        language: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        enclosing_class: Optional[str],
        enclosing_func: Optional[str],
        import_map: Optional[dict[str, str]],
        defined_names: Optional[set[str]],
        _depth: int,
    ) -> bool:
        """Handle JS/TS variable declarations that assign functions.

        Patterns handled:
          const foo = () => {}
          let bar = function() {}
          export const baz = (x: number): string => x.toString()

        Returns True if at least one function was extracted from the
        declaration, so the caller can skip generic recursion.
        """
        handled = False
        for declarator in child.children:
            if declarator.type != "variable_declarator":
                continue

            # Find identifier and function value
            var_name = None
            func_node = None
            for sub in declarator.children:
                if sub.type == "identifier" and var_name is None:
                    var_name = sub.text.decode("utf-8", errors="replace")
                elif sub.type in self._JS_FUNC_VALUE_TYPES:
                    func_node = sub

            if not var_name or not func_node:
                continue

            is_test = _is_test_function(var_name, file_path)
            kind = "Test" if is_test else "Function"
            qualified = self._qualify(var_name, file_path, enclosing_class)
            params = self._get_params(func_node, language, source)
            ret_type = self._get_return_type(func_node, language, source)

            nodes.append(NodeInfo(
                kind=kind,
                name=var_name,
                file_path=file_path,
                line_start=child.start_point[0] + 1,
                line_end=child.end_point[0] + 1,
                language=language,
                parent_name=enclosing_class,
                params=params,
                return_type=ret_type,
                is_test=is_test,
            ))
            container = (
                self._qualify(enclosing_class, file_path, None)
                if enclosing_class else file_path
            )
            edges.append(EdgeInfo(
                kind="CONTAINS",
                source=container,
                target=qualified,
                file_path=file_path,
                line=child.start_point[0] + 1,
            ))

            # Recurse into the function body for calls
            self._extract_from_tree(
                func_node, source, language, file_path, nodes, edges,
                enclosing_class=enclosing_class,
                enclosing_func=var_name,
                import_map=import_map,
                defined_names=defined_names,
                _depth=_depth + 1,
            )
            handled = True

        if not handled:
            # Not a function assignment — let generic recursion handle it
            return False
        return True

    def _extract_js_field_function(
        self,
        child,
        source: bytes,
        language: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        enclosing_class: Optional[str],
        enclosing_func: Optional[str],
        import_map: Optional[dict[str, str]],
        defined_names: Optional[set[str]],
        _depth: int,
    ) -> bool:
        """Handle class field arrow functions: handler = (e) => { ... }"""
        prop_name = None
        func_node = None
        for sub in child.children:
            if sub.type == "property_identifier" and prop_name is None:
                prop_name = sub.text.decode("utf-8", errors="replace")
            elif sub.type in self._JS_FUNC_VALUE_TYPES:
                func_node = sub

        if not prop_name or not func_node:
            return False

        is_test = _is_test_function(prop_name, file_path)
        kind = "Test" if is_test else "Function"
        qualified = self._qualify(prop_name, file_path, enclosing_class)
        params = self._get_params(func_node, language, source)

        nodes.append(NodeInfo(
            kind=kind,
            name=prop_name,
            file_path=file_path,
            line_start=child.start_point[0] + 1,
            line_end=child.end_point[0] + 1,
            language=language,
            parent_name=enclosing_class,
            params=params,
            is_test=is_test,
        ))
        container = (
            self._qualify(enclosing_class, file_path, None)
            if enclosing_class else file_path
        )
        edges.append(EdgeInfo(
            kind="CONTAINS",
            source=container,
            target=qualified,
            file_path=file_path,
            line=child.start_point[0] + 1,
        ))

        self._extract_from_tree(
            func_node, source, language, file_path, nodes, edges,
            enclosing_class=enclosing_class,
            enclosing_func=prop_name,
            import_map=import_map,
            defined_names=defined_names,
            _depth=_depth + 1,
        )
        return True

    def _extract_js_member_functions(
        self,
        child,
        source: bytes,
        language: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        enclosing_class: Optional[str],
        enclosing_func: Optional[str],
        import_map: Optional[dict[str, str]],
        defined_names: Optional[set[str]],
        _depth: int,
    ) -> bool:
        """Handle JS/TS member-assigned functions.

        Patterns handled (LHS is a ``member_expression``, RHS is a function):
          app.handle = function handle(req, res) {}
          Router.prototype.dispatch = (req) => {}
          exports.render = function () {}

        These prototype- and module-augmentation patterns carry the entire
        public API of Express, Koa and many older JS modules, but were
        previously invisible to the graph: only ``const x = fn``
        (:func:`_extract_js_var_functions`) and class fields
        (:func:`_extract_js_field_function`) produced Function nodes. The node
        is qualified by its full member path (``file::app.handle``), matching
        the ``file::Class.method`` shape used elsewhere.

        Returns True if a function was extracted, so the caller can skip
        generic recursion.
        """
        # ``child`` is the expression_statement wrapping the assignment.
        assign = None
        if child.type == "assignment_expression":
            assign = child
        else:
            for sub in child.children:
                if sub.type == "assignment_expression":
                    assign = sub
                    break
        if assign is None:
            return False

        left = assign.child_by_field_name("left")
        right = assign.child_by_field_name("right")
        if left is None or right is None:
            return False
        if left.type != "member_expression":
            return False
        if right.type not in self._JS_FUNC_VALUE_TYPES:
            return False

        # An assignment nested in a function belongs to that function's
        # runtime scope, not to the module-level object namespace.  Without
        # lexical scope in the member name, identical assignments in sibling
        # functions would both become ``file::obj.method`` and produce
        # duplicate CONTAINS targets. Top-level lexical blocks have the same
        # problem, so only direct program statements have a stable identity.
        if (
            enclosing_func
            or child.parent is None
            or child.parent.type != "program"
        ):
            return False

        member_name = self._get_js_static_member_path(left)
        if member_name is None:
            return False

        is_test = _is_test_function(member_name, file_path)
        kind = "Test" if is_test else "Function"
        qualified = self._qualify(member_name, file_path, enclosing_class)
        params = self._get_params(right, language, source)
        ret_type = self._get_return_type(right, language, source)

        nodes.append(NodeInfo(
            kind=kind,
            name=member_name,
            file_path=file_path,
            line_start=child.start_point[0] + 1,
            line_end=child.end_point[0] + 1,
            language=language,
            parent_name=enclosing_class,
            params=params,
            return_type=ret_type,
            is_test=is_test,
        ))
        container = (
            self._qualify(enclosing_class, file_path, None)
            if enclosing_class else file_path
        )
        edges.append(EdgeInfo(
            kind="CONTAINS",
            source=container,
            target=qualified,
            file_path=file_path,
            line=child.start_point[0] + 1,
        ))

        # Recurse into the function body for calls, attributing them to the
        # member function.
        self._extract_from_tree(
            right, source, language, file_path, nodes, edges,
            enclosing_class=enclosing_class,
            enclosing_func=member_name,
            import_map=import_map,
            defined_names=defined_names,
            _depth=_depth + 1,
        )
        return True

    @staticmethod
    def _get_js_static_member_path(node) -> Optional[str]:
        """Return a stable identifier-only JS/TS member path."""
        if node.type != "member_expression":
            return None
        text = node.text.decode("utf-8", errors="replace")
        if not text or "[" in text or "\n" in text:
            return None

        parts: list[str] = []
        current = node
        while current.type == "member_expression":
            object_node = current.child_by_field_name("object")
            property_node = current.child_by_field_name("property")
            if (
                object_node is None
                or property_node is None
                or property_node.type not in ("identifier", "property_identifier")
            ):
                return None
            parts.append(
                property_node.text.decode("utf-8", errors="replace"),
            )
            current = object_node

        if current.type not in ("identifier", "this"):
            return None
        parts.append(current.text.decode("utf-8", errors="replace"))
        return ".".join(reversed(parts))

    def _get_docstring_summary(self, node, language: str) -> Optional[str]:
        """Extract a bounded documentation summary for a definition node."""
        if language == "python":
            raw = self._python_docstring_value(node)
        else:
            raw = self._preceding_doc_comment(node, language)
        if not raw:
            return None
        return _clean_docstring_summary(raw, language) or None

    @staticmethod
    def _python_docstring_value(node) -> Optional[str]:
        """Return Python's actual string value for the first body statement.

        ``ast.literal_eval`` gives us CPython-compatible escape handling and
        implicit literal concatenation while naturally rejecting f-strings.
        A bytes literal evaluates successfully but is rejected by the final
        type check, matching ``__doc__`` semantics.
        """
        body = node.child_by_field_name("body")
        if body is None:
            return None
        statement = next(
            (child for child in body.named_children if child.type != "comment"),
            None,
        )
        if statement is None:
            return None
        expression = statement
        if expression.type == "expression_statement":
            named = expression.named_children
            if len(named) != 1:
                return None
            expression = named[0]
        if expression.type not in (
            "string",
            "concatenated_string",
            "parenthesized_expression",
        ):
            return None
        try:
            value = ast.literal_eval(
                expression.text.decode("utf-8", errors="strict"),
            )
        except (SyntaxError, ValueError, UnicodeDecodeError):
            return None
        return value if isinstance(value, str) else None

    @staticmethod
    def _line_doc_payload(text: str, language: str) -> Optional[str]:
        """Return one documentation-line payload, or ``None`` if not docs."""
        stripped = text.strip()
        if language == "rust":
            # Rust ``//!`` is inner module/crate documentation; ``////`` is
            # an ordinary comment, not an outer item doc comment.
            if not stripped.startswith("///") or stripped.startswith("////"):
                return None
            return stripped[3:].lstrip()
        if stripped.startswith(("///", "//!")):
            return stripped[3:].lstrip()
        return None

    def _preceding_doc_comment(self, node, language: str) -> Optional[str]:
        """Return documentation directly attached above a definition."""
        anchor = node
        while (
            anchor.parent is not None
            and anchor.parent.type in _DOC_COMMENT_WRAPPER_TYPES
        ):
            anchor = anchor.parent

        siblings: list = []
        current_line = anchor.start_point[0]
        sibling = anchor.prev_sibling
        while sibling is not None:
            if sibling.end_point[0] < current_line - 1:
                break
            if sibling.type in _DOC_COMMENT_SKIP_TYPES:
                current_line = sibling.start_point[0]
                sibling = sibling.prev_sibling
                continue
            if sibling.type not in _DOC_COMMENT_NODE_TYPES:
                break
            siblings.append(sibling)
            current_line = sibling.start_point[0]
            sibling = sibling.prev_sibling

        if not siblings:
            return None

        nearest = siblings[0].text.decode("utf-8", errors="replace").strip()
        if nearest.startswith("/*"):
            allowed = ("/**",) if language == "rust" else ("/**", "/*!")
            if not nearest.startswith(allowed):
                return None
            return _strip_block_doc_comment(nearest)

        # Work from the definition upward and stop at the first adjacent
        # ordinary comment.  This attaches only the nearest documentation
        # block and avoids hoovering unrelated implementation notes into it.
        payloads: list[str] = []
        for comment in siblings:
            text = comment.text.decode("utf-8", errors="replace")
            payload = self._line_doc_payload(text, language)
            if payload is None:
                break
            payloads.append(payload)
        if not payloads:
            return None
        payloads.reverse()
        return "\n".join(payloads)

    def _extract_classes(
        self,
        child,
        source: bytes,
        language: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        enclosing_class: Optional[str],
        import_map: Optional[dict[str, str]],
        defined_names: Optional[set[str]],
        _depth: int,
    ) -> bool:
        """Extract a class definition node and its inheritance edges.

        Returns True if the child was handled (class with a name found).
        """
        name = self._get_name(child, language, "class")
        if not name:
            return False

        class_parent = enclosing_class

        extra: dict = {}

        # Class-level annotation persistence for all annotation-bearing
        # languages. Stored in ``modifiers`` (string)
        # and ``extra["decorators"]`` (list).  See: #295
        class_decorators = _modifier_annotation_names(child)
        if language == "python":
            class_decorators.extend(_python_decorator_names(child))
        class_modifiers: Optional[str] = (
            ",".join(class_decorators) if class_decorators else None
        )
        if class_decorators and "decorators" not in extra:
            extra["decorators"] = class_decorators

        docstring = self._get_docstring_summary(child, language)
        if docstring:
            extra["docstring"] = docstring

        node = NodeInfo(
            kind="Class",
            name=name,
            file_path=file_path,
            line_start=child.start_point[0] + 1,
            line_end=child.end_point[0] + 1,
            language=language,
            parent_name=class_parent,
            modifiers=class_modifiers,
            extra=extra,
        )
        nodes.append(node)

        # CONTAINS edge
        class_container = file_path
        edges.append(EdgeInfo(
            kind="CONTAINS",
            source=class_container,
            target=self._qualify(name, file_path, class_parent),
            file_path=file_path,
            line=child.start_point[0] + 1,
        ))

        # Inheritance edges
        bases = self._get_bases(child, language, source)
        for base in bases:
            edges.append(EdgeInfo(
                kind="INHERITS",
                source=self._qualify(
                    name, file_path, class_parent,
                ),
                target=base,
                file_path=file_path,
                line=child.start_point[0] + 1,
            ))

        # Recurse into class body
        recursive_class = name
        self._extract_from_tree(
            child, source, language, file_path, nodes, edges,
            enclosing_class=recursive_class, enclosing_func=None,
            import_map=import_map, defined_names=defined_names,
            _depth=_depth + 1,
        )
        return True

    def _extract_functions(
        self,
        child,
        source: bytes,
        language: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        enclosing_class: Optional[str],
        import_map: Optional[dict[str, str]],
        defined_names: Optional[set[str]],
        _depth: int,
        enclosing_func: Optional[str] = None,
    ) -> bool:
        """Extract a function/method definition node.

        Returns True if the child was handled (function with a name found).
        """
        name = self._get_name(child, language, "function")
        if not name:
            return False

        # Extract annotations/decorators for test detection
        decorators: tuple[str, ...] = ()
        deco_list: list[str] = []
        for sub in child.children:
            # Annotations inside a modifiers child
            if sub.type == "modifiers":
                for mod in sub.children:
                    if mod.type in ("annotation", "marker_annotation"):
                        text = mod.text.decode("utf-8", errors="replace")
                        deco_list.append(text.lstrip("@").strip())
        # Python: check parent decorated_definition for decorator siblings
        if child.parent and child.parent.type == "decorated_definition":
            for sib in child.parent.children:
                if sib.type == "decorator":
                    text = sib.text.decode("utf-8", errors="replace")
                    deco_list.append(text.lstrip("@").strip())
        # Rust: attributes are preceding siblings of function_item, not
        # children. Walk back through `attribute_item` nodes and strip the
        # `#[ ]` (or `#![ ]`) wrapper.
        if language == "rust":
            sib = child.prev_sibling
            while sib is not None and sib.type == "attribute_item":
                text = sib.text.decode("utf-8", errors="replace").strip()
                if text.startswith("#!["):
                    inner = text[3:].rstrip()
                elif text.startswith("#["):
                    inner = text[2:].rstrip()
                else:
                    inner = text
                if inner.endswith("]"):
                    inner = inner[:-1]
                deco_list.append(inner.strip())
                sib = sib.prev_sibling
        if deco_list:
            decorators = tuple(deco_list)

        is_test = _is_test_function(name, file_path, decorators)
        kind = "Test" if is_test else "Function"

        parent_name = enclosing_class
        container_scope = enclosing_class

        identity_name = name
        params = self._get_params(child, language, source)
        if language == "cpp":
            explicit_scope, identity_name, cpp_params = self._cpp_function_identity(
                child, name, source,
            )
            lexical_namespace = self._cpp_lexical_namespace(child)
            lexical_classes = self._cpp_lexical_class_names(child)
            lexical_class_scope = ".".join(lexical_classes) or None
            parent_name = self._cpp_scope_join(
                lexical_namespace,
                explicit_scope or lexical_class_scope or enclosing_class,
            )
            if lexical_classes:
                container_scope = ".".join(lexical_classes[-2:])
            elif enclosing_class:
                container_scope = enclosing_class
            if cpp_params is not None:
                params = cpp_params

        qualified = self._qualify(identity_name, file_path, parent_name)
        ret_type = self._get_return_type(child, language, source)

        method_extra: dict = {}

        # Persist annotations/decorators so consumers can filter on them
        # (e.g. "show me all @Composable functions").  Stored in BOTH
        # ``modifiers`` (comma-joined string) and ``extra["decorators"]``
        # (list) — merged into the existing method_extra dict rather than a
        # separate one.  See: #295
        modifiers_str: Optional[str] = ",".join(deco_list) if deco_list else None
        if deco_list:
            method_extra["decorators"] = list(deco_list)

        docstring = self._get_docstring_summary(child, language)
        if docstring:
            method_extra["docstring"] = docstring

        node = NodeInfo(
            kind=kind,
            name=name,
            file_path=file_path,
            line_start=child.start_point[0] + 1,
            line_end=child.end_point[0] + 1,
            language=language,
            parent_name=parent_name,
            params=params,
            return_type=ret_type,
            modifiers=modifiers_str,
            is_test=is_test,
            extra=method_extra,
            identity_name=identity_name,
        )
        nodes.append(node)

        # CONTAINS edge
        container = (
            self._qualify(container_scope, file_path, None)
            if container_scope
            else file_path
        )
        edges.append(EdgeInfo(
            kind="CONTAINS",
            source=container,
            target=qualified,
            file_path=file_path,
            line=child.start_point[0] + 1,
        ))

        # Recurse to find calls inside the function
        recursive_class = (
            parent_name if language == "cpp" else enclosing_class
        )
        self._extract_from_tree(
            child, source, language, file_path, nodes, edges,
            enclosing_class=recursive_class, enclosing_func=identity_name,
            import_map=import_map, defined_names=defined_names,
            _depth=_depth + 1,
        )
        return True

    def _extract_imports(
        self,
        child,
        language: str,
        source: bytes,
        file_path: str,
        edges: list[EdgeInfo],
    ) -> bool:
        """Extract import edges from an import statement node.

        Returns True if at least one import edge was emitted. A grammar can
        reuse a single node type for both imports and ordinary calls.
        Returning False lets the dispatcher fall through to call extraction
        instead of silently dropping the call.
        """
        imports = self._extract_import(child, language, source)
        for imp_target in imports:
            resolved = self._resolve_module_to_file(
                imp_target, file_path, language,
            )
            edges.append(EdgeInfo(
                kind="IMPORTS_FROM",
                source=file_path,
                target=resolved if resolved else imp_target,
                file_path=file_path,
                line=child.start_point[0] + 1,
            ))
        return bool(imports)

    def _extract_calls(
        self,
        child,
        source: bytes,
        language: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        enclosing_class: Optional[str],
        enclosing_func: Optional[str],
        import_map: Optional[dict[str, str]],
        defined_names: Optional[set[str]],
        _depth: int,
    ) -> bool:
        """Extract call expressions, including test runner special cases.

        Returns True if the child was fully handled (a test runner call or a
        statically unreachable Python call that should skip default
        recursion). Returns False if the caller should continue to default
        recursion.
        """
        if (
            language == "python"
            and (child.start_point[0] + 1, child.start_point[1])
            in _python_unreachable_call_positions(source)
        ):
            return True

        # Non-Python languages: tree-sitter dead-guard walk (TS/JS
        # ``if false``, C/C++ ``#if 0``).  ``ast`` above cannot reach them.
        if language != "python" and _is_in_static_dead_guard(child):
            return True

        call_name = self._get_call_name(child, language, source)

        # For member expressions like describe.only / it.skip / test.each,
        # resolve the base call name so those are treated as test runner
        # calls.
        effective_call_name = call_name
        if (
            call_name
            and language in ("javascript", "typescript", "tsx")
            and _is_test_file(file_path)
            and call_name not in _TEST_RUNNER_NAMES
        ):
            effective_call_name = (
                self._get_base_call_name(child, source) or call_name
            )

        # Special handling: test runner calls in test files -> Test nodes
        if (
            effective_call_name
            and language in ("javascript", "typescript", "tsx")
            and _is_test_file(file_path)
            and effective_call_name in _TEST_RUNNER_NAMES
        ):
            test_desc = self._get_test_description(child, source)
            line_no = child.start_point[0] + 1
            synthetic_base = (
                f"{effective_call_name}:{test_desc}"
                if test_desc else effective_call_name
            )
            synthetic_name = f"{synthetic_base}@L{line_no}"
            qualified = self._qualify(
                synthetic_name, file_path, enclosing_class,
            )

            nodes.append(NodeInfo(
                kind="Test",
                name=synthetic_name,
                file_path=file_path,
                line_start=child.start_point[0] + 1,
                line_end=child.end_point[0] + 1,
                language=language,
                parent_name=enclosing_class,
                is_test=True,
            ))

            # CONTAINS edge: parent -> this test
            container = (
                self._qualify(
                    enclosing_func, file_path, enclosing_class,
                )
                if enclosing_func
                else file_path
            )
            edges.append(EdgeInfo(
                kind="CONTAINS",
                source=container,
                target=qualified,
                file_path=file_path,
                line=child.start_point[0] + 1,
            ))

            # Recurse into the call's children (the arrow function body)
            self._extract_from_tree(
                child, source, language, file_path, nodes, edges,
                enclosing_class=enclosing_class,
                enclosing_func=synthetic_name,
                import_map=import_map, defined_names=defined_names,
                _depth=_depth + 1,
            )
            return True

        if call_name:
            # Module-scope calls (no enclosing function) are attributed to
            # the File node. Matches the existing convention for CONTAINS
            # edges and _extract_value_references. Without this fallback,
            # any function called only from top-level script glue, CLI
            # entrypoints, or Jupyter/Databricks notebook cells is flagged
            # as dead by find_dead_code.
            # For Verilog module instantiations, create CALLS edges from the
            # enclosing module.
            if enclosing_func:
                caller = self._qualify(
                    enclosing_func, file_path, enclosing_class,
                )
            elif language == "verilog" and enclosing_class:
                caller = self._qualify(
                    enclosing_class, file_path, None
                )
            else:
                caller = file_path

            # Preserve simple member-call receivers. Typed-receiver resolution
            # uses this evidence during parsing.
            call_extra: dict = {}
            if language in ("javascript", "typescript", "tsx"):
                member_call = self._get_js_member_call_name(child)
                if member_call:
                    call_extra["member_call"] = member_call
            if (
                language in self._TYPED_CALL_LANGUAGES
                or language in ("cpp", "rust")
            ):
                receiver, method_name = self._get_member_call_receiver_method(
                    child, language,
                )
                if method_name:
                    call_name = method_name
                if receiver:
                    call_extra["receiver"] = receiver

            # When a receiver is present, skip scope-based resolution: the method
            # lives on the receiver's type, not in the current file's scope.
            receiver_name = call_extra.get("receiver")
            if receiver_name in ("self", "cls", "this") and enclosing_class:
                target = (
                    call_name
                    if language == "cpp"
                    else self._qualify(call_name, file_path, enclosing_class)
                )
            elif (
                language == "rust"
                and call_name.startswith("Self::")
                and enclosing_class
            ):
                target = self._qualify(
                    call_name.rsplit("::", 1)[-1], file_path, enclosing_class,
                )
            elif receiver_name:
                target = call_name
            else:
                target = self._resolve_call_target(
                    call_name, file_path, language,
                    import_map or {}, defined_names or set(),
                )
            edges.append(EdgeInfo(
                kind="CALLS",
                source=caller,
                target=target,
                file_path=file_path,
                line=child.start_point[0] + 1,
                extra=call_extra,
            ))

        return False

    @staticmethod
    def _get_js_member_call_name(node) -> Optional[str]:
        """Return a static JS/TS member-call expression, if present.

        ``_get_call_name`` intentionally reduces ``app.handle()`` to
        ``handle`` for general method-call handling. Retain ``app.handle`` as
        supplemental evidence so the same-file resolver can link it to a
        member-assigned definition without changing unresolved external calls.
        Computed and multiline expressions are intentionally excluded.
        """
        callee = node.child_by_field_name("function")
        if callee is None and node.children:
            callee = node.children[0]
        if callee is None or callee.type != "member_expression":
            return None
        return CodeParser._get_js_static_member_path(callee)

    def _get_member_call_receiver_method(
        self,
        node,
        language: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """Return a simple receiver name and method for a member call.

        ``self.field.save()`` and ``this.field.save()`` use ``field`` as the
        receiver so class-field annotations can resolve them. More complex
        receiver expressions are deliberately left unresolved.
        """
        if language == "rust" and node.type == "call_expression":
            callee = node.child_by_field_name("function")
            while callee is not None and callee.type == "generic_function":
                callee = callee.child_by_field_name("function")
            if callee is None or callee.type != "field_expression":
                return None, None
            receiver = callee.child_by_field_name("value")
            method = callee.child_by_field_name("field")
            if receiver is None or method is None:
                return None, None
            return (
                receiver.text.decode("utf-8", errors="replace"),
                method.text.decode("utf-8", errors="replace"),
            )

        if language == "cpp" and node.type == "call_expression":
            callee = node.child_by_field_name("function")
            if callee is None or callee.type != "field_expression":
                return None, None
            receiver = callee.child_by_field_name("argument")
            method = callee.child_by_field_name("field")
            if receiver is None or method is None:
                return None, None
            return (
                receiver.text.decode("utf-8", errors="replace"),
                method.text.decode("utf-8", errors="replace"),
            )

        callee = node.child_by_field_name("function")
        if callee is None and node.children:
            callee = node.children[0]
        if callee is None:
            return None, None

        if callee.type not in ("attribute", "member_expression"):
            return None, None
        object_node = callee.child_by_field_name("object")
        property_node = (
            callee.child_by_field_name("attribute")
            or callee.child_by_field_name("property")
        )
        if object_node is None or property_node is None:
            return None, None

        method = property_node.text.decode("utf-8", errors="replace")
        if object_node.type in ("identifier", "simple_identifier", "self", "this"):
            return (
                object_node.text.decode("utf-8", errors="replace"),
                method,
            )

        if object_node.type in ("attribute", "member_expression"):
            root = object_node.child_by_field_name("object")
            field_node = (
                object_node.child_by_field_name("attribute")
                or object_node.child_by_field_name("property")
            )
            if (
                root is not None
                and field_node is not None
                and root.type in ("identifier", "self", "this")
                and root.text in (b"self", b"this")
            ):
                return (
                    field_node.text.decode("utf-8", errors="replace"),
                    method,
                )

        return None, method


    def _extract_jsx_component_call(
        self,
        child,
        language: str,
        file_path: str,
        edges: list[EdgeInfo],
        enclosing_class: Optional[str],
        enclosing_func: Optional[str],
        import_map: Optional[dict[str, str]],
        defined_names: Optional[set[str]],
    ) -> None:
        """Emit a synthetic CALLS edge for JSX component usage.

        React-style component invocations use JSX rather than ``call_expression``.
        Treat uppercase component tags such as ``<MarkdownMsg />`` as call-like
        edges so caller/impact queries can cross the JSX boundary. Intrinsic DOM
        tags (``<div>``) are ignored.

        Module-scope JSX (e.g. a top-level ``<App />`` render call) attributes
        to the File node.
        """
        target = self._resolve_jsx_component_target(
            child, language, file_path, import_map or {}, defined_names or set(),
        )
        if not target:
            return

        caller = (
            self._qualify(enclosing_func, file_path, enclosing_class)
            if enclosing_func
            else file_path
        )
        edges.append(EdgeInfo(
            kind="CALLS",
            source=caller,
            target=target,
            file_path=file_path,
            line=child.start_point[0] + 1,
        ))

    def _resolve_jsx_component_target(
        self,
        node,
        language: str,
        file_path: str,
        import_map: dict[str, str],
        defined_names: set[str],
    ) -> Optional[str]:
        """Resolve a JSX component element to a call target."""
        component_ref = self._get_jsx_component_reference(node)
        if component_ref is None:
            return None

        base_name, component_name = component_ref
        if base_name is None:
            return self._resolve_call_target(
                component_name, file_path, language, import_map, defined_names,
            )

        if base_name in import_map:
            resolved = self._resolve_imported_symbol(
                component_name, import_map[base_name], file_path, language,
            )
            if resolved:
                return resolved

        return component_name

    # ------------------------------------------------------------------
    # Value-reference extraction (function-as-value patterns)
    # ------------------------------------------------------------------

    # AST node types that represent object literal key-value pairs.
    _PAIR_TYPES = frozenset({"pair"})

    # AST node types for array/list containers.
    _ARRAY_TYPES = frozenset({"array", "list"})

    # AST node types for call argument containers. JS/TS uses ``arguments``;
    # Python uses ``argument_list``. Both share the same identifier-child shape
    # for bare-identifier callbacks like ``executor.submit(my_handler)``.
    _ARGUMENTS_TYPES = frozenset({"arguments", "argument_list"})

    # Names that are almost certainly not function references (constants,
    # common primitives).  All-uppercase identifiers and very short names
    # are excluded by a length/casing heuristic in the method itself.
    _VALUE_REF_SKIP_NAMES = frozenset({
        "true", "false", "null", "undefined", "None", "True", "False",
        "self", "this", "cls", "super",
    })

    def _extract_ts_type_reference(
        self,
        child,
        language: str,
        file_path: str,
        edges: list[EdgeInfo],
        enclosing_class: Optional[str],
        enclosing_func: Optional[str],
        import_map: Optional[dict[str, str]],
        defined_names: Optional[set[str]],
    ) -> None:
        """Emit a ``REFERENCES`` edge for a type used in a TS type position.

        ``function summarize(items: Finding[])`` is a real dependency on
        ``Finding``, but a type annotation is not call syntax, so neither
        _extract_calls nor _extract_value_references sees it and callers_of on
        an interface stays empty.

        ``REFERENCES`` (0.6 in IMPACT_EDGE_WEIGHTS) rather than ``CALLS`` (1.0):
        a type use is a weaker signal than an invocation, and folding the two
        together would let type churn outrank call churn in impact ranking.
        """
        parent = child.parent
        if parent is not None:
            # The declaration's own name is a definition, not a use. Compare by
            # byte span: child_by_field_name returns a fresh wrapper object, so
            # identity/equality checks against *child* are unreliable.
            if parent.type in _TS_TYPE_DECLARATIONS:
                name_node = parent.child_by_field_name("name")
                if (
                    name_node is not None
                    and name_node.start_byte == child.start_byte
                    and name_node.end_byte == child.end_byte
                ):
                    return
            # extends/implements are already covered by INHERITS edges. Generic
            # bases add a ``generic_type`` wrapper, so walk up to the clause.
            # Do not suppress a separate imported type used as a type argument:
            # ``extends Base<Dependency>`` inherits Base but references Dependency.
            ancestor = parent
            inside_type_arguments = False
            while ancestor is not None:
                if ancestor.type == "type_arguments":
                    inside_type_arguments = True
                if ancestor.type in _TS_HERITAGE_CLAUSES:
                    if not inside_type_arguments:
                        return
                    break
                if ancestor.type in _TS_TYPE_DECLARATIONS:
                    break
                ancestor = ancestor.parent

        # Attribute to the enclosing function, else the enclosing type, else the
        # file — so `interface Wrapper { nested: Verdict }` names Wrapper as the
        # dependent rather than collapsing to the whole module.
        if enclosing_func:
            caller = self._qualify(enclosing_func, file_path, enclosing_class)
        elif enclosing_class:
            caller = self._qualify(enclosing_class, file_path, None)
        else:
            caller = file_path

        self._emit_reference_if_known(
            child.text.decode("utf-8", errors="replace"),
            language, file_path, caller, edges,
            import_map or {}, defined_names or set(),
            line=child.start_point[0] + 1,
        )

    def _extract_value_references(
        self,
        child,
        node_type: str,
        source: bytes,
        language: str,
        file_path: str,
        edges: list[EdgeInfo],
        enclosing_class: Optional[str],
        enclosing_func: Optional[str],
        import_map: Optional[dict[str, str]],
        defined_names: Optional[set[str]],
    ) -> None:
        """Emit ``REFERENCES`` edges for function-as-value patterns.

        Detects identifiers in value positions that likely refer to
        functions — object literal values, map property assignments,
        array elements, and callback arguments.  This reduces false
        positives in dead-code detection for dispatch-map patterns
        like ``Record<string, Handler>``.

        Only emits edges when the identifier matches a locally defined
        name or an imported symbol, avoiding noise from arbitrary
        variable references.
        """
        imap = import_map or {}
        dnames = defined_names or set()

        # Use enclosing function as source, or the file path for module-scope code.
        if enclosing_func:
            caller = self._qualify(enclosing_func, file_path, enclosing_class)
        else:
            caller = file_path

        # --- JS/TS/Python: object literal pair values  { key: fnRef } ---
        if node_type in self._PAIR_TYPES:
            self._ref_from_pair(child, source, language, file_path, caller, edges, imap, dnames)
            return

        # --- JS/TS: shorthand property identifiers  { fnRef } ---
        if (
            node_type == "shorthand_property_identifier"
            and language in ("javascript", "typescript", "tsx")
        ):
            name = child.text.decode("utf-8", errors="replace")
            self._emit_reference_if_known(
                name, language, file_path, caller, edges, imap, dnames,
                line=child.start_point[0] + 1,
            )
            return

        # --- JS/TS/Python: assignment with member/subscript LHS ---
        if node_type in ("assignment_expression", "augmented_assignment", "assignment"):
            self._ref_from_assignment(
                child, source, language, file_path, caller, edges, imap, dnames,
            )
            return

        # --- JS/TS/Python: array / list elements ---
        if node_type in self._ARRAY_TYPES:
            self._ref_from_array(child, source, language, file_path, caller, edges, imap, dnames)
            return

        # --- Callback arguments (identifier args inside call_expression) ---
        if node_type in self._ARGUMENTS_TYPES:
            self._ref_from_arguments(
                child, source, language, file_path, caller, edges, imap, dnames,
            )

    def _emit_reference_if_known(
        self,
        name: str,
        language: str,
        file_path: str,
        caller: str,
        edges: list[EdgeInfo],
        import_map: dict[str, str],
        defined_names: set[str],
        line: int = 0,
    ) -> None:
        """Emit a ``REFERENCES`` edge if *name* is a known function/import."""
        if not name or name in self._VALUE_REF_SKIP_NAMES:
            return
        # Skip all-uppercase names (likely constants) and single-char names.
        if name.isupper() or len(name) <= 1:
            return
        # Must be a known local definition or import to be worth tracking.
        if name not in defined_names and name not in import_map:
            return

        target = self._resolve_call_target(
            name, file_path, language, import_map, defined_names,
        )
        edges.append(EdgeInfo(
            kind="REFERENCES",
            source=caller,
            target=target,
            file_path=file_path,
            line=line,
        ))

    def _ref_from_pair(
        self,
        pair_node,
        source: bytes,
        language: str,
        file_path: str,
        caller: str,
        edges: list[EdgeInfo],
        import_map: dict[str, str],
        defined_names: set[str],
    ) -> None:
        """Extract a REFERENCES edge from an object/dict literal pair value."""
        # pair children: key, ":", value
        children = pair_node.children
        # Find the value — it's the last meaningful child.
        value_node = None
        for ch in reversed(children):
            if ch.type not in (":", ",", "comment"):
                value_node = ch
                break
        if value_node is None:
            return
        if value_node.type == "identifier":
            name = value_node.text.decode("utf-8", errors="replace")
            self._emit_reference_if_known(
                name, language, file_path, caller, edges,
                import_map, defined_names,
                line=value_node.start_point[0] + 1,
            )

    def _ref_from_assignment(
        self,
        assign_node,
        source: bytes,
        language: str,
        file_path: str,
        caller: str,
        edges: list[EdgeInfo],
        import_map: dict[str, str],
        defined_names: set[str],
    ) -> None:
        """Extract REFERENCES from ``obj.key = fnRef`` or ``obj['key'] = fnRef``."""
        children = assign_node.children
        if len(children) < 3:
            return
        lhs = children[0]
        # LHS must be a member_expression or subscript_expression (map assignment).
        if lhs.type not in (
            "member_expression", "subscript_expression",
            "attribute", "subscript",
        ):
            return
        # RHS is the last non-punctuation child.
        rhs = None
        for ch in reversed(children):
            if ch.type not in ("=", ":", ",", "comment", "type_annotation"):
                rhs = ch
                break
        if rhs is None or rhs.type != "identifier":
            return
        name = rhs.text.decode("utf-8", errors="replace")
        self._emit_reference_if_known(
            name, language, file_path, caller, edges,
            import_map, defined_names,
            line=rhs.start_point[0] + 1,
        )

    def _ref_from_array(
        self,
        array_node,
        source: bytes,
        language: str,
        file_path: str,
        caller: str,
        edges: list[EdgeInfo],
        import_map: dict[str, str],
        defined_names: set[str],
    ) -> None:
        """Extract REFERENCES from array/list elements that are identifiers."""
        for ch in array_node.children:
            if ch.type == "identifier":
                name = ch.text.decode("utf-8", errors="replace")
                self._emit_reference_if_known(
                    name, language, file_path, caller, edges,
                    import_map, defined_names,
                    line=ch.start_point[0] + 1,
                )

    def _ref_from_arguments(
        self,
        args_node,
        source: bytes,
        language: str,
        file_path: str,
        caller: str,
        edges: list[EdgeInfo],
        import_map: dict[str, str],
        defined_names: set[str],
    ) -> None:
        """Extract REFERENCES from identifier arguments (callbacks)."""
        for ch in args_node.children:
            if ch.type == "identifier":
                name = ch.text.decode("utf-8", errors="replace")
                self._emit_reference_if_known(
                    name, language, file_path, caller, edges,
                    import_map, defined_names,
                    line=ch.start_point[0] + 1,
                )


    def _rust_path_segments(self, node) -> list[str]:
        """Return semantic Rust path segments while discarding type arguments."""
        if node is None:
            return []
        if node.type in (
            "identifier", "type_identifier", "crate", "self", "super",
        ):
            return [node.text.decode("utf-8", errors="replace")]
        if node.type in (
            "scoped_identifier", "scoped_type_identifier",
        ):
            path = node.child_by_field_name("path")
            name = node.child_by_field_name("name")
            return self._rust_path_segments(path) + self._rust_path_segments(name)
        if node.type == "generic_type":
            return self._rust_path_segments(node.child_by_field_name("type"))
        if node.type == "generic_function":
            return self._rust_path_segments(node.child_by_field_name("function"))
        return []

    def _parse_rust_use_node(
        self, node, prefix: tuple[str, ...] = (),
    ) -> list[tuple[str, str]]:
        """Flatten nested Rust use trees into local-name/original-path pairs."""
        if node.type == "use_declaration":
            argument = node.child_by_field_name("argument")
            return self._parse_rust_use_node(argument, prefix) if argument else []

        if node.type in ("identifier", "type_identifier"):
            name = node.text.decode("utf-8", errors="replace")
            full = (*prefix, name)
            return [(name, "::".join(full))]

        if node.type == "self":
            if not prefix:
                return []
            return [(prefix[-1], "::".join(prefix))]

        if node.type in ("scoped_identifier", "scoped_type_identifier"):
            segments = tuple(self._rust_path_segments(node))
            if not segments:
                return []
            full = (*prefix, *segments)
            return [(segments[-1], "::".join(full))]

        if node.type == "use_as_clause":
            path = node.child_by_field_name("path")
            alias = node.child_by_field_name("alias")
            segments = tuple(self._rust_path_segments(path))
            if not segments or alias is None:
                return []
            local_name = alias.text.decode("utf-8", errors="replace")
            return [(local_name, "::".join((*prefix, *segments)))]

        if node.type == "scoped_use_list":
            path = node.child_by_field_name("path")
            use_list = node.child_by_field_name("list")
            path_segments = tuple(self._rust_path_segments(path))
            if use_list is None:
                return []
            return self._parse_rust_use_node(
                use_list, (*prefix, *path_segments),
            )

        if node.type == "use_list":
            results: list[tuple[str, str]] = []
            for child in node.children:
                if child.is_named:
                    results.extend(self._parse_rust_use_node(child, prefix))
            return results

        if node.type == "use_wildcard":
            path = node.child_by_field_name("path")
            segments = tuple(self._rust_path_segments(path))
            full = (*prefix, *segments)
            return [("*", "::".join(full))] if full else []

        return []

    def _resolve_rust_type_target(
        self,
        segments: list[str],
        file_path: str,
        import_map: dict[str, str],
        defined_names: set[str],
    ) -> str:
        """Resolve a Rust type path only when file evidence is available."""
        if not segments:
            return ""
        local_name = segments[-1]
        if len(segments) == 1 and local_name in defined_names:
            return self._qualify(local_name, file_path, None)

        first = segments[0]
        if first in import_map:
            imported = import_map[first].split("::") + segments[1:]
            original_name = imported[-1]
            resolved = self._resolve_module_to_file(
                "::".join(imported), file_path, "rust",
            )
            if resolved:
                return self._qualify(original_name, resolved, None)

        resolved = self._resolve_module_to_file(
            "::".join(segments), file_path, "rust",
        )
        if resolved:
            return self._qualify(local_name, resolved, None)
        return "::".join(segments)

    def _extract_rust_impl(
        self,
        impl_node,
        source: bytes,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        import_map: dict[str, str],
        defined_names: set[str],
        depth: int,
    ) -> None:
        """Use impl blocks as method scopes without emitting duplicate types."""
        type_node = impl_node.child_by_field_name("type")
        target_segments = self._rust_path_segments(type_node)
        if not target_segments:
            return
        target_name = target_segments[-1]
        trait_node = impl_node.child_by_field_name("trait")
        if trait_node is not None:
            trait_segments = self._rust_path_segments(trait_node)
            trait_target = self._resolve_rust_type_target(
                trait_segments, file_path, import_map, defined_names,
            )
            if trait_target:
                edges.append(EdgeInfo(
                    kind="IMPLEMENTS",
                    source=self._qualify(target_name, file_path, None),
                    target=trait_target,
                    file_path=file_path,
                    line=impl_node.start_point[0] + 1,
                ))

        self._extract_from_tree(
            impl_node,
            source,
            "rust",
            file_path,
            nodes,
            edges,
            enclosing_class=target_name,
            import_map=import_map,
            defined_names=defined_names,
            _depth=depth + 1,
        )

    def _extract_verilog_constructs(
        self,
        child,
        node_type: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        enclosing_class: Optional[str],
        enclosing_func: Optional[str],
    ) -> bool:
        """Index module-level RTL declarations without inventing local globals.

        Signal-like declarations use Function nodes for backward-compatible
        storage, but carry ``extra["verilog_kind"]`` so function-oriented
        analyses can exclude them. Function/task-local declarations are
        intentionally consumed without emission because the graph has no
        variable-scope identity model.
        """

        def decode(node) -> str:
            return node.text.decode("utf-8", errors="replace")

        def find_simple_identifier(node) -> Optional[str]:
            if node.type == "simple_identifier":
                return decode(node)
            for sub in node.children:
                found = find_simple_identifier(sub)
                if found:
                    return found
            return None

        def emit(
            name: Optional[str],
            source_node,
            kind: str,
            modifiers: Optional[str] = None,
            return_type: Optional[str] = None,
            default: Optional[str] = None,
        ) -> None:
            if not name:
                return
            if any(
                node.name == name
                and node.parent_name == enclosing_class
                and node.extra.get("verilog_kind") == kind
                for node in nodes
            ):
                return
            extra: dict = {"verilog_kind": kind}
            if default is not None:
                extra["default"] = default
            qualified = self._qualify(name, file_path, enclosing_class)
            nodes.append(NodeInfo(
                kind="Function",
                name=name,
                file_path=file_path,
                line_start=source_node.start_point[0] + 1,
                line_end=source_node.end_point[0] + 1,
                language="verilog",
                parent_name=enclosing_class,
                return_type=return_type,
                modifiers=modifiers,
                extra=extra,
            ))
            container = (
                self._qualify(enclosing_class, file_path, None)
                if enclosing_class
                else file_path
            )
            edges.append(EdgeInfo(
                kind="CONTAINS",
                source=container,
                target=qualified,
                file_path=file_path,
                line=source_node.start_point[0] + 1,
            ))

        local_declarations = {
            "data_declaration",
            "input_declaration",
            "output_declaration",
            "inout_declaration",
            "net_declaration",
            "parameter_declaration",
            "local_parameter_declaration",
            "type_declaration",
        }
        if enclosing_func is not None and node_type in local_declarations:
            return True

        if node_type == "list_of_port_declarations":
            last_direction: Optional[str] = None
            last_type: Optional[str] = None
            for port in child.children:
                if port.type != "ansi_port_declaration":
                    continue
                direction = last_direction
                data_type = last_type
                name = None
                for sub in port.children:
                    if sub.type in (
                        "variable_port_header",
                        "net_port_header",
                        "net_port_header1",
                        "interface_port_header",
                    ):
                        for header_part in sub.children:
                            if header_part.type == "port_direction":
                                direction = decode(header_part).strip() or direction
                            elif header_part.type in (
                                "data_type",
                                "net_port_type1",
                                "variable_port_type",
                                "data_type_or_implicit1",
                            ):
                                data_type = decode(header_part)
                    elif sub.type == "port_identifier":
                        name = find_simple_identifier(sub)
                if name:
                    last_direction = direction
                    last_type = data_type
                    emit(name, port, "port", direction, data_type)
            return True

        if node_type in (
            "input_declaration", "output_declaration", "inout_declaration",
        ):
            direction = node_type.split("_", 1)[0]
            data_type = None
            for sub in child.children:
                if sub.type in ("data_type", "data_type_or_implicit1"):
                    data_type = decode(sub)
            for sub in child.children:
                if sub.type not in (
                    "list_of_port_identifiers",
                    "list_of_variable_identifiers",
                    "list_of_variable_port_identifiers",
                ):
                    continue
                for identifier in sub.children:
                    if identifier.type == "port_identifier":
                        emit(
                            find_simple_identifier(identifier),
                            identifier,
                            "port",
                            direction,
                            data_type,
                        )
                    elif identifier.type == "simple_identifier":
                        emit(
                            decode(identifier),
                            identifier,
                            "port",
                            direction,
                            data_type,
                        )
            return True

        if node_type in (
            "parameter_declaration", "local_parameter_declaration",
        ):
            kind = (
                "localparam"
                if node_type == "local_parameter_declaration"
                else "parameter"
            )
            data_type = None
            for sub in child.children:
                if sub.type in ("data_type_or_implicit1", "data_type"):
                    data_type = decode(sub)
                elif sub.type == "list_of_param_assignments":
                    for assignment in sub.children:
                        if assignment.type != "param_assignment":
                            continue
                        name = None
                        default = None
                        for part in assignment.children:
                            if part.type in (
                                "parameter_identifier", "simple_identifier",
                            ):
                                name = find_simple_identifier(part)
                            elif part.type == "constant_param_expression":
                                default = decode(part)
                        emit(
                            name,
                            assignment,
                            kind,
                            return_type=data_type,
                            default=default,
                        )
            return True

        if node_type == "net_declaration":
            keyword = None
            for sub in child.children:
                if sub.type == "net_type":
                    keyword = decode(sub).strip()
            for sub in child.children:
                if sub.type != "list_of_net_decl_assignments":
                    continue
                for assignment in sub.children:
                    if assignment.type == "net_decl_assignment":
                        emit(
                            find_simple_identifier(assignment),
                            assignment,
                            "net",
                            keyword,
                            keyword,
                        )
            return True

        if node_type == "data_declaration":
            if any(
                sub.type in ("package_import_declaration", "type_declaration")
                for sub in child.children
            ):
                return False
            data_type = None
            for sub in child.children:
                if sub.type == "data_type_or_implicit1":
                    data_type = decode(sub)
            keyword = data_type.split()[0] if data_type else None
            for sub in child.children:
                if sub.type != "list_of_variable_decl_assignments":
                    continue
                for assignment in sub.children:
                    if assignment.type == "variable_decl_assignment":
                        emit(
                            find_simple_identifier(assignment),
                            assignment,
                            "net",
                            keyword,
                            data_type,
                        )
            return True

        if node_type == "type_declaration":
            name = None
            data_type = None
            for sub in child.children:
                if sub.type == "simple_identifier":
                    name = decode(sub)
                elif sub.type == "data_type":
                    data_type = decode(sub)
            emit(name, child, "typedef", return_type=data_type)
            return True

        if node_type == "modport_declaration":
            for item in child.children:
                if item.type != "modport_item":
                    continue
                name = next(
                    (
                        find_simple_identifier(sub)
                        for sub in item.children
                        if sub.type == "modport_identifier"
                    ),
                    None,
                )
                emit(name, item, "modport")
            return True

        if node_type == "named_port_connection":
            expression = next(
                (sub for sub in child.children if sub.type == "expression"),
                None,
            )
            if expression is None:
                return True
            roots: set[str] = set()

            def collect_roots(node) -> None:
                if node.type == "simple_identifier":
                    roots.add(decode(node))
                    return
                for sub in node.children:
                    if sub.type in (
                        "select1",
                        "select",
                        "bit_select",
                        "constant_range",
                        "constant_expression",
                    ):
                        continue
                    collect_roots(sub)

            collect_roots(expression)
            known_signals = {
                node.name
                for node in nodes
                if node.parent_name == enclosing_class
                and node.extra.get("verilog_kind") in {
                    "port", "net", "parameter", "localparam",
                }
            }
            source_name = (
                self._qualify(enclosing_class, file_path, None)
                if enclosing_class
                else file_path
            )
            for signal in sorted(roots & known_signals):
                edges.append(EdgeInfo(
                    kind="REFERENCES",
                    source=source_name,
                    target=self._qualify(signal, file_path, enclosing_class),
                    file_path=file_path,
                    line=child.start_point[0] + 1,
                ))
            return True

        if node_type in ("covergroup_declaration", "property_declaration"):
            identifier_type = (
                "covergroup_identifier"
                if node_type == "covergroup_declaration"
                else "property_identifier"
            )
            name = next(
                (
                    find_simple_identifier(sub)
                    for sub in child.children
                    if sub.type == identifier_type
                ),
                None,
            )
            emit(name, child, node_type.split("_", 1)[0])
            return True

        if node_type == "sequence_declaration":
            name = next(
                (
                    decode(sub)
                    for sub in child.children
                    if sub.type == "simple_identifier"
                ),
                None,
            )
            emit(name, child, "sequence")
            return True

        return False

    def _collect_file_scope(
        self, root, language: str, source: bytes,
    ) -> tuple[dict[str, str], set[str]]:
        """Pre-scan top-level AST to collect import mappings and defined names.

        Returns:
            (import_map, defined_names) where import_map maps imported names
            to their source module/path, and defined_names is the set of
            function/class names defined at file scope.
        """
        import_map: dict[str, str] = {}
        defined_names: set[str] = set()

        class_types = set(self._class_types.get(language, []))
        func_types = set(self._function_types.get(language, []))
        import_types = set(self._import_types.get(language, []))

        # Node types that wrap a class/function with decorators/annotations
        decorator_wrappers = {"decorated_definition", "decorator"}

        for child in root.children:
            node_type = child.type

            # Unwrap decorator wrappers to reach the inner definition
            target = child
            if node_type in decorator_wrappers:
                for inner in child.children:
                    if inner.type in func_types or inner.type in class_types:
                        target = inner
                        break
            elif (
                language in ("javascript", "typescript", "tsx")
                and node_type == "export_statement"
            ):
                for inner in child.children:
                    if inner.type in func_types or inner.type in class_types:
                        target = inner
                        break

            target_type = target.type

            # Collect defined function/class names
            if target_type in func_types or target_type in class_types:
                name = self._get_name(target, language,
                                      "class" if target_type in class_types else "function")
                if name:
                    defined_names.add(name)
                    continue

            if (
                language in ("javascript", "typescript", "tsx")
                and node_type == "export_statement"
            ):
                self._collect_js_exported_local_names(child, defined_names)

            # Collect import mappings: imported_name → module_path
            if node_type in import_types:
                self._collect_import_names(child, language, source, import_map)

            if (
                language in ("javascript", "typescript", "tsx")
                and node_type in ("lexical_declaration", "variable_declaration")
            ):
                self._collect_js_require_names(child, import_map)

        return import_map, defined_names


    def _expand_python_star_imports(
        self,
        root,
        file_path: str,
        import_map: dict[str, str],
        resolving: frozenset[str] = frozenset(),
    ) -> None:
        """Add public names from repository-local Python star imports."""
        for child in root.children:
            if child.type != "import_from_statement":
                continue
            if not any(part.type == "wildcard_import" for part in child.children):
                continue
            module_node = child.child_by_field_name("module_name")
            if module_node is None:
                continue
            module = module_node.text.decode("utf-8", errors="replace")
            resolved = self._resolve_python_module_in_repo(module, file_path)
            if resolved is None or resolved in resolving:
                continue
            for name, origin in self._get_python_star_exports(
                resolved, resolving,
            ).items():
                import_map.setdefault(name, origin)

    def _get_python_star_exports(
        self,
        module_file: str,
        resolving: frozenset[str] = frozenset(),
    ) -> dict[str, str]:
        """Return exported names mapped to their repository-local origin files."""
        try:
            module_path = Path(module_file).resolve()
            file_stat = module_path.stat()
        except (OSError, ValueError):
            return {}
        resolved_module = normalize_file_path(module_path)
        if resolved_module in resolving:
            return {}

        cache_key = (resolved_module, file_stat.st_mtime_ns, file_stat.st_size)
        with _PYTHON_STAR_EXPORT_CACHE_LOCK:
            cached = _PYTHON_STAR_EXPORT_CACHE.get(cache_key)
            if cached is not None:
                return dict(cached)

            exports = self._read_python_star_exports(
                module_path, resolving,
            )
            stale_keys = [
                key for key in _PYTHON_STAR_EXPORT_CACHE
                if key[0] == resolved_module and key != cache_key
            ]
            for stale_key in stale_keys:
                _PYTHON_STAR_EXPORT_CACHE.pop(stale_key, None)
            if len(_PYTHON_STAR_EXPORT_CACHE) >= _PYTHON_STAR_CACHE_MAX:
                oldest_keys = list(_PYTHON_STAR_EXPORT_CACHE)[: _PYTHON_STAR_CACHE_MAX // 2]
                for oldest_key in oldest_keys:
                    _PYTHON_STAR_EXPORT_CACHE.pop(oldest_key, None)
            _PYTHON_STAR_EXPORT_CACHE[cache_key] = dict(exports)
            return exports

    def _read_python_star_exports(
        self,
        module_path: Path,
        resolving: frozenset[str],
    ) -> dict[str, str]:
        """Read and parse one Python module for star-export discovery."""
        resolved_module = normalize_file_path(module_path)
        try:
            source = module_path.read_bytes()
        except (OSError, PermissionError):
            return {}
        try:
            parser = self._get_parser("python")
            if not parser:
                return {}
            tree = parser.parse(source)  # type: ignore[union-attr]
            import_map, defined_names = self._collect_file_scope(
                tree.root_node, "python", source,
            )

            origins: dict[str, str] = {}
            next_resolving = resolving | {resolved_module}
            self._expand_python_star_imports(
                tree.root_node, resolved_module, origins, next_resolving,
            )
            for name, module in import_map.items():
                origin = self._resolve_python_module_in_repo(module, resolved_module)
                if origin is not None:
                    origins[name] = origin
            for name in defined_names:
                origins[name] = resolved_module

            explicit_exports = self._extract_python_dunder_all(tree.root_node)
            if explicit_exports is not None:
                return {
                    name: origins.get(name, resolved_module)
                    for name in explicit_exports
                }
            return {
                name: origin
                for name, origin in origins.items()
                if not name.startswith("_")
            }
        except Exception as exc:
            logger.debug(
                "Skipping Python star exports for %s: %s",
                module_path,
                exc,
            )
            return {}

    @staticmethod
    def _extract_python_dunder_all(root) -> Optional[set[str]]:
        """Return literal string names from ``__all__``, or None if absent."""
        for child in root.children:
            if child.type != "assignment":
                continue
            left = child.child_by_field_name("left")
            if left is None or left.type != "identifier" or left.text != b"__all__":
                continue
            right = child.child_by_field_name("right")
            if right is None:
                return set()
            try:
                value = ast.literal_eval(right.text.decode("utf-8", errors="replace"))
            except (SyntaxError, ValueError):
                return set()
            if not isinstance(value, (list, tuple)):
                return set()
            return {name for name in value if isinstance(name, str)}
        return None

    def _python_repo_boundary(self, file_path: str) -> Path:
        """Return the filesystem boundary for safe Python import lookup."""
        caller_dir = Path(file_path).resolve().parent
        if self._repo_root is not None:
            return self._repo_root
        for candidate in (caller_dir, *caller_dir.parents):
            if (candidate / ".git").exists() or (candidate / ".svn").exists():
                return candidate
        return caller_dir

    @staticmethod
    def _path_is_within(path: Path, boundary: Path) -> bool:
        """Return whether *path* is *boundary* or one of its descendants."""
        try:
            path.relative_to(boundary)
        except ValueError:
            return False
        return True

    def _resolve_python_module_in_repo(
        self, module: str, file_path: str,
    ) -> Optional[str]:
        """Resolve a Python module without traversing above the repository."""
        caller_dir = Path(file_path).resolve().parent
        boundary = self._python_repo_boundary(file_path)
        leading_dots = len(module) - len(module.lstrip("."))
        module_name = module[leading_dots:]
        relative = Path(*module_name.split(".")) if module_name else Path()

        search_roots: list[Path] = []
        if leading_dots:
            base = caller_dir
            for _ in range(leading_dots - 1):
                if base == boundary:
                    return None
                base = base.parent
            search_roots.append(base)
        else:
            current = caller_dir
            while self._path_is_within(current, boundary):
                search_roots.append(current)
                if current == boundary:
                    break
                current = current.parent

        for root in search_roots:
            base = root / relative
            candidates = (
                base.with_suffix(".py") if module_name else base / "__init__.py",
                base / "__init__.py",
            )
            for candidate in candidates:
                try:
                    resolved = candidate.resolve()
                except (OSError, ValueError):
                    continue
                if not self._path_is_within(resolved, boundary):
                    continue
                if resolved.is_file():
                    return normalize_file_path(resolved)
        return None

    def _collect_js_exported_local_names(
        self, node, defined_names: set[str],
    ) -> None:
        """Collect locally exported JS/TS names from export statements."""
        for child in node.children:
            if child.type in ("lexical_declaration", "variable_declaration"):
                for sub in child.children:
                    if sub.type == "variable_declarator":
                        for part in sub.children:
                            if part.type == "identifier":
                                defined_names.add(
                                    part.text.decode("utf-8", errors="replace"),
                                )
                                break

    @staticmethod
    def _js_static_module_target(call_node) -> Optional[str]:
        """Return a literal module target from ``require``/``import``.

        Only direct calls with exactly one non-empty string (or a template
        literal without substitutions) are accepted. Expressions such as
        ``path.join(...)`` and interpolated templates are deliberately
        ignored because reducing them to a path prefix creates false edges.
        """
        function = call_node.child_by_field_name("function")
        if function is None:
            function = next(iter(call_node.named_children), None)
        if function is None:
            return None
        function_text = function.text.decode("utf-8", errors="replace")
        if function_text not in ("require", "import"):
            return None

        arguments = call_node.child_by_field_name("arguments")
        if arguments is None:
            arguments = next(
                (child for child in call_node.children if child.type == "arguments"),
                None,
            )
        if arguments is None or len(arguments.named_children) != 1:
            return None

        argument = arguments.named_children[0]
        raw = argument.text.decode("utf-8", errors="replace")
        if argument.type == "string":
            target = raw[1:-1] if len(raw) >= 2 else ""
            return target or None
        if argument.type == "template_string":
            if any(child.type == "template_substitution" for child in argument.children):
                return None
            target = raw[1:-1] if len(raw) >= 2 else ""
            return target or None
        return None

    def _extract_js_module_call(
        self,
        call_node,
        file_path: str,
        language: str,
        edges: list[EdgeInfo],
    ) -> None:
        """Emit one file-level IMPORTS_FROM edge for a static module call."""
        module = self._js_static_module_target(call_node)
        if not module:
            return
        target = self._resolve_module_to_file(module, file_path, language) or module
        if any(
            edge.kind == "IMPORTS_FROM"
            and edge.source == file_path
            and edge.target == target
            for edge in edges
        ):
            return
        edges.append(EdgeInfo(
            kind="IMPORTS_FROM",
            source=file_path,
            target=target,
            file_path=file_path,
            line=call_node.start_point[0] + 1,
        ))

    def _collect_js_require_names(
        self,
        declaration,
        import_map: dict[str, str],
    ) -> None:
        """Collect direct and shorthand-destructured CommonJS bindings."""
        for declarator in declaration.named_children:
            if declarator.type != "variable_declarator":
                continue
            value = declarator.child_by_field_name("value")
            if value is None or value.type != "call_expression":
                continue
            module = self._js_static_module_target(value)
            if not module:
                continue
            name = declarator.child_by_field_name("name")
            if name is None:
                continue
            if name.type == "identifier":
                import_map[name.text.decode("utf-8", errors="replace")] = module
                continue
            if name.type != "object_pattern":
                continue
            for child in name.named_children:
                if child.type == "shorthand_property_identifier_pattern":
                    local_name = child.text.decode("utf-8", errors="replace")
                    import_map[local_name] = module

    def _collect_import_names(
        self, node, language: str, source: bytes, import_map: dict[str, str],
    ) -> None:
        """Extract imported names and their source modules into import_map."""
        if language == "python":
            if node.type == "import_from_statement":
                # from X.Y import A, B → {A: X.Y, B: X.Y}
                module = None
                seen_import_keyword = False
                for child in node.children:
                    if child.type == "dotted_name" and not seen_import_keyword:
                        module = child.text.decode("utf-8", errors="replace")
                    elif child.type == "import":
                        seen_import_keyword = True
                    elif seen_import_keyword and module:
                        if child.type in ("identifier", "dotted_name"):
                            name = child.text.decode("utf-8", errors="replace")
                            import_map[name] = module
                        elif child.type == "aliased_import":
                            # from X import A as B → {B: X}
                            names = [
                                sub.text.decode("utf-8", errors="replace")
                                for sub in child.children
                                if sub.type in ("identifier", "dotted_name")
                            ]
                            # Last name is the alias (local name)
                            if names:
                                import_map[names[-1]] = module

        elif language in ("javascript", "typescript", "tsx"):
            # import { A, B } from './path' → {A: ./path, B: ./path}
            module = None
            for child in node.children:
                if child.type == "string":
                    module = child.text.decode("utf-8", errors="replace").strip("'\"")
            if module:
                for child in node.children:
                    if child.type == "import_clause":
                        self._collect_js_import_names(child, module, import_map)

        elif language == "rust":
            for local_name, original_path in self._parse_rust_use_node(node):
                if local_name != "*":
                    import_map[local_name] = original_path


    def _collect_js_import_names(
        self, clause_node, module: str, import_map: dict[str, str],
    ) -> None:
        """Walk JS/TS import_clause to extract named and default imports."""
        for child in clause_node.children:
            if child.type == "identifier":
                # Default import
                import_map[child.text.decode("utf-8", errors="replace")] = module
            elif child.type == "namespace_import":
                for sub in child.children:
                    if sub.type == "identifier":
                        import_map[sub.text.decode("utf-8", errors="replace")] = module
                        break
            elif child.type == "named_imports":
                for spec in child.children:
                    if spec.type == "import_specifier":
                        # Could be: name or name as alias
                        imported_node = spec.child_by_field_name("name")
                        alias_node = spec.child_by_field_name("alias")
                        names = [
                            s.text.decode("utf-8", errors="replace")
                            for s in spec.children
                            if s.type in ("identifier", "property_identifier")
                        ]
                        # Last identifier is the local name
                        if names:
                            local_name = names[-1]
                            import_map[local_name] = module
                            imported_name = (
                                imported_node.text.decode(
                                    "utf-8", errors="replace",
                                )
                                if imported_node is not None
                                else names[0]
                            )
                            if alias_node is not None and imported_name != local_name:
                                import_map[
                                    f"{_JS_IMPORT_ORIGINAL_PREFIX_KEY}{local_name}"
                                ] = imported_name

    @staticmethod
    def _js_imported_symbol_name(
        local_name: str,
        import_map: dict[str, str],
    ) -> str:
        """Return the exported name behind a local JS/TS import alias."""
        return import_map.get(
            f"{_JS_IMPORT_ORIGINAL_PREFIX_KEY}{local_name}",
            local_name,
        )

    def exclude_files(self, paths: set[str]) -> None:
        """Treat these files as absent when resolving imports.

        ``forget`` calls this before re-parsing the surviving referrers of a
        forgotten file so their imports resolve exactly as they would in a
        build where the forgotten files never existed: an import that would
        point at a forgotten file falls back to a bare module, and the calls
        it feeds stay bare too.
        """
        self._excluded_files = {normalize_file_path(Path(p).resolve()) for p in paths}
        # Drop resolutions cached before the exclusions were applied.
        self._module_file_cache.clear()

    def _resolve_module_to_file(
        self, module: str, file_path: str, language: str,
    ) -> Optional[str]:
        """Resolve a module/import path to an absolute file path.

        Uses self._module_file_cache to avoid repeated filesystem lookups.
        Files marked via :meth:`exclude_files` resolve to ``None`` so callers
        fall back to the bare module string, matching a build without them.
        """
        caller_dir = str(Path(file_path).parent)
        cache_key = f"{language}:{caller_dir}:{module}"
        if cache_key in self._module_file_cache:
            resolved = self._module_file_cache[cache_key]
        else:
            resolved = self._do_resolve_module(module, file_path, language)
            if resolved is not None:
                # Resolution walks the real filesystem, so on Windows the
                # raw result uses backslashes; identity must not (#774).
                resolved = normalize_file_path(resolved)
            if len(self._module_file_cache) >= self._MODULE_CACHE_MAX:
                self._module_file_cache.clear()
            self._module_file_cache[cache_key] = resolved
        if resolved is not None and resolved in self._excluded_files:
            return None
        return resolved

    def _do_resolve_module(
        self, module: str, file_path: str, language: str,
    ) -> Optional[str]:
        """Language-aware module-to-file resolution."""
        caller_dir = Path(file_path).parent

        if language == "bash":
            # ``source ./lib.sh`` or ``source lib.sh`` — resolve relative
            # to the caller's directory. See: #197
            try:
                target = (caller_dir / module).resolve()
                if target.is_file():
                    return str(target)
            except (OSError, ValueError):
                pass
            return None

        if language == "python":
            rel_path = module.replace(".", "/")
            candidates = [rel_path + ".py", rel_path + "/__init__.py"]
            # Walk up from caller's directory to find the module file
            current = caller_dir
            while True:
                for candidate in candidates:
                    target = current / candidate
                    if target.is_file():
                        return str(target.resolve())
                if current == current.parent:
                    break
                current = current.parent

        elif language in ("javascript", "typescript", "tsx"):
            if module.startswith("."):
                # Relative import — resolve from caller's directory
                base = caller_dir / module
                extensions = [".ts", ".tsx", ".js", ".jsx"]
                # Try exact path first (might already have extension)
                if base.is_file():
                    return str(base.resolve())
                # Try with extensions
                for ext in extensions:
                    target = base.with_suffix(ext)
                    if target.is_file():
                        return str(target.resolve())
                # Try index file in directory
                if base.is_dir():
                    for ext in extensions:
                        target = base / f"index{ext}"
                        if target.is_file():
                            return str(target.resolve())
            else:
                # Non-relative import — try tsconfig path alias resolution
                resolved = self._tsconfig_resolver.resolve_alias(module, file_path)
                if resolved:
                    return resolved

        elif language == "rust":
            return self._resolve_rust_module_file(module, file_path)

        return None

    @staticmethod
    def _rust_dependency_specs(manifest: dict[str, Any]) -> dict[str, Any]:
        """Collect Cargo dependency tables, including target-specific ones."""
        specs: dict[str, Any] = {}
        for section in ("dependencies", "dev-dependencies", "build-dependencies"):
            table = manifest.get(section)
            if isinstance(table, dict):
                specs.update(table)
        target_tables = manifest.get("target")
        if isinstance(target_tables, dict):
            for target in target_tables.values():
                if not isinstance(target, dict):
                    continue
                for section in (
                    "dependencies", "dev-dependencies", "build-dependencies",
                ):
                    table = target.get(section)
                    if isinstance(table, dict):
                        specs.update(table)
        return specs

    @staticmethod
    def _rust_crate_layout(crate_root: Path) -> Optional[tuple[Path, Path]]:
        """Return ``(source root, crate root module)`` for a local crate."""
        manifest = _load_cargo_manifest(crate_root / "Cargo.toml")
        if not isinstance(manifest.get("package"), dict):
            return None
        lib = manifest.get("lib")
        explicit_lib = lib.get("path") if isinstance(lib, dict) else None
        if isinstance(explicit_lib, str):
            root_file = crate_root / explicit_lib
            if root_file.is_file():
                return root_file.parent, root_file

        source_root = crate_root / "src"
        for name in ("lib.rs", "main.rs"):
            candidate = source_root / name
            if candidate.is_file():
                return source_root, candidate
        return None

    def _rust_project_context(
        self, file_path: str,
    ) -> Optional[tuple[Path, Path, Path, dict[str, Path], Path]]:
        """Discover a bounded Cargo crate/workspace once per source directory."""
        try:
            caller_dir = Path(file_path).resolve().parent
        except (OSError, RuntimeError, ValueError):
            return None
        if self._repo_root is not None and not _path_is_within(
            caller_dir, self._repo_root,
        ):
            return None
        key = str(caller_dir)
        if key in self._rust_project_cache:
            return self._rust_project_cache[key]

        manifests: list[tuple[Path, dict[str, Any]]] = []
        current = caller_dir
        for _ in range(64):
            manifest_path = current / "Cargo.toml"
            if manifest_path.is_file():
                manifests.append((manifest_path, _load_cargo_manifest(manifest_path)))
            if self._repo_root is not None and current == self._repo_root:
                break
            if current == current.parent:
                break
            current = current.parent

        crate_entry = next(
            (
                entry for entry in manifests
                if isinstance(entry[1].get("package"), dict)
            ),
            None,
        )
        if crate_entry is None:
            return None
        crate_manifest, crate_data = crate_entry
        crate_root = crate_manifest.parent
        workspace_entry = next(
            (
                entry for entry in manifests
                if isinstance(entry[1].get("workspace"), dict)
            ),
            None,
        )
        workspace_root = (
            workspace_entry[0].parent if workspace_entry else crate_root
        )
        boundary = self._repo_root or workspace_root
        try:
            boundary = boundary.resolve()
            crate_root = crate_root.resolve()
        except (OSError, RuntimeError, ValueError):
            return None
        if not _path_is_within(crate_root, boundary):
            return None

        layout = self._rust_crate_layout(crate_root)
        if layout is None:
            return None
        source_root, root_file = layout

        workspace_specs: dict[str, Any] = {}
        workspace_base = workspace_root
        if workspace_entry:
            workspace_table = workspace_entry[1].get("workspace")
            if isinstance(workspace_table, dict):
                raw_specs = workspace_table.get("dependencies")
                if isinstance(raw_specs, dict):
                    workspace_specs = raw_specs

        dependencies: dict[str, Path] = {}
        for alias, raw_spec in self._rust_dependency_specs(crate_data).items():
            if not isinstance(alias, str) or not isinstance(raw_spec, dict):
                continue
            spec = raw_spec
            base = crate_root
            if raw_spec.get("workspace") is True:
                inherited = workspace_specs.get(alias)
                if not isinstance(inherited, dict):
                    continue
                spec = inherited
                base = workspace_base
            raw_path = spec.get("path")
            if not isinstance(raw_path, str):
                continue
            try:
                dependency_root = (base / raw_path).resolve()
            except (OSError, RuntimeError, ValueError):
                continue
            if not _path_is_within(dependency_root, boundary):
                continue
            if self._rust_crate_layout(dependency_root) is None:
                continue
            dependencies[alias] = dependency_root
            dependencies[alias.replace("-", "_")] = dependency_root

        context = (crate_root, source_root, root_file, dependencies, boundary)
        self._rust_project_cache[key] = context
        return context

    @staticmethod
    def _rust_current_module_parts(file_path: Path, source_root: Path) -> list[str]:
        try:
            relative = file_path.resolve().relative_to(source_root.resolve())
        except (OSError, RuntimeError, ValueError):
            return []
        parts = list(relative.parts)
        if not parts:
            return []
        filename = parts.pop()
        if filename not in ("lib.rs", "main.rs", "mod.rs"):
            parts.append(Path(filename).stem)
        return parts

    @staticmethod
    def _rust_module_file_for_parts(
        source_root: Path, root_file: Path, parts: list[str],
    ) -> Optional[Path]:
        if not parts:
            return root_file
        relative = Path(*parts)
        flat = source_root / relative.with_suffix(".rs")
        nested = source_root / relative / "mod.rs"
        if flat.is_file():
            return flat
        if nested.is_file():
            return nested
        return None

    def _resolve_rust_module_file(
        self, module: str, file_path: str,
    ) -> Optional[str]:
        """Resolve crate/self/super and local path dependencies to source files."""
        context = self._rust_project_context(file_path)
        if context is None:
            return None
        _, source_root, root_file, dependencies, boundary = context
        segments = [segment for segment in module.split("::") if segment]
        if not segments:
            return None

        current_parts: list[str] = []
        current_file = root_file
        remaining = list(segments)
        first = remaining[0]
        if first == "crate":
            remaining.pop(0)
        elif first == "self":
            remaining.pop(0)
            current_parts = self._rust_current_module_parts(
                Path(file_path), source_root,
            )
            current_file = Path(file_path)
        elif first == "super":
            current_parts = self._rust_current_module_parts(
                Path(file_path), source_root,
            )
            while remaining and remaining[0] == "super":
                remaining.pop(0)
                if current_parts:
                    current_parts.pop()
            parent_file = self._rust_module_file_for_parts(
                source_root, root_file, current_parts,
            )
            if parent_file is None:
                return None
            current_file = parent_file
        elif first in dependencies:
            dependency_root = dependencies[first]
            remaining.pop(0)
            layout = self._rust_crate_layout(dependency_root)
            if layout is None:
                return None
            source_root, current_file = layout
            current_parts = []

        for index, segment in enumerate(remaining):
            candidate_parts = [*current_parts, segment]
            candidate = self._rust_module_file_for_parts(
                source_root, current_file if not current_parts else root_file,
                candidate_parts,
            )
            if candidate is not None:
                current_parts = candidate_parts
                current_file = candidate
                continue
            # The final segment can be an item exported by the current module.
            if index != len(remaining) - 1:
                return None
            break

        try:
            resolved = current_file.resolve()
        except (OSError, RuntimeError, ValueError):
            return None
        if not _path_is_within(resolved, boundary):
            return None
        return normalize_file_path(resolved)


    def _resolve_rust_scoped_call(
        self,
        call_name: str,
        file_path: str,
        import_map: dict[str, str],
        defined_names: set[str],
    ) -> Optional[str]:
        """Resolve associated/module Rust calls with alias provenance."""
        parts = [part for part in call_name.split("::") if part]
        if len(parts) < 2:
            return None
        method = parts[-1]
        prefix = parts[:-1]
        if prefix == ["Self"]:
            return None
        if len(prefix) == 1 and prefix[0] in defined_names:
            return f"{self._qualify(prefix[0], file_path, None)}.{method}"

        if prefix[0] in import_map:
            prefix = import_map[prefix[0]].split("::") + prefix[1:]

        resolved = self._resolve_module_to_file(
            "::".join(prefix), file_path, "rust",
        )
        if resolved is None:
            return None
        parent_resolved = None
        if len(prefix) > 1:
            parent_resolved = self._resolve_module_to_file(
                "::".join(prefix[:-1]), file_path, "rust",
            )
        if parent_resolved == resolved and prefix[-1] not in {
            "crate", "self", "super",
        }:
            return f"{self._qualify(prefix[-1], resolved, None)}.{method}"
        return self._qualify(method, resolved, None)

    def _resolve_call_target(
        self,
        call_name: str,
        file_path: str,
        language: str,
        import_map: dict[str, str],
        defined_names: set[str],
    ) -> str:
        """Resolve a bare call name to a qualified target, with fallback."""
        if language == "rust" and "::" in call_name:
            resolved_rust = self._resolve_rust_scoped_call(
                call_name, file_path, import_map, defined_names,
            )
            if resolved_rust:
                return resolved_rust
        if call_name in defined_names:
            if language == "cpp":
                return call_name
            return self._qualify(call_name, file_path, None)
        if call_name in import_map:
            resolved = self._resolve_imported_symbol(
                self._js_imported_symbol_name(call_name, import_map),
                import_map[call_name],
                file_path,
                language,
            )
            if resolved:
                return resolved
        return call_name

    def _resolve_imported_symbol(
        self,
        symbol_name: str,
        module: str,
        file_path: str,
        language: str,
    ) -> Optional[str]:
        """Resolve an imported symbol to its defining qualified name when possible."""
        module_path = Path(module)
        if language == "python" and module_path.is_absolute():
            try:
                candidate = module_path.resolve()
            except (OSError, ValueError):
                return None
            boundary = self._python_repo_boundary(file_path)
            if not self._path_is_within(candidate, boundary) or not candidate.is_file():
                return None
            resolved = normalize_file_path(candidate)
        else:
            resolved = self._resolve_module_to_file(module, file_path, language)
        if not resolved:
            return None

        export_target = self._resolve_exported_symbol(resolved, symbol_name)
        if export_target:
            return export_target
        return self._qualify(symbol_name, resolved, None)

    def _resolve_exported_symbol(
        self,
        module_file: str,
        symbol_name: str,
        seen: Optional[set[tuple[str, str]]] = None,
    ) -> Optional[str]:
        """Resolve a JS/TS symbol through common re-export/barrel patterns."""
        cache_key = f"{module_file}::{symbol_name}"
        if cache_key in self._export_symbol_cache:
            return self._export_symbol_cache[cache_key]

        key = (module_file, symbol_name)
        if seen is None:
            seen = set()
        if key in seen:
            return None
        seen.add(key)

        path = Path(module_file)
        language = self.detect_language(path)
        if language not in ("javascript", "typescript", "tsx"):
            return None

        try:
            source = path.read_bytes()
        except (OSError, PermissionError):
            return None

        parser = self._get_parser(language)
        if not parser:
            return None

        tree = parser.parse(source)

        # Direct local definition/export in the module file.
        import_map, defined_names = self._collect_file_scope(
            tree.root_node, language, source,
        )
        if symbol_name in defined_names:
            result = self._qualify(symbol_name, module_file, None)
            self._export_symbol_cache[cache_key] = result
            return result

        for child in tree.root_node.children:
            if child.type != "export_statement":
                continue

            export_clause = None
            target_module = None
            has_star_export = False

            for sub in child.children:
                if sub.type == "export_clause":
                    export_clause = sub
                elif sub.type == "string":
                    target_module = sub.text.decode("utf-8", errors="replace").strip("'\"")
                elif sub.type == "*":
                    has_star_export = True

            # Re-exported names: export { Foo as Bar } from './x'
            if export_clause is not None:
                for spec in export_clause.children:
                    if spec.type != "export_specifier":
                        continue
                    names = [
                        part.text.decode("utf-8", errors="replace")
                        for part in spec.children
                        if part.type in ("identifier", "property_identifier")
                    ]
                    if not names:
                        continue
                    exported_name = names[-1]
                    original_name = names[0]
                    if exported_name != symbol_name:
                        continue
                    if target_module:
                        resolved_module = self._resolve_module_to_file(
                            target_module, module_file, language,
                        )
                        if resolved_module:
                            result = self._resolve_exported_symbol(
                                resolved_module, original_name, seen,
                            ) or self._qualify(original_name, resolved_module, None)
                            self._export_symbol_cache[cache_key] = result
                            return result
                    result = self._qualify(original_name, module_file, None)
                    self._export_symbol_cache[cache_key] = result
                    return result

            # Star re-export: export * from './x'
            if has_star_export and target_module:
                resolved_module = self._resolve_module_to_file(
                    target_module, module_file, language,
                )
                if resolved_module:
                    result = self._resolve_exported_symbol(
                        resolved_module, symbol_name, seen,
                    )
                    if result:
                        self._export_symbol_cache[cache_key] = result
                        return result

        self._export_symbol_cache[cache_key] = None
        return None

    def _qualify(self, name: str, file_path: str, enclosing_class: Optional[str]) -> str:
        """Create a qualified name: file_path::ClassName.name or file_path::name.

        The path component is normalized to POSIX separators so identities
        are stable across operating systems (#774). ``name`` and
        ``enclosing_class`` are never touched.
        """
        file_path = normalize_file_path(file_path)
        if enclosing_class:
            return f"{file_path}::{enclosing_class}.{name}"
        return f"{file_path}::{name}"

    def _node_qualified(self, node: NodeInfo) -> str:
        """Return the parser identity for a node without changing display name."""
        return self._qualify(
            node.identity_name or node.name,
            node.file_path,
            node.parent_name,
        )

    # Leaf node types that typically carry a definition's name across grammars.
    # Used when descending from a configured ``name_field`` target to a clean
    # text leaf (config-driven custom languages only).
    _CUSTOM_NAME_LEAF_TYPES = (
        "word", "identifier", "name", "simple_identifier",
        "command_name", "key_brace", "type_identifier",
        "property_identifier", "constant",
    )
    #: Depth guard for custom name-field descent / descendant search.
    _MAX_CUSTOM_NAME_DEPTH = 4
    #: Cap on a resolved custom name before it is rejected as junk.
    _MAX_CUSTOM_NAME_LEN = 256

    def _custom_name_leaf(self, node, depth: int):
        """Return the first text-bearing leaf of a known name type within
        ``depth`` levels of ``node`` (preorder), or None."""
        if node.type in self._CUSTOM_NAME_LEAF_TYPES and node.child_count == 0:
            return node
        if depth <= 0:
            return None
        for child in node.children:
            found = self._custom_name_leaf(child, depth - 1)
            if found is not None:
                return found
        return None

    def _find_custom_descendant(self, node, type_name: str, depth: int):
        """Return the first descendant of ``node`` whose type == ``type_name``
        within ``depth`` levels (preorder), or None."""
        if depth <= 0:
            return None
        for child in node.children:
            if child.type == type_name:
                return child
            found = self._find_custom_descendant(child, type_name, depth - 1)
            if found is not None:
                return found
        return None

    def _clean_custom_name(self, text: str) -> Optional[str]:
        """Strip wrapping braces/quotes/whitespace; reject empty, multi-line,
        or oversized text so a bad target never becomes a garbage name."""
        cleaned = text.strip().strip("{}\"'").strip()
        if not cleaned or "\n" in cleaned or len(cleaned) > self._MAX_CUSTOM_NAME_LEN:
            return None
        return cleaned

    def _custom_leaf_name(self, node) -> Optional[str]:
        """Resolve a configured ``name_field`` target node to a clean name.

        Prefers a text-bearing leaf of a known name type; falls back to the
        target's own text (covers fieldless wrappers like Markdown ``inline``).
        """
        leaf = self._custom_name_leaf(node, self._MAX_CUSTOM_NAME_DEPTH)
        target = leaf if leaf is not None else node
        return self._clean_custom_name(
            target.text.decode("utf-8", errors="replace")
        )

    def _resolve_custom_name(self, node, language: str) -> Optional[str]:
        """Resolve a definition name for a config-driven custom language using
        the language's ordered ``name_field`` candidates.

        Two passes so grammar *fields* are always preferred over a broader
        *type* search: this avoids matching an unrelated same-typed node in a
        different field (e.g. LaTeX ``\\newcommand`` whose ``implementation``
        body contains a ``text`` node — the ``declaration`` field must win).
        Returns None when no candidate resolves (caller then applies the legacy
        ``name`` field fallback).
        """
        custom = self._custom_languages.get(language)
        candidates = custom.name_field if custom is not None else ()
        if not candidates:
            return None
        # Pass 1: field lookups (authoritative).
        for cand in candidates:
            target = node.child_by_field_name(cand)
            if target is not None:
                resolved = self._custom_leaf_name(target)
                if resolved:
                    return resolved
        # Pass 2: typed-descendant search (for fieldless shapes).
        for cand in candidates:
            target = self._find_custom_descendant(
                node, cand, self._MAX_CUSTOM_NAME_DEPTH
            )
            if target is not None:
                resolved = self._custom_leaf_name(target)
                if resolved:
                    return resolved
        return None

    def _get_name(self, node, language: str, kind: str) -> Optional[str]:
        """Extract the name from a class/function definition node."""
        if language == "cpp" and kind == "function":
            declarator = node.child_by_field_name("declarator")
            if node.type in ("declaration", "field_declaration"):
                if (
                    not self._cpp_declaration_has_callable_scope(node)
                    or not self._cpp_is_callable_declaration(declarator)
                ):
                    return None
                return self._cpp_callable_name(declarator)
            cpp_name = self._cpp_callable_name(declarator)
            if cpp_name:
                return cpp_name

        # For C/C++: function names are inside
        # function_declarator / pointer_declarator. Check these first to
        # avoid matching the return type_identifier as the function name.
        if language in ("c", "cpp") and kind == "function":
            for child in node.children:
                if child.type in ("function_declarator", "pointer_declarator"):
                    # Scoped names like Foo::bar use qualified_identifier; take
                    # the rightmost identifier/field_identifier after the last ::.
                    for sub in child.children:
                        if sub.type == "qualified_identifier":
                            for qsub in reversed(sub.children):
                                if qsub.type in ("identifier", "field_identifier"):
                                    return qsub.text.decode("utf-8", errors="replace")
                    result = self._get_name(child, language, kind)
                    if result:
                        return result
            # C++: inside function_declarator, the name appears as
            # qualified_identifier (Class::method), destructor_name (~Class),
            # operator_name (operator==), or field_identifier. The generic
            # loop below only recognizes 'identifier'/'type_identifier',
            # so scoped method definitions would otherwise fall through and
            # match the outer return-type type_identifier as the function name.
            # Nested scopes (Outer::Inner::method) produce nested
            # qualified_identifier nodes — peel until we find the leaf name.
            if language == "cpp" and node.type == "function_declarator":
                def _leaf_name(qi):
                    # Walk right-to-left: the rightmost identifier/
                    # destructor_name/operator_name is the method name.
                    # If the rightmost child is itself a qualified_identifier
                    # (nested scope), recurse into it.
                    for sub in reversed(qi.children):
                        if sub.type in (
                            "identifier",
                            "destructor_name",
                            "operator_name",
                        ):
                            return sub.text.decode(
                                "utf-8", errors="replace")
                        if sub.type == "qualified_identifier":
                            inner = _leaf_name(sub)
                            if inner:
                                return inner
                    return None
                for child in node.children:
                    if child.type == "qualified_identifier":
                        name = _leaf_name(child)
                        if name:
                            return name
                    if child.type in (
                        "field_identifier",
                        "destructor_name",
                        "operator_name",
                    ):
                        return child.text.decode(
                            "utf-8", errors="replace")

        # Bash function_definition: ``foo() { ... }`` — tree-sitter-bash
        # stores the function name as a ``word`` child, which the generic
        # loop below doesn't recognize.
        if language == "bash" and node.type == "function_definition":
            for child in node.children:
                if child.type == "word":
                    return child.text.decode("utf-8", errors="replace")
        # Verilog/SystemVerilog: names are nested differently per construct type.
        if language == "verilog":
            if node.type == "package_declaration":
                for child in node.children:
                    if child.type == "package_identifier":
                        for sub in child.children:
                            if sub.type == "simple_identifier":
                                return sub.text.decode("utf-8", errors="replace")
            # module_declaration: name is in module_header > simple_identifier
            if node.type == "module_declaration":
                for child in node.children:
                    if child.type == "module_header":
                        for sub in child.children:
                            if sub.type == "simple_identifier":
                                return sub.text.decode("utf-8", errors="replace")
            # interface_declaration: name is in interface_ansi_header > interface_identifier
            if node.type == "interface_declaration":
                for child in node.children:
                    if child.type in ("interface_header", "interface_ansi_header"):
                        for sub in child.children:
                            if sub.type == "simple_identifier":
                                return sub.text.decode("utf-8", errors="replace")
                            if sub.type == "interface_identifier":
                                for ss in sub.children:
                                    if ss.type == "simple_identifier":
                                        return ss.text.decode("utf-8", errors="replace")
                                return sub.text.decode("utf-8", errors="replace")
            # task_declaration: name is in task_body_declaration > task_identifier
            if node.type == "task_declaration":
                for child in node.children:
                    if child.type == "task_body_declaration":
                        for sub in child.children:
                            if sub.type == "task_identifier":
                                return sub.text.decode("utf-8", errors="replace")
            # function_declaration: name is in function_body_declaration > function_identifier
            if node.type == "function_declaration":
                for child in node.children:
                    if child.type == "function_body_declaration":
                        for sub in child.children:
                            if sub.type == "function_identifier":
                                return sub.text.decode("utf-8", errors="replace")


        # Config-driven custom languages make ``name_field`` authoritative.
        # Resolve it before the generic direct-child heuristic so an unrelated
        # identifier (for example a return type) cannot win.
        if language in self._custom_languages:
            resolved = self._resolve_custom_name(node, language)
            if resolved:
                return resolved
            name_child = node.child_by_field_name("name")
            if name_child is not None:
                return name_child.text.decode("utf-8", errors="replace")

        # Most built-in languages use a 'name' child.
        # field_identifier covers C++ class member function names inside
        # function_declarator (e.g. virtual std::string get_name() = 0).
        for child in node.children:
            if child.type in (
                "identifier", "name", "type_identifier", "property_identifier",
                "simple_identifier", "constant", "field_identifier",
            ):
                return child.text.decode("utf-8", errors="replace")
        return None

    @staticmethod
    def _cpp_scope_join(
        outer: Optional[str],
        inner: Optional[str],
    ) -> Optional[str]:
        if outer and inner:
            return f"{outer}.{inner}"
        return outer or inner

    def _cpp_lexical_namespace(self, node) -> Optional[str]:
        """Return the dotted namespace path containing a C++ AST node."""
        namespaces: list[str] = []
        ancestor = node.parent
        while ancestor is not None:
            if ancestor.type == "namespace_definition":
                name_node = ancestor.child_by_field_name("name")
                namespace = (
                    name_node.text.decode("utf-8", errors="replace")
                    if name_node is not None
                    else "(anonymous)"
                )
                namespaces.append(re.sub(r"\s*::\s*", ".", namespace))
            ancestor = ancestor.parent
        namespaces.reverse()
        return ".".join(namespaces) or None

    def _cpp_lexical_class_names(self, node) -> list[str]:
        """Return containing C++ class names from outermost to innermost."""
        classes: list[str] = []
        ancestor = node.parent
        class_types = self._class_types.get("cpp", [])
        while ancestor is not None:
            if ancestor.type in class_types:
                name = self._get_name(ancestor, "cpp", "class")
                if name:
                    classes.append(name)
            ancestor = ancestor.parent
        classes.reverse()
        return classes

    def _cpp_function_identity(
        self,
        node,
        name: str,
        source: bytes,
    ) -> tuple[Optional[str], str, Optional[str]]:
        """Return explicit scope, signature identity, and raw C++ parameters."""
        declarator_root = node.child_by_field_name("declarator")
        declarator = self._cpp_find_function_declarator(declarator_root)
        if declarator is None:
            return None, name, None

        callable_name = self._cpp_callable_name(declarator_root) or name
        callable_node = declarator.child_by_field_name("declarator")
        if declarator_root is not None and declarator_root.type == "qualified_identifier":
            callable_node = declarator_root
        elif callable_node is not None and callable_node.type != "qualified_identifier":
            callable_node = self._cpp_find_qualified_identifier(callable_node)
        explicit_scope: Optional[str] = None
        if callable_node is not None and callable_node.type == "qualified_identifier":
            callable_text = callable_node.text.decode(
                "utf-8", errors="replace",
            )
            if "::" in callable_text:
                scope_text = callable_text.rsplit("::", 1)[0].lstrip(":").strip()
                explicit_scope = re.sub(
                    r"\s*::\s*", ".", scope_text,
                )

        parameters = declarator.child_by_field_name("parameters")
        if parameters is None:
            return explicit_scope, name, None

        parameter_types = [
            self._cpp_parameter_type(parameter, source)
            for parameter in parameters.named_children
            if parameter.type != "comment"
        ]
        parameter_types = [value for value in parameter_types if value]
        if any(child.type == "..." for child in parameters.children):
            parameter_types.append("...")
        if parameter_types == ["void"]:
            parameter_types = []
        qualifiers = [
            child.text.decode("utf-8", errors="replace").strip()
            for child in declarator.children
            if child.type in ("type_qualifier", "ref_qualifier")
        ]
        qualifier_suffix = f" {' '.join(qualifiers)}" if qualifiers else ""
        raw_params = parameters.text.decode("utf-8", errors="replace")
        return (
            explicit_scope,
            f"{callable_name}({','.join(parameter_types)}){qualifier_suffix}",
            raw_params,
        )

    def _cpp_find_function_declarator(self, declarator):
        """Find the callable declarator through reference/pointer wrappers."""
        if declarator is None:
            return None
        if declarator.type in ("function_declarator", "abstract_function_declarator"):
            nested = self._cpp_find_function_declarator(
                declarator.child_by_field_name("declarator"),
            )
            if nested is not None:
                return nested
            return declarator
        for child in declarator.named_children:
            if child.type in ("parameter_list", "template_argument_list"):
                continue
            found = self._cpp_find_function_declarator(child)
            if found is not None:
                return found
        return None

    def _cpp_is_callable_declaration(self, declarator) -> bool:
        """Return whether a declaration names a function, not a function pointer."""
        function_declarator = self._cpp_find_function_declarator(declarator)
        if function_declarator is None:
            return False

        callable_declarator = function_declarator.child_by_field_name("declarator")
        if (
            callable_declarator is None
            or callable_declarator.type != "parenthesized_declarator"
        ):
            return True

        # ``void (*callback)(int)`` has no nested function declarator inside
        # the parentheses.  A real function returning a function pointer,
        # such as ``void (*factory())(int)``, does.
        return self._cpp_find_function_declarator(callable_declarator) is not None

    @staticmethod
    def _cpp_declaration_has_callable_scope(declaration) -> bool:
        """Limit callable declarations to file, namespace, and class scopes."""
        scope = declaration.parent
        while scope is not None:
            if scope.type in (
                "translation_unit",
                "namespace_definition",
                "field_declaration_list",
            ):
                return not _is_in_static_dead_guard(declaration)
            if scope.type in (
                "compound_statement",
                "function_definition",
                "lambda_expression",
            ):
                return False
            scope = scope.parent
        return False

    def _cpp_find_qualified_identifier(self, declarator):
        """Find the callable's qualified identifier outside its parameters."""
        if declarator is None:
            return None
        if declarator.type == "qualified_identifier":
            return declarator
        for child in declarator.named_children:
            if child.type in ("parameter_list", "template_argument_list"):
                continue
            found = self._cpp_find_qualified_identifier(child)
            if found is not None:
                return found
        return None

    def _cpp_callable_name(self, declarator) -> Optional[str]:
        """Return a C++ callable name without confusing it with its return type."""
        if declarator is None:
            return None

        operator_cast = self._cpp_find_declarator_kind(declarator, "operator_cast")
        if operator_cast is not None:
            function_declarator = self._cpp_find_function_declarator(operator_cast)
            if function_declarator is not None:
                prefix_end = function_declarator.start_byte - operator_cast.start_byte
                name = operator_cast.text[:prefix_end].decode(
                    "utf-8", errors="replace",
                )
                name = re.sub(r"\s+", " ", name).strip()
                return re.sub(r"\s*([*&])\s*", r"\1", name)

        def leaf_name(current):
            for child in reversed(current.named_children):
                if child.type in ("parameter_list", "template_argument_list"):
                    continue
                if child.type in (
                    "identifier",
                    "field_identifier",
                    "destructor_name",
                    "operator_name",
                ):
                    return child.text.decode("utf-8", errors="replace")
                found = leaf_name(child)
                if found:
                    return found
            return None

        return leaf_name(declarator)

    def _cpp_find_declarator_kind(self, declarator, kind: str):
        """Find one declarator node kind while ignoring parameter declarations."""
        if declarator is None:
            return None
        if declarator.type == kind:
            return declarator
        for child in declarator.named_children:
            if child.type in ("parameter_list", "template_argument_list"):
                continue
            found = self._cpp_find_declarator_kind(child, kind)
            if found is not None:
                return found
        return None

    def _cpp_parameter_type(self, parameter, source: bytes) -> str:
        """Normalize one C++ parameter to its type-only identity fragment."""
        end_byte = parameter.end_byte
        for child in parameter.children:
            if child.type == "=":
                end_byte = child.start_byte
                break

        declarator = parameter.child_by_field_name("declarator")
        name_node = self._cpp_declarator_name(declarator)
        if name_node is not None and name_node.start_byte < end_byte:
            raw = (
                source[parameter.start_byte:name_node.start_byte]
                + source[name_node.end_byte:end_byte]
            ).decode("utf-8", errors="replace")
        else:
            raw = source[parameter.start_byte:end_byte].decode(
                "utf-8", errors="replace",
            )

        raw = re.sub(r"/\*.*?\*/|//[^\r\n]*", " ", raw, flags=re.DOTALL)
        raw = re.sub(r"\[\[.*?\]\]", " ", raw, flags=re.DOTALL)
        normalized = re.sub(r"\s+", " ", raw).strip()
        normalized = re.sub(r"\s*::\s*", "::", normalized)
        normalized = re.sub(r"\s*([<>,*&()\[\]])\s*", r"\1", normalized)
        return normalized

    def _cpp_declarator_name(self, declarator):
        """Find the declared identifier while avoiding nested parameter types."""
        if declarator is None:
            return None
        if declarator.type in ("identifier", "field_identifier"):
            return declarator

        nested = declarator.child_by_field_name("declarator")
        if nested is not None and nested != declarator:
            found = self._cpp_declarator_name(nested)
            if found is not None:
                return found

        for child in declarator.named_children:
            if child.type in ("parameter_list", "template_argument_list"):
                continue
            found = self._cpp_declarator_name(child)
            if found is not None:
                return found
        return None

    def _get_params(self, node, language: str, source: bytes) -> Optional[str]:
        """Extract parameter list as a string."""
        for child in node.children:
            param_types = (
                "parameters", "formal_parameters",
                "parameter_list", "formal_parameter_list",
            )
            if child.type in param_types:
                return child.text.decode("utf-8", errors="replace")
        return None

    def _get_return_type(self, node, language: str, source: bytes) -> Optional[str]:
        """Extract return type annotation if present."""
        for child in node.children:
            if child.type in ("type", "return_type", "type_annotation", "return_type_definition"):
                return child.text.decode("utf-8", errors="replace")
        # Python: look for -> annotation
        if language == "python":
            for i, child in enumerate(node.children):
                if child.type == "->" and i + 1 < len(node.children):
                    return node.children[i + 1].text.decode("utf-8", errors="replace")
        return None

    def _get_bases(self, node, language: str, source: bytes) -> list[str]:
        """Extract base classes / implemented interfaces."""
        bases = []
        if language == "python":
            for child in node.children:
                if child.type == "argument_list":
                    for arg in child.children:
                        if arg.type in ("identifier", "attribute"):
                            bases.append(arg.text.decode("utf-8", errors="replace"))
        elif language == "cpp":
            # C++: base_class_clause contains type_identifiers
            for child in node.children:
                if child.type == "base_class_clause":
                    for sub in child.children:
                        if sub.type == "type_identifier":
                            bases.append(sub.text.decode("utf-8", errors="replace"))
        elif language in ("typescript", "javascript", "tsx"):
            # Classes nest their heritage one level down, under class_heritage
            # (`class C extends B implements I`); interfaces carry
            # extends_type_clause as a direct child. Scanning only direct
            # children therefore missed every class base.
            clauses: list = []
            for child in node.children:
                if child.type == "class_heritage":
                    clauses.extend(child.children)
                else:
                    clauses.append(child)
            for clause in clauses:
                if clause.type not in _TS_HERITAGE_CLAUSES:
                    continue
                for sub in clause.children:
                    if sub.type in ("identifier", "type_identifier", "nested_identifier"):
                        bases.append(sub.text.decode("utf-8", errors="replace"))
                    elif sub.type == "generic_type":
                        # `extends Base<T>` — the base is the generic's head.
                        for ident in sub.children:
                            if ident.type in ("type_identifier", "nested_type_identifier"):
                                bases.append(ident.text.decode("utf-8", errors="replace"))
                                break
        return bases

    def _extract_import(self, node, language: str, source: bytes) -> list[str]:
        """Extract import targets as module/path strings."""
        imports = []
        text = node.text.decode("utf-8", errors="replace").strip()

        if language == "python":
            # import x.y.z  or  from x.y import z
            if node.type == "import_from_statement":
                for child in node.children:
                    if child.type == "dotted_name":
                        imports.append(child.text.decode("utf-8", errors="replace"))
                        break
            else:
                for child in node.children:
                    if child.type == "dotted_name":
                        imports.append(child.text.decode("utf-8", errors="replace"))
        elif language in ("javascript", "typescript", "tsx"):
            # import ... from 'module'
            for child in node.children:
                if child.type == "string":
                    val = child.text.decode("utf-8", errors="replace").strip("'\"")
                    imports.append(val)
        elif language == "rust":
            imports.extend(
                original_path
                for _, original_path in self._parse_rust_use_node(node)
            )
        elif language in ("c", "cpp"):
            # #include <header> or #include "header"
            for child in node.children:
                if child.type in ("system_lib_string", "string_literal"):
                    val = child.text.decode("utf-8", errors="replace").strip("<>\"")
                    imports.append(val)
        elif language == "verilog":
            # import pkg::*; or import pkg::item;
            # Node structure: package_import_declaration > package_import_item > package_identifier
            for child in node.children:
                if child.type == "package_import_item":
                    for subchild in child.children:
                        if subchild.type == "package_identifier":
                            imports.append(subchild.text.decode("utf-8", errors="replace"))
        elif language in self._custom_languages:
            # Custom languages (languages.toml): prefer the grammar's
            # module-ish field over the raw statement text (e.g. Erlang
            # ``-import(lists, [map/2]).`` → ``lists``; Haskell
            # ``import Data.List`` → ``Data.List``).
            for field_name in ("module", "name", "path", "source"):
                target = node.child_by_field_name(field_name)
                if target is None:
                    continue
                val = target.text.decode("utf-8", errors="replace").strip().strip("'\"")
                if val:
                    imports.append(val)
                    break
            else:
                imports.append(text)
        else:
            # Fallback: just record the text
            imports.append(text)

        return imports

    def _get_call_name(self, node, language: str, source: bytes) -> Optional[str]:
        """Extract the function/method name being called."""
        if not node.children:
            return None

        first = node.children[0]

        if language == "rust" and node.type == "call_expression":
            callee = node.child_by_field_name("function")
            segments = self._rust_path_segments(callee)
            if segments:
                return "::".join(segments)
            while callee is not None and callee.type == "generic_function":
                callee = callee.child_by_field_name("function")
            if callee is not None and callee.type == "field_expression":
                field = callee.child_by_field_name("field")
                if field is not None:
                    return field.text.decode("utf-8", errors="replace")


        # Bash: `command` node's first child is the command name.
        if language == "bash" and node.type == "command":
            for child in node.children:
                if child.type == "command_name":
                    # command_name wraps a word — get its text
                    txt = child.text.decode("utf-8", errors="replace").strip()
                    return txt or None
            return None

        # Verilog/SystemVerilog: the first child is the instantiated type.
        if language == "verilog" and node.type in (
            "module_instantiation", "interface_instantiation",
        ):
            if first.type == "simple_identifier":
                return first.text.decode("utf-8", errors="replace")
            return None

        # Simple call: func_name(args)
        if first.type in ("identifier", "simple_identifier"):
            return first.text.decode("utf-8", errors="replace")

        # Method call: obj.method(args)
        member_types = (
            "attribute", "member_expression",
            "field_expression", "selector_expression",
            "navigation_expression", "member_access_expression",
            "conditional_access_expression",
        )
        if first.type in member_types:
            # Get the rightmost identifier (the method name)
            for child in reversed(first.children):
                if child.type in (
                    "identifier", "property_identifier", "field_identifier",
                    "field_name", "simple_identifier",
                ):
                    return child.text.decode("utf-8", errors="replace")
                if child.type == "navigation_suffix":
                    for sub in child.children:
                        if sub.type == "simple_identifier":
                            return sub.text.decode("utf-8", errors="replace")
                if child.type == "member_binding_expression":
                    for sub in child.children:
                        if sub.type == "identifier":
                            return sub.text.decode("utf-8", errors="replace")
            return first.text.decode("utf-8", errors="replace")

        # Scoped call (e.g., Rust path::func())
        if first.type in (
            "scoped_identifier",
            "qualified_identifier",
            "qualified_name",
        ):
            return first.text.decode("utf-8", errors="replace")

        # Custom languages (languages.toml): probe common callee field names
        # (Erlang ``call`` uses ``expr``; Haskell ``apply`` uses ``function``).
        if language in self._custom_languages:
            return self._get_custom_call_name(node)

        return None

    # Callee field names probed for config-driven custom languages, in order.
    _CUSTOM_CALLEE_FIELDS = ("function", "callee", "expr", "name")
    _MAX_CUSTOM_CALLEE_DESCENT = 32  # Curried-application depth guard

    def _get_custom_call_name(self, node) -> Optional[str]:
        """Generic callee extraction for config-driven custom languages.

        Tries common tree-sitter field names for the callee.  When the field
        child is itself an application node carrying the same field (curried
        calls, e.g. Haskell ``f x y`` = ``apply(apply(f, x), y)``), descend
        to the leaf callee.  Multi-line or oversized callee text (a lambda
        being invoked, for instance) is rejected rather than recorded as a
        garbage call target.
        """
        for field_name in self._CUSTOM_CALLEE_FIELDS:
            callee = node.child_by_field_name(field_name)
            if callee is None:
                continue
            for _ in range(self._MAX_CUSTOM_CALLEE_DESCENT):
                inner = callee.child_by_field_name(field_name)
                if inner is None:
                    break
                callee = inner
            text = callee.text.decode("utf-8", errors="replace").strip()
            if text and len(text) <= 256 and "\n" not in text:
                return text
            return None
        return None

    def _get_jsx_component_reference(self, node) -> Optional[tuple[Optional[str], str]]:
        """Extract ``(base_name, component_name)`` for a JSX element.

        ``base_name`` is set for member-style elements such as
        ``<UI.MarkdownMsg />`` and ``None`` for plain component tags such as
        ``<MarkdownMsg />``.
        """
        for child in node.children:
            if child.type == "identifier":
                name = child.text.decode("utf-8", errors="replace")
                if self._looks_like_component_name(name):
                    return (None, name)
                return None
            if child.type == "member_expression":
                base_name = self._get_member_expression_root_name(child)
                component_name = None
                for sub in reversed(child.children):
                    if sub.type in ("identifier", "property_identifier"):
                        component_name = sub.text.decode("utf-8", errors="replace")
                        break
                if component_name and self._looks_like_component_name(component_name):
                    return (base_name, component_name)
                for sub in reversed(child.children):
                    if sub.type in ("identifier", "property_identifier"):
                        name = sub.text.decode("utf-8", errors="replace")
                        if self._looks_like_component_name(name):
                            return (None, name)
                        return None
                text = child.text.decode("utf-8", errors="replace")
                tail = text.split(".")[-1]
                if self._looks_like_component_name(tail):
                    return (None, tail)
                return None
        return None

    def _get_member_expression_root_name(self, node) -> Optional[str]:
        """Return the leftmost identifier for a nested member expression."""
        for child in node.children:
            if child.type == "identifier":
                return child.text.decode("utf-8", errors="replace")
            if child.type == "member_expression":
                return self._get_member_expression_root_name(child)
        return None

    @staticmethod
    def _looks_like_component_name(name: str) -> bool:
        """Return True for JSX names that look like user components."""
        return bool(name) and name[0].isupper()

    # Modifier suffixes used in JS/TS test runners
    _TEST_MODIFIER_SUFFIXES = frozenset({
        "only", "skip", "each", "todo", "concurrent", "failing",
    })

    def _get_base_call_name(self, node, source: bytes) -> Optional[str]:
        """Return the base object name for member-expression calls like describe.only()."""
        if not node.children:
            return None
        first = node.children[0]
        if first.type != "member_expression":
            return None
        rightmost: Optional[str] = None
        for child in reversed(first.children):
            if child.type in ("identifier", "property_identifier"):
                rightmost = child.text.decode("utf-8", errors="replace")
                break
        if rightmost not in self._TEST_MODIFIER_SUFFIXES:
            return None
        for child in first.children:
            if child.type == "identifier":
                return child.text.decode("utf-8", errors="replace")
            if child.type == "member_expression":
                for inner in child.children:
                    if inner.type == "identifier":
                        return inner.text.decode("utf-8", errors="replace")
        return None

