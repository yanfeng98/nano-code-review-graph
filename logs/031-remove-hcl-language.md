# 031 — Remove Terraform/HCL (hcl) Language Support

**Date:** 2026-08-05
**Branch:** 260802-v2.3.7

## Summary

Removed Terraform/HCL (`hcl`) language support from the parser and downstream
consumers. `.tf` and `.hcl` files are no longer detected as source code
(**user decision: fully remove both** — the `hcl` language covered both the
Terraform `.tf` extension and the generic HashiCorp Configuration Language
`.hcl`). HCL had **no entries** in the four node-type tables (`"hcl": []`), no
shebang mapping, and dispatched entirely through `_extract_hcl_constructs`
(resource/module/variable/data/output/locals/provider/terraform blocks) from
`_extract_from_tree`. Its implementation was a module-level helper section
(`_hcl_text`/`_hcl_child`/`_hcl_block_name`/`_HCL_REF_PREFIXES`/`_hcl_ref_target`/
`_hcl_variable_refs`/`_HCL_RECURSE_TYPES`/`_hcl_for_iterator_names`/
`_hcl_dynamic_iterator_name`/`_HCL_BLOCK_CFG`), the dispatch gate, and four
class methods (`_extract_hcl_constructs`/`_emit_hcl_locals`/
`_hcl_get_attribute_string`/`_walk_hcl_expressions`), plus a standalone
`hcl_resolver.py` (Terraform module-reference resolution) wired into
`incremental.py`. **Ansible is fully decoupled** (independent PyYAML path,
never uses HCL), so Ansible parsing is unaffected. The `tree-sitter-hcl`
grammar remains bundled inside `tree-sitter-language-pack` (a single wheel
with ~170 grammars) and cannot be uninstalled independently, so the removal
is at the code/mapping layer only.

## Changes

### Core code (3 files)
- **`code_review_graph/parser.py`**:
  - Removed `".tf": "hcl"` and `".hcl": "hcl"` from `EXTENSION_TO_LANGUAGE`
  - Removed the four `"hcl": []` node-type table entries with their comments
    (`_CLASS_TYPES`/`_FUNCTION_TYPES`/`_IMPORT_TYPES`/`_CALL_TYPES`)
  - Deleted the module-level `# HCL / Terraform helpers` section (10 symbols:
    7 functions + `_HCL_REF_PREFIXES`/`_HCL_RECURSE_TYPES`/`_HCL_BLOCK_CFG`)
  - Removed the `# --- HCL/Terraform-specific constructs ---` dispatch gate in
    `_extract_from_tree`
  - Deleted the `# HCL / Terraform constructs` class section (4 methods)
  - `_builtin_language_names()` derives from the mappings/tables — auto-excludes
    hcl; shared helpers (`_qualify`/`_resolve_module_to_file`/`_get_parser`) and
    all Ansible code untouched
- **`code_review_graph/hcl_resolver.py`**: Deleted (110 lines,
  `resolve_hcl_module_references`)
- **`code_review_graph/incremental.py`**: Deleted `_run_hcl_resolver` and the
  `"hcl_resolution"` stat key from `full_build`, identity-rebuild, and
  `incremental_update` return dicts, plus the `hcl_changed` update logic

### Tests (2 files edited, 1 file + 1 fixture deleted)
- **`tests/test_multilang.py`**: Deleted `TestHCLParsing` (~35 test methods).
  `TestAnsiblePlaybookParsing`/`TestAnsibleTasksParsing`/`TestAnsibleMetaParsing`
  retained (Ansible unaffected)
- **`tests/test_hcl_parser.py`**: **Deleted** (HCL-specific)
- **`tests/test_windows_path_identity.py`**: Deleted
  `test_hcl_references_use_forward_slashes_for_windows_paths`
- **`tests/fixtures/sample.tf`**: Deleted (sole `.tf` fixture)

### Documentation
- **`README.md`**: Removed `Terraform/OpenTofu 结构（`.tf`；通用 `.hcl` 文件被识别为文件节点）` from language lists (2 places)
- **`docs/FEATURES.md`**: Removed `Terraform/OpenTofu structure (`.tf`; generic `.hcl` files are recognized as file nodes)` from parser-surface list
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `Terraform/OpenTofu structure (`.tf`; generic `.hcl` files are recognized as file nodes)` from languages section

### Not changed
- **Ansible parsing** (`_parse_ansible` family, `_ANSIBLE_*` constants,
  `_is_ansible_path`) — independent PyYAML path
- **`tree-sitter-language-pack`** dependency (hcl grammar bundled in wheel)
- Shared helpers (`_qualify`/`_resolve_module_to_file`/`_get_parser`)
- **`docs/USAGE.md`** (no HCL), **`diagrams/generate_diagrams.py`** (no HCL),
  **`token_benchmark.py`**/**`agent_baseline.py`** (no `.tf`/`.hcl`)
- **`CHANGELOG.md`** (historical Terraform/OpenTofu structural-parsing entry),
  **`.serena/project.yml`** (comment-only), `code-review-graph-vscode/`

## Verification
- `code_review_graph/parser.py` and `incremental.py` import cleanly; zero
  `hcl`/`HCL`/`terraform`/`Terraform`/`.tf`/`.hcl`/`_hcl_`/`_HCL_`/
  `hcl_resolver`/`hcl_resolution` references remain in `code_review_graph/`
  and `tests/`
- 323 tests passed in `test_multilang.py` + `test_windows_path_identity.py` +
  `test_parser.py`
- Full suite: 1869 passed, 5 skipped (2 pre-existing `test_documentation.py`
  failures from a missing `README.hi-IN.md`, unrelated)
- Zero `Terraform`/`HCL` references in docs (except historical records)
- End-to-end: `detect_language(Path("x.tf"))`/`x.hcl` → None;
  `detect_language(Path("x.py"))` still works
- **Ansible retained**: `TestAnsiblePlaybookParsing`/`TestAnsibleTasksParsing`/
  `TestAnsibleMetaParsing` pass
