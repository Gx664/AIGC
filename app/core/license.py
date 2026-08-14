import os

from core.i18n import tr


class License:
    """免费版 + 预留的专业版授权接口。

    后续接在线激活服务器时，只需替换 _validate 内部实现，
    其余界面逻辑无需改动。
    """

    def __init__(self, base_dir):
        self.path = os.path.join(base_dir, "license.key")

    def current_tier(self):
        key = self._read_key()
        return "pro" if self._validate(key) else "free"

    def _read_key(self):
        if not os.path.exists(self.path):
            return ""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return ""

    def _validate(self, key):
        # 预留接口：当前为本地离线校验（演示用）。
        # 上线收费时改为调用服务器 API 验证。
        return bool(key) and key.startswith("AIGC-PRO-") and len(key) >= 20

    def activate(self, key):
        key = (key or "").strip()
        if self._validate(key):
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(key)
            return True, tr("activated_pro")
        return False, tr("invalid_key")

    def deactivate(self):
        if os.path.exists(self.path):
            os.remove(self.path)
