"""Tests for Rust, C, and C++ parsing."""

from pathlib import Path

import pytest

from code_review_graph.parser import CodeParser

FIXTURES = Path(__file__).parent / "fixtures"


class TestRustParsing:
    def setup_method(self):
        self.parser = CodeParser()
        self.nodes, self.edges = self.parser.parse_file(FIXTURES / "sample_rust.rs")

    def test_detects_language(self):
        assert self.parser.detect_language(Path("lib.rs")) == "rust"

    def test_finds_structs_and_traits(self):
        classes = [n for n in self.nodes if n.kind == "Class"]
        names = {c.name for c in classes}
        assert "User" in names
        assert "InMemoryRepo" in names

    def test_finds_functions(self):
        funcs = [n for n in self.nodes if n.kind == "Function"]
        names = {f.name for f in funcs}
        assert "new" in names
        assert "create_user" in names
        assert "find_by_id" in names
        assert "save" in names

    def test_finds_imports(self):
        imports = [e for e in self.edges if e.kind == "IMPORTS_FROM"]
        assert len(imports) >= 1

    def test_finds_calls(self):
        calls = [e for e in self.edges if e.kind == "CALLS"]
        assert len(calls) >= 3

    def test_detects_test_attribute(self):
        tests = [n for n in self.nodes if n.kind == "Test"]
        names = {t.name for t in tests}
        assert "new_repo_is_empty" in names
        assert "create_user_saves_to_repo" in names
        assert all(t.is_test for t in tests)

    def test_detects_tokio_test_attribute(self):
        tests = {n.name for n in self.nodes if n.kind == "Test"}
        assert "async_test_is_detected" in tests

    def test_non_test_functions_not_misclassified(self):
        funcs = {n.name for n in self.nodes if n.kind == "Function"}
        assert "create_user" in funcs
        assert "new" in funcs
        # `create_user` carries no `#[test]` — must stay Function.
        for n in self.nodes:
            if n.name == "create_user":
                assert not n.is_test


class TestCParsing:
    def setup_method(self):
        self.parser = CodeParser()
        self.nodes, self.edges = self.parser.parse_file(FIXTURES / "sample.c")

    def test_detects_language(self):
        assert self.parser.detect_language(Path("main.c")) == "c"

    def test_finds_structs(self):
        classes = [n for n in self.nodes if n.kind == "Class"]
        names = {c.name for c in classes}
        assert "User" in names

    def test_finds_functions(self):
        funcs = [n for n in self.nodes if n.kind == "Function"]
        names = {f.name for f in funcs}
        assert "print_user" in names
        assert "main" in names
        assert "create_user" in names

    def test_finds_imports(self):
        imports = [e for e in self.edges if e.kind == "IMPORTS_FROM"]
        targets = {e.target for e in imports}
        assert "stdio.h" in targets


class TestCppParsing:
    def setup_method(self):
        self.parser = CodeParser()
        self.nodes, self.edges = self.parser.parse_file(FIXTURES / "sample.cpp")

    def test_detects_language(self):
        assert self.parser.detect_language(Path("main.cpp")) == "cpp"

    def test_finds_classes(self):
        classes = [n for n in self.nodes if n.kind == "Class"]
        names = {c.name for c in classes}
        assert "Animal" in names
        assert "Dog" in names

    def test_finds_functions(self):
        funcs = [n for n in self.nodes if n.kind == "Function"]
        names = {f.name for f in funcs}
        assert "greet" in names or "main" in names

    def test_finds_inheritance(self):
        inherits = [e for e in self.edges if e.kind == "INHERITS"]
        assert len(inherits) >= 1


class TestHhParsing:
    def setup_method(self):
        self.parser = CodeParser()
        self.nodes, self.edges = self.parser.parse_file(FIXTURES / "sample.hh")

    def test_detects_language(self):
        assert self.parser.detect_language(Path("types.hh")) == "cpp"

    def test_finds_classes(self):
        classes = [n for n in self.nodes if n.kind == "Class"]
        names = {c.name for c in classes}
        assert "Shape" in names
        assert "Circle" in names

    def test_finds_functions(self):
        funcs = [n for n in self.nodes if n.kind == "Function"]
        names = {f.name for f in funcs}
        assert "perimeter" in names

    def test_finds_inheritance(self):
        inherits = [e for e in self.edges if e.kind == "INHERITS"]
        assert len(inherits) >= 1


class TestBashParsing:
    """Bash/Shell parser — closes #197."""

    def setup_method(self):
        self.parser = CodeParser()
        self.nodes, self.edges = self.parser.parse_file(FIXTURES / "sample.sh")

    def test_detects_language(self):
        assert self.parser.detect_language(Path("build.sh")) == "bash"
        assert self.parser.detect_language(Path("build.bash")) == "bash"
        assert self.parser.detect_language(Path("run.zsh")) == "bash"
        # Regression for #235 — Korn shell (.ksh) should parse as bash.
        assert self.parser.detect_language(Path("legacy.ksh")) == "bash"

    def test_ksh_extension_parses_as_bash(self, tmp_path):
        """Regression for #235: a real .ksh file is parsed through the bash
        grammar end-to-end and produces the same structural nodes/edges
        as an equivalent .sh file."""
        fixture_source = (FIXTURES / "sample.sh").read_text(encoding="utf-8")
        ksh_copy = tmp_path / "legacy.ksh"
        ksh_copy.write_text(fixture_source, encoding="utf-8")

        ksh_nodes, ksh_edges = self.parser.parse_file(ksh_copy)

        # Language tagging: every node must be "bash".
        assert ksh_nodes, "parser produced zero nodes for .ksh file"
        for n in ksh_nodes:
            assert n.language == "bash"

        # Same function set as the .sh fixture.
        ksh_funcs = {n.name for n in ksh_nodes if n.kind == "Function"}
        sh_funcs = {n.name for n in self.nodes if n.kind == "Function"}
        assert ksh_funcs == sh_funcs, (
            f".ksh and .sh produced different function sets: "
            f"sh-only={sh_funcs - ksh_funcs}, ksh-only={ksh_funcs - sh_funcs}"
        )

        # Same structural-edge totals by kind.
        def by_kind(edges):
            counts: dict[str, int] = {}
            for e in edges:
                counts[e.kind] = counts.get(e.kind, 0) + 1
            return counts
        assert by_kind(ksh_edges) == by_kind(self.edges)

    def test_nodes_have_bash_language(self):
        for n in self.nodes:
            assert n.language == "bash"

    def test_finds_functions(self):
        funcs = {n.name for n in self.nodes if n.kind == "Function"}
        assert "log_info" in funcs
        assert "log_error" in funcs
        assert "ensure_dir" in funcs
        assert "cleanup" in funcs
        assert "main" in funcs

    def test_functions_have_no_parent(self):
        """Bash has no classes so every function should be top-level."""
        for n in self.nodes:
            if n.kind == "Function":
                assert n.parent_name is None

    def test_source_creates_import_edge(self):
        """`source ./lib.sh` / `. ./config.sh` should produce IMPORTS_FROM
        edges (#197)."""
        imports = [e for e in self.edges if e.kind == "IMPORTS_FROM"]
        assert len(imports) >= 2
        targets = [e.target for e in imports]
        # sample_lib.sh exists on disk so should be resolved to an absolute path
        assert any(t.endswith("sample_lib.sh") for t in targets)
        # sample_config.sh doesn't exist; unresolved path is kept as-is
        assert any("sample_config.sh" in t for t in targets)

    def test_command_invocations_create_call_edges(self):
        """Each `command` node inside a function body should become a
        CALLS edge keyed on its command_name (#197)."""
        calls = [e for e in self.edges if e.kind == "CALLS"]
        targets = {e.target for e in calls}
        # Built-ins and external commands kept as bare names
        assert "echo" in targets
        assert "mkdir" in targets
        # Internal function calls should resolve to qualified names
        assert any(t.endswith("::log_info") for t in targets)
        assert any(t.endswith("::ensure_dir") for t in targets)
        assert any(t.endswith("::cleanup") for t in targets)

    def test_main_calls_resolve_to_internal_functions(self):
        """main() should have CALLS edges to log_info, ensure_dir, and cleanup."""
        calls = [
            e for e in self.edges
            if e.kind == "CALLS" and e.source.endswith("::main")
        ]
        call_targets = {e.target for e in calls}
        assert any(t.endswith("::log_info") for t in call_targets)
        assert any(t.endswith("::ensure_dir") for t in call_targets)
        assert any(t.endswith("::cleanup") for t in call_targets)


# ---------------------------------------------------------------------------
# Verilog / SystemVerilog
# ---------------------------------------------------------------------------


def _has_verilog_parser():
    try:
        import tree_sitter_language_pack as tslp
        tslp.get_parser("verilog")
        return True
    except (LookupError, ImportError):
        return False


@pytest.mark.skipif(not _has_verilog_parser(), reason="verilog tree-sitter grammar not installed")
class TestVerilogParsing:
    def setup_method(self):
        self.parser = CodeParser()
        self.nodes, self.edges = self.parser.parse_file(FIXTURES / "sample.sv")

    def test_detects_language(self):
        assert self.parser.detect_language(Path("top.sv")) == "verilog"
        assert self.parser.detect_language(Path("pkg.svh")) == "verilog"
        assert self.parser.detect_language(Path("cpu.v")) == "verilog"
        assert self.parser.detect_language(Path("header.vh")) == "verilog"

    def test_finds_modules(self):
        classes = [n for n in self.nodes if n.kind == "Class"]
        names = {c.name for c in classes}
        assert "FIFOController" in names
        assert "Adder" in names

    def test_finds_interfaces(self):
        classes = [n for n in self.nodes if n.kind == "Class"]
        names = {c.name for c in classes}
        assert "BusIf" in names

    def test_finds_tasks(self):
        funcs = [n for n in self.nodes if n.kind == "Function"]
        names = {f.name for f in funcs}
        assert "do_write" in names

    def test_finds_functions_in_module(self):
        funcs = [n for n in self.nodes if n.kind == "Function"]
        names = {f.name for f in funcs}
        assert "is_full" in names

    def test_task_and_function_parent_is_module(self):
        funcs = {f.name: f for f in self.nodes if f.kind == "Function"}
        assert funcs["do_write"].parent_name == "FIFOController"
        assert funcs["is_full"].parent_name == "FIFOController"

    def test_finds_package_imports(self):
        imports = [e for e in self.edges if e.kind == "IMPORTS_FROM"]
        targets = {e.target for e in imports}
        assert "utils_pkg" in targets
        assert "arith_pkg" in targets

    def test_module_instantiation_creates_call_edge(self):
        calls = [e for e in self.edges if e.kind == "CALLS"]
        targets = {e.target for e in calls}
        assert any("Adder" in t for t in targets)

    def test_module_instantiation_caller_is_enclosing_module(self):
        # module_instantiation CALLS must be attributed to the containing
        # module, not a function — Verilog-specific fallback in _extract_calls.
        calls = [e for e in self.edges if e.kind == "CALLS"]
        adder_calls = [e for e in calls if "Adder" in e.target]
        assert adder_calls, "Expected a CALLS edge for Adder instantiation"
        assert any("FIFOController" in e.source for e in adder_calls)

    def test_file_node_language(self):
        file_nodes = [n for n in self.nodes if n.kind == "File"]
        assert len(file_nodes) == 1
        assert file_nodes[0].language == "verilog"


# ---------------------------------------------------------------------------
# Ansible YAML parsing tests
# ---------------------------------------------------------------------------

try:
    import yaml as _yaml_check  # noqa: F401
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

_ANSIBLE_SKIP = pytest.mark.skipif(not _YAML_AVAILABLE, reason="pyyaml not installed")

_PLAYBOOK = FIXTURES / "playbooks" / "sample_ansible_playbook.yml"
_TASKS_FILE = FIXTURES / "tasks" / "sample_ansible_tasks.yml"
_META_FILE = FIXTURES / "roles" / "myrole" / "meta" / "main.yml"


@_ANSIBLE_SKIP
class TestAnsiblePlaybookParsing:
    def setup_method(self):
        self.parser = CodeParser()
        self.nodes, self.edges = self.parser.parse_file(_PLAYBOOK)

    def test_detects_language_ansible_paths(self):
        p = self.parser
        assert p.detect_language(Path("playbooks/site.yml")) == "ansible"
        assert p.detect_language(Path("roles/web/tasks/main.yml")) == "ansible"
        assert p.detect_language(Path("handlers/main.yml")) == "ansible"
        assert p.detect_language(Path("config/settings.yml")) == "yaml"

    def test_file_node_created(self):
        file_nodes = [n for n in self.nodes if n.kind == "File"]
        assert len(file_nodes) == 1
        assert file_nodes[0].language == "ansible"

    def test_finds_plays_as_class_nodes(self):
        play_names = {n.name for n in self.nodes if n.kind == "Class"}
        assert "Configure web servers" in play_names
        assert "Configure database servers" in play_names

    def test_plays_have_ansible_kind_extra(self):
        plays = [n for n in self.nodes if n.kind == "Class"]
        assert plays, "expected at least one play"
        for p in plays:
            assert p.extra.get("ansible_kind") == "play"

    def test_import_playbook_produces_imports_from(self):
        targets = {e.target for e in self.edges if e.kind == "IMPORTS_FROM"}
        assert "base-setup.yml" in targets

    def test_pre_task_extracted(self):
        func_names = {n.name for n in self.nodes if n.kind == "Function"}
        assert "Verify connectivity" in func_names

    def test_post_task_extracted(self):
        func_names = {n.name for n in self.nodes if n.kind == "Function"}
        assert "Smoke test" in func_names

    def test_finds_tasks_as_function_nodes(self):
        func_names = {n.name for n in self.nodes if n.kind == "Function"}
        assert "Install packages" in func_names
        assert "Deploy config" in func_names
        assert "Run deploy tasks" in func_names

    def test_fqcn_module_stored_in_extra(self):
        task = next(
            n for n in self.nodes
            if n.kind == "Function" and n.name == "Verify connectivity"
        )
        assert task.extra.get("ansible_module") == "ansible.builtin.wait_for_connection"

    def test_finds_handlers(self):
        handlers = [
            n for n in self.nodes
            if n.kind == "Function" and n.extra.get("ansible_kind") == "handler"
        ]
        handler_names = {h.name for h in handlers}
        assert "restart app" in handler_names
        assert "restart db" in handler_names

    def test_handler_listen_stored(self):
        handler = next(
            n for n in self.nodes
            if n.kind == "Function" and n.name == "restart app"
        )
        assert handler.extra.get("ansible_listen") == "app restarted"

    def test_notify_scalar_produces_calls(self):
        calls = {e.target for e in self.edges if e.kind == "CALLS"}
        assert any(target.endswith("::Configure web servers.restart app") for target in calls)

    def test_notify_list_produces_multiple_calls(self):
        calls = {e.target for e in self.edges if e.kind == "CALLS"}
        assert any(target.endswith("::Configure database servers.restart db") for target in calls)
        assert any(target.endswith("::Configure database servers.run migrations") for target in calls)

    def test_include_tasks_imports_from(self):
        targets = {e.target for e in self.edges if e.kind == "IMPORTS_FROM"}
        assert "deploy.yml" in targets

    def test_import_role_imports_from(self):
        targets = {e.target for e in self.edges if e.kind == "IMPORTS_FROM"}
        assert "security" in targets

    def test_roles_list_imports_from(self):
        targets = {e.target for e in self.edges if e.kind == "IMPORTS_FROM"}
        assert "common" in targets
        assert "nginx" in targets

    def test_vars_files_imports_from(self):
        targets = {e.target for e in self.edges if e.kind == "IMPORTS_FROM"}
        assert "vars/common.yml" in targets

    def test_block_tasks_extracted(self):
        func_names = {n.name for n in self.nodes if n.kind == "Function"}
        assert "Run migration script" in func_names
        assert "Verify migration" in func_names

    def test_rescue_tasks_extracted(self):
        func_names = {n.name for n in self.nodes if n.kind == "Function"}
        assert "Log migration failure" in func_names

    def test_block_tasks_parented_to_play(self):
        block_task = next(
            n for n in self.nodes
            if n.kind == "Function" and n.name == "Run migration script"
        )
        assert block_task.parent_name == "Configure web servers"

    def test_file_contains_plays(self):
        file_path_str = str(_PLAYBOOK)
        file_contains = {e.target for e in self.edges
                         if e.kind == "CONTAINS" and e.source == file_path_str}
        assert any("Configure web servers" in t for t in file_contains)

    def test_line_numbers_positive(self):
        for n in self.nodes:
            assert n.line_start > 0, f"{n.name} has line_start={n.line_start}"
            assert n.line_end >= n.line_start, f"{n.name} has bad line range"

    def test_all_nodes_language_ansible(self):
        for n in self.nodes:
            assert n.language == "ansible", f"{n.name} has language={n.language!r}"


@_ANSIBLE_SKIP
class TestAnsibleTasksParsing:
    def setup_method(self):
        self.parser = CodeParser()
        self.nodes, self.edges = self.parser.parse_file(_TASKS_FILE)

    def test_file_language_ansible(self):
        file_nodes = [n for n in self.nodes if n.kind == "File"]
        assert file_nodes[0].language == "ansible"

    def test_named_tasks_found(self):
        func_names = {n.name for n in self.nodes if n.kind == "Function"}
        assert "Create app user" in func_names
        assert "Clone repository" in func_names
        assert "Install requirements" in func_names

    def test_nameless_task_fallback_name(self):
        func_names = {n.name for n in self.nodes if n.kind == "Function"}
        fallbacks = [n for n in func_names if "@line" in n and "package" in n.lower()]
        assert fallbacks, "expected a fallback-named task for the nameless package task"

    def test_loop_key_not_misidentified_as_module(self):
        func_names = {n.name for n in self.nodes if n.kind == "Function"}
        assert not any(n.startswith("loop@") or n.startswith("with_") for n in func_names)

    def test_fqcn_include_role_imports_from(self):
        targets = {e.target for e in self.edges if e.kind == "IMPORTS_FROM"}
        assert "shared_config" in targets

    def test_import_tasks_imports_from(self):
        targets = {e.target for e in self.edges if e.kind == "IMPORTS_FROM"}
        assert "deploy_steps.yml" in targets

    def test_include_vars_imports_from(self):
        targets = {e.target for e in self.edges if e.kind == "IMPORTS_FROM"}
        assert "env_vars.yml" in targets

    def test_file_contains_tasks(self):
        file_path_str = str(_TASKS_FILE)
        sources = {e.source for e in self.edges if e.kind == "CONTAINS"}
        assert file_path_str in sources

    def test_tasks_have_no_parent_play(self):
        for n in self.nodes:
            if n.kind == "Function":
                assert n.parent_name is None, f"{n.name} should have no parent_play"


@_ANSIBLE_SKIP
class TestAnsibleMetaParsing:
    def setup_method(self):
        self.parser = CodeParser()
        self.nodes, self.edges = self.parser.parse_file(_META_FILE)

    def test_file_language_ansible(self):
        file_nodes = [n for n in self.nodes if n.kind == "File"]
        assert file_nodes[0].language == "ansible"

    def test_depends_on_bare_string(self):
        dep_targets = {e.target for e in self.edges if e.kind == "DEPENDS_ON"}
        assert "common" in dep_targets

    def test_depends_on_role_key(self):
        dep_targets = {e.target for e in self.edges if e.kind == "DEPENDS_ON"}
        assert "nginx" in dep_targets

    def test_depends_on_name_key_collections(self):
        dep_targets = {e.target for e in self.edges if e.kind == "DEPENDS_ON"}
        assert "security.hardening" in dep_targets
