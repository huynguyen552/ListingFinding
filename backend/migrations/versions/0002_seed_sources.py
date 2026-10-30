"""Seed user-owned sources and list indexes."""

import sqlalchemy as sa
from alembic import op

revision = "0002_seed_sources"
down_revision = "3ece1287422c"
branch_labels = None
depends_on = None


def upgrade():
    sources = sa.table(
        "sources",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("allow_store", sa.Boolean),
        sa.column("allow_display", sa.Boolean),
        sa.column("allow_export", sa.Boolean),
    )
    existing = set(op.get_bind().execute(sa.select(sources.c.id)).scalars())
    rows = [
        {
            "id": "csv",
            "name": "Danh sách CSV của bạn",
            "allow_store": True,
            "allow_display": True,
            "allow_export": True,
        },
        {
            "id": "manual",
            "name": "Chỉnh sửa thủ công",
            "allow_store": True,
            "allow_display": True,
            "allow_export": True,
        },
    ]
    for row in rows:
        if row["id"] not in existing:
            op.bulk_insert(sources, [row])
    op.create_index("ix_locations_updated", "locations", ["updated_at", "id"])
    op.create_index("ix_locations_city_status", "locations", ["city", "status"])


def downgrade():
    op.drop_index("ix_locations_city_status", table_name="locations")
    op.drop_index("ix_locations_updated", table_name="locations")
    # Preserve sources referenced by observations when rolling back indexes.
