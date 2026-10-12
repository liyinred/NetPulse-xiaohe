"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}


revision: str = ${repr(up_revision)}
down_revision: Union[str, Sequence[str], None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    """应用本次数据库结构变更。

    参数:
        无。
    返回:
        无返回值。
    """
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """撤销本次数据库结构变更。

    参数:
        无。
    返回:
        无返回值。
    """
    ${downgrades if downgrades else "pass"}
