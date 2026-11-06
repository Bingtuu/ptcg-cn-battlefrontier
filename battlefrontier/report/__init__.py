"""报告层：胜率 / 决策聚合 / 换卡敏感性 / 校准对比（PRD §9）。

task 106：sim 解释限定语（docs/claims-register.md 使用守则 1/3 的落地）——
所有面向人的胜率/校准输出必须携带「自对局模拟结果，不构成真实胜率预测」。
"""

SIM_INTERPRETATION_NOTE = (
    "声明：sim 数字为自对局模拟结果，不构成真实胜率预测"
    "（见 docs/claims-register.md）"
)

CALIBRATION_EXTRA_NOTE = (
    "真实侧窗口与模拟卡快照可能不同代；|Δ| 是描述量，不是模拟精度指标"
)
