"""Optional Feishu long-connection listener for Base change invalidation."""

from __future__ import annotations

import json
import os


def listen_forever(on_change=None):
    try:
        import lark_oapi as lark
    except ImportError as exc:
        raise RuntimeError("listen requires lark-oapi; install it only in the service runtime") from exc
    app_id, secret = os.getenv("FEISHU_APP_ID"), os.getenv("FEISHU_APP_SECRET")
    if not app_id or not secret:
        raise RuntimeError("FEISHU_APP_ID and FEISHU_APP_SECRET are required")

    def callback(data):
        payload = json.loads(lark.JSON.marshal(data))
        if on_change: on_change(payload)

    handler = lark.EventDispatcherHandler.builder("", "").register_p1_customized_event(
        "drive.file.bitable_record_changed_v1", callback
    ).build()
    lark.ws.Client(app_id, secret, event_handler=handler, log_level=lark.LogLevel.INFO).start()
