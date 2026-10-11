"""Small checks for dashboard presentation and deployment helpers."""

from dashboard import app
from dashboard.app import as_percent, metric_rows


def test_as_percent() -> None:
    assert as_percent(0.125) == "12.5%"


def test_metric_rows_preserves_metric_names() -> None:
    result = metric_rows({"mae": 2.5, "wape": 0.1})
    assert result.to_dict("records") == [
        {"metric": "mae", "value": 2.5},
        {"metric": "wape", "value": 0.1},
    ]


def test_remote_warehouse_settings_reads_a_release_manifest(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self) -> bytes:
            return b'{"url":"https://example.test/snapshot.duckdb","sha256":"abc123"}'

    monkeypatch.setattr(app, "WAREHOUSE_MANIFEST_URL", "https://example.test/manifest.json")
    monkeypatch.setattr(app, "urlopen", lambda *_args, **_kwargs: Response())

    assert app.remote_warehouse_settings() == ("https://example.test/snapshot.duckdb", "abc123")
