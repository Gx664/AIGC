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
    if progress_cb:
        # 引擎接口本来就支持 progress_cb（simpleai 每段回调一次），但这个参数
        # 此前**接了没人用** —— 单卡（绝大多数用户）因此整个检测阶段进度条都
        # 不动，只在 4%~14%（下载模型）与结尾 99% 跳两下。
        params = dict(params, progress_cb=progress_cb)
    probs = engine.predict_paragraphs(paragraphs, device, **params)
    # 一并回传引擎实例：统计派引擎会把逐段四档（GLTR Test-2）存在
    # `last_buckets` 上，只返回 probs 的话那份数据就随实例一起丢了。
    return probs, engine


def detect_local(engine_cfg, base_dir, paragraphs, params, progress_cb=None):
    """本地检测：多张显卡时按段落分片并行，单卡/CPU 直接跑。

    返回 ``(probs, engine)`` —— ``engine`` 是最先完成的那个实例，
    调用方从它上面取 ``last_buckets``（四档）。多卡时四档取第一片的。
    """
    if not TORCH_OK:
        raise RuntimeError(tr("torch_unavailable") % _torch_error())
    devices = _devices(params)
    if len(devices) == 1:
        # 单卡/CPU：把 progress_cb 一路传进引擎（多卡分支不传 —— 分片在各自
        # 线程里跑，多个回调同时改同一条进度条只会打架）
        return _run_one_device(engine_cfg, base_dir, paragraphs, devices[0],
                               params, progress_cb)

    total = len(paragraphs)
    chunk = max(total // len(devices), 1)
    splits = []
    for d in range(len(devices)):
        start = d * chunk
        end = total if d == len(devices) - 1 else (d + 1) * chunk
        splits.append((devices[d], list(range(start, end))))

    results = [None] * total
    first_engine = None
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(splits)) as ex:
        futures = []
        for device, indices in splits:
            sub = [paragraphs[i] for i in indices]
            futures.append(ex.submit(_run_one_device, engine_cfg, base_dir, sub, device, params))
        for fut, (device, indices) in zip(futures, splits):
            probs, eng = fut.result()
            if first_engine is None:
                first_engine = eng
            for i, p in zip(indices, probs):
                results[i] = p
            done += len(indices)
            if progress_cb:
                progress_cb(done, total)
    return results, first_engine


def detect_with_cluster(engine_cfg, base_dir, paragraphs, params, master, progress_cb=None):
    """集群检测：把段落分片发给局域网工作节点，本地也留一份兜底。

    返回 ``(probs, engine)`` —— 与 ``detect_local`` 一致（engine 供取四档，
    集群模式下四档拿不到，调用方按 None 处理）。
    """
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
                probs, _eng = _run_one_device(
                    engine_cfg, base_dir, sub, _devices(params)[0], params
                )
            for i, p in zip(indices, probs):
                results[i] = p
            done += len(indices)
            if progress_cb:
                progress_cb(done, total)
    # 集群模式的四档拿不到（分片在别的进程里算），故 engine 传 None
    return results, None
