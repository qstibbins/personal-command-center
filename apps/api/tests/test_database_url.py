from pcc.core.database_url import normalize_database_url


def test_normalize_postgresql_url():
    assert (
        normalize_database_url("postgresql://user:pass@host:5432/db")
        == "postgresql+psycopg://user:pass@host:5432/db"
    )


def test_normalize_postgres_scheme():
    assert (
        normalize_database_url("postgres://user:pass@host/db")
        == "postgresql+psycopg://user:pass@host/db"
    )


def test_normalize_already_psycopg():
    url = "postgresql+psycopg://user:pass@localhost:5432/pcc"
    assert normalize_database_url(url) == url


def test_normalize_trims_whitespace():
    assert (
        normalize_database_url("  postgresql://u:p@h/db  ")
        == "postgresql+psycopg://u:p@h/db"
    )
