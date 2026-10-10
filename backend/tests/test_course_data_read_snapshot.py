"""R-SNAPSHOT：Provider authority path 必须是**单一 SQLite consistent read snapshot**。

Reviewer 要求的 concurrency adversarial probe：

```text
Reader : BEGIN → read acceptance → pause
Writer : 修改 / 删除 / 替换 acceptance / membership / accepted row → COMMIT
Reader : 继续读 canonical manifest / membership / rows
```

允许：完整 epoch A · writer 被锁等待 · reader fail closed
⛔ 禁止：acceptance A **+** membership/rows B（mixed epoch）

⚠️ 本文件用**真实生产读取路径**（`load_accepted_offerings` / `get_course_offerings`），
只 patch stdlib `sqlite3.connect` 挂 trace 回调，从而在读取序列中途**确定性暂停**
（暂停点在 membership SELECT **之前**：此时 acceptance 已经读过）。

epoch 用可见内容标识（`course_name = EPOCH_A_* / EPOCH_B_*`、`source` 同理），
因此"混合 epoch"是**可观测**的；writer 绕过 API 直接改库（模拟 rogue writer）。
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from app.course_data import (
    SCOPE_KIND_FULL_SEMESTER,
    CourseDataStoreError,
    OfferingSnapshot,
    SnapshotScope,
    StoreBackedCourseDataProvider,
    canonical_manifest_bytes,
    compute_manifest_sha256,
    import_offering_snapshot,
    load_accepted_offerings,
    offering_payload_sha256,
    offering_set_sha256,
)
from app.models.contracts import CourseOffering, DataSource

SEMESTER = "2026-1"
SCOPE = SnapshotScope(scope_kind=SCOPE_KIND_FULL_SEMESTER, scope_id=SEMESTER)
WRITER_BUSY_TIMEOUT_MS = 300


# --------------------------------------------------------------------------- #
# fixtures / helpers
# --------------------------------------------------------------------------- #


def _offering(course_id: str, class_id: str, *, epoch: str) -> CourseOffering:
    return CourseOffering(
        course_id=course_id,
        course_name=f"EPOCH_{epoch}_{class_id}",
        class_id=class_id,
        semester=SEMESTER,
        teacher="REDACTED",
        credit=3.0,
        meetings=[],
        capacity=90,
        remaining_capacity=75,
        source=f"capture://sysu/{SEMESTER}/full-semester/{SEMESTER}/epoch-{epoch.lower()}",
        data_source=DataSource.REAL,
    )


def _epoch_offerings(epoch: str) -> list[CourseOffering]:
    return [
        _offering("SYN-A", "A-01", epoch=epoch),
        _offering("SYN-B", "B-01", epoch=epoch),
        _offering("SYN-C", "C-01", epoch=epoch),
    ]


def _manifest(offerings: list[CourseOffering]) -> dict[str, object]:
    total = len(offerings)
    return {
        "format": "sysu-course-data-full-semester-acceptance-v1",
        "manifest_version": 2,
        "tool": "probe",
        "semester": SEMESTER,
        "scope_kind": SCOPE_KIND_FULL_SEMESTER,
        "scope_id": SEMESTER,
        "source": f"capture://sysu/{SEMESTER}/full-semester/{SEMESTER}",
        "inventory_sha256": "a" * 64,
        "baseline_before": total,
        "baseline_after": total,
        "merged_offering_count": total,
        "merged_offering_set_sha256": offering_set_sha256(offerings),
        "shards": [
            {
                "shard_id": "east-campus",
                "openingSchoolNumber": "5063559",
                "raw_bundle_sha256": "b" * 64,
                "campus_acceptance_sha256": "b" * 64,
                "campus_source": f"capture://sysu/{SEMESTER}/campus/5063559",
                "campus_offering_set_sha256": offering_set_sha256(offerings),
                "page_count": 1,
                "loaded_count": total,
                "reported_total": total,
            }
        ],
    }


def _seed_epoch_a(store: Path) -> str:
    offerings = _epoch_offerings("A")
    manifest = _manifest(offerings)
    digest = compute_manifest_sha256(manifest)
    import_offering_snapshot(
        store,
        OfferingSnapshot(
            semester=SEMESTER,
            offerings=tuple(offerings),
            completeness="complete",
            reported_total=len(offerings),
        ),
        artifact_sha256=digest,
        scope=SCOPE,
        canonical_manifest=manifest,
    )
    return digest


#: 读序列中**确定性**的暂停点：membership SELECT（此时 acceptance / canonical
#: manifest 已经读过，membership 与 rows 还没读）。
_ACCEPTANCE_READ_SQL = "FROM course_data_acceptance WHERE"
_MEMBERSHIP_READ_SQL = "FROM course_data_acceptance_member WHERE"


def _install_pausable_connect(
    monkeypatch: pytest.MonkeyPatch,
    *,
    paused: threading.Event,
    resume: threading.Event,
    state: dict[str, object],
) -> None:
    """在 membership SELECT 执行**之前**暂停读者（确定性并发窗口）。

    ⚠️ 只暂停**一次**（one-shot）：`sqlite3.connect` 是全局 patch，rogue writer 自己
    也走这个 patch；若不限次，writer 的 `DELETE FROM course_data_acceptance_member`
    会把自己也挂住 ⇒ 双方互等（写成"死锁"而不是"锁等待"）。
    由于 writer 只在 `paused` 被置位后才开始，one-shot 必然由读者先消耗。

    ⚠️ 锚点必须是 `FROM course_data_acceptance_member WHERE`（不是裸表名）：
    `_require_current_columns()` 会执行 `PRAGMA table_info(course_data_acceptance_member)`，
    而它在 `BEGIN` **之前** —— 用裸表名匹配会把暂停点放在事务之外（那样探针就测不到事务）。
    """

    import app.course_data.store as store_module

    real_connect = sqlite3.connect

    def _connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection = real_connect(*args, **kwargs)

        def _trace(statement: str) -> None:
            normalized = " ".join(statement.split())
            if _ACCEPTANCE_READ_SQL in normalized:
                state["acceptance_read"] = True
                return
            if _MEMBERSHIP_READ_SQL not in normalized:
                return
            if state.get("paused_once"):
                return
            state["paused_once"] = True
            state["in_transaction_at_pause"] = bool(connection.in_transaction)
            state["acceptance_read_before_pause"] = bool(state.get("acceptance_read"))
            paused.set()
            resume.wait(timeout=20)

        connection.set_trace_callback(_trace)
        return connection

    monkeypatch.setattr(store_module.sqlite3, "connect", _connect)


# --------------------------------------------------------------------------- #
# rogue writers（绕过 API 直接改库；每种覆盖一个 reviewer 要求的场景）
# --------------------------------------------------------------------------- #


def _writer_sql(store: Path, statements: list[tuple[str, tuple[object, ...]]]) -> str:
    """执行一组写语句；返回 `committed` / `locked` / `error:<type>`。"""

    connection = sqlite3.connect(str(store), isolation_level=None)
    try:
        connection.execute(f"PRAGMA busy_timeout = {WRITER_BUSY_TIMEOUT_MS}")
        connection.execute("BEGIN IMMEDIATE")
        for statement, parameters in statements:
            connection.execute(statement, parameters)
        connection.execute("COMMIT")
        return "committed"
    except sqlite3.OperationalError as exc:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        return "locked" if "locked" in str(exc).lower() else f"error:{type(exc).__name__}"
    finally:
        connection.close()


def _delete_acceptance(store: Path, digest: str) -> str:
    return _writer_sql(
        store,
        [
            ("DELETE FROM course_data_acceptance WHERE artifact_sha256 = ?", (digest,)),
            ("DELETE FROM course_data_import WHERE artifact_sha256 = ?", (digest,)),
        ],
    )


def _replace_accepted_row(store: Path, digest: str) -> str:
    row_b = _epoch_offerings("B")[0]
    return _writer_sql(
        store,
        [
            (
                "UPDATE course_offering SET course_name = ?, source = ? "
                "WHERE semester = ? AND class_id = ?",
                (row_b.course_name, row_b.source, SEMESTER, "A-01"),
            )
        ],
    )


def _mutate_membership(store: Path, digest: str) -> str:
    offerings_b = _epoch_offerings("B")
    statements: list[tuple[str, tuple[object, ...]]] = [
        (
            "UPDATE course_data_acceptance SET offering_set_sha256 = ?, "
            "canonical_manifest_json = ? WHERE artifact_sha256 = ?",
            (
                offering_set_sha256(offerings_b),
                canonical_manifest_bytes(_manifest(offerings_b)).decode("utf-8"),
                digest,
            ),
        ),
        ("DELETE FROM course_data_acceptance_member WHERE artifact_sha256 = ?", (digest,)),
    ]
    for offering in offerings_b:
        statements.append(
            (
                "INSERT INTO course_data_acceptance_member "
                "(artifact_sha256, semester, scope_kind, scope_id, course_id, class_id, "
                " offering_payload_sha256) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    digest,
                    SEMESTER,
                    SCOPE_KIND_FULL_SEMESTER,
                    SEMESTER,
                    offering.course_id,
                    offering.class_id,
                    offering_payload_sha256(offering),
                ),
            )
        )
    return _writer_sql(store, statements)


def _post_state(store: Path, digest: str, *, writer: str) -> str:
    """写完之后的库状态（用于证明 writer **确实**改动了库，避免空泛通过）。"""

    connection = sqlite3.connect(str(store))
    try:
        if writer == "delete_acceptance":
            row = connection.execute(
                "SELECT 1 FROM course_data_acceptance WHERE artifact_sha256 = ?", (digest,)
            ).fetchone()
            return "missing" if row is None else "present"
        if writer == "replace_row":
            row = connection.execute(
                "SELECT course_name FROM course_offering WHERE class_id = ?", ("A-01",)
            ).fetchone()
            return "EPOCH_B" if row and row[0].startswith("EPOCH_B") else "EPOCH_A"
        row = connection.execute(
            "SELECT offering_set_sha256 FROM course_data_acceptance WHERE artifact_sha256 = ?",
            (digest,),
        ).fetchone()
        return (
            "EPOCH_B"
            if row and row[0] == offering_set_sha256(_epoch_offerings("B"))
            else "EPOCH_A"
        )
    finally:
        connection.close()


def _assert_single_epoch(offerings: list[CourseOffering]) -> str:
    """所有行 + source 必须来自同一个 epoch；返回该 epoch。"""

    names = {offering.course_name for offering in offerings}
    epochs = {name.split("_")[1] for name in names}
    assert len(epochs) == 1, f"⛔ mixed epoch in rows: {sorted(names)}"
    epoch = epochs.pop()

    sources = {offering.source for offering in offerings}
    assert all(f"epoch-{epoch.lower()}" in source for source in sources), (
        f"⛔ rows and sources disagree: {sorted(sources)}"
    )
    assert len(offerings) == len(_epoch_offerings(epoch))
    return epoch


# --------------------------------------------------------------------------- #
# probe driver
# --------------------------------------------------------------------------- #

_WRITERS: dict[str, Callable[[Path, str], str]] = {
    "delete_acceptance": _delete_acceptance,
    "replace_row": _replace_accepted_row,
    "mutate_membership": _mutate_membership,
}


def _run_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    writer_name: str,
    reader: Callable[[Path, str], object],
) -> dict[str, object]:
    """运行一次并发 probe，返回 {reader, reader_error, writer, writer_retry, post_state}。"""

    store = tmp_path / "course-data.sqlite3"
    digest = _seed_epoch_a(store)

    paused = threading.Event()
    resume = threading.Event()
    reader_done = threading.Event()
    state: dict[str, object] = {}

    _install_pausable_connect(
        monkeypatch, paused=paused, resume=resume, state=state
    )

    outcome: dict[str, object] = {"reader": None, "reader_error": None}

    def _writer() -> None:
        writer = _WRITERS[writer_name]
        assert paused.wait(timeout=15), "reader never reached the pause point"
        try:
            first = writer(store, digest)
        finally:
            resume.set()
        reader_done.wait(timeout=15)
        # 读者已经结束（快照释放）⇒ 若第一次被锁等待，这里必须能成功，从而证明
        # "库确实被改过"，让"读者看到完整 A"成为**非空泛**的结论。
        retry = None if first == "committed" else writer(store, digest)
        outcome["writer"] = first
        outcome["writer_retry"] = retry

    writer_thread = threading.Thread(target=_writer)
    writer_thread.start()

    try:
        outcome["reader"] = reader(store, digest)
    except CourseDataStoreError as exc:
        outcome["reader_error"] = exc
    finally:
        reader_done.set()

    writer_thread.join(timeout=20)
    assert not writer_thread.is_alive(), "writer thread did not finish"

    # 非空泛：暂停点必须**在 acceptance 读过之后**，否则"看到完整 A"没有意义。
    assert state.get("paused_once") is True, "probe never paused inside the read sequence"
    assert state.get("acceptance_read_before_pause") is True, (
        "probe paused before the acceptance SELECT — the concurrency window is wrong"
    )
    outcome["paused_in_transaction"] = state.get("in_transaction_at_pause")

    outcome["post_state"] = _post_state(store, digest, writer=writer_name)
    outcome["digest"] = digest
    return outcome


def _probe_reader(store: Path, digest: str) -> object:
    dataset = load_accepted_offerings(store, semester=SEMESTER, acceptance_sha256=digest, require_approval=False)
    return list(dataset.offerings)


def _provider_reader(store: Path, digest: str) -> object:
    provider = StoreBackedCourseDataProvider(
        sqlite_path=store, semester=SEMESTER, acceptance_sha256=digest, require_approval=False
    )
    return provider.get_course_offerings(SEMESTER)


# --------------------------------------------------------------------------- #
# 1–3. reviewer 要求的三个 writer 场景
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("writer_name", "expected_post_state"),
    [
        ("delete_acceptance", "missing"),
        ("replace_row", "EPOCH_B"),
        ("mutate_membership", "EPOCH_B"),
    ],
)
def test_reader_keeps_one_complete_epoch_across_a_concurrent_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    writer_name: str,
    expected_post_state: str,
) -> None:
    """delete acceptance / replace accepted row / mutate membership 都不产生混合 epoch。"""

    outcome = _run_probe(
        tmp_path, monkeypatch, writer_name=writer_name, reader=_probe_reader
    )

    # writer 确实改动过库（否则下面的"读者看到完整 A"是空泛结论）。
    assert outcome["post_state"] == expected_post_state

    error = outcome["reader_error"]
    if error is not None:
        pytest.fail(f"reader failed closed instead of a consistent snapshot: {error}")

    offerings = outcome["reader"]
    assert isinstance(offerings, list)
    epoch = _assert_single_epoch(offerings)  # type: ignore[arg-type]
    assert epoch == "A", f"reader must keep its own snapshot, saw epoch {epoch}"


def test_provider_get_course_offerings_is_also_a_single_epoch_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Provider authority path（`get_course_offerings`）同样只能是单一 epoch。"""

    outcome = _run_probe(
        tmp_path, monkeypatch, writer_name="replace_row", reader=_provider_reader
    )

    assert outcome["post_state"] == "EPOCH_B"
    assert outcome["reader_error"] is None, outcome["reader_error"]

    offerings = outcome["reader"]
    assert isinstance(offerings, list)
    assert _assert_single_epoch(offerings) == "A"  # type: ignore[arg-type]


def test_writer_is_blocked_or_defers_until_the_reader_snapshot_ends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """写者要么被读事务挡住，要么在读者结束之后才提交（⛔ 不得在读中途插入）。"""

    outcome = _run_probe(
        tmp_path, monkeypatch, writer_name="mutate_membership", reader=_probe_reader
    )

    assert outcome["writer"] in {
        "committed",
        "locked",
    }, f"unexpected writer outcome: {outcome['writer']}"
    # 若第一次就被挡下，则读者结束之后必须能成功提交（证明是"锁等待"而非"写失败"）。
    if outcome["writer"] == "locked":
        assert outcome["writer_retry"] == "committed"
    assert outcome["post_state"] == "EPOCH_B"
    assert outcome["reader_error"] is None


# --------------------------------------------------------------------------- #
# 4–5. 事务边界本身
# --------------------------------------------------------------------------- #


def test_reader_holds_a_read_transaction_across_the_whole_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """行为级：读者在 pause 时**已经持有读事务**（写者此时无法提交）。"""

    store = tmp_path / "course-data.sqlite3"
    digest = _seed_epoch_a(store)

    paused = threading.Event()
    resume = threading.Event()
    state: dict[str, object] = {}
    _install_pausable_connect(monkeypatch, paused=paused, resume=resume, state=state)

    observed: dict[str, str] = {}

    def _writer() -> None:
        assert paused.wait(timeout=15)
        observed["during_read"] = _replace_accepted_row(store, digest)
        resume.set()

    thread = threading.Thread(target=_writer)
    thread.start()
    try:
        load_accepted_offerings(store, semester=SEMESTER, acceptance_sha256=digest, require_approval=False)
    finally:
        resume.set()
    thread.join(timeout=20)

    assert state.get("acceptance_read_before_pause") is True
    assert state.get("in_transaction_at_pause") is True, (
        "reader had no open transaction at the pause point — "
        "the multi-SELECT read is not a consistent snapshot"
    )
    assert observed["during_read"] == "locked", (
        "reader did not hold a read transaction across the whole verification: "
        f"writer outcome was {observed['during_read']!r}"
    )
    # 读者结束之后写者可以正常提交 ⇒ 读事务是**只读**的，不留写锁。
    assert _replace_accepted_row(store, digest) == "committed"


def test_authority_path_uses_the_explicit_read_snapshot_helper() -> None:
    """源码级：权威读取路径必须用 `_open_read_snapshot()`（显式 BEGIN … ROLLBACK）。"""

    import app.course_data.store as store_module

    source = Path(store_module.__file__).read_text(encoding="utf-8")

    assert "def _open_read_snapshot(" in source
    assert 'connection.execute("BEGIN")' in source
    assert 'connection.execute("ROLLBACK")' in source
    assert "isolation_level=None" in source

    # 权威读取（load_accepted_offerings）必须走这条路径，且**不再**用 _open_store。
    reader_body = source.split("def load_accepted_offerings(", 1)[1].split("\ndef ", 1)[0]
    assert "with _open_read_snapshot(path) as connection:" in reader_body
    assert "_open_store(path, must_exist=True, ensure_schema=False)" not in reader_body


# --------------------------------------------------------------------------- #
# 6. 反空泛：没有显式事务时，同一 probe 必须**不再**是原子读
# --------------------------------------------------------------------------- #


def test_without_the_explicit_transaction_the_same_probe_is_not_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⛔ 证明 `BEGIN` 是**承重**的，而不是装饰性关键字。

    把 `_open_read_snapshot` 换成"只连接、不开显式事务"的等价实现
    （= 旧 Provider HEAD `ef910e3` 的行为：`sqlite3.connect` 默认 isolation_level），
    同一 probe 必须变成 **fail closed 或混合 epoch**；两者都与"完整 epoch A"互斥。
    """

    import app.course_data.store as store_module

    @contextmanager
    def _no_transaction(path: object) -> Iterator[sqlite3.Connection]:
        resolved = store_module._require_store_path(path, must_exist=True)
        connection = sqlite3.connect(str(resolved))  # ← ef910e3 的行为：无显式事务
        try:
            connection.row_factory = sqlite3.Row
            store_module._require_schema(connection)
            yield connection
        finally:
            connection.close()

    monkeypatch.setattr(store_module, "_open_read_snapshot", _no_transaction)

    store = tmp_path / "course-data.sqlite3"
    digest = _seed_epoch_a(store)

    paused = threading.Event()
    resume = threading.Event()
    state: dict[str, object] = {}
    _install_pausable_connect(monkeypatch, paused=paused, resume=resume, state=state)

    def _writer() -> None:
        assert paused.wait(timeout=15)
        _replace_accepted_row(store, digest)
        resume.set()

    thread = threading.Thread(target=_writer)
    thread.start()

    result: object = None
    error: BaseException | None = None
    try:
        result = load_accepted_offerings(
            store, semester=SEMESTER, acceptance_sha256=digest, require_approval=False
        )
    except CourseDataStoreError as exc:
        error = exc
    finally:
        resume.set()
    thread.join(timeout=20)

    if error is not None:
        # 允许：fail closed（没有事务 ⇒ 读到的不是同一 epoch，被内容校验拦下）。
        message = str(error)
        assert any(
            token in message for token in ("内容", "digest", "行数", "membership", "acceptance")
        ), message
        return

    # 或者：确实是混合 epoch（那正是要禁止的结果类别）。
    offerings = result
    assert isinstance(offerings, list)
    names = {offering.course_name for offering in offerings}
    epochs = {name.split("_")[1] for name in names}
    assert epochs != {"A"}, (
        "without an explicit transaction the read still looked atomic — "
        "the probe is not exercising the concurrency window"
    )
