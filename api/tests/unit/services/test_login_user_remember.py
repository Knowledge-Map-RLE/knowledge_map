"""Unit-тесты для application.auth.login_user: встраивание флага remember_me в device_info."""
import json

from application.auth.login_user import login_user


class FakeGateway:
    def __init__(self):
        self.seen = None

    def login(self, login, password, captcha, device_info="", ip_address=""):
        self.seen = device_info
        return {"success": True, "message": "ok", "token": "t", "user": {"uid": "1"}, "requires_2fa": False}


def test_remember_me_embeds_flag_preserving_device_info():
    gateway = FakeGateway()
    login_user(gateway, "a", "b", "c", device_info='{"ua":"chrome"}', remember_me=True)
    payload = json.loads(gateway.seen)
    assert payload["remember_me"] is True
    assert payload["ua"] == "chrome"


def test_remember_me_false_passes_device_info_unchanged():
    gateway = FakeGateway()
    login_user(gateway, "a", "b", "c", remember_me=False)
    assert gateway.seen == ""


def test_remember_me_with_invalid_device_info():
    gateway = FakeGateway()
    login_user(gateway, "a", "b", "c", device_info="not-json", remember_me=True)
    payload = json.loads(gateway.seen)
    assert payload["remember_me"] is True
