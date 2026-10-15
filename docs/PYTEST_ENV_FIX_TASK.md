# 测试环境修复任务（pytest 基线失败）

> 状态：**独立任务，本阶段不处理**（按负责人要求从 P0 开发任务中剥离）。
> 本文件只登记现象与定位，供后续单独立项。

## 1. 背景

在本阶段（B1/B2 + 专业选择链）开发过程中，后端 `pytest` 存在 **15 个失败**。
这些失败在**改动前就已存在**，与本阶段任何改动无关，已用失败清单前后 diff 证明：

```text
baseline failures: 15    after failures: 15
新增失败: （空）
```

复现命令：

```powershell
cd backend
python -m pytest -q
```

## 2. 失败清单（基线，15 项）

```text
tests/test_curriculum_case.py::test_saved_demo_output_matches_the_runtime_result
tests/test_curriculum_case.py::test_saved_elective_demo_computes_only_the_confirmed_remaining_selection
tests/test_curriculum_case.py::test_real_case_cannot_reuse_mock_elective_selection_evidence
tests/test_curriculum_cli.py::test_case_cli_only_prints_statistics_for_private_input
tests/test_curriculum_docx_reader.py::test_duplicate_or_unsafe_archive_members_are_rejected[word\DEMO-PRIVATE-PART]
tests/test_curriculum_file_case.py::test_private_office_files_flow_through_computed_provider_with_original_locations
tests/test_curriculum_file_case.py::test_case_cli_does_not_publish_private_word_rows_or_file_paths
tests/test_curriculum_file_case.py::test_missing_word_identity_is_preserved_in_draft_and_blocks_whole_case
tests/test_curriculum_file_case.py::test_in_memory_normalization_never_opens_file_references[old]
tests/test_curriculum_file_case.py::test_in_memory_normalization_never_opens_file_references[new]
tests/test_curriculum_file_case.py::test_in_memory_normalization_never_opens_file_references[completed]
tests/test_curriculum_file_case.py::test_ambiguous_inline_and_file_inputs_are_rejected_without_fallback[old]
tests/test_curriculum_file_case.py::test_ambiguous_inline_and_file_inputs_are_rejected_without_fallback[completed]
tests/test_curriculum_file_case.py::test_blocked_group_case_remains_inspectable_without_projecting_partial_tasks
tests/test_curriculum_json_reader.py::test_remote_or_invalid_local_references_have_redacted_errors[bad\x00path]
```

## 3. 已初步定位的两类根因

### 3.1 中文路径 / GBK locale 导致的 UnicodeDecodeError（约 14 项）

```text
UnicodeDecodeError: 'gbk' codec can't decode byte 0x80 in position 289: illegal multibyte sequence
  at pathlib.Path.read_text()  ← 默认 encoding='locale'
  self = WindowsPath('C:/Users/.../AI+教育/AI-education-fe2/mock_data/curriculum_demo/case.json')
```

- 现象：`Path.read_text()` / `open()` 未显式指定 `encoding`，在中文 Windows
  上回退到 GBK，而文件是 UTF-8。
- 影响面：`app/curriculum/json_reader.py`、`docx_reader.py`、`cli` 及
  `test_curriculum_file_case.py` 相关用例。
- ⚠️ 注意：生产路径 `load_json_input()` 是**显式 UTF-8**（`raw.decode("utf-8")`），
  因此这更像是**测试/CLI 侧的编码假设**问题，需先确认到底是哪一层在用 locale 编码。

### 3.2 `bad\x00path` 未按预期抛错（1 项）

```text
tests/test_curriculum_json_reader.py::test_remote_or_invalid_local_references_have_redacted_errors[bad\x00path]
Failed: DID NOT RAISE CurriculumNormalizationError
```

- 现象：含 NUL 的路径未触发校验失败。
- 待查：`resolve_local_input()` 在 Windows 上对 `\x00` 的处理（可能被提前拒绝
  并抛出别的异常类型，或 Python 版本行为变化）。

## 4. 为什么必须单独立项

1. 失败集中在 **Curriculum 模块的测试/CLI 基础设施**，与本阶段的
   前端接线、匹配解释层无关；
2. 修复需要动 `json_reader` / `docx_reader` / CLI 等**共享底层**，
   属于跨模块改动，应当独立评审；
3. 在本阶段顺手修复会混入大量无关 diff，破坏 review 的可追溯性。

## 5. 建议的立项内容

```text
范围：backend 测试与 CLI 的编码/路径校验基础设施
目标：pytest 全绿（0 failed）
约束：⛔ 不改业务判定逻辑；⛔ 不放宽任何 fail-closed 校验；
     编码修复必须显式指定 encoding="utf-8"，不得依赖 locale
验收：pytest -q 全通过；现有 15 项失败全部消除且无新增
风险：json_reader / docx_reader 是共享底层，需全量回归
```

## 6. 本阶段的处理结论

- ⛔ **不修**（按负责人指示）；
- ✅ 已用失败清单 diff 证明**本阶段未引入任何新失败**；
- ✅ 本阶段的验收以「失败集合与基线完全一致」为准。
