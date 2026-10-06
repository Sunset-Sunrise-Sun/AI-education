# Store-backed CourseDataProvider（内部）

> 实现：`backend/app/course_data/store_provider.py`（`StoreBackedCourseDataProvider`）
> 内部查询：`backend/app/course_data/store.py`（`load_course_offerings_for_acceptance`）
> ⛔ 不改 `CourseDataProvider` Protocol、⛔ 不改 `CourseOffering` 公共 Schema、⛔ 零网络。

## 为什么需要它

`SnapshotCourseDataProvider` 持有的是**一份内存快照**；真实链路的数据落在 SQLite 里。
而**"这个学期的所有行"并不等于"某一次 full-semester acceptance 的那批行"**：

```text
load_course_offerings(semester)          = 该学期库里**当前所有**行
                                           （含旧 campus import / 其它 artifact / 陈旧行）
load_course_offerings_for_acceptance()   = 只属于该次 full-semester acceptance 的行
```

campus-scoped artifact 与 full-semester acceptance 可以**共存于同一个库**，
因此 production Provider 必须绑定到**某一次具体 acceptance**，而不是"这个学期有什么就用什么"。

## 构造契约（fail closed）

```python
StoreBackedCourseDataProvider(
    sqlite_path=...,
    semester="2026-1",
    acceptance_sha256="<full-semester manifest SHA-256>",
)
```

构造时必须**全部**成立，否则 `CourseDataAcceptanceError`（⛔ 不返回半成品 Provider）：

```text
恰好一条 provenance 记录匹配 (semester, scope_kind=full_semester, scope_id=semester, sha)
  completeness   == "complete"
  loaded_count   == reported_total
  offering_count > 0
  实际绑定行数    == provenance.offering_count        （⛔ 不采信自报数字）
```

拒绝情形（各有测试）：库不存在 / 不是 Course Data 库 / 空库 / **campus-only 库** /
SHA 不对 / scope_kind 或 scope_id 不对 / `completeness != complete` /
计数不自洽 / 零行 / 行被删除 / 行的 provenance 被外部改写 / `meetings_json` 被篡改 /
semester 或 digest 形态非法 / `sqlite_path` 类型非法。

## 读取契约

```python
provider.get_course_offerings("2026-1")   # → list[CourseOffering]（只含绑定行）
provider.get_course_offerings("2026-2")   # → CourseDataAcceptanceError（fail closed）
```

- `semester` 必须**精确等于**构造时绑定的学期；⛔ **不返回空列表**、⛔ 不 fallback；
- 每次调用都**重新按 acceptance 绑定读回**并与构造时的行数比对：
  构造之后若有别的 import 覆盖了其中某些行的 provenance（或库被外部修改），
  ⛔ **不会**静默返回"少了几行"的数据，而是 fail closed；
- 顺序确定：`ORDER BY course_id, class_id`；
- 只读：⛔ 不写库、⛔ 不联网、⛔ 不读认证材料；
- 结构上满足冻结的 `CourseDataProvider`（`docs/interfaces/integration.md`），
  但**不继承、不修改**它：签名仍是 `get_course_offerings(self, semester)`。

## 行级 provenance 语义（⛔ 不得改动）

`course_offering` 表的 `artifact_sha256` / `scope_kind` / `scope_id`
记录的是**最后一次写入该行的那次 import**（见 `import_offering_snapshot`）。因此：

| 情形 | 结果 |
| --- | --- |
| 该行属于本次 acceptance | 返回 |
| 该行只被 campus artifact 写过 | 排除（陈旧行隔离） |
| 该行被**后来的** campus import 覆盖过 provenance | 从集合中**消失** ⇒ 行数对账失败 ⇒ fail closed |
| 其它学期的行 | 排除 |

⛔ **不需要新增表**：行级 provenance 列已经足以绑定 acceptance；
⛔ 也**未**改动 `load_course_offerings()` 的既有语义（它仍然返回整学期所有行）。

## 与 runtime 的关系（Gate C 才接线）

本模块**只提供 Provider**：⛔ 不读环境变量、⛔ 不装配 `PlanningOrchestrator`、
⛔ 不接 API、⛔ 不 fallback 到 Mock。`APP_COURSE_DATA_SQLITE_PATH` /
`APP_COURSE_DATA_SEMESTER` / `APP_COURSE_DATA_ACCEPTANCE_SHA256` 的接线属于
**Gate C（runtime replacement）**。

## 非空泛性（mutation sweep）

`mutate_store_provider.py`（development-only，⛔ 不入库）对
`store_provider.py` + 新增的 store 查询施加 **18** 处唯一锚点变异：

```text
killed = 13 / 18
equivalent = 5（⛔ 已逐个注明原因，不删除、不计为 killed）
  B03 loaded_count != offering_count   → 构造时的行数对账拦下同一形态
  B04 offering_count <= 0              → 同上（冗余但保留以尽早报错）
  B05 records 为空                     → 与 `len(records) != 1` 互为冗余
  B06 len(records) != 1                → 主键保证匹配记录至多一条
  B09 artifact_sha256 筛选             → SHA 不对时按该 SHA 读回 0 行 ⇒ 行数对账拦下
survived = 0
```
