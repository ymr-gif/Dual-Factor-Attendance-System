"""Stored face embeddings come back as arrays whatever pgvector version is installed.

pgvector-python 0.5.x returns its own `Vector` object for a `vector` column where 0.4.x
returned an array. `db.embedding_to_numpy` unwraps it, and both functions that read a
student row go through it. The database is replaced by a fake cursor.
"""

from contextlib import contextmanager

import pytest

from backend import db

STUDENT = {"student_id": "S001", "uid": "C3BE343A", "name": "Test Student"}


class Vector:
    """What pgvector 0.5.x returns for a `vector` column."""

    def to_numpy(self):
        return "unwrapped"


def test_embedding_to_numpy_unwraps_a_vector_and_keeps_none():
    assert db.embedding_to_numpy(Vector()) == "unwrapped"
    assert db.embedding_to_numpy(None) is None


@pytest.mark.parametrize(
    ("reader", "argument"), [(db.find_student_by_uid, "C3BE343A"), (db.get_student, "S001")]
)
def test_student_rows_come_back_with_the_embedding_unwrapped(monkeypatch, reader, argument):
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql, params=None):
            pass

        def fetchone(self):
            return dict(STUDENT, face_embedding=Vector())

    class Connection:
        def cursor(self, *args, **kwargs):
            return Cursor()

    @contextmanager
    def get_conn():
        yield Connection()

    monkeypatch.setattr(db, "get_conn", get_conn)

    assert reader(argument)["face_embedding"] == "unwrapped"
