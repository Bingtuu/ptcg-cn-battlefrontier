"""事件流渲染为人类可读回合记录（PRD §5.4 人工 check 模式最小版）。

回放 / 人工 check / 过程统计共用同一份事件数据；这里只做文本渲染。
"""

from __future__ import annotations

from battlefrontier.engine.events import GameEvent

_TEMPLATES = {
    "coin_flip": "掷币定先攻：玩家{first_player}",
    "mulligan": "玩家{player} 起手无基础宝可梦，展示并洗回重抽",
    "mulligan_bonus_draw": "玩家{player} 因对手 mulligan 抽 {count} 张",
    "setup_ready": "起手与 mulligan 就绪，开始布阵（背面放置）",
    "set_prizes": "双方布阵完成：翻开场上宝可梦；各从牌库顶取 6 张背面置为奖赏卡",
    "place_active": "玩家{player} 放置战斗场：{name}",
    "place_bench": "玩家{player} 放置备战区：{name}",
    "draw": "玩家{player} 抽 1 张",
    "evolve": "玩家{player} 进化：{onto} → {name}",
    "attach_energy": "玩家{player} 给 {target} 附着能量",
    "retreat": "玩家{player} 撤退：{out} → {into}（弃 {paid} 能量）",
    "attack": "玩家{player} 使用招式，对 {target} 造成 {damage} 伤害",
    "knockout": "玩家{player} 的 {name} 昏厥",
    "take_prize": "玩家{player} 拿 1 张奖赏卡（剩 {left}）",
    "promote": "玩家{player} 换上 {name}",
    "end_turn": "玩家{player} 回合结束",
    "play_trainer": "玩家{player} 使用{subtype}：{name}",
    "effect_start": "· 效果发动：{card}（{trigger}）",
    "effect_primitive": "· {action} → {result}",
    "effect_observe": "· 观测锚点：{anchor}",
    "effect_end": "· 效果结束",
    "deck_out": "玩家{player} 牌库抽空",
    "turn_cap": "达到回合上限，强制判平",
    "no_legal_actions": "无合法行动，强制判平",
    "game_over": "对局结束（{reason}）",
}


def render_log(events: list[GameEvent]) -> str:
    """把事件流渲染为逐行中文回合记录。"""
    lines: list[str] = []
    for ev in events:
        template = _TEMPLATES.get(ev.kind, ev.kind)
        detail = {"player": ev.player, **ev.detail}
        line = template.format_map(_SafeDict(detail))
        lines.append(f"回合{ev.turn} | {line}")
    return "\n".join(lines)


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return f"<{key}>"
