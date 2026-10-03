# -*- coding: utf-8 -*-
"""集群类探针：端口绑定竞争、avg_logprob 分块口径、发现链路。

来源（原 2 个脚本，逻辑一字未改）：
  probe_cluster_port_and_logprob_chunk.py
  probe_cluster_discovery_chain.py

**副作用**：占用 UDP 47650 / TCP 47651 约 20 秒，跑完自动释放。
"""
import socket
import time

from . import head


def run_cluster_port(v):
    """2.4 集群发现端口被静默吞 —— cluster.py:59-66。

    **副作用**：占用 UDP 47650 约 5 秒。
    （原与 2.5 合并，2026-09-23 拆分 —— 2.5 是纯计算，不应被拖进 heavy 组。）
    """
    head("2.4", "集群发现端口被静默吞 —— cluster.py:59-66")
    print('    try:\n        s.bind(("", DISCOVERY_PORT))\n    except OSError:\n        pass')
    print()
    PORT = 47650
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ok_bind = True
    err = ""
    try:
        s.bind(("", PORT))
    except OSError as e:
        ok_bind = False
        err = "%s: %s" % (type(e).__name__, e)
    print('bind(("", %d)) -> %s %s' % (PORT, "成功" if ok_bind else "失败", err))
    s.close()

    from core.cluster import ClusterMaster

    print()
    print("启动 ClusterMaster 5 秒:")
    m = ClusterMaster()
    m.start()
    time.sleep(5)
    nodes = m.nodes_snapshot()
    print("    nodes_snapshot() = %r" % nodes)
    m.stop()
    print()
    print("main_window.py:96:")
    print('    if self.params.get("use_cluster") and self.master and self.master.nodes_snapshot():')
    print("    nodes 为空 -> 永不进入集群分支，UI 无提示")
    v.add("2.4", not nodes,
          "bind=%s，5 秒后 nodes=%r；集群分支要求 nodes 非空"
          % ("OK" if ok_bind else "FAIL", nodes))


def run_logprob_chunk(v):
    """2.5 avg_logprob 分块口径错 —— base.py:193-203。

    **纯计算**：只用 torch.arange + 桩模型，不联网、不碰 socket、零副作用。
    （原与 2.4 合并，2026-09-23 拆分 —— 使本条可归入 safe 组。）
    """
    head("2.5", "avg_logprob 分块口径错 —— base.py:193-203")
    print("        out = model(piece, labels=piece)")
    print("        total += out.loss.item() * (end - begin)   # 权重用块长 L")
    print("        n += end - begin")
    print()
    print("因果 LM 内部 shift：实际参与平均的是 L-1 个 token")
    print()

    import torch

    class StubOut:
        def __init__(self, loss):
            self.loss = loss

    class StubModel:
        def __call__(self, piece, labels=None):
            L = piece.size(1)
            return StubOut(piece.new_tensor(1.0 + 0.01 * L))

    class Enc:
        pass

    class StubTok:
        def __init__(self, n):
            self.n = n

        def __call__(self, text, **kw):
            e = Enc()
            e.input_ids = torch.arange(self.n).reshape(1, -1)
            return e

    def avg_logprob(model, tok, chunk=256):
        ids = tok("x").input_ids
        if ids.size(1) < 2:
            return float("-inf")
        total, n = 0.0, 0
        with torch.no_grad():
            for begin in range(0, ids.size(1), chunk):
                end = min(begin + chunk, ids.size(1))
                piece = ids[:, begin:end]
                if piece.size(1) < 2:
                    break
                out = model(piece, labels=piece)
                total += out.loss.item() * (end - begin)
                n += end - begin
                if end == ids.size(1):
                    break
        return -(total / n) if n else float("-inf")

    N = 100
    tok = StubTok(N)
    model = StubModel()
    vals = {}
    for ch in (1024, 50, 25, 10, 4):
        vals[ch] = avg_logprob(model, tok, chunk=ch)
        print("    chunk=%-5d -> avg_logprob = %.6f" % (ch, vals[ch]))
    a, b = vals[1024], vals[25]
    diff = abs(a - b) / abs(a) * 100
    print()
    print("单块(1024) vs 4块(25) 相对差 = %.4f%%" % diff)
    print()
    ids = torch.arange(N).reshape(1, -1)
    tot2, n2 = 0.0, 0
    with torch.no_grad():
        for begin in range(0, N, 1024):
            end = min(begin + 1024, N)
            out = model(ids[:, begin:end], labels=ids[:, begin:end])
            w = max(end - begin - 1, 1)
            tot2 += out.loss.item() * w
            n2 += w
    print("正确权重(end-begin-1) 下单块 = %.6f" % (-(tot2 / n2)))
    v.add("2.5", diff > 0.5,
          "chunk 变则结果变，相对差 %.4f%%（正确值应恒定）" % diff)


def run_cluster_discovery(v):
    """2.4b 集群发现链路：本机同时跑 master + worker，验证发现与分发。"""
    from core.cluster import (
        DISCOVERY_PORT,
        TASK_PORT,
        ClusterMaster,
        ClusterWorker,
    )

    head("2.4b", "集群发现链路（本机同时跑 master + worker）")
    print("DISCOVERY_PORT = %d, TASK_PORT = %d" % (DISCOVERY_PORT, TASK_PORT))
    print()
    print("配置 A) 用 use_cluster 开关观察 master 是否自行启动")
    print("   main_window.py:679 传入 master 的条件:")
    print('       self.master if params.get("use_cluster") else None')
    print("   main_window.py:533 on_cluster_toggled 会在勾选时 master.start()")
    print()

    logs = []
    m = ClusterMaster(on_log=lambda s: logs.append(s))
    w = ClusterWorker(engine_factory=lambda eid: None,
                      on_log=lambda s: logs.append("W:" + s))
    print("启动 worker（worker.start() 内部自动开 UDP/TCP 监听）")
    w.start()
    time.sleep(1)
    print("启动 master")
    m.start()
    print()
    print("等待 8 秒观察发现过程...")
    for i in range(8):
        time.sleep(1)
        snap = m.nodes_snapshot()
        if snap:
            print("   第 %d 秒: 发现 %d 个节点 -> %r" % (i + 1, len(snap), snap))
            break
    else:
        snap = m.nodes_snapshot()
        print("   8 秒后仍未发现节点: %r" % snap)

    print()
    print("--- 日志 ---")
    for s in logs[:25]:
        print("   %s" % s)
    if not logs:
        print("   (无日志)")
    print()

    print("配置 B) worker 绑定 %d，master 绑定同一个端口会不会冲突" % DISCOVERY_PORT)
    s1 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    r1 = "OK"
    try:
        s1.bind(("", DISCOVERY_PORT))
    except OSError as e:
        r1 = "FAIL %s" % e
    s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    r2 = "OK"
    try:
        s2.bind(("", DISCOVERY_PORT))
    except OSError as e:
        r2 = "FAIL %s" % e
    print("   第一个 socket bind: %s" % r1)
    print("   第二个 socket bind: %s" % r2)
    print("   -> SO_REUSEADDR 下两者都能绑定，UDP 单播回包只会送到其中一个")
    print()
    s1.close()
    s2.close()

    print("配置 C) master 是否能分发任务到 worker（用桩引擎）")
    try:
        from core.cluster import _recv_json, _send_json

        class StubEngine:
            def predict_paragraphs(self, paragraphs, device,
                                   progress_cb=None, **kw):
                return [0.77] * len(paragraphs)

        w.stop()
        time.sleep(0.5)
        w2 = ClusterWorker(engine_factory=lambda eid: StubEngine(),
                           on_log=lambda s: logs.append("W2:" + s))
        w2.start()
        time.sleep(1)
        try:
            with socket.create_connection(("127.0.0.1", TASK_PORT),
                                          timeout=5) as c:
                c.settimeout(20)
                _send_json(c, {"type": "detect", "engine": "stub",
                               "paragraphs": ["测试一", "测试二"],
                               "params": {}})
                resp = _recv_json(c)
            print("   直接连 worker TASK_PORT 发任务 -> %r" % resp)
        except Exception as e:
            print("   直接分发失败: %s: %s" % (type(e).__name__, e))
        w2.stop()
    except Exception as e:
        import traceback

        print("   分发测试异常: %s: %s" % (type(e).__name__, e))
        traceback.print_exc(limit=2)

    m.stop()
    w.stop()
    print()
    print(">>> 结论: 见上方发现结果；若 nodes 始终为空，")
    print("          则 main_window.py:96 的集群分支永远走不到。")
    v.add("2.4b", not snap,
          "8 秒内发现节点: %r" % (bool(snap),))
