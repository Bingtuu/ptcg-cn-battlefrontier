# task 121 · 换卡报告森林图（轻量 SVG）

- 状态：进行中
- 关联：task 075（swap_pack 四件）/ task 117（定量口径）；使用便利性 P2
- 日期：2026-11-14 立项（四层优化拍板 P2）

## 目标

换卡报告从「表格数字」升级为「一图看清」：每变体 ΔWR 点估计 + CI 须线的森林图，零线参照。手写轻量 SVG（不加依赖；runtime 保持 numpy only）。

## 验收标准（TDD）

1. 红测 → 绿：`write_swap_pack` 增产 `swap.svg`（XML 良构、含各变体名称/ΔWR/CI 数值、零线；数值与 `VariantComparison` 一致）。
2. 红测 → 绿：swap.html 内嵌/引用该 SVG。
3. 全量 pytest 绿 + ruff 零告警。

## 实现要点

- `battlefrontier/report/swap_pack.py` 加 `forest_svg(rep) -> str`（纯函数，可单测）；布局：横轴 ΔWR%、每变体一行、点 + 水平须线 + 竖直零线、CI 不跨零的变体视觉区分。
- 坐标映射纯手写（无图表库）；中文标签用 SVG text（字体由阅读器承担）。

## 结果与遗留

- **实现 ✅**：`forest_svg(rep)` 纯函数（手写轻量 SVG，零图表依赖）：每变体一行 = 名称 + CI 须线 + ΔWR 点 + 零线参照，CI 不跨零（p<0.05）红色加粗；标题内嵌「同模拟器内对比，不构成真实预测」。`write_swap_pack` 增产 `swap.svg` 并内嵌 swap.html（转义正文之后）。
- **测试（验收 1–3 ✅）**：红测（ImportError）→ 绿：XML 良构（ElementTree 解析）、变体名/点估计数值一致、html 含 `<svg`、纯函数出口与包内文件一致；4 passed + ruff 零告警。
- **实证 ✅**：task 117 真实库重新导出，swap.svg 数值与报告一致（CLI 换卡包行自动含 svg）。
- **遗留**：提交随 119/120 同批。
