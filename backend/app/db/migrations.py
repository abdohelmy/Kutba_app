from sqlalchemy import Engine, inspect, text


def migrate_super_admin(engine: Engine) -> None:
    inspector = inspect(engine)
    if engine.dialect.name != "sqlite":
        return
    additions = {
        "mosques": {"approval_status": "VARCHAR(24) NOT NULL DEFAULT 'APPROVED'"},
        "mosque_glossary_terms": {"approval_status": "VARCHAR(24) NOT NULL DEFAULT 'APPROVED'"},
        "global_glossary_terms": {"approval_status": "VARCHAR(24) NOT NULL DEFAULT 'APPROVED'"},
        "sermon_segments": {"live_alignment": "JSON NOT NULL DEFAULT '{}'"},
        "users": {
            "contact_email": "VARCHAR(254)",
            "auth_version": "INTEGER NOT NULL DEFAULT 0",
        },
    }
    with engine.begin() as connection:
        for table, fields in additions.items():
            if not inspector.has_table(table):
                continue
            columns = {item["name"] for item in inspector.get_columns(table)}
            for name, definition in fields.items():
                if name not in columns:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))


def migrate_translation_languages(engine: Engine) -> None:
    inspector = inspect(engine)
    if engine.dialect.name != "sqlite" or not inspector.has_table("sermons"):
        return
    with engine.begin() as connection:
        columns = {item["name"] for item in inspector.get_columns("sermons")}
        for name, definition in {
            "english_sermon_id": "VARCHAR(36) REFERENCES sermons(id)",
            "english_revision": "VARCHAR(64)",
        }.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE sermons ADD COLUMN {name} {definition}"))
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_sermon_language "
                "ON sermons (english_sermon_id, target_language)"
            )
        )
        if inspector.has_table("sermon_segments"):
            columns = {item["name"] for item in inspector.get_columns("sermon_segments")}
            if "localized_glossary" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE sermon_segments ADD COLUMN localized_glossary JSON "
                        "NOT NULL DEFAULT '[]'"
                    )
                )


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
            text("ALTER TABLE sermons ADD COLUMN title_is_inferred BOOLEAN NOT NULL DEFAULT 0")
        )
