"""匿名使用统计（遥测）。

隐私约定（开源可审查）：
- 只上报元数据：版本、系统、显卡、引擎、次数、时长、错误类型
- 绝不包含论文正文、文件名、路径、邮箱等个人信息
- 默认开启；界面可一键关闭；关闭后立即清空本地队列
- API Key 留空或未配置 posthog_config.json 时，功能自动禁用
"""

import json
import os
import platform
import queue
import threading
import time
import urllib.request
import uuid
from datetime import datetime, timezone

from .meta import APP_VERSION

POSTHOG_API_KEY = ""  # 留空 = 不启用；或安装目录放 posthog_config.json
POSTHOG_HOST = "https://us.i.posthog.com"
BATCH_MAX = 10
FLUSH_SECONDS = 30
MAX_OFFLINE = 500
TIMEOUT = 10


class Telemetry:
    def __init__(self, base_dir, settings):
        self.base_dir = base_dir
        self.settings = settings
        cfg = self._load_config()
        self.api_key = cfg.get("api_key") or POSTHOG_API_KEY
        self.host = (cfg.get("host") or POSTHOG_HOST).rstrip("/")
        self.enabled = bool(self.api_key) and settings.get(
            "telemetry", "enabled", default=True
        )
        self.device_id = self._ensure_device_id()
        self.q = queue.Queue()
        self.lock = threading.Lock()
        self.last_flush = time.time()
        self.retry = 1.0
        self._load_offline()
        threading.Thread(target=self._loop, daemon=True).start()

    def _load_config(self):
        p = os.path.join(self.base_dir, "posthog_config.json")
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _ensure_device_id(self):
        did = self.settings.get("app", "device_id")
        if not did:
            did = "dev-" + uuid.uuid4().hex
            self.settings.set(did, "app", "device_id")
        return did

    def _offline_path(self):
        return os.path.join(self.base_dir, "telemetry_queue.json")

    def _load_offline(self):
        try:
            with open(self._offline_path(), "r", encoding="utf-8") as f:
                items = json.load(f)
            for it in items[-MAX_OFFLINE:]:
                self.q.put(it)
        except Exception:
            pass

    def _save_offline(self):
        try:
            items = list(self.q.queue)[-MAX_OFFLINE:]
            with open(self._offline_path(), "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False)
        except Exception:
            pass

    def _drop_offline(self):
        try:
            os.remove(self._offline_path())
        except Exception:
            pass

    def set_enabled(self, flag):
        self.enabled = bool(flag) and bool(self.api_key)
        if not self.enabled:
            with self.q.mutex:
                self.q.queue.clear()
            self._drop_offline()
        self.settings.set(self.enabled, "telemetry", "enabled")

    def track(self, event, **props):
        if not self.enabled:
            return
        props.setdefault("app_version", APP_VERSION)
        props.setdefault("os", platform.system() + " " + platform.release())
        rec = {
            "event": event,
            "distinct_id": self.device_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "properties": props,
        }
        self.q.put(rec)
        now = time.time()
        if self.q.qsize() >= BATCH_MAX or now - self.last_flush >= FLUSH_SECONDS:
            self.flush()

    def _loop(self):
        while True:
            time.sleep(1)
            try:
                if not self.enabled:
                    continue
                now = time.time()
                if self.q.qsize() >= BATCH_MAX or now - self.last_flush >= FLUSH_SECONDS:
                    self.flush()
            except Exception:
                pass

    def flush_now(self):
        self.flush()

    def flush(self):
        if not self.enabled:
            return
        with self.lock:
            if self.q.empty():
                self.last_flush = time.time()
                return
            batch = []
            for _ in range(min(BATCH_MAX, self.q.qsize())):
                try:
                    batch.append(self.q.get_nowait())
                except queue.Empty:
                    break
            try:
                self._post(batch)
                self.retry = 1.0
                self.last_flush = time.time()
            except Exception:
                for b in batch:
                    self.q.put(b)
                self._save_offline()
                self.last_flush = time.time() + self.retry
                self.retry = min(self.retry * 2, 60.0)

    def _post(self, batch):
        payload = {"api_key": self.api_key, "batch": batch}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.host + "/batch/",
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "aigc-toolkit-telemetry",
            },
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            r.read()
