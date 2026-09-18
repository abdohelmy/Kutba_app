from sqlalchemy import Engine, inspect, text


def migrate_legacy_user_login(engine: Engine) -> None:
    """Make legacy SQLite email storage support role-scoped usernames."""
    if engine.dialect.name != "sqlite" or not inspect(engine).has_table("users"):
        return
    indexes = {item["name"]: item for item in inspect(engine).get_indexes("users")}
    with engine.begin() as connection:
        legacy_index = indexes.get("ix_users_email")
        if legacy_index and legacy_index.get("unique"):
            connection.execute(text("DROP INDEX ix_users_email"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_users_username ON users (email)"))
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username_role ON users (email, role)")
        )


def migrate_inferred_sermon_titles(engine: Engine) -> None:
    """Add title provenance without rebuilding existing SQLite development databases."""
    inspector = inspect(engine)
    if engine.dialect.name != "sqlite" or not inspector.has_table("sermons"):
        return
    columns = {item["name"] for item in inspector.get_columns("sermons")}
    if "title_is_inferred" in columns:
        return
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE sermons ADD COLUMN title_is_inferred "
                "BOOLEAN NOT NULL DEFAULT 0"
            )
        )
