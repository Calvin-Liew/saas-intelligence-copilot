from __future__ import annotations

from scripts import production_monitor


def test_monitor_waits_for_status_ready_before_analyze(monkeypatch) -> None:
    calls: list[str] = []
    health_ok = production_monitor.RemoteCheck("Netlify/Render", "health", True, "status=200")
    status_starting = production_monitor.RemoteCheck(
        "Netlify/Render",
        "status",
        False,
        'status=503, body={"detail":"Preparing product data, Chroma indexes, enrichment metadata, and options."}',
    )
    status_ready = production_monitor.RemoteCheck("Netlify/Render", "status", True, "products=335")
    analyze_ok = production_monitor.RemoteCheck("analyze", "template analyze", True, "evidence=6")

    def fake_status(*args, **kwargs):
        calls.append("status")
        return status_starting if calls.count("status") == 1 else status_ready

    def fake_analyze(*args, **kwargs):
        calls.append("analyze")
        return analyze_ok

    monkeypatch.setattr(production_monitor, "check_health", lambda *args, **kwargs: health_ok)
    monkeypatch.setattr(production_monitor, "check_status", fake_status)
    monkeypatch.setattr(production_monitor, "check_analyze", fake_analyze)
    monkeypatch.setattr(production_monitor.time, "sleep", lambda *_args, **_kwargs: None)

    checks = production_monitor.run_monitor_checks(
        "https://example.test",
        timeout=45,
        retries=2,
        retry_delay=8,
        startup_timeout=30,
        poll_interval=1,
    )

    assert [check.passed for check in checks] == [True, True, True]
    assert calls == ["status", "status", "analyze"]
    assert "ready_after_polls=2" in checks[1].detail


def test_monitor_skips_analyze_when_status_never_ready(monkeypatch) -> None:
    calls = {"analyze": 0}
    health_ok = production_monitor.RemoteCheck("Netlify/Render", "health", True, "status=200")
    status_starting = production_monitor.RemoteCheck(
        "Netlify/Render",
        "status",
        False,
        'status=503, body={"detail":"Preparing product data, Chroma indexes, enrichment metadata, and options."}',
    )

    def fake_analyze(*args, **kwargs):
        calls["analyze"] += 1
        return production_monitor.RemoteCheck("analyze", "template analyze", True, "evidence=6")

    monkeypatch.setattr(production_monitor, "check_health", lambda *args, **kwargs: health_ok)
    monkeypatch.setattr(production_monitor, "check_status", lambda *args, **kwargs: status_starting)
    monkeypatch.setattr(production_monitor, "check_analyze", fake_analyze)

    checks = production_monitor.run_monitor_checks(
        "https://example.test",
        timeout=45,
        retries=2,
        retry_delay=8,
        startup_timeout=0,
        poll_interval=1,
    )

    assert [check.passed for check in checks] == [True, False, False]
    assert "readiness_timeout=0s" in checks[1].detail
    assert checks[2].detail == "skipped because /api/status was not ready"
    assert calls["analyze"] == 0


def test_monitor_rechecks_transient_health_after_status_ready(monkeypatch) -> None:
    calls = {"health": 0}
    health_fail = production_monitor.RemoteCheck("Netlify/Render", "health", False, "status=504, body=<empty>")
    health_ok = production_monitor.RemoteCheck("Netlify/Render", "health", True, "status=200")
    status_ok = production_monitor.RemoteCheck("Netlify/Render", "status", True, "products=335")
    analyze_ok = production_monitor.RemoteCheck("analyze", "template analyze", True, "evidence=6")

    def fake_health(*args, **kwargs):
        calls["health"] += 1
        return health_fail if calls["health"] == 1 else health_ok

    monkeypatch.setattr(production_monitor, "check_health", fake_health)
    monkeypatch.setattr(production_monitor, "check_status", lambda *args, **kwargs: status_ok)
    monkeypatch.setattr(production_monitor, "check_analyze", lambda *args, **kwargs: analyze_ok)

    checks = production_monitor.run_monitor_checks("https://example.test", 45, 2, 8, startup_timeout=0, poll_interval=1)

    assert [check.passed for check in checks] == [True, True, True]
    assert calls["health"] == 2


def test_monitor_rechecks_transient_analyze_after_ready_status(monkeypatch) -> None:
    calls = {"analyze": 0}
    health_ok = production_monitor.RemoteCheck("Netlify/Render", "health", True, "status=200")
    status_ok = production_monitor.RemoteCheck("Netlify/Render", "status", True, "products=335")
    analyze_fail = production_monitor.RemoteCheck("Netlify/Render", "template analyze", False, "status=504, body=<empty>")
    analyze_ok = production_monitor.RemoteCheck("analyze", "template analyze", True, "evidence=6")

    def fake_analyze(*args, **kwargs):
        calls["analyze"] += 1
        return analyze_fail if calls["analyze"] == 1 else analyze_ok

    monkeypatch.setattr(production_monitor, "check_health", lambda *args, **kwargs: health_ok)
    monkeypatch.setattr(production_monitor, "check_status", lambda *args, **kwargs: status_ok)
    monkeypatch.setattr(production_monitor, "check_analyze", fake_analyze)

    checks = production_monitor.run_monitor_checks("https://example.test", 45, 2, 8, startup_timeout=0, poll_interval=1)

    assert [check.passed for check in checks] == [True, True, True]
    assert calls["analyze"] == 2
