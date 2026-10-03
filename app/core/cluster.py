import json
import socket
import threading
import time

DISCOVERY_PORT = 47650
TASK_PORT = 47651
BROADCAST_ADDR = "255.255.255.255"


def _send_json(sock, obj):
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sock.sendall(len(data).to_bytes(4, "big") + data)


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        part = sock.recv(n - len(buf))
        if not part:
            raise ConnectionError("连接中断")
        buf += part
    return buf


def _recv_json(sock):
    hdr = _recv_exact(sock, 4)
    n = int.from_bytes(hdr, "big")
    if n > 64 * 1024 * 1024:
        raise ValueError("数据包过大")
    return json.loads(_recv_exact(sock, n).decode("utf-8"))


class ClusterMaster:
    """主节点：局域网自动发现工作节点，分发检测任务。"""

    def __init__(self, on_log=None):
        self.on_log = on_log or (lambda m: None)
        self.nodes = {}
        self.running = False
        self.lock = threading.Lock()

    def log(self, msg):
        try:
            self.on_log(msg)
        except Exception:
            pass

    def start(self):
        if self.running:
            return
        self.running = True
        threading.Thread(target=self._discover_loop, daemon=True).start()
        self.log("集群主节点已启动，正在扫描设备...")

    def stop(self):
        self.running = False

    def _discover_loop(self):
        """广播 AIGC_QUERY 并收集工作节点应答。

        端口分工（这里踩过一个坑）
        --------------------------
        只有**工作节点**绑定 ``DISCOVERY_PORT`` 收广播；主节点**不绑**该端口，
        而是绑一个临时端口（bind 到 0）再发广播。原因：若 master 与 worker
        都用 ``SO_REUSEADDR`` 绑同一个 UDP 端口，内核只会把单播回包投递给
        其中一个 socket —— 实测本机同开 master + worker 时，回包全被 worker
        收走，master 的 ``nodes`` 恒为空，集群分支（main_window 里要求
        ``nodes_snapshot()`` 非空）永远不会触发。

        worker 用 ``sendto(..., addr)`` 回包，``addr`` 就是 master 的实际源
        地址（临时端口），所以不需要 master 占着发现端口。
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            # 绑随机可用端口，避免与 worker 的发现端口冲突
            s.bind(("", 0))
        except OSError as e:
            self.log("发现服务初始化失败：%s" % e)
            return
        while self.running:
            try:
                s.sendto(b"AIGC_QUERY", (BROADCAST_ADDR, DISCOVERY_PORT))
            except Exception:
                pass
            s.settimeout(0.6)
            end = time.time() + 1.0
            while time.time() < end:
                try:
                    data, addr = s.recvfrom(65536)
                except socket.timeout:
                    break
                except Exception:
                    break
                if data.startswith(b"AIGC_WORKER "):
                    try:
                        info = json.loads(data[len(b"AIGC_WORKER "):].decode("utf-8"))
                        with self.lock:
                            self.nodes[addr[0]] = {
                                "name": info.get("name", "?"),
                                "gpu": info.get("gpu", "?"),
                                "vram": info.get("vram", "?"),
                                "last": time.time(),
                            }
                        self.log("发现设备：%s (%s)" % (info.get("name", "?"), addr[0]))
                    except Exception:
                        pass
            self._prune()
            time.sleep(3)

    def _prune(self):
        now = time.time()
        with self.lock:
            dead = [k for k, v in self.nodes.items() if now - v["last"] > 15]
            for k in dead:
                del self.nodes[k]

    def nodes_snapshot(self):
        with self.lock:
            return dict(self.nodes)

    def detect_chunk(self, addr, engine_id, paragraphs, params, timeout=1800):
        with socket.create_connection((addr, TASK_PORT), timeout=10) as s:
            s.settimeout(timeout)
            _send_json(
                s,
                {
                    "type": "detect",
                    "engine": engine_id,
                    "paragraphs": paragraphs,
                    "params": params,
                },
            )
            resp = _recv_json(s)
        if resp.get("type") == "result":
            return resp.get("probs", [])
        raise RuntimeError(resp.get("error", "工作节点返回错误"))


class ClusterWorker:
    """工作节点：响应发现广播，接收并执行检测任务。"""

    def __init__(self, engine_factory, on_log=None):
        self.engine_factory = engine_factory
        self.on_log = on_log or (lambda m: None)
        self.running = False

    def log(self, msg):
        try:
            self.on_log(msg)
        except Exception:
            pass

    def start(self):
        if self.running:
            return
        self.running = True
        threading.Thread(target=self._udp_loop, daemon=True).start()
        threading.Thread(target=self._tcp_loop, daemon=True).start()
        self.log("工作节点已启动，等待主节点分发任务...")

    def stop(self):
        self.running = False

    def _udp_loop(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("", DISCOVERY_PORT))
        except OSError:
            self.log("端口 %d 被占用，发现广播不可用" % DISCOVERY_PORT)
            return
        while self.running:
            try:
                data, addr = s.recvfrom(65536)
            except Exception:
                continue
            if data == b"AIGC_QUERY":
                gpu, vram = self._gpu_info()
                info = {"name": socket.gethostname(), "gpu": gpu, "vram": vram}
                try:
                    s.sendto(b"AIGC_WORKER " + json.dumps(info).encode("utf-8"), addr)
                except Exception:
                    pass

    @staticmethod
    def _gpu_info():
        try:
            import torch

            if torch.cuda.is_available():
                name = torch.cuda.get_device_name(0)
                vram = torch.cuda.get_device_properties(0).total_memory // (2**30)
                return name, "%dGB" % vram
        except Exception:
            pass
        return "无GPU(CPU)", "-"

    def _tcp_loop(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind(("", TASK_PORT))
        except OSError:
            self.log("端口 %d 被占用，任务服务不可用" % TASK_PORT)
            return
        srv.listen(8)
        srv.settimeout(2)
        while self.running:
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except Exception:
                continue
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        try:
            req = _recv_json(conn)
            if req.get("type") != "detect":
                raise ValueError("未知任务类型")
            engine = self.engine_factory(req["engine"])
            if engine is None:
                raise ValueError("本机未安装该引擎：" + str(req.get("engine")))
            params = req.get("params", {})
            probs = engine.predict_paragraphs(req["paragraphs"], self._pick_device(), **params)
            _send_json(conn, {"type": "result", "probs": probs})
            self.log("完成一个任务分片（%d 段）" % len(req["paragraphs"]))
        except Exception as e:
            try:
                _send_json(conn, {"type": "error", "error": str(e)})
            except Exception:
                pass
            self.log("任务失败：%s" % e)
        finally:
            conn.close()

    @staticmethod
    def _pick_device():
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda:0"
        except Exception:
            pass
        return "cpu"
