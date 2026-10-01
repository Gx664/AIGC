# -*- coding: utf-8 -*-
"""审查探针主程序：按组运行，汇总结论。

用法
----
    python tools/audit_probes.py                  # 默认跑 safe 组（零风险，秒级）
    python tools/audit_probes.py --group heavy    # 跑高代价组
    python tools/audit_probes.py --group all      # 全部（含 heavy，可能 45 分钟）
    python tools/audit_probes.py --only dtype_compare   # 单个探针
    python tools/audit_probes.py --list           # 列出探针与代价/风险

分组（按**风险**划分，代价与风险在注册表里逐条标注）
----
  safe   无副作用或可忽略，默认启用（6 个：静态扫描、风格、签名、公式、参数、license）
  heavy  高代价 / 高风险，需显式指定（7 个：占端口、Qt、加载模型、2.7B 溢出）

设计说明
--------
2026-09-23 重构：原 15 个独立脚本（合计约 2400 行顶层代码）改为
「主程序 + 探针函数」两层结构。理由：
  1. 原脚本无 main()，import 混在中间，无法按需调用、无法汇总
  2. 副作用各异（占端口 / 写文件 / 吃显存），合并成一个入口后需能分组隔离
  3. sys.path / stdout 包装 / ROOT 路径原本每脚本重复一遍

**探针内部的验证逻辑一字未改** —— 改动仅限包成函数、统一公共部分。
历史结论（见 docs/FIXES.md §1）仍然成立。
"""
import argparse
import os
import sys
import traceback

_TOOLS = os.path.dirname(os.path.abspath(__file__))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from probes import Verdicts, setup_stdout  # noqa: E402

# 探针注册表：(名称, 组, 代价, 风险, 说明, 函数)
#
# 分组只有两档，按**风险**而非验证对象划分：
#   safe   无副作用或副作用可忽略，默认启用
#   heavy  高代价 / 高风险（吃显存、耗时长），必须显式指定
#
# 代价与风险写在字段里而不是靠组名暗示 —— 同一组内差异可达 20 倍
# （如 model 组里 xformers_sig 1 秒 vs dtype_compare 2 分钟）。
#
# 函数用 "模块:函数" 字符串而非函数对象 —— 延迟导入，避免只跑 safe
# 时也去拉起 torch / Qt。
REGISTRY = [
    # ---------------- safe：默认启用 ----------------
    ("static_scan",   "safe", "秒级",  "无",
     "静态扫描：未用导入 / 行长 / 静默 except / 引擎参数签名",
     "static:run_static_scan"),
    ("style_report",  "safe", "秒级",  "无（只打控制台）",
     "原作者代码风格核查 + 改动一致性（结论见 docs/FIXES.md §5）",
     "static:run_style_report"),
    ("xformers_sig",  "safe", "秒级",  "无（只读 inspect 签名，不加载模型）",
     "transformers API 存在性（**有误报**，结论以 xformers_call 为准）",
     "model:run_api_signature"),
    ("bino_math",     "safe", "秒级",  "无",
     "Binoculars 公式恒判 AI（复刻算术式代入真实量级）",
     "logic:run_bino_math"),
    ("style_loop",    "safe", "秒级",  "无",
     "降重死循环隐患 + 引擎参数覆盖顺序",
     "logic:run_style_loop_and_param"),
    ("license_i18n",  "safe", "秒级",  "写系统临时目录（自清理）",
     "license 空壳 / i18n 拼接键 / 报告文件名转义",
     "logic:run_license_i18n"),
    ("logprob_chunk", "safe", "秒级",  "无（纯 torch.arange + 桩模型）",
     "avg_logprob 分块口径错（chunk 变则结果变，偏差 34~67%）",
     "cluster:run_logprob_chunk"),
    ("env_setup",     "safe", "秒级（含 1.5 秒自检）", "无（只读源码 + 纯函数）",
     "安装/环境：路径校验、CUDA 映射、卸载器 exe、进度解析、启动自检",
     "env_setup:run_env_setup"),
    ("display_marks", "safe", "秒级（含 Qt 导入 1 秒）", "无（只调纯函数，不构造窗口）",
     "展示层标记：报告四档和恒为 100、柱状图边界、引擎语言标注",
     "display_marks:run_display_marks"),

    # ---------------- heavy：需显式指定 ----------------
    ("cluster_port",  "heavy", "十几秒", "**占 UDP 47650 / TCP 47651**（跑完释放）",
     "集群端口绑定竞争（修前 nodes 恒为空）",
     "cluster:run_cluster_port"),
    ("cluster_chain", "heavy", "二十几秒", "**占 UDP 47650 / TCP 47651**；起 master+worker",
     "集群发现链路（本机同时跑 master + worker）",
     "cluster:run_cluster_discovery"),
    ("gui_offscreen", "heavy", "十几秒", "需 Qt 离屏；写系统临时 settings.json",
     "主窗口 / 设置对话框离屏复现",
     "gui:run_gui_offscreen"),
    ("report_render", "heavy", "几秒",  "需 Qt 离屏",
     "报告 HTML 注入的真实危害（Qt 离屏真渲染）",
     "gui:run_report_render"),
    ("xformers_call", "heavy", "几秒",  "加载本地随机权重小模型（不联网）",
     "transformers 真调用，排除 xformers_sig 的误报",
     "model:run_real_call"),
    ("dtype_compare", "heavy", "约 2 分钟", "加载 gltr 模型（gpt2）、吃显存",
     "fp16 vs fp32 对判定结论的影响（Kendall 排序一致率）",
     "model:run_dtype_compare"),
    ("crosslingual", "heavy", "约 4 分钟", "加载 gpt2 + gpt2-medium（约 1.9GB）",
     "gltr / binoculars 同量样本的中英对照（同源内对比才有效）",
     "crosslingual:run_crosslingual"),
    ("zh_backbone",  "heavy", "约 5 分钟", "加载 gpt2 + gpt2-chinese（约 0.9GB）",
     "中文底座对照：gpt2 vs gpt2-chinese-cluecorpussmall（待办 3 的评估）",
     "zh_backbone:run_zh_backbone"),
    ("auc_bench",    "heavy", "约 3 分钟", "加载 simpleai + gpt2 组合",
     "AUC 基准：与论文可比的指标（排除阈值漂移干扰）",
     "auc_bench:run_auc"),
    ("k_timing",     "heavy", "约 25 分钟", "加载 gpt-neo-2.7B、k=100 很慢",
     "采样数 k 的耗时基准实测（k=5/20/100）",
     "k_timing:run_k_timing"),
    ("zh_threshold", "heavy", "约 5 分钟", "加载 gpt2-chinese（约 0.2GB）",
     "zh_perplexity 引擎的阈值标定（TODO-8 方案 A，tqdm 进度）",
     "zh_threshold:run_zh_threshold"),
    ("english_fpr",   "heavy", "约 4 分钟", "加载 simpleai + gpt2 组合（约 1.9GB）",
     "英文侧 FPR<=5% 复核（acc 与可交付性是两件事，补齐英文标注依据）",
     "english_fpr:run_english_fpr"),
    ("holdout",       "heavy", "约 5 分钟", "加载 gpt2-chinese（约 0.2GB）",
     "留出集验证：标定/评测按问题分开，检验指标是否过拟合",
     "holdout:run_holdout"),
    ("bino_cal",      "heavy", "约 8 分钟", "加载 gpt2 + gpt2-medium（约 1.9GB）",
     "binoculars 英文阈值重标（现有 0.615 标自 120 条，已失效）",
     "binoculars_calib:run_binoculars_calib"),
    ("ui_flow",       "heavy", "约 2 分钟", "需 Qt 离屏；真跑一次检测（CPU）",
     "界面交互测试：主窗口/引擎下拉/真跑检测/设置往返/降重对话框",
     "ui_flow:run_ui_flow"),
    ("package_flow",  "safe",  "秒级",  "无（只读文件，不写盘不碰注册表）",
     "装机 / 发布流程静态检查：必需文件、标定数据位置、零依赖、卸载完整性",
     "package_flow:run_package_check"),
    ("ui_config",     "safe",  "秒级",  "无（只读源码）",
     "UI 配置合理性：设置项是否真被使用、有无读了未声明的键、默认值是否合理",
     "ui_config:run_config_check"),
    ("gltr_cal",      "heavy", "约 10 分钟", "加载 gpt2（约 500MB）",
     "gltr 中英阈值重标（现值抄自旧文档），结果写回 engines_calibration.json",
     "gltr_calib:run_gltr_calib"),
    ("simpleai",      "heavy", "约 8 分钟", "加载 simpleai 模型（约 780MB），CPU 跑",
     "simpleai 中英实跑复核（acc/FPR/AUC），结果写回 engines_calibration.json",
     "simpleai_check:run_simpleai_check"),
    ("vram_spill",    "heavy", "约 45 分钟", "加载 gpt-neo-2.7B、**可能溢出显存**",
     "溢出实测：fp32/fp16 都跑，跑时每秒采样共享显存",
     "model:run_vram_spill"),
]

GROUPS = ["safe", "heavy"]
DEFAULT_GROUPS = ["safe"]


def show_list():
    print("可运行的探针（默认只跑 safe 组）：\n")
    print("  %-15s %-6s %-10s %-34s %s"
          % ("名称", "组", "代价", "风险", "说明"))
    for name, grp, cost, risk, desc, _ in REGISTRY:
        print("  %-15s %-6s %-10s %-34s %s" % (name, grp, cost, risk, desc))
    print("\n组：")
    for g in GROUPS:
        rows = [r for r in REGISTRY if r[1] == g]
        mark = "（默认启用）" if g in DEFAULT_GROUPS else "（需显式指定）"
        print("  %-6s %d 个探针 %s" % (g, len(rows), mark))
        for r in rows:
            print("        %-15s %-10s %s" % (r[0], r[2], r[3]))


def resolve(spec):
    """把 '模块:函数' 解析成可调用对象（延迟导入，按包路径）。"""
    mod_name, fn_name = spec.split(":")
    mod = __import__("probes." + mod_name, fromlist=[fn_name])
    return getattr(mod, fn_name)


def main():
    ap = argparse.ArgumentParser(
        description="审查探针主程序",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--group", action="append", default=None,
                    choices=GROUPS + ["all"],
                    help="要跑的组（可重复；all = 除 heavy 外全部）")
    ap.add_argument("--only", action="append", default=None,
                    help="只跑指定探针（可重复，用 --list 看名称）")
    ap.add_argument("--list", action="store_true", help="列出所有探针")
    args = ap.parse_args()

    if args.list:
        show_list()
        return 0

    # 选定要跑的探针
    if args.only:
        wanted = [r for r in REGISTRY if r[0] in args.only]
        unknown = set(args.only) - {r[0] for r in REGISTRY}
        if unknown:
            print("未知探针: %s（用 --list 查看）" % ", ".join(sorted(unknown)))
            return 2
    else:
        groups = args.group or DEFAULT_GROUPS
        if "all" in groups:
            groups = ["safe", "heavy"]
        wanted = [r for r in REGISTRY if r[1] in groups]

    if not wanted:
        print("没有匹配的探针。")
        return 2

    setup_stdout()
    v = Verdicts()

    print("=" * 68)
    print("审查探针：共 %d 个" % len(wanted))
    print("=" * 68)
    for name, grp, cost, risk, desc, _ in wanted:
        print("  [%-5s] %-15s %-10s %s" % (grp, name, cost, desc))
        if risk and risk != "无":
            print("          %s风险: %s" % (" " * 12, risk))
    print()

    failed = []
    for name, grp, cost, risk, desc, spec in wanted:
        print("\n" + "#" * 68)
        print("# 探针: %s（组 %s，代价 %s）" % (name, grp, cost))
        print("# %s" % desc)
        if risk and risk != "无":
            print("# 风险: %s" % risk)
        print("#" * 68)
        try:
            fn = resolve(spec)
            fn(v)
        except Exception as e:
            failed.append((name, "%s: %s" % (type(e).__name__, e)))
            print("\n!! 探针 %s 异常: %s: %s" % (name, type(e).__name__, e))
            traceback.print_exc(limit=3)

    v.table()

    if failed:
        print("\n失败 %d 个:" % len(failed))
        for name, err in failed:
            print("  %-16s %s" % (name, err))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
