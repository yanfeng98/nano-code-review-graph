"""Tests for Go, Rust, C, C++, and Vue parsing."""

from pathlib import Path

import pytest

from code_review_graph.parser import CodeParser

FIXTURES = Path(__file__).parent / "fixtures"


class TestGoParsing:
    def setup_method(self):
        self.parser = CodeParser()
        self.nodes, self.edges = self.parser.parse_file(FIXTURES / "sample_go.go")

    def test_detects_language(self):
        assert self.parser.detect_language(Path("main.go")) == "go"

    def test_finds_structs_and_interfaces(self):
        classes = [n for n in self.nodes if n.kind == "Class"]
        names = {c.name for c in classes}
        assert "User" in names
        assert "InMemoryRepo" in names
        assert "UserRepository" in names

    def test_finds_functions(self):
        funcs = [n for n in self.nodes if n.kind == "Function"]
        names = {f.name for f in funcs}
        assert "NewInMemoryRepo" in names
        assert "CreateUser" in names

    def test_finds_imports(self):
        imports = [e for e in self.edges if e.kind == "IMPORTS_FROM"]
        targets = {e.target for e in imports}
        assert "errors" in targets
        assert "fmt" in targets

    def test_finds_calls(self):
        calls = [e for e in self.edges if e.kind == "CALLS"]
        assert len(calls) >= 1

    def test_finds_contains(self):
        contains = [e for e in self.edges if e.kind == "CONTAINS"]
        assert len(contains) >= 3

    def test_methods_attached_to_receiver(self):
        """Go methods should be attached to their receiver type (#190).

        `func (r *InMemoryRepo) FindByID(...)` should produce a Function node
        with parent_name='InMemoryRepo' and a CONTAINS edge from the type to
        the method, so `inheritors_of`/`query_graph` can find methods via the
        struct they belong to.
        """
        funcs = [n for n in self.nodes if n.kind == "Function"]
        by_name = {f.name: f for f in funcs}
        assert "FindByID" in by_name
        assert "Save" in by_name
        assert by_name["FindByID"].parent_name == "InMemoryRepo"
        assert by_name["Save"].parent_name == "InMemoryRepo"
        # Free functions should still have no parent.
        assert by_name["NewInMemoryRepo"].parent_name is None
        assert by_name["CreateUser"].parent_name is None

        contains = [(e.source, e.target) for e in self.edges if e.kind == "CONTAINS"]
        find_by_id_contains = [
            (s, t) for (s, t) in contains
            if t.endswith("::InMemoryRepo.FindByID")
        ]
        save_contains = [
            (s, t) for (s, t) in contains
            if t.endswith("::InMemoryRepo.Save")
        ]
        assert find_by_id_contains, (
            f"no CONTAINS edge for InMemoryRepo.FindByID in {contains}"
        )
        assert save_contains, (
            f"no CONTAINS edge for InMemoryRepo.Save in {contains}"
        )
        # Source of each CONTAINS should be the InMemoryRepo type,
        # not the file path.
        assert find_by_id_contains[0][0].endswith("::InMemoryRepo")
        assert save_contains[0][0].endswith("::InMemoryRepo")


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


class TestVueParsing:
    def setup_method(self):
        self.parser = CodeParser()
        self.nodes, self.edges = self.parser.parse_file(FIXTURES / "sample_vue.vue")

    def test_detects_language(self):
        assert self.parser.detect_language(Path("App.vue")) == "vue"

    def test_finds_functions(self):
        funcs = [n for n in self.nodes if n.kind == "Function"]
        names = {f.name for f in funcs}
        assert "increment" in names
        assert "onSelectUser" in names
        assert "fetchUsers" in names

    def test_finds_imports(self):
        imports = [e for e in self.edges if e.kind == "IMPORTS_FROM"]
        targets = {e.target for e in imports}
        assert "vue" in targets
        assert "./UserList.vue" in targets

    def test_finds_contains(self):
        contains = [e for e in self.edges if e.kind == "CONTAINS"]
        assert len(contains) >= 3

    def test_nodes_have_vue_language(self):
        for node in self.nodes:
            assert node.language == "vue"

    def test_finds_calls(self):
        calls = [e for e in self.edges if e.kind == "CALLS"]
        assert len(calls) >= 1


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



class TestRescriptParser:
    def setup_method(self):
        self.parser = CodeParser()
        self.nodes, self.edges = self.parser.parse_file(FIXTURES / "sample.res")

    def test_detects_language_for_res_and_resi(self):
        assert self.parser.detect_language(Path("lib.res")) == "rescript"
        assert self.parser.detect_language(Path("lib.resi")) == "rescript"

    def test_file_node(self):
        files = [n for n in self.nodes if n.kind == "File"]
        assert len(files) == 1
        assert files[0].language == "rescript"
        assert files[0].extra.get("rescript_interface") is not True

    def test_finds_top_level_modules(self):
        classes = [n for n in self.nodes if n.kind == "Class"]
        names = {c.name for c in classes}
        assert {"User", "App", "Validator"}.issubset(names)

    def test_nested_module_has_parent(self):
        validator = next(
            n for n in self.nodes if n.kind == "Class" and n.name == "Validator"
        )
        assert validator.parent_name == "User"

    def test_finds_top_level_lets(self):
        funcs = [n for n in self.nodes if n.kind == "Function"]
        names = {f.name for f in funcs}
        assert "main" in names
        assert "defaultTimeout" in names
        assert "fact" in names
        assert "helper" in names

    def test_let_inside_let_body_is_not_top_level(self):
        # `let u = ...` inside App.start should NOT appear as a Function node.
        funcs = [n for n in self.nodes if n.kind == "Function"]
        names = {f.name for f in funcs}
        assert "u" not in names
        assert "valid" not in names
        assert "n" not in names

    def test_external_binding_extracted(self):
        funcs = [n for n in self.nodes if n.kind == "Function"]
        by_name = {f.name: f for f in funcs}
        assert "readFile" in by_name
        assert by_name["readFile"].extra.get("rescript_external") is True

    def test_module_attr_creates_import_edge(self):
        imports = [e for e in self.edges if e.kind == "IMPORTS_FROM"]
        targets = {e.target for e in imports}
        assert "fs" in targets

    def test_open_and_include_create_import_edges(self):
        imports = [e for e in self.edges if e.kind == "IMPORTS_FROM"]
        targets = {e.target for e in imports}
        assert "Belt" in targets
        assert "Js.Promise" in targets

    def test_types_extracted(self):
        types = [n for n in self.nodes if n.kind == "Type"]
        names = {t.name for t in types}
        assert {"status", "result", "t", "config"}.intersection(names)

    def test_member_let_has_parent_module(self):
        funcs = [n for n in self.nodes if n.kind == "Function"]
        by_name = {f.name: f for f in funcs}
        assert by_name["greet"].parent_name == "User"
        assert by_name["isAdult"].parent_name == "Validator"
        assert by_name["start"].parent_name == "App"

    def test_calls_attributed_to_enclosing_let(self):
        calls = [e for e in self.edges if e.kind == "CALLS"]
        sources = {e.source for e in calls}
        targets = {e.target for e in calls}
        assert any(s.endswith("::App.start") for s in sources)
        assert "User.make" in targets or any(
            t.endswith("::User.make") for t in targets
        )

    def test_contains_edges_wire_module_to_members(self):
        contains = [e for e in self.edges if e.kind == "CONTAINS"]
        targets = {e.target for e in contains}
        assert any(t.endswith("::User.greet") for t in targets)
        assert any(t.endswith("::Validator.isAdult") for t in targets)

    def test_nodes_have_rescript_language(self):
        non_file = [n for n in self.nodes if n.kind != "File"]
        assert all(n.language == "rescript" for n in non_file)


class TestRescriptInterfaceParser:
    def setup_method(self):
        self.parser = CodeParser()
        self.nodes, self.edges = self.parser.parse_file(FIXTURES / "sample.resi")

    def test_file_flagged_as_interface(self):
        file_node = next(n for n in self.nodes if n.kind == "File")
        assert file_node.extra.get("rescript_interface") is True

    def test_modules_extracted_from_interface(self):
        classes = [n for n in self.nodes if n.kind == "Class"]
        names = {c.name for c in classes}
        assert "User" in names
        assert "App" in names
        assert "Validator" in names

    def test_signatures_extracted_without_bodies(self):
        funcs = [n for n in self.nodes if n.kind == "Function"]
        names = {f.name for f in funcs}
        # Top-level and module-member signatures should both appear.
        assert "defaultTimeout" in names
        assert "fact" in names
        assert "make" in names
        assert "greet" in names
        assert "isAdult" in names
        assert "start" in names

    def test_external_signature_extracted(self):
        funcs = [n for n in self.nodes if n.kind == "Function"]
        by_name = {f.name: f for f in funcs}
        assert "readFile" in by_name
        assert by_name["readFile"].extra.get("rescript_external") is True

    def test_no_calls_extracted_from_interface(self):
        calls = [e for e in self.edges if e.kind == "CALLS"]
        assert calls == []


class TestRescriptEdgeCases:
    """Bug-fix tests: IMPORTS_FROM dedup, JS binding tag, JSX, module alias."""

    def setup_method(self):
        self.parser = CodeParser()
        self.nodes, self.edges = self.parser.parse_file(FIXTURES / "sample.res")

    def test_duplicate_open_produces_single_import_edge(self):
        # sample.res has `open Belt` twice — should emit only one edge.
        belt_edges = [
            e for e in self.edges
            if e.kind == "IMPORTS_FROM" and e.target == "Belt"
        ]
        assert len(belt_edges) == 1

    def test_module_alias_emits_import_edge(self):
        # `module IntMap = Belt.Map.Int` → IMPORTS_FROM Belt.Map.Int
        aliases = [
            e for e in self.edges
            if e.extra.get("rescript_import_kind") == "module_alias"
        ]
        assert any(e.target == "Belt.Map.Int" for e in aliases)
        assert any(e.extra.get("alias_name") == "IntMap" for e in aliases)

    def test_module_alias_is_not_treated_as_block_module(self):
        # IntMap is an alias — should NOT appear as a Class node.
        classes = [n for n in self.nodes if n.kind == "Class"]
        names = {c.name for c in classes}
        assert "IntMap" not in names

    def test_js_binding_module_is_tagged(self):
        text_encoder = next(
            n for n in self.nodes if n.kind == "Class" and n.name == "TextEncoder"
        )
        assert text_encoder.extra.get("rescript_kind") == "js_binding"

    def test_regular_module_keeps_module_tag(self):
        user = next(
            n for n in self.nodes if n.kind == "Class" and n.name == "User"
        )
        assert user.extra.get("rescript_kind") == "module"

    def test_jsx_emits_import_and_call_edges(self):
        jsx_imports = [
            e for e in self.edges
            if e.extra.get("rescript_import_kind") == "jsx"
        ]
        jsx_targets = {e.target for e in jsx_imports}
        assert "Layout" in jsx_targets
        assert "User" in jsx_targets
        assert "AnalyticsFilterUi" in jsx_targets

        jsx_calls = [
            e for e in self.edges
            if e.kind == "CALLS"
            and e.extra.get("rescript_call_kind") == "jsx"
        ]
        call_targets = {e.target for e in jsx_calls}
        assert "User.Badge" in call_targets
        assert "AnalyticsFilterUi.Filter" in call_targets

    def test_jsx_call_attributed_to_enclosing_let(self):
        jsx_calls = [
            e for e in self.edges
            if e.kind == "CALLS"
            and e.extra.get("rescript_call_kind") == "jsx"
        ]
        assert all(e.source.endswith("::render") for e in jsx_calls)


class TestRescriptCrossModuleResolver:
    """Integration test for the cross-module resolver post-pass."""

    def _build(self, tmp_path):
        from code_review_graph.graph import GraphStore
        from code_review_graph.incremental import full_build

        (tmp_path / ".git").mkdir()

        (tmp_path / "LogicUtils.res").write_text(
            "let safeParse = (s) => s\n"
            "let trim = (s) => s\n"
        )
        (tmp_path / "CurrencyFormatUtils.res").write_text(
            "let format = (n) => n\n"
        )
        (tmp_path / "Caller.res").write_text(
            "open CurrencyFormatUtils\n"
            "let run = () => {\n"
            "  let a = LogicUtils.safeParse(\"x\")\n"
            "  let b = LogicUtils.safeParse(\"y\")\n"
            "  let c = format(12.0)\n"
            "  let d = <Layout name=\"hi\" />\n"
            "  (a, b, c, d)\n"
            "}\n"
        )
        (tmp_path / "Layout.res").write_text(
            "let make = (~name) => name\n"
        )

        store = GraphStore(tmp_path / "graph.db")
        result = full_build(tmp_path, store)
        return store, result

    def test_qualified_call_resolves_to_canonical_node(self, tmp_path):
        store, _ = self._build(tmp_path)
        cur = store._conn.cursor()
        rows = cur.execute(
            "SELECT target_qualified FROM edges "
            "WHERE kind='CALLS' AND source_qualified LIKE '%Caller.res::run'"
        ).fetchall()
        targets = {r["target_qualified"] for r in rows}
        # Both LogicUtils.safeParse callsites should now point to the canonical
        # node path, not the bare `LogicUtils.safeParse` string.
        assert any(
            t.endswith("LogicUtils.res::safeParse") for t in targets
        ), f"no canonical resolution in {targets}"
        assert not any(t == "LogicUtils.safeParse" for t in targets)

    def test_callers_of_canonical_node_finds_both_sites(self, tmp_path):
        store, _ = self._build(tmp_path)
        # Two calls to safeParse from the same caller — both should survive
        # as separate edges pointing to the canonical node.
        cur = store._conn.cursor()
        count = cur.execute(
            "SELECT COUNT(*) as c FROM edges "
            "WHERE kind='CALLS' "
            "AND target_qualified LIKE '%LogicUtils.res::safeParse'"
        ).fetchone()["c"]
        assert count == 2

    def test_bare_call_resolves_via_open_directive(self, tmp_path):
        store, _ = self._build(tmp_path)
        cur = store._conn.cursor()
        rows = cur.execute(
            "SELECT target_qualified FROM edges WHERE kind='CALLS' "
            "AND target_qualified LIKE '%CurrencyFormatUtils.res::format'"
        ).fetchall()
        assert len(rows) == 1

    def test_imports_from_rewrites_to_file_path(self, tmp_path):
        store, _ = self._build(tmp_path)
        cur = store._conn.cursor()
        rows = cur.execute(
            "SELECT target_qualified FROM edges WHERE kind='IMPORTS_FROM' "
            "AND file_path LIKE '%Caller.res'"
        ).fetchall()
        targets = {r["target_qualified"] for r in rows}
        # `open CurrencyFormatUtils` and `<Layout />` should both resolve
        # to file paths.
        assert any(t.endswith("CurrencyFormatUtils.res") for t in targets)
        assert any(t.endswith("Layout.res") for t in targets)

    def test_resolver_stats_in_build_result(self, tmp_path):
        _, result = self._build(tmp_path)
        stats = result["rescript_resolution"]
        assert stats["files_indexed"] == 4
        assert stats["calls_resolved"] >= 3
        assert stats["imports_resolved"] >= 2

    def test_resolver_is_idempotent(self, tmp_path):
        from code_review_graph.rescript_resolver import (
            resolve_rescript_cross_module,
        )
        store, _ = self._build(tmp_path)
        second = resolve_rescript_cross_module(store)
        # Second run should find nothing new — all already resolved.
        assert second["calls_resolved"] == 0
        assert second["imports_resolved"] == 0

class TestNixParsing:
    """Flake-aware Nix parser — see the Nix language-support epic."""

    def setup_method(self):
        self.parser = CodeParser()
        # Parse the flake-shaped fixture as if its basename were ``flake.nix``
        # so the ``inputs.*.url`` branch of _extract_nix_constructs fires.
        flake_bytes = (FIXTURES / "sample.nix").read_bytes()
        self.flake_path = FIXTURES / "flake.nix"
        self.flake_nodes, self.flake_edges = self.parser.parse_bytes(
            self.flake_path, flake_bytes,
        )
        # The non-flake fixture retains its actual path; it's used to verify
        # the flake-input branch does *not* fire on non-flake files.
        module_path = FIXTURES / "sample_module.nix"
        self.module_nodes, self.module_edges = self.parser.parse_file(module_path)

    def test_detects_language(self):
        assert self.parser.detect_language(Path("flake.nix")) == "nix"
        assert self.parser.detect_language(Path("modules/foo.nix")) == "nix"

    def test_nodes_have_nix_language(self):
        for n in self.flake_nodes:
            assert n.language == "nix"
        for n in self.module_nodes:
            assert n.language == "nix"

    def test_top_level_bindings_become_functions(self):
        funcs = {n.name for n in self.flake_nodes if n.kind == "Function"}
        # Top-level bindings from sample.nix (flake-shaped).
        assert "description" in funcs
        assert "inputs" in funcs
        assert "outputs" in funcs
        # Nested bindings flattened to dotted names.
        assert "packages.default" in funcs
        assert "devShells.default" in funcs

    def test_flake_inputs_produce_import_edges(self):
        targets = {
            e.target for e in self.flake_edges if e.kind == "IMPORTS_FROM"
        }
        assert "github:NixOS/nixpkgs/nixos-unstable" in targets
        assert "github:numtide/flake-utils" in targets

    def test_import_and_callpackage_produce_import_edges(self):
        targets = {
            e.target for e in self.flake_edges if e.kind == "IMPORTS_FROM"
        }
        # callPackage ./default.nix and import ./shell.nix. Relative paths
        # are resolved against the caller's directory when possible; since
        # neither file exists alongside the fixture, the raw relative
        # path is preserved.
        assert "./default.nix" in targets
        assert "./shell.nix" in targets

    def test_non_flake_file_has_no_input_edges(self):
        # ``sample_module.nix`` is not named ``flake.nix``, so the
        # inputs.*.url branch must not fire — no github:-prefixed targets.
        targets = [
            e.target for e in self.module_edges if e.kind == "IMPORTS_FROM"
        ]
        assert not any(t.startswith("github:") for t in targets)
        # The import ./foo.nix inside the `let` body still produces an edge.
        assert any("foo.nix" in t for t in targets)

    def test_contains_edges_wire_file_to_top_level_bindings(self):
        file_path = self.flake_path.as_posix()
        contains_targets = {
            e.target for e in self.flake_edges
            if e.kind == "CONTAINS" and e.source == file_path
        }
        # Each top-level binding should be CONTAINS-linked from the file.
        for name in ("description", "inputs", "outputs"):
            qualified = f"{file_path}::{name}"
            assert qualified in contains_targets, (
                f"missing CONTAINS edge for {qualified}"
            )


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


class TestZigParsing:
    def setup_method(self):
        self.parser = CodeParser()
        self.fixture = FIXTURES / "sample_zig.zig"
        self.nodes, self.edges = self.parser.parse_file(self.fixture)

    def test_detects_language(self):
        assert self.parser.detect_language(Path("main.zig")) == "zig"

    def test_finds_top_level_functions(self):
        funcs = {
            n.name for n in self.nodes
            if n.kind == "Function" and n.parent_name is None
        }
        assert {"main", "helper"} <= funcs

    def test_finds_struct_methods(self):
        methods = {
            n.name for n in self.nodes
            if n.kind == "Function" and n.parent_name == "Point"
        }
        assert {"init", "distance"} <= methods

    def test_finds_struct_enum_union_classes(self):
        classes = {
            n.name: n.extra.get("zig_kind") for n in self.nodes
            if n.kind == "Class"
        }
        assert classes.get("Point") == "struct"
        assert classes.get("Color") == "enum"
        assert classes.get("Shape") == "union"

    def test_finds_imports(self):
        imports = [e for e in self.edges if e.kind == "IMPORTS_FROM"]
        targets = {e.target for e in imports}
        # std stays unresolved (no relative .zig path); util resolves to
        # the absolute fixture path.
        assert "std" in targets
        assert any(
            t.endswith("sample_zig_util.zig") and t != "./sample_zig_util.zig"
            for t in targets
        )

    def test_finds_calls(self):
        calls = [e for e in self.edges if e.kind == "CALLS"]
        # Bare callees (std.debug.print, expect, util.noop) keep their final
        # identifier as the target; same-file helper resolves to the
        # qualified name via _resolve_call_targets.
        bare_targets = {e.target.split("::")[-1] for e in calls}
        assert "print" in bare_targets
        assert "expect" in bare_targets
        assert "helper" in bare_targets

    def test_builtin_calls_emitted(self):
        # @intCast inside Point.distance should produce a CALLS edge
        # whose target is the builtin name (with the leading @).
        targets = {e.target for e in self.edges if e.kind == "CALLS"}
        assert "@intCast" in targets

    def test_at_import_is_not_a_call(self):
        # @import is modelled as IMPORTS_FROM only — never as CALLS, so
        # it doesn't pollute the call graph.
        targets = {e.target for e in self.edges if e.kind == "CALLS"}
        assert "@import" not in targets

    def test_test_block_creates_test_node(self):
        tests = [n for n in self.nodes if n.kind == "Test"]
        assert len(tests) == 1
        assert tests[0].name.startswith("test:helper increments@L")
        assert tests[0].is_test is True

    def test_in_source_test_emits_tested_by_outside_test_path(self):
        path = Path("src/math.zig")
        nodes, edges = self.parser.parse_bytes(
            path,
            b"fn increment(x: i32) i32 { return x + 1; }\n"
            b'test "increment" { try expect(increment(1) == 2); }\n',
        )

        file_node = next(n for n in nodes if n.kind == "File")
        test_node = next(n for n in nodes if n.kind == "Test")
        function_node = next(
            n for n in nodes if n.kind == "Function" and n.name == "increment"
        )
        test_qname = self.parser._qualify(
            test_node.name, test_node.file_path, test_node.parent_name,
        )
        function_qname = self.parser._qualify(
            function_node.name, function_node.file_path, function_node.parent_name,
        )

        assert file_node.is_test is False
        assert any(
            edge.kind == "CALLS"
            and edge.source == test_qname
            and edge.target == function_qname
            for edge in edges
        )
        assert any(
            edge.kind == "TESTED_BY"
            and edge.source == function_qname
            and edge.target == test_qname
            for edge in edges
        )

    def test_calls_inside_methods_have_qualified_source(self):
        # Point.distance calls helper(...) — the source should be the
        # qualified Point.distance name, not the bare file path.
        sources = {
            e.source.split("::")[-1] for e in self.edges
            if e.kind == "CALLS"
        }
        assert "Point.distance" in sources

    def test_nodes_have_zig_language(self):
        for node in self.nodes:
            assert node.language == "zig"


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
