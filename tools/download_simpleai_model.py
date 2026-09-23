"""下载 SimpleAI 中文检测模型（约 400MB，走国内镜像）。"""

import os

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from transformers import AutoModelForSequenceClassification, AutoTokenizer

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_ID = "Hello-SimpleAI/chatgpt-detector-roberta-chinese"
MODEL_DIR = os.path.join(BASE, "models", "simpleai")

os.makedirs(MODEL_DIR, exist_ok=True)
print("== 下载分词器 ==")
AutoTokenizer.from_pretrained(MODEL_ID, cache_dir=MODEL_DIR)
print("== 下载模型参数（约 400MB，请耐心等待）==")
AutoModelForSequenceClassification.from_pretrained(MODEL_ID, cache_dir=MODEL_DIR)
print("模型就绪：", MODEL_DIR)
