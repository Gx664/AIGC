"""运行日志：本地滚动保存 + 一键导出（不含论文内容）。"""

import logging
import os
import platform
import sys
import zipfile
from logging.handlers import RotatingFileHandler

from .meta import APP_NAME, APP_VERSION


def _gpu_text():
    try:
        import torch

        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except Exception:
        pass
    return "无GPU(CPU)"


def setup_logging(base_dir):
    log_dir = os.path.join(base_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("aigc")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        fh = RotatingFileHandler(
            os.path.join(log_dir, "app.log"),
            maxBytes=1024 * 1024,
            backupCount=4,
            encoding="utf-8",
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        logger.info("=== %s v%s 启动 ===", APP_NAME, APP_VERSION)
        logger.info("系统: %s | Python: %s | GPU: %s", platform.platform(), platform.python_version(), _gpu_text())
    return logger


def collect_system_info(base_dir):
    lines = [
        "%s v%s" % (APP_NAME, APP_VERSION),
        "系统: %s" % platform.platform(),
        "Python: %s" % platform.python_version(),
        "GPU: %s" % _gpu_text(),
        "安装目录: %s" % base_dir,
    ]
    log_dir = os.path.join(base_dir, "logs")
    if os.path.isdir(log_dir):
        lines.append("日志文件:")
        for fn in sorted(os.listdir(log_dir)):
            fp = os.path.join(log_dir, fn)
            if os.path.isfile(fp):
                lines.append("  - %s (%d KB)" % (fn, os.path.getsize(fp) // 1024))
    return "\n".join(lines)


def export_logs(base_dir, out_zip):
    """把日志 + 系统信息打包成 zip。"""
    log_dir = os.path.join(base_dir, "logs")
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        if os.path.isdir(log_dir):
            for fn in sorted(os.listdir(log_dir)):
                fp = os.path.join(log_dir, fn)
                if os.path.isfile(fp):
                    z.write(fp, "logs/" + fn)
        z.writestr("system_info.txt", collect_system_info(base_dir))

# aigc-toolkit: file purpose marker
