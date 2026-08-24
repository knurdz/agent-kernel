"""One-shot mover: legacy Phase 15-17 SQLite marketplace DB -> Postgres.

Manual tool; never runs at boot. Copies all rows preserving IDs and
timestamps, then resyncs Postgres identity sequences.

Usage:
    AK_MARKETPLACE__DATABASE_URL=postgresql+psycopg://agripilot:agripilot@localhost:5432/agripilot \
        uv run python scripts/migrate_sqlite_to_postgres.py [--sqlite data/app.db] [--force]

Refuses a non-empty target unless --force is given.
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, func, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import marketplace.models  # noqa: E402,F401
from marketplace.database import DEFAULT_URL, get_database_url, run_migrations  # noqa: E402
from marketplace.models import BuyerProfile, ConnectionRequest, FarmerProfile, Listing, User  # noqa: E402

_COPY_ORDER = [User, FarmerProfile, BuyerProfile, Listing, ConnectionRequest]


def _copy_fields(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def _resync_sequences(engine) -> None:
    with engine.connect() as conn:
        for table in ("users", "listings", "connection_requests"):
            conn.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)"
                )
            )
        conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", default="data/app.db", help="legacy SQLite file (default: data/app.db)")
    parser.add_argument("--force", action="store_true", help="migrate even if the target already has rows")
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite)
    if not sqlite_path.is_file():
        print(f"no legacy DB at {sqlite_path} - nothing to migrate")
        raise SystemExit(0)

    target_url = get_database_url()
    if target_url == DEFAULT_URL and not os.environ.get("AK_MARKETPLACE__DATABASE_URL"):
        print("warning: no AK_MARKETPLACE__DATABASE_URL set; using config/default:", target_url)
    if target_url.startswith("sqlite"):
        print("error: target URL is SQLite; set AK_MARKETPLACE__DATABASE_URL to a Postgres URL")
        raise SystemExit(1)

    src_engine = create_engine(f"sqlite:///{sqlite_path}")
    dst_engine = create_engine(target_url, pool_pre_ping=True)

    run_migrations(target_url)  # ensure the target schema exists

    with Session(src_engine) as src:
        total_source = sum(src.scalar(select(func.count()).select_from(model)) or 0 for model in _COPY_ORDER)

        with Session(dst_engine) as dst:
            existing_users = dst.query(User).count()
            if existing_users and not args.force:
                print(f"target already has {existing_users} users; refusing to migrate (use --force to override)")
                raise SystemExit(1)
            if existing_users:
                print("warning: --force set; rows will be added on top of existing data")

            migrated = 0
            for model in _COPY_ORDER:
                rows = list(src.scalars(select(model)).all())
                for row in rows:
                    dst.add(model(**_copy_fields(row)))
                if rows:
                    dst.flush()
                migrated += len(rows)
            dst.commit()

            _resync_sequences(dst_engine)

    print(f"migrated {migrated}/{total_source} rows from {sqlite_path}")
    print("done")


if __name__ == "__main__":
    main()
