"""数据库迁移冒烟测试。

通过子进程真实执行 alembic 命令（而非导入调用），验证：
1. `alembic upgrade head` 能在数据库父目录不存在时自动创建并完成迁移；
2. 迁移完成后 `alembic check` 无差集（模型与迁移脚本保持一致）。
"""

import os
import subprocess
import sys
from pathlib import Path


def test_alembic_check_creates_missing_sqlite_parent_directory(tmp_path: Path) -> None:
    """全新环境（SQLite 父目录不存在）下迁移可成功执行且与模型定义一致。"""
    backend_dir = Path(__file__).resolve().parents[1]
    # 指向一个不存在的子目录，验证迁移流程会自行创建目录结构
    database_path = tmp_path / "new-data-dir" / "app.db"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"

    # 第一步：执行全部迁移，应成功（returncode == 0）
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr

    # 第二步：alembic check 确认迁移结果与 ORM 模型无差异
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=backend_dir,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert database_path.parent.is_dir()
