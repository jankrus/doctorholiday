"""The ORM models mirror the migrated schema, and the application role has least privilege."""

import pytest
from sqlalchemy import Engine, delete, insert, inspect, text, update
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from doctorholiday.models import Appointment, AuditEvent, Base, PracticeSettings, User


def test_every_table_has_a_model(db_engine: Engine) -> None:
    tables = set(inspect(db_engine).get_table_names()) - {"schema_migrations"}
    assert tables == set(Base.metadata.tables)


@pytest.mark.parametrize("table", sorted(Base.metadata.tables))
def test_model_columns_match_the_table(db_engine: Engine, table: str) -> None:
    model = Base.metadata.tables[table]
    columns = {column["name"]: column for column in inspect(db_engine).get_columns(table)}

    assert set(columns) == set(model.columns.keys())
    for column in model.columns:
        reflected = columns[column.name]
        assert reflected["nullable"] == column.nullable, f"{table}.{column.name} nullability"
        assert (reflected["default"] is not None) == (column.server_default is not None), (
            f"{table}.{column.name} default"
        )


@pytest.mark.parametrize("table", sorted(Base.metadata.tables))
def test_model_foreign_keys_match_the_table(db_engine: Engine, table: str) -> None:
    reflected = {
        (tuple(fk["constrained_columns"]), fk["referred_table"], fk["options"].get("ondelete"))
        for fk in inspect(db_engine).get_foreign_keys(table)
    }
    model = {
        ((fk.parent.name,), fk.column.table.name, fk.ondelete)
        for fk in Base.metadata.tables[table].foreign_keys
    }
    assert reflected == model


@pytest.mark.parametrize(
    "statement",
    [
        pytest.param(update(AuditEvent).values(outcome="SUCCESS"), id="update-audit-events"),
        pytest.param(delete(AuditEvent), id="delete-audit-events"),
        pytest.param(delete(User), id="delete-users"),
        pytest.param(delete(Appointment), id="delete-appointments"),
        pytest.param(
            insert(PracticeSettings).values(id=2, practice_name="x"), id="insert-practice-settings"
        ),
        pytest.param(delete(PracticeSettings), id="delete-practice-settings"),
        pytest.param(text("SELECT version FROM schema_migrations"), id="read-schema-migrations"),
        pytest.param(text("CREATE TABLE intruder (id int)"), id="create-table"),
        pytest.param(text("TRUNCATE appointments"), id="truncate"),
    ],
)
def test_application_role_is_refused(db_session: Session, statement: object) -> None:
    with pytest.raises(ProgrammingError) as exc_info:
        db_session.execute(statement)  # type: ignore[call-overload]
    assert exc_info.value.orig.sqlstate == "42501"  # type: ignore[union-attr]  # insufficient_privilege
