"""task 038 F1（D-038-1）：legal_actions 返回值契约——调用方得到独立副本。

两条返回路径（缓存命中 / 未命中重枚举）都返回 list 副本，缓存槽内部 list
永不外露：调用方对返回值 pop/排序等原地变异，不影响同状态再枚举结果，
也不影响引擎后续 apply 的合法行动校验（mcts.py untried.pop(0) 类消费方安全）。
"""

from helpers import engine_at, main_state

from battlefrontier.engine.core import GameEngine


def test_legal_actions_hit_path_returns_copy():
    """缓存命中路径：变异首次返回值后，同状态同玩家再枚举结果完整一致。"""
    engine = engine_at(main_state())
    first = engine.legal_actions(0)
    snapshot = list(first)
    assert first, "main 阶段应有合法行动"
    first.pop(0)
    first.sort(key=repr)  # 原地变异（模拟消费方掏空/重排）
    second = engine.legal_actions(0)  # 缓存命中
    assert second == snapshot
    assert second is not first


def test_legal_actions_miss_path_returns_copy():
    """未命中路径同样返回副本：变异后缓存命中路径结果仍完整。"""
    engine = engine_at(main_state())
    first = engine.legal_actions(0)  # 未命中（枚举并写缓存）
    snapshot = list(first)
    first.clear()
    assert engine.legal_actions(0) == snapshot  # 命中路径不受污染


def test_legal_actions_mutation_does_not_break_apply():
    """调用方掏空返回值后，apply 的非法行动校验仍认全部合法行动。"""
    engine = engine_at(main_state())
    actions = engine.legal_actions(0)
    keep = list(actions)
    actions.clear()
    engine.apply(0, keep[0])  # 不抛 IllegalActionError 即通过


def test_legal_actions_cache_slot_never_escapes():
    """缓存槽内部 list 与任何一次返回值都不是同一对象。"""
    engine = engine_at(main_state())
    first = engine.legal_actions(0)
    cache = engine._legal_cache
    assert cache is not None
    assert cache[2] is not first
    second = engine.legal_actions(0)
    assert cache[2] is not second and second is not first


def test_legal_actions_enumeration_stable_across_players():
    """换玩家（缓存 miss 重写）后回到原玩家，结果仍完整。"""
    engine = engine_at(main_state(p1_bench=()))
    first = engine.legal_actions(0)
    snapshot = list(first)
    first.pop()
    engine.legal_actions(1)  # 不同玩家 → miss，重写缓存槽
    again = engine.legal_actions(0)  # 再 miss（玩家不同）→ 重枚举
    assert again == snapshot
    assert isinstance(engine, GameEngine)
