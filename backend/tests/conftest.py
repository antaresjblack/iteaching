"""共享测试夹具：内存 SQLite 引擎与 FastAPI get_db 依赖覆盖。

提供两类通用能力，供业务测试统一装配数据库环境，避免各文件重复样板：

  1. testing_sessionmaker：内存 SQLite（StaticPool 共享连接）+ 建表后的 sessionmaker；
  2. db_override：替换 FastAPI get_db 依赖的会话供给函数，每个请求独立会话。

各测试文件在此之上自行完成账号、课程、录音等业务种子数据构造。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  # 导入全部模型，确保 create_all 注册完整表结构
from app.db.base import Base


@pytest.fixture
def testing_sessionmaker() -> sessionmaker[Session]:
    """内存 SQLite + StaticPool：整个测试共享同一连接，事务内种子数据不丢失。"""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def db_override(testing_sessionmaker: sessionmaker[Session]) -> Callable[[], Iterator[Session]]:
    """替换 FastAPI get_db 依赖：每次请求从共享引擎开一个新会话。"""

    def override() -> Iterator[Session]:
        with testing_sessionmaker() as session:
            yield session

    return override
