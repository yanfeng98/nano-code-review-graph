# 017 — Remove PHP (php) Language Support

**Date:** 2026-08-04
**Branch:** 260802-v2.3.7

## Summary

Removed PHP (`.php`/`.blade.php`) language support from the parser and
downstream consumers. `.php` files are no longer detected as source code.
PHP was the most complex of the removed languages: it carried Laravel /
Composer / Blade / PHPUnit framework support, a PHP-specific scoped-call
resolver path in `scoped_resolver.py`, PHPUnit `@Test` annotation handling,
and the `Test` entry in `_TEST_ANNOTATIONS`. The `tree-sitter-php` grammar
remains bundled inside `tree-sitter-language-pack` (a single wheel with
~170 grammars) and cannot be uninstalled independently, so the removal is at
the code/mapping layer only.

## Changes

### Core code (6 files)
- **`code_review_graph/parser.py`**:
  - Removed `".php": "php"` from `EXTENSION_TO_LANGUAGE` and the shebang
    mapping; removed the `.blade.php` → `"blade"` special-case and the
    `_parse_blade`/`_mask_blade_comments` regex parser
  - Removed `"php"` entries from `_CLASS_TYPES`, `_FUNCTION_TYPES`,
    `_IMPORT_TYPES`, `_CALL_TYPES` (shared node-type strings like
    `function_call_expression`/`method_call_expression`/`class_declaration`
    preserved for Perl/TS/Solidity etc.)
  - Removed `"php"` from `_TYPED_CALL_LANGUAGES` and `block_types`;
    removed `"Test"` from `_TEST_ANNOTATIONS` (PHP was the last producer;
    Rust entries kept)
  - Deleted the PHP/Laravel framework function block (`_resolve_php_scoped_calls`,
    `_extract_php_laravel_edges`, `_walk_php_laravel_*`, `_php_*`,
    `_emit_laravel_*`), the Composer PSR-4 loader (`_read_php_composer_psr4`,
    `_resolve_php_composer_module`, `_php_repository_boundary`,
    `_find_php_composer_psr4`), and the PHPUnit helpers
    (`_php_attribute_aliases`, `_php_attribute_names`, `_php_docblock_marks_test`,
    `_PHPUNIT_TEST_ATTRIBUTE`, `_PHP_TEST_DOC_TAG_RE`)
  - Removed the `_php_assigned_variables` method and simplified the
    `assigned_names` logic in `_collect_typed_call_targets` (now PHP-free);
    removed the `constructed_receiver` evidence branch in `_apply_typed_call_targets`
  - Removed ~13 `language == "php"` branches (typed bindings, import collection,
    module resolution, `_get_bases`, `_extract_import`, `_get_call_name`,
    `_get_member_call_receiver_method`, `_extract_functions` PHPUnit naming)
  - Note: restored `_find_dart_pubspec_root` which sits adjacent to the removed
    Composer functions (it belongs to Dart support)
- **`code_review_graph/scoped_resolver.py`**: Rust-only now —
  `_SCOPED_LANGUAGES = ("rust",)`, removed `_RECEIVER_SCOPE_LANGUAGES` and the
  receiver_scope branch, removed `_PHP_SELF_SCOPES`, made `_fold` the identity
  function, removed the PHP branches in `_safe_import_suffixes` and
  `_scope_and_method`; rewrote the module docstring and comments
- **`code_review_graph/flows.py`**: Deleted the PHP-only
  `_LANGUAGE_ENTRY_NAME_PATTERNS` dict and its consumer loop
- **`code_review_graph/incremental.py`**: Deleted the Laravel/Composer ignore
  patterns (`**/vendor/**`, `/storage/**`, `/bootstrap/cache/**`,
  `/public/build/**`); changed the scoped-resolver trigger
  `(".php", ".rs")` → `(".rs",)` (Rust still triggers it)
- **`code_review_graph/token_benchmark.py`**, **`eval/benchmarks/agent_baseline.py`**:
  Removed `.php` from source-extension tuples

### Tests (2 files deleted + 7 edited + 1 fixture deleted)
- **Deleted**: `tests/test_php_scoped_calls.py`, `tests/test_php_laravel.py`
- **`tests/test_multilang.py`**: Deleted `TestPHPParsing`,
  `TestPHPTestAnnotations`, `TestPHPImportResolution`; removed `PHP` from
  module docstring
- **`tests/test_language_reconciliation.py`**: Deleted
  `TestPHPScopedCallReconciliation`
- **`tests/test_flows.py`**: Deleted `test_php_entry_names_are_language_scoped`
- **`tests/test_graph.py`**: Deleted
  `test_get_node_bridge_keeps_php_backslashes_in_symbol_part`
- **`tests/test_windows_path_identity.py`**: Deleted
  `test_php_namespace_backslashes_survive_normalization`
- **`tests/test_incremental.py`**: Removed DEFAULT-dependent Laravel/vendor
  assertions (kept explicit-pattern-list assertions, which still pass)
- **`tests/test_parser.py`**: Updated a docstring comment
- **`tests/fixtures/sample.php`**: Deleted

### Documentation
- **`README.md`**: Removed `PHP` from language lists (2 places), deleted the
  Composer/Blade/Laravel paragraph and the framework-aware PHP parsing table
  row, updated the flow-detection note
- **`docs/FEATURES.md`**: Deleted the Framework-aware PHP parsing feature and
  removed `PHP` from parser-surface list
- **`docs/USAGE.md`**: Removed `PHP` from supported-languages and shebang lists
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `PHP` from languages section
- **`docs/GITHUB_ACTION.md`**: Updated the lockfile cache-key note
- **`skills/build-graph/SKILL.md`**: Removed `PHP` from supported-languages list
- **`diagrams/generate_diagrams.py`**: Scripting group removed `PHP`;
  regenerated `.excalidraw` sources
- **`action.yml`**: Removed `**/composer.lock` from the cache-key hash glob
- **Deleted 2 PHP-dedicated docs**: `docs/superpowers/specs/2026-07-17-php-laravel-parser-design.md`,
  `docs/superpowers/plans/2026-07-17-php-laravel-parser.md`

### Not changed
- **`tree-sitter-language-pack`** dependency (php grammar bundled in wheel,
  cannot be uninstalled separately)
- **`_qualify`/`normalize_file_path`** backslash handling (generic FQN support,
  no longer PHP-specific)
- **`CHANGELOG.md`**, `docs/MAINTAINER_RECONCILIATION_2026-07-17.md`, historical
  records
- **`.serena/project.yml`** (comment-only language list), `code-review-graph-vscode/`

## Verification
- `code_review_graph/parser.py` and `scoped_resolver.py` import cleanly; zero
  `php`/`blade`/`composer`/`laravel` references remain in `code_review_graph/`
- 705 tests passed in edited files (multilang, language reconciliation, flows,
  graph, windows path identity, incremental, parser) — including the restored
  Dart `_find_dart_pubspec_root` tests
- Zero `PHP`/`composer`/`laravel`/`blade` references in docs
- Diagram source regenerated
