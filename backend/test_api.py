"""
API tests for the FastAPI backend.

Run with:
    pytest test_api.py -v
"""
from __future__ import annotations

import io
import os
import struct

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("TESTING", "1")

import models as _models

_models.DATABASE_URL = "sqlite://"
_models.engine = create_engine(
    _models.DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_models.SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=_models.engine,
)

from main import app
from models import SessionLocal, SmsCode

client = TestClient(app)


@pytest.fixture(scope="module")
def token():
    send = client.post("/auth/sms/send", json={"phone": "13800000001"})
    assert send.status_code == 200

    db = SessionLocal()
    code = db.query(SmsCode).filter(SmsCode.phone == "13800000001").first().code
    db.close()

    verify = client.post("/auth/sms/verify", json={"phone": "13800000001", "code": code})
    assert verify.status_code == 200
    return verify.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


class TestHealthCheck:
    def test_root(self):
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_ping(self):
        response = client.get("/ping")
        assert response.status_code == 200
        assert response.json()["pong"] is True


class TestAuth:
    def test_wechat_login(self):
        response = client.post("/auth/wechat", json={"code": "wx_code_001"})
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data

    def test_wechat_login_saves_profile(self):
        response = client.post(
            "/auth/wechat",
            json={
                "code": "wx_code_profile",
                "name": "真实头像用户",
                "avatar_url": "https://example.com/avatar.png",
            },
        )
        assert response.status_code == 200
        user = response.json()["user"]
        assert user["name"] == "真实头像用户"
        assert user["avatar_url"] == "https://example.com/avatar.png"

    def test_wechat_same_code_same_user(self):
        first = client.post("/auth/wechat", json={"code": "wx_code_same"})
        second = client.post("/auth/wechat", json={"code": "wx_code_same"})
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["user"]["id"] == second.json()["user"]["id"]

    def test_sms_verify_wrong_code(self):
        client.post("/auth/sms/send", json={"phone": "13900000003"})
        response = client.post("/auth/sms/verify", json={"phone": "13900000003", "code": "000000"})
        assert response.status_code == 400

    def test_protected_without_token(self):
        response = client.get("/devices/mine")
        assert response.status_code == 401

    def test_update_profile_name(self, auth_headers):
        response = client.put("/auth/profile", json={"name": "新用户名"}, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["user"]["name"] == "新用户名"

    def test_update_profile_avatar(self, auth_headers):
        response = client.put(
            "/auth/profile",
            json={"avatar_url": "https://example.com/new-avatar.png"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["user"]["avatar_url"] == "https://example.com/new-avatar.png"


class TestDevices:
    pending_command_id = None

    def test_bind_ble_device(self, auth_headers):
        response = client.post(
            "/devices/bind",
            json={"hardware_id": "BH:AA:BB:CC:DD:EE"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["device"]["transport"] == "ble"

    def test_bind_wifi_device(self, auth_headers):
        response = client.post(
            "/devices/bind",
            json={
                "hardware_id": "DUOS-WIFI-001",
                "transport": "wifi",
                "device_name": "MilkV Duo S",
                "board_token": "duos-secret",
                "wifi_host": "192.168.1.99",
                "wifi_port": 8080,
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()["device"]
        assert data["transport"] == "wifi"
        assert data["device_name"] == "MilkV Duo S"

    def test_list_my_devices(self, auth_headers):
        response = client.get("/devices/mine", headers=auth_headers)
        assert response.status_code == 200
        devices = response.json()["devices"]
        assert any(item["hardware_id"] == "BH:AA:BB:CC:DD:EE" for item in devices)
        assert any(item["hardware_id"] == "DUOS-WIFI-001" and item["transport"] == "wifi" for item in devices)

    def test_wifi_register(self):
        response = client.post(
            "/devices/wifi/register",
            json={
                "hardware_id": "DUOS-WIFI-001",
                "board_token": "duos-secret",
                "firmware_version": "1.0.0",
                "wifi_host": "192.168.1.99",
                "wifi_port": 8080,
            },
        )
        assert response.status_code == 200
        assert response.json()["device"]["status"] == "online"

    def test_wifi_heartbeat(self):
        response = client.post(
            "/devices/wifi/heartbeat",
            json={
                "hardware_id": "DUOS-WIFI-001",
                "board_token": "duos-secret",
                "ip_address": "192.168.1.99",
                "battery_level": 76,
                "signal_strength": -51,
                "telemetry": {
                    "strength": 42,
                    "rms_value": 128.6,
                    "side_pressure": 19.4,
                    "muscle_status": "正常",
                },
            },
        )
        assert response.status_code == 200
        assert response.json()["pending_command"] is None

    def test_wifi_status(self, auth_headers):
        response = client.get("/devices/DUOS-WIFI-001/status", headers=auth_headers)
        assert response.status_code == 200
        device = response.json()["device"]
        assert device["status"] == "online"
        assert device["battery_level"] == 76
        assert device["telemetry"]["strength"] == 42

    def test_push_wifi_command(self, auth_headers):
        response = client.post(
            "/devices/DUOS-WIFI-001/command",
            json={
                "action": "start_collect",
                "payload": {"mode": "personal", "gesture_name": "握拳"},
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        command = response.json()["command"]
        assert command["action"] == "start_collect"
        assert command["command_id"]

    def test_heartbeat_returns_pending_command(self):
        response = client.post(
            "/devices/wifi/heartbeat",
            json={
                "hardware_id": "DUOS-WIFI-001",
                "board_token": "duos-secret",
                "ip_address": "192.168.1.99",
                "telemetry": {"strength": 56},
            },
        )
        assert response.status_code == 200
        pending = response.json()["pending_command"]
        assert pending["action"] == "start_collect"
        TestDevices.pending_command_id = pending["command_id"]

    def test_wifi_command_ack(self):
        response = client.post(
            "/devices/wifi/command/ack",
            json={
                "hardware_id": "DUOS-WIFI-001",
                "board_token": "duos-secret",
                "command_id": TestDevices.pending_command_id,
                "success": True,
                "message": "started",
                "result": {"collecting": True},
            },
        )
        assert response.status_code == 200
        assert response.json()["ack"]["success"] is True

    def test_status_contains_last_ack(self, auth_headers):
        response = client.get("/devices/DUOS-WIFI-001/status", headers=auth_headers)
        assert response.status_code == 200
        ack = response.json()["device"]["last_command_ack"]
        assert ack["command_id"] == TestDevices.pending_command_id

    def test_unbind_device(self, auth_headers):
        response = client.delete("/devices/BH:AA:BB:CC:DD:EE", headers=auth_headers)
        assert response.status_code == 200

    def test_unbind_nonexistent(self, auth_headers):
        response = client.delete("/devices/NOT_EXIST", headers=auth_headers)
        assert response.status_code == 404


class TestEsp32Telemetry:
    def test_wifi_heartbeat_contains_module_status_and_prediction(self, auth_headers):
        bind = client.post(
            "/devices/bind",
            json={
                "hardware_id": "ESP32-HAND-001",
                "transport": "wifi",
                "device_name": "ESP32 Hand",
                "board_token": "esp32-secret",
            },
            headers=auth_headers,
        )
        assert bind.status_code == 200

        heartbeat = client.post(
            "/devices/wifi/heartbeat",
            json={
                "hardware_id": "ESP32-HAND-001",
                "board_token": "esp32-secret",
                "battery_level": 63,
                "signal_strength": -47,
                "telemetry": {
                    "module_statuses": {
                        "storage": "ok",
                        "model": "loaded",
                        "bluetooth": "connected",
                        "cpu": "running",
                    },
                    "prediction_result": "握拳",
                    "prediction_confidence": 0.94,
                },
            },
        )
        assert heartbeat.status_code == 200

        status = client.get("/devices/ESP32-HAND-001/status", headers=auth_headers)
        assert status.status_code == 200
        device = status.json()["device"]
        assert device["battery_level"] == 63
        assert device["telemetry"]["module_statuses"]["storage"] == "ok"
        assert device["telemetry"]["prediction_result"] == "握拳"

    def test_wifi_emg_upload_creates_training_session(self, auth_headers):
        first_batch = client.post(
            "/devices/wifi/emg",
            json={
                "hardware_id": "ESP32-HAND-001",
                "board_token": "esp32-secret",
                "session_id": "esp32_session_001",
                "gesture_name": "握拳",
                "samples": [
                    [100, 101, 102, 103, 104, 105, 106, 107],
                    [110, 111, 112, 113, 114, 115, 116, 117],
                ],
            },
        )
        assert first_batch.status_code == 200
        assert first_batch.json()["sample_count"] == 2

        final_batch = client.post(
            "/devices/wifi/emg",
            json={
                "hardware_id": "ESP32-HAND-001",
                "board_token": "esp32-secret",
                "session_id": "esp32_session_001",
                "gesture_name": "握拳",
                "samples": [
                    [120, 121, 122, 123, 124, 125, 126, 127],
                ],
                "is_final": True,
            },
        )
        assert final_batch.status_code == 200
        assert final_batch.json()["completed"] is True
        assert final_batch.json()["total_samples"] == 3

        status = client.get("/devices/ESP32-HAND-001/status", headers=auth_headers)
        assert status.status_code == 200
        collect_state = status.json()["device"]["telemetry"]["last_collection"]
        assert collect_state["sample_count"] == 3
        assert collect_state["recording"] is False

    def test_delete_emg_session(self, auth_headers):
        response = client.delete("/devices/emg/sessions/esp32_session_001", headers=auth_headers)
        assert response.status_code == 200

        get_response = client.get("/devices/emg/sessions/esp32_session_001", headers=auth_headers)
        assert get_response.status_code == 404


class TestHealth:
    def test_generate_report(self, auth_headers):
        response = client.post("/health/report/generate", json={}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "rms_value" in data
        assert "side_presure" in data
        assert "muscle_status" in data
        assert "generated_at" in data

    def test_get_records(self, auth_headers):
        response = client.get("/health/records", headers=auth_headers)
        assert response.status_code == 200
        assert len(response.json()["records"]) >= 1


class TestAI:
    def test_battery_question(self, auth_headers):
        response = client.post("/ai/chat", json={"message": "设备电量怎么样"}, headers=auth_headers)
        assert response.status_code == 200
        assert "reply" in response.json()

    def test_emg_question(self, auth_headers):
        response = client.post("/ai/chat", json={"message": "最近肌电数据正常吗"}, headers=auth_headers)
        assert response.status_code == 200
        assert "reply" in response.json()

    def test_empty_message_rejected(self, auth_headers):
        response = client.post("/ai/chat", json={"message": "   "}, headers=auth_headers)
        assert response.status_code == 400


class _TestAIDeviceContext:
    def test_device_status_question_uses_bound_device_data(self, auth_headers):
        response = client.post(
            "/ai/chat",
            json={
                "message": "设备现在在线吗，电量多少？",
                "hardware_id": "DUOS-WIFI-001",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        reply = response.json()["reply"]
        assert "76" in reply or "online" in reply or "在线" in reply


class TestAIDeviceContextPrepared:
    def test_device_status_question_uses_bound_device_data(self, auth_headers):
        bind = client.post(
            "/devices/bind",
            json={
                "hardware_id": "DUOS-WIFI-001",
                "transport": "wifi",
                "device_name": "MilkV Duo S",
                "board_token": "duos-secret",
                "wifi_host": "192.168.1.99",
                "wifi_port": 8080,
            },
            headers=auth_headers,
        )
        assert bind.status_code == 200

        heartbeat = client.post(
            "/devices/wifi/heartbeat",
            json={
                "hardware_id": "DUOS-WIFI-001",
                "board_token": "duos-secret",
                "ip_address": "192.168.1.99",
                "battery_level": 76,
                "signal_strength": -51,
                "telemetry": {
                    "rms_value": 128.6,
                    "side_pressure": 19.4,
                    "muscle_status": "正常",
                },
            },
        )
        assert heartbeat.status_code == 200

        response = client.post(
            "/ai/chat",
            json={
                "message": "设备现在在线吗，电量多少？",
                "hardware_id": "DUOS-WIFI-001",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        reply = response.json()["reply"]
        assert "76" in reply or "online" in reply or "在线" in reply


class TestForum:
    post_id = None
    post_with_image_id = None
    comment_id = None
    reply_id = None
    image_url = None

    def test_list_posts(self):
        response = client.get("/forum/posts?page=1&size=15")
        assert response.status_code == 200
        assert "posts" in response.json()

    def test_create_post(self, auth_headers):
        response = client.post(
            "/forum/posts",
            json={"content": "测试帖子", "image_urls": []},
            headers=auth_headers,
        )
        assert response.status_code == 200
        TestForum.post_id = response.json()["post_id"]

    def test_upload_image_and_create_post_with_image(self, auth_headers):
        upload = client.post(
            "/forum/upload/image",
            files={"file": ("demo.png", io.BytesIO(b"fake-image-content"), "image/png")},
            headers=auth_headers,
        )
        assert upload.status_code == 200
        TestForum.image_url = upload.json()["url"]
        assert TestForum.image_url.startswith("/static/images/")

        post = client.post(
            "/forum/posts",
            json={"content": "带图帖子", "image_urls": [TestForum.image_url]},
            headers=auth_headers,
        )
        assert post.status_code == 200
        TestForum.post_with_image_id = post.json()["post_id"]

    def test_like_toggle(self, auth_headers):
        first = client.post(f"/forum/posts/{TestForum.post_id}/like", headers=auth_headers)
        second = client.post(f"/forum/posts/{TestForum.post_id}/like", headers=auth_headers)
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["liked"] is True
        assert second.json()["liked"] is False

    def test_add_comment_and_list(self, auth_headers):
        add = client.post(
            f"/forum/posts/{TestForum.post_id}/comments",
            json={"content": "继续保持"},
            headers=auth_headers,
        )
        assert add.status_code == 200
        TestForum.comment_id = add.json()["comment_id"]

        list_response = client.get(f"/forum/posts/{TestForum.post_id}/comments?page=1&size=20")
        assert list_response.status_code == 200
        data = list_response.json()
        assert data["total"] >= 1
        assert data["comments"][0]["content"] == "继续保持"


    def test_reply_comment_and_list(self, auth_headers):
        add = client.post(
            f"/forum/posts/{TestForum.post_id}/comments",
            json={"content": "reply", "parent_id": TestForum.comment_id},
            headers=auth_headers,
        )
        assert add.status_code == 200
        TestForum.reply_id = add.json()["comment_id"]

        list_response = client.get(f"/forum/posts/{TestForum.post_id}/comments?page=1&size=20")
        assert list_response.status_code == 200
        data = list_response.json()
        assert data["total"] >= 2
        assert len(data["comments"][0]["replies"]) >= 1
        assert data["comments"][0]["replies"][0]["content"] == "reply"

    def test_delete_own_reply(self, auth_headers):
        response = client.delete(
            f"/forum/posts/{TestForum.post_id}/comments/{TestForum.reply_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["deleted_count"] == 1

        list_response = client.get(f"/forum/posts/{TestForum.post_id}/comments?page=1&size=20")
        assert list_response.status_code == 200
        data = list_response.json()
        replies = data["comments"][0]["replies"]
        assert all(item["id"] != TestForum.reply_id for item in replies)

    def test_delete_own_top_level_comment(self, auth_headers):
        response = client.delete(
            f"/forum/posts/{TestForum.post_id}/comments/{TestForum.comment_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["deleted_count"] == 1

        list_response = client.get(
            f"/forum/posts/{TestForum.post_id}/comments?page=1&size=20",
            headers=auth_headers,
        )
        assert list_response.status_code == 200
        data = list_response.json()
        assert all(item["id"] != TestForum.comment_id for item in data["comments"])

    def test_delete_own_post(self, auth_headers):
        add_comment = client.post(
            f"/forum/posts/{TestForum.post_with_image_id}/comments",
            json={"content": "delete cascade comment"},
            headers=auth_headers,
        )
        assert add_comment.status_code == 200
        comment_id = add_comment.json()["comment_id"]

        add_reply = client.post(
            f"/forum/posts/{TestForum.post_with_image_id}/comments",
            json={"content": "delete cascade reply", "parent_id": comment_id},
            headers=auth_headers,
        )
        assert add_reply.status_code == 200

        response = client.delete(
            f"/forum/posts/{TestForum.post_with_image_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200

        list_response = client.get("/forum/posts?page=1&size=15", headers=auth_headers)
        assert list_response.status_code == 200
        posts = list_response.json()["posts"]
        assert all(item["id"] != TestForum.post_with_image_id for item in posts)


class TestUpload:
    def test_upload_chunk_and_merge(self, auth_headers):
        values = []
        for _ in range(100):
            for channel in range(8):
                values.append(500 + channel * 10)
        raw = struct.pack(f"<{len(values)}h", *values)

        session_id = "test_session_001"
        chunk_size = len(raw) // 2
        chunks = [raw[:chunk_size], raw[chunk_size:]]

        for index, chunk in enumerate(chunks):
            response = client.post(
                "/upload/chunk",
                data={"session_id": session_id, "chunk_index": str(index)},
                files={"file": (f"chunk_{index}.dat", io.BytesIO(chunk), "application/octet-stream")},
                headers=auth_headers,
            )
            assert response.status_code == 200

        merge = client.post(
            "/upload/merge",
            json={
                "session_id": session_id,
                "total_chunks": len(chunks),
                "gesture_name": "握拳",
            },
            headers=auth_headers,
        )
        assert merge.status_code == 200
        data = merge.json()
        assert data["sample_count"] == 100
        assert data["rms"] > 0
