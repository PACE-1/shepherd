"""The library parse is warmed in the background so a rider's first Library visit is fast."""
import app


def test_warm_up_fills_the_rows_cache_and_never_raises(monkeypatch):
    monkeypatch.setattr(app, "_LIBRARY_ROWS_CACHE", None)
    app._warm_library_rows()
    assert app._LIBRARY_ROWS_CACHE is not None

    def boom():
        raise RuntimeError("disk gone")
    monkeypatch.setattr(app, "_get_library_rows_cached", boom)
    app._warm_library_rows()  # swallowed
