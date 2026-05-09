from __future__ import annotations

from scripts import production_monitor


def test_monitor_rechecks_transient_health_and_status_after_analyze_success(monkeypatch) -> None:
    calls = {"health": 0, "status": 0, "analyze": 0}
    transient_health = production_monitor.RemoteCheck("Netlify/Render", "health", False, "status=504, body=<empty>")
    recovered_health = production_monitor.RemoteCheck("Netlify/Render", "health", True, "status=200")
    transient_status = production_monitor.RemoteCheck("Netlify/Render", "status", False, "status=504, body=<empty>")
    recovered_status = production_monitor.RemoteCheck("Netlify/Render", "status", True, "products=335")
    analyze_ok = production_monitor.RemoteCheck("analyze", "template analyze", True, "evidence=6")

    def fake_health(*args, **kwargs):
        calls["health"] += 1
        return transient_health if calls["health"] == 1 else recovered_health

    def fake_status(*args, **kwargs):
        calls["status"] += 1
        return transient_status if calls["status"] == 1 else recovered_status

    def fake_analyze(*args, **kwargs):
        calls["analyze"] += 1
        return analyze_ok

    monkeypatch.setattr(production_monitor, "check_health", fake_health)
    monkeypatch.setattr(production_monitor, "check_status", fake_status)
    monkeypatch.setattr(production_monitor, "check_analyze", fake_analyze)

    checks = production_monitor.run_monitor_checks("https://example.test", 45, 2, 8)

    assert [check.passed for check in checks] == [True, True, True]
    assert calls == {"health": 2, "status": 2, "analyze": 1}


def test_monitor_keeps_persistent_status_failure(monkeypatch) -> None:
    calls = {"status": 0}
    health_ok = production_monitor.RemoteCheck("Netlify/Render", "health", True, "status=200")
    status_fail = production_monitor.RemoteCheck("Netlify/Render", "status", False, "status=504, body=<empty>")
    analyze_ok = production_monitor.RemoteCheck("analyze", "template analyze", True, "evidence=6")

    def fake_status(*args, **kwargs):
        calls["status"] += 1
        return status_fail

    monkeypatch.setattr(production_monitor, "check_health", lambda *args, **kwargs: health_ok)
    monkeypatch.setattr(production_monitor, "check_status", fake_status)
    monkeypatch.setattr(production_monitor, "check_analyze", lambda *args, **kwargs: analyze_ok)

    checks = production_monitor.run_monitor_checks("https://example.test", 45, 2, 8)

    assert [check.passed for check in checks] == [True, False, True]
    assert calls["status"] == 2


def test_monitor_does_not_recheck_when_analyze_fails(monkeypatch) -> None:
    calls = {"health": 0, "status": 0, "analyze": 0}
    health_fail = production_monitor.RemoteCheck("Netlify/Render", "health", False, "status=504, body=<empty>")
    status_fail = production_monitor.RemoteCheck("Netlify/Render", "status", False, "status=504, body=<empty>")
    analyze_fail = production_monitor.RemoteCheck("analyze", "template analyze", False, "status=504, body=<empty>")

    def fake_health(*args, **kwargs):
        calls["health"] += 1
        return health_fail

    def fake_status(*args, **kwargs):
        calls["status"] += 1
        return status_fail

    def fake_analyze(*args, **kwargs):
        calls["analyze"] += 1
        return analyze_fail

    monkeypatch.setattr(production_monitor, "check_health", fake_health)
    monkeypatch.setattr(production_monitor, "check_status", fake_status)
    monkeypatch.setattr(production_monitor, "check_analyze", fake_analyze)

    checks = production_monitor.run_monitor_checks("https://example.test", 45, 2, 8)

    assert [check.passed for check in checks] == [False, False, False]
    assert calls == {"health": 1, "status": 1, "analyze": 1}
