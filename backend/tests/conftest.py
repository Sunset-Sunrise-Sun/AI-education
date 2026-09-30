"""pytest 公共夹具。

这里提供三样东西：
1. `client` —— FastAPI 测试客户端；
2. `schemas_dir` / `mock_data_dir` —— 公共 Schema 与 Mock 数据的真实路径；
3. `load_schema` —— 按文件名读取 `/schemas/*.schema.json`。

测试直接读取仓库里的真实 Schema 文件（而不是复制一份），
这样任何对公共契约或 Mock 数据的改动都会立刻被测试发现。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

# backend/tests/conftest.py -> 上溯 3 层到仓库根目录
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_DIR = REPO_ROOT / "schemas"
MOCK_DATA_DIR = REPO_ROOT / "mock_data"


@pytest.fixture(scope="session")
def client() -> TestClient:
    """FastAPI 测试客户端。

    使用 with 语句进入上下文，确保 lifespan 启动自检会被执行——
    也就是说，如果 Mock 数据坏了，所有接口测试都会一起失败，而不是悄悄地通过。
    """

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def schemas_dir() -> Path:
    return SCHEMAS_DIR


@pytest.fixture(scope="session")
def mock_data_dir() -> Path:
    return MOCK_DATA_DIR


@pytest.fixture(scope="session")
def load_schema():
    """返回 `load_schema(file_name) -> dict`，读取公共 JSON Schema。"""

    def _load(file_name: str) -> dict:
        path = SCHEMAS_DIR / file_name
        if not path.is_file():
            raise AssertionError(f"缺少公共 Schema 文件：{path}")
        return json.loads(path.read_text(encoding="utf-8"))

    return _load


@pytest.fixture(scope="session")
def load_mock_file():
    """返回 `load_mock_file(file_name) -> object`，读取 mock_data 下的原始 JSON。"""

    def _load(file_name: str) -> object:
        path = MOCK_DATA_DIR / file_name
        if not path.is_file():
            raise AssertionError(f"缺少 Mock 数据文件：{path}")
        return json.loads(path.read_text(encoding="utf-8"))

    return _load
