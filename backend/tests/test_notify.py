"""外部推送提醒：配置存取与掩码、摘要聚合、消息组装、节流与渠道校验（网络全 mock）。"""
import json

import pytest

from app import db, notify


@pytest.fixture
def cfg_clean():
    db.set_meta(notify._META_KEY, "")
    db.set_meta(notify._LAST_PUSH_KEY, "")
    db.set_meta(notify._ERR_KEY, "")
    yield
    db.set_meta(notify._META_KEY, "")
    db.set_meta(notify._LAST_PUSH_KEY, "")
    db.set_meta(notify._ERR_KEY, "")


def test_defaults_and_roundtrip(cfg_clean):
    cfg = notify.get_cfg()
    assert cfg["enabled"] is False and cfg["channel"] == "serverchan" and cfg["push_hour"] == 8
    saved = notify.save_cfg({"enabled": True, "channel": "wecom_webhook",
                             "wecom_webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc",
                             "push_hour": 99})
    assert saved["enabled"] is True and saved["channel"] == "wecom_webhook"
    assert saved["push_hour"] == 23  # 钳制到 0-23
    # 非法渠道回退默认
    notify.save_cfg({"channel": "evil"})
    assert notify.get_cfg()["channel"] == "serverchan"


def test_masked_cfg_hides_secrets(cfg_clean):
    notify.save_cfg({"serverchan_sendkey": "SCT1234567890abcdef",
                     "wecom_webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=secret"})
    m = notify.masked_cfg()
    assert "SCT1234567890abcdef" not in json.dumps(m)
    assert "secret" not in m["wecom_webhook"]
    assert "qyapi.weixin.qq.com" in m["wecom_webhook"]  # host 保留便于辨认


def _patch_digest(monkeypatch, spaces, digest):
    monkeypatch.setattr(db, "list_spaces", lambda: spaces)
    monkeypatch.setattr(notify.db, "today_snapshot", lambda sid: digest[sid])


def test_build_digest_aggregates_and_skips_empty(cfg_clean, monkeypatch):
    spaces = [{"id": "s1", "name": "高数"}, {"id": "s2", "name": "普物"}]
    digest_map = {
        "s1": {"due_total": 3, "flash_due": 5, "tasks_today": [{"id": "t1"}],
               "due_points": [{"point": "泰勒公式"}, {"point": "洛必达"}, {"point": "夹逼"}]},
        "s2": {"due_total": 0, "flash_due": 0, "tasks_today": [], "due_points": []},
    }
    _patch_digest(monkeypatch, spaces, digest_map)
    d = notify.build_digest()
    assert d and len(d["items"]) == 1  # 空空间不进摘要
    assert d["items"][0]["space"] == "高数" and d["items"][0]["top_points"][0] == "泰勒公式"
    monkeypatch.setattr(notify.db, "today_snapshot",
                        lambda sid: {"due_total": 0, "flash_due": 0, "tasks_today": [], "due_points": []})
    assert notify.build_digest() is None


def test_format_text_pure(cfg_clean):
    digest = {"date": "2026-09-13", "items": [
        {"space": "高数", "due": 3, "flash": 5, "tasks": 1, "top_points": ["泰勒公式"]}]}
    title, text = notify.format_text(digest)
    assert "3 个知识点" in title and "5 张闪卡" in title
    assert "《高数》" in text and "泰勒公式" in text


def test_channel_validation_before_network(cfg_clean):
    with pytest.raises(ValueError):
        notify._send_serverchan("", "t", "x")
    for bad in ("", "https://evil.com/x?key=k"):
        with pytest.raises(ValueError):
            notify._send_wecom(bad, "t", "x")


def test_push_throttle_and_gates(cfg_clean, monkeypatch):
    digest = {"date": "2026-09-13", "items": [
        {"space": "高数", "due": 1, "flash": 0, "tasks": 0, "top_points": []}]}
    sent = []

    def fake_send(cfg, title, text):
        sent.append(title)

    monkeypatch.setattr(notify, "send", fake_send)
    monkeypatch.setattr(notify, "build_digest", lambda: dict(digest))
    monkeypatch.setattr(notify, "get_cfg",
                        lambda: {**notify._defaults(), "enabled": True, "push_hour": 8})

    # 未到 push_hour：不推
    monkeypatch.setattr(notify.time, "localtime", lambda: type("T", (), {"tm_hour": 7})())
    assert notify.push_if_due() == {"pushed": False, "reason": "before_push_hour"}
    # 到点：推成功并记录日期
    monkeypatch.setattr(notify.time, "localtime", lambda: type("T", (), {"tm_hour": 9})())
    r = notify.push_if_due()
    assert r["pushed"] is True and len(sent) == 1
    # 当日再触发：节流
    assert notify.push_if_due() == {"pushed": False, "reason": "already_pushed"}
    assert len(sent) == 1
    # force 绕过节流
    assert notify.push_if_due(force=True)["pushed"] is True
    assert len(sent) == 2
    # 无到期内容：不推
    monkeypatch.setattr(notify, "build_digest", lambda: None)
    db.set_meta(notify._LAST_PUSH_KEY, "")
    assert notify.push_if_due() == {"pushed": False, "reason": "nothing_due"}


def test_send_failure_records_error(cfg_clean, monkeypatch):
    def boom(cfg, title, text):
        raise RuntimeError("连接超时")

    monkeypatch.setattr(notify, "send", boom)
    monkeypatch.setattr(notify, "build_digest",
                        lambda: {"date": "2026-09-13", "items": [{"space": "s", "due": 1,
                                                                  "flash": 0, "tasks": 0, "top_points": []}]})
    monkeypatch.setattr(notify, "get_cfg", lambda: {**notify._defaults(), "enabled": True})
    r = notify.push_if_due()
    assert r["pushed"] is False and r["reason"].startswith("send_failed")
    assert "连接超时" in db.get_meta(notify._ERR_KEY)


def test_disabled_short_circuit(cfg_clean, monkeypatch):
    monkeypatch.setattr(notify, "build_digest",
                        lambda: (_ for _ in ()).throw(AssertionError("disabled 时不该构建摘要")))
    assert notify.push_if_due() == {"pushed": False, "reason": "disabled"}
