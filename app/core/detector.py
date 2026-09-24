import concurrent.futures

from .engines import TORCH_OK, create_engine
from .i18n import tr


def _torch_error():
    from . import engines

    return getattr(engines, "TORCH_ERROR", "")


def _devices(params):
    import torch

    if params.get("use_gpu", True) and torch.cuda.is_available():
        n = torch.cuda.device_count()
        maxw = params.get("max_workers", 0) or n
        return ["cuda:%d" % i for i in range(min(n, maxw))]
    return ["cpu"]


def _run_one_device(engine_cfg, base_dir, paragraphs, device, params, progress_cb=None):
    engine = create_engine(engine_cfg, base_dir)
    return engine.predict_paragraphs(paragraphs, device, **params)


def detect_local(engine_cfg, base_dir, paragraphs, params, progress_cb=None):
    """本地检测：多张显卡时按段落分片并行，单卡/CPU 直接跑。"""
    if not TORCH_OK:
        raise RuntimeError(tr("torch_unavailable") % _torch_error())
    devices = _devices(params)
    if len(devices) == 1:
        return _run_one_device(engine_cfg, base_dir, paragraphs, devices[0], params)

    total = len(paragraphs)
    chunk = max(total // len(devices), 1)
    splits = []
    for d in range(len(devices)):
        start = d * chunk
        end = total if d == len(devices) - 1 else (d + 1) * chunk
        splits.append((devices[d], list(range(start, end))))

    results = [None] * total
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(splits)) as ex:
        futures = []
        for device, indices in splits:
            sub = [paragraphs[i] for i in indices]
            futures.append(ex.submit(_run_one_device, engine_cfg, base_dir, sub, device, params))
        for fut, (device, indices) in zip(futures, splits):
            probs = fut.result()
            for i, p in zip(indices, probs):
                results[i] = p
            done += len(indices)
            if progress_cb:
                progress_cb(done, total)
    return results


def detect_with_cluster(engine_cfg, base_dir, paragraphs, params, master, progress_cb=None):
    """集群检测：把段落分片发给局域网工作节点，本地也留一份兜底。"""
    nodes = master.nodes_snapshot()
    if not nodes:
        return detect_local(engine_cfg, base_dir, paragraphs, params, progress_cb)

    addrs = list(nodes.keys())
    total = len(paragraphs)
    chunk = max(total // len(addrs), 1)
    splits = []
    for i in range(len(addrs)):
        start = i * chunk
        end = total if i == len(addrs) - 1 else (i + 1) * chunk
        splits.append((addrs[i], list(range(start, end))))

    results = [None] * total
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(splits)) as ex:
        futures = []
        for addr, indices in splits:
            sub = [paragraphs[i] for i in indices]
            futures.append(
                ex.submit(master.detect_chunk, addr, engine_cfg["id"], sub, params)
            )
        for fut, (addr, indices) in zip(futures, splits):
            try:
                probs = fut.result()
            except Exception:
                # 工作节点失败时回退到本机计算该分片
                sub = [paragraphs[i] for i in indices]
                probs = _run_one_device(
                    engine_cfg, base_dir, sub, _devices(params)[0], params
                )
            for i, p in zip(indices, probs):
                results[i] = p
            done += len(indices)
            if progress_cb:
                progress_cb(done, total)
    return results

# aigc-toolkit: file purpose marker
