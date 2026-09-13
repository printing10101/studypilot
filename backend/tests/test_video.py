"""B站视频字幕导入：BV 解析、时间戳转写、域明白名单、入库闭环（网络全 mock）。"""
import pytest

from app import db, llm, video


def test_extract_bvid_variants():
    assert video.extract_bvid("BV1xx411c7mD") == "BV1xx411c7mD"
    assert video.extract_bvid("https://www.bilibili.com/video/BV1GJ411x7h7/?p=2&vd_source=x") \
        == "BV1GJ411x7h7"
    assert video.extract_bvid("看看这个 www.bilibili.com/video/BV1abcDEFghi 讲膜的") == "BV1abcDEFghi"
    for bad in ("", "   ", "https://example.com/video/BV123", "b23.tv/abc123",
                "https://b23.tv/BV1abcDEFghi"):
        with pytest.raises(ValueError):
            video.extract_bvid(bad)


def test_fmt_ts():
    assert video._fmt_ts(0) == "00:00"
    assert video._fmt_ts(59.4) == "00:59"
    assert video._fmt_ts(61) == "01:01"
    assert video._fmt_ts(3600) == "1:00:00"
    assert video._fmt_ts(-5) == "00:00"


def _sub_body():
    return {"body": [
        {"from": 0.0, "to": 3.0, "content": "今天讲傅里叶变换"},
        {"from": 3.5, "to": 6.0, "content": "它把信号从时域搬到频域"},
        {"from": 30.0, "to": 33.0, "content": "第二部分讲卷积"},   # 与上一行间隔 24s → 同段
        {"from": 120.0, "to": 123.0, "content": "第三部分讲采样"},  # 间隔 87s → 断段
    ]}


def test_transcript_groups_by_gap():
    text = video.transcript_from_subtitle(_sub_body(), "信号与系统第3讲", owner="张老师", duration_sec=3661)
    assert text.startswith("【视频字幕】信号与系统第3讲（UP：张老师），时长 1:01:01")
    paras = [p for p in text.split("\n\n") if p]
    # 头部 + 段[0-30s：间隔 24s≤25s 同段] + 段[120s：间隔 87s 断段] = 3 块
    assert len(paras) == 3
    assert "[01:00]" not in text
    assert "[02:00] 第三部分讲采样" in text
    assert "[00:00] 今天讲傅里叶变换" in text


def test_transcript_caps_paragraph_lines():
    body = {"body": [{"from": i * 2.0, "to": i * 2.0 + 1.5, "content": f"第{i}行"}
                     for i in range(30)]}
    text = video.transcript_from_subtitle(body, "长字幕")
    paras = [p for p in text.split("\n\n") if p]
    # 30 行 / 每段上限 10 行 = 3 段（+头部）
    assert len(paras) == 4


def test_transcript_rejects_empty():
    for bad in ({}, {"body": []}, {"body": [{"from": 1, "to": 2, "content": "  "}]}):
        with pytest.raises(ValueError):
            video.transcript_from_subtitle(bad, "x")


def test_pick_subtitle_prefers_chinese():
    subs = [{"lan": "en-US", "subtitle_url": "https://aisubtitle.hdslb.com/en.json"},
            {"lan": "ai-zh", "subtitle_url": "https://aisubtitle.hdslb.com/ai.json"},
            {"lan": "zh-CN", "subtitle_url": "https://aisubtitle.hdslb.com/zh.json"}]
    assert video.pick_subtitle(subs)["lan"] == "zh-CN"
    assert video.pick_subtitle(subs[:2])["lan"] == "ai-zh"
    with pytest.raises(ValueError):
        video.pick_subtitle([])
    with pytest.raises(ValueError):
        video.pick_subtitle([{"lan": "zh-CN"}])  # 缺下载地址


def test_check_host_whitelist():
    assert video._check_host("https://api.bilibili.com/x/web-interface/view?bvid=BV1x", ())
    assert video._check_host("https://aisubtitle.hdslb.com/s.json", (video._SUB_HOST_SUFFIX,))
    for bad in ("https://evil.com/s.json", "file:///etc/passwd",
                "https://api.bilibili.com.evil.com/x"):
        with pytest.raises(ValueError):
            video._check_host(bad, (video._SUB_HOST_SUFFIX,))


def test_ingest_video_end_to_end(db_space, tmp_path, monkeypatch):
    """全链路（网络/嵌入 mock）：文档入库、时间戳转写参与向量索引。"""
    info = {"bvid": "BV1GJ411x7h7", "title": "信号与系统第3讲", "owner": "张老师",
            "duration": 600,
            "subtitles": [{"lan": "zh-CN", "subtitle_url": "https://aisubtitle.hdslb.com/zh.json"}]}
    monkeypatch.setattr(video, "fetch_video_info", lambda bvid: info)
    monkeypatch.setattr(video, "fetch_subtitle_json", lambda url: _sub_body())

    captured = {}

    def fake_embed(texts, *a, **k):
        captured["n"] = len(texts)
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(llm, "embed", fake_embed)
    r = video.ingest_video(db_space, "https://www.bilibili.com/video/BV1GJ411x7h7/")
    assert r["status"] == "ready" and r["chunks"] == captured["n"] >= 1
    doc = db.get_document(r["id"])
    assert doc["filename"] == "【视频】信号与系统第3讲.txt"
    assert doc["status"] == "ready"
    chunks = [c for c in db.space_chunks(db_space) if c["document_id"] == r["id"]]
    assert any("[00:00] 今天讲傅里叶变换" in c["text"] for c in chunks)
    assert any("[02:00]" in c["text"] for c in chunks)


def test_ingest_video_no_subtitle_gives_readable_error(db_space, monkeypatch):
    info = {"bvid": "BV1GJ411x7h7", "title": "无字幕视频", "owner": "", "duration": 100,
            "subtitles": []}
    monkeypatch.setattr(video, "fetch_video_info", lambda bvid: info)
    with pytest.raises(ValueError) as ei:
        video.ingest_video(db_space, "BV1GJ411x7h7")
    assert "没有可用的 CC 字幕" in str(ei.value)
    assert db.list_documents(db_space) == []
