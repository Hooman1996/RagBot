# alembic/versions/script.py.mako

"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    """
    Upgrade database schema

    This function contains the operations to upgrade the database
    to this revision. All changes should be idempotent and reversible.
    """
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """
    Downgrade database schema

    This function contains the operations to downgrade the database
    from this revision. All changes should cleanly reverse the upgrade.
    """
    ${downgrades if downgrades else "pass"}