from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite:///{DATA_DIR / 'routes.db'}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def ensure_schema() -> None:
    """Лёгкая миграция для уже существующего SQLite."""
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(route_records)"))}
        if not cols:
            return
        if "approved" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE route_records ADD COLUMN approved BOOLEAN NOT NULL DEFAULT 0"
                )
            )
            conn.execute(
                text(
                    "UPDATE route_records SET approved = 1 WHERE status = 'approved'"
                )
            )
        if "documents" not in cols:
            conn.execute(
                text("ALTER TABLE route_records ADD COLUMN documents JSON NOT NULL DEFAULT '[]'")
            )
            # backfill: один документ из legacy raw_input
            rows = conn.execute(
                text(
                    "SELECT id, raw_input, source_file FROM route_records "
                    "WHERE (documents IS NULL OR documents = '[]' OR documents = '') "
                    "AND raw_input IS NOT NULL AND raw_input != ''"
                )
            ).fetchall()
            import json

            for row_id, raw_input, source_file in rows:
                doc = [
                    {
                        "id": f"legacy-{row_id[-6:]}",
                        "filename": source_file or "raw_input",
                        "filetype": "text",
                        "raw_text": raw_input,
                        "important": {},
                        "metadata_junk": {},
                        "summary": "",
                        "structure_model": None,
                        "warnings": ["migrated from legacy raw_input"],
                    }
                ]
                conn.execute(
                    text("UPDATE route_records SET documents = :docs WHERE id = :id"),
                    {"docs": json.dumps(doc, ensure_ascii=False), "id": row_id},
                )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
