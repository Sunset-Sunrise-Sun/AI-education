# Store-backed CourseDataProvider（内部）

> 实现：`backend/app/course_data/store_provider.py`（`StoreBackedCourseDataProvider`）
> 权威读取：`store.load_accepted_offerings()`（content-bound 平面 + membership）
> ⛔ 不改 `CourseDataProvider` Protocol、⛔ 不改 `CourseOffering` 公共 Schema、⛔ 零网络。

## 为什么需要它

`SnapshotCourseDataProvider` 持有的是**一份内存快照**；真实链路的数据落在 SQLite 里。
而**"这个学期的所有行"并不等于"某一次 full-semester acceptance 的那批行"**：

```text
load_course_offerings(semester)           = 该学期库里**当前所有**行
                                            （含旧 campus import / 其它 artifact / 陈旧行）
load_accepted_offerings(...)              = 只属于该次 acceptance、**且内容仍然一致**的行
load_course_offerings_for_acceptance(...) = 只按行级 provenance 过滤
                                            （⚠️ 不核对内容，仅供诊断，⛔ 非权威路径）
```

## 构造契约（fail closed）

```python
StoreBackedCourseDataProvider(
    sqlite_path=...,
    semester="2026-1",
    acceptance_sha256="<full-semester manifest SHA-256>",
)
```

构造期走**同一条**验证路径（fail fast），⛔ 但**不把结果当作此后读取的依据**。

## 持续验证（BLOCK B4）⛔ 不得退回"构造时校验一次"

```text
每一次 get_course_offerings(semester)
        ↓  同一个一致读事务（store.load_accepted_offerings）
acceptance 元数据仍然存在且精确匹配（semester / scope_kind / scope_id / digest）
两个平面（course_data_import / course_data_acceptance）同时存在且计数一致
completeness == complete；loaded_count == reported_total == offering_count > 0
membership 行数 == offering_count
membership identity 集合 == 实际读到的行集合（既不少也不多）
逐行 offering_payload_sha256 == membership 记录
重算的整批 offering_set_sha256 == 元数据
每行的行级 provenance 仍指向本 acceptance
        ↓  全部通过才返回 rows（⛔ 不缓存 metadata、⛔ 不缓存 rows）
```

因此以下任一情形都会让**下一次读取** fail closed：

```text
acceptance 记录被删除 / 被改写      （reviewer probe：构造后 DELETE course_data_acceptance）
历史导入记录被删除（两个平面不一致）
membership 被删除 / 被改写
某一行的公共字段被替换（同数量 / 同身份）
某一行的行级 provenance 被后来的 campus import 覆盖
acceptance 元数据的 scope / counts 被篡改
```

⛔ 也**不 cache rows**：每次调用都从库里重新物化（`first is not second`）。

## 单一 consistent read snapshot（R-SNAPSHOT，第三轮 Red-Team BLOCK）

上面的验证序列是**多次 SELECT**（acceptance / canonical manifest / provenance /
membership / rows）。⛔ 它们必须来自**同一个 SQLite 一致读快照**，否则并发写者可以
在读序列中途提交，产生

```text
acceptance A 的元数据  +  epoch B 的 membership / rows      ← ⛔ 混合 epoch（禁止）
```

⚠️ **`with sqlite3.connect(...)` ⛔ 不是**一致快照：Python `sqlite3` 默认
`isolation_level` **只在 DML 之前**隐式开启事务，裸 `SELECT` 各自一个隐式事务。
因此权威读取路径显式建立事务（`store.py`）：

```text
_open_read_snapshot(path)
    sqlite3.connect(path, isolation_level=None)   # 事务完全由我们控制
    PRAGMA busy_timeout = 5000                    # 并发写者等待，而不是立刻失败
    _require_schema(...)                          # 只读 sqlite_master / PRAGMA（BEGIN 之前）
    BEGIN                                         # ← 显式 deferred **读**事务，在第一次 SELECT 之前
        acceptance 元数据 + canonical manifest（一条 SELECT）
        provenance → membership → rows → 逐行 digest → 整批 digest
    finally: ROLLBACK                             # 只读，⛔ 永不 COMMIT
```

- ⛔ 不因为这次修复改变 journal mode；rollback-journal 下写者的 `COMMIT` 会被读者的
  SHARED 读锁挡住（写者等待/被拒），**仍然**不会与读序列交错；
- 读者在快照内的读取**必须成功返回完整 epoch A**（⛔ 不是靠 R-CONTENT 的内容校验
  把混合读"拦下来"，而是**根本不产生**混合读）。

并发探针（`backend/tests/test_course_data_read_snapshot.py`，8 个测试）：读者在
membership SELECT **之前确定性地暂停**，rogue writer 直接改库（绕过 API），
三种场景各覆盖一次 reviewer 要求：

```text
delete acceptance 期间读取       （DELETE course_data_acceptance / course_data_import）
replace accepted row 期间读取    （UPDATE course_offering 的公共字段）
mutate membership 期间读取       （改写 offering_set_sha256 + canonical_manifest_json + membership）
```

允许的结果只有三类：**完整 epoch A** · **writer 被锁等待** · **reader fail closed**；
探针同时断言"写者第一次确实被挡住、读者结束后重试成功"（证明库真的被改过 ⇒
"读者看到完整 A"不是空泛结论）。把 `_open_read_snapshot` 换成"只连接、不开显式事务"
的等价实现后，同一探针立刻退化为**混合 epoch / fail closed**（反空泛测试）。

## 读取契约

```python
provider.get_course_offerings("2026-1")   # → list[CourseOffering]（只含绑定行）
provider.get_course_offerings("2026-2")   # → CourseDataAcceptanceError（fail closed）
```

- `semester` 必须**精确等于**构造时绑定的学期；⛔ **不返回空列表**、⛔ 不 fallback
  （否则 Planner 会把"学期不匹配"当成"没有供给"）；
- 顺序确定：`ORDER BY course_id, class_id`；
- 只读：⛔ 不写库、⛔ 不建表、⛔ 不联网、⛔ 不读认证材料；
- 结构上满足冻结的 `CourseDataProvider`（签名仍是 `get_course_offerings(self, semester)`）。

## 错误映射（就绪性失败 → 503）

`CourseDataAcceptanceError` 是**就绪性失败**：

- runtime factory 捕获它 ⇒ `course_data_not_ready` ⇒ `POST /api/v1/plan` 返回
  `503 real_pipeline_not_configured`；
- 请求期间才发现失效（例如库被改写）时，`app/main.py` 里有**显式**异常处理器
  把同一个错误映射成同样的 503（⛔ 不是 500、⛔ 不是 Mock fallback）；
- ⛔ 其它未预期异常（例如 SQLite 损坏）**不**被映射成 503，仍然保持 500
  （⛔ 不把程序缺陷伪装成"未装配"）。

## 拒绝矩阵（各有测试）

库不存在 / 非 Course Data 库 / 空库 / **campus-only 库** / SHA 不对 /
scope_kind 或 scope_id 不对 / `completeness != complete` / 计数不自洽 /
零行 / 两个平面不一致 / 行被删除 / membership 被删除或改写 /
逐行内容被替换（course_name / course_id / class_id / source / meetings / credit）/
陈旧 campus 行 / 其它学期行 / 请求其它学期 / semester 与 digest 形态非法 /
`sqlite_path` 类型非法。

## 与 runtime 的关系

Provider 只提供"**已接受且内容一致**的那批行"；
环境变量接线（`APP_COURSE_DATA_SQLITE_PATH` / `APP_COURSE_DATA_SEMESTER` /
`APP_COURSE_DATA_ACCEPTANCE_SHA256`）与 orchestrator 装配见
`docs/data/CASE_A_RUNTIME_WIRING.md`。

## 未做 / 未声称

- ⛔ 未实现 physical immutability（专用 immutable acceptance DB / versioned row payload）：
  当前机制是 **membership + 内容指纹 + 任何篡改即 fail closed**，
  真正的不可变存储属**后续 Architecture Decision**；
- ⛔ 不改 public Schema / frozen Provider contract；⛔ 不联网；formal Real E2E = **LEVEL0**。


## immutable acceptance identity（第二轮 Red-Team BLOCK 的修复）

trust chain 多了一层（在原有 7 条之前）：

```text
 0. configured SHA
      → 已持久化的 canonical_manifest_json（canonical 形式，strict 校验）
      → SHA256(canonical bytes) == configured SHA        （可重算，⛔ 不靠 DB 自报）
      → manifest 语义字段 == 列式 metadata（semester / scope / counts /
        offering_set_sha256 / baseline）
    ⛔ full_semester acceptance 没有 canonical manifest ⇒ 拒绝服务
    （campus acceptance 的 identity 是 raw artifact 字节 digest，不要求 manifest）
```

写入侧：

- `import_offering_snapshot(..., canonical_manifest=manifest)`：
  manifest 的 SHA 必须**就是** `artifact_sha256`，语义字段必须与快照一致；
- 同一 acceptance identity 已存在时**逐项比较**（含 manifest 字节与 membership），
  完全相同 ⇒ 幂等 no-op，任一不同 ⇒ `ImmutableAcceptanceConflictError`
  （⛔ 不再 `ON CONFLICT DO UPDATE`、⛔ 不再"先删成员再插入"）；
- membership 主键含 `(scope_kind, scope_id)`：同一批字节可在不同 scope 下各自留记录。

因此"同一个 SHA + Dataset B"这条攻击路径在语义上**不可表达**；
即使绕过 API 直接 rewrite DB，重算 `SHA256(canonical stored manifest)` 也对不上。
