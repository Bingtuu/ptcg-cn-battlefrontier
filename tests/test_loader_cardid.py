"""task 026 WP0：装载键 name_group → card_id 精确挂载（2026-09-06 用户决议）。

CardLibrary（dict 子类，键 = card_id）+ 引擎 effect_doc 解析助手：
CardLibrary 仅按 card_id 取文档（无名字兜底——防彷徨夜灵 D 标顶替 H 标事故）；
朴素 dict 为存量测试兼容路径，仍按卡名取。
"""

from pathlib import Path

import pytest
from helpers import engine_at, inst, main_state

from battlefrontier.dsl.loader import (
    CardLibrary,
    DslError,
    load_card_dir,
    parse_card_doc,
)
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import effect_doc
from battlefrontier.engine.state import CardDef

DRAW_YAML = """\
card:
  name_group: 双文鸟
  card_ids: [{cid}]
effects:
  - trigger: on_play
    actions:
      - {{action: draw, count: 1}}
"""

SHUFFLE_YAML = """\
card:
  name_group: 双文鸟
  card_ids: [{cid}]
effects:
  - trigger: on_play
    actions:
      - {{action: shuffle_deck}}
"""


def _item(name: str, card_id: str) -> CardDef:
    return CardDef(card_id=card_id, name=name, supertype="trainer", trainer_subtype="物品")


def _write(tmp_path: Path, filename: str, text: str) -> Path:
    p = tmp_path / filename
    p.write_text(text, encoding="utf-8")
    return p


# ── loader / CardLibrary ─────────────────────────────────

def test_load_card_dir_返回_CardLibrary_按_card_id_精确挂载(tmp_path):
    _write(tmp_path, "a.yml", DRAW_YAML.format(cid="X-1"))
    _write(tmp_path, "b.yml", SHUFFLE_YAML.format(cid="X-2"))
    lib = load_card_dir(tmp_path)
    assert isinstance(lib, CardLibrary)
    assert lib["X-1"].effects[0].actions[0].action == "draw"
    assert lib["X-2"].effects[0].actions[0].action == "shuffle_deck"


def test_同名两文件共存_by_name_返回全部文档(tmp_path):
    """同名多文本（card_ids 不相交）共存不报错——（卡名+文本）等价类严格拆分。"""
    _write(tmp_path, "双文鸟-甲.yml", DRAW_YAML.format(cid="X-1"))
    _write(tmp_path, "双文鸟-乙.yml", SHUFFLE_YAML.format(cid="X-2, X-3"))
    lib = load_card_dir(tmp_path)
    docs = lib.by_name("双文鸟")
    assert len(docs) == 2
    assert {d.effects[0].actions[0].action for d in docs} == {"draw", "shuffle_deck"}
    assert lib.by_name("不存在的卡") == []


def test_card_id_跨文件重复_报_DslError_含文件名(tmp_path):
    _write(tmp_path, "a.yml", DRAW_YAML.format(cid="X-1"))
    _write(tmp_path, "b.yml", SHUFFLE_YAML.format(cid="X-1, X-2"))
    with pytest.raises(DslError, match="X-1") as exc_info:
        load_card_dir(tmp_path)
    assert "b.yml" in str(exc_info.value)


def test_card_ids_为空_报_DslError_挂载键必填(tmp_path):
    """挂载键必填（2026-09-06 决议）：空 card_ids 的文档无法精确挂载。"""
    _write(tmp_path, "a.yml", "card:\n  name_group: 双文鸟\n  card_ids: []\n"
                             "effects:\n  - trigger: on_play\n"
                             "    actions:\n      - {action: shuffle_deck}\n")
    with pytest.raises(DslError, match="挂载键必填"):
        load_card_dir(tmp_path)


# ── 引擎解析（effect_doc）─────────────────────────────────

def _library() -> CardLibrary:
    return CardLibrary.from_docs([
        ("双文鸟-甲.yml", parse_card_doc(DRAW_YAML.format(cid="X-1"))),
        ("双文鸟-乙.yml", parse_card_doc(SHUFFLE_YAML.format(cid="X-2"))),
    ])


def test_effect_doc_CardLibrary_仅按_card_id_无名字兜底():
    """彷徨夜灵事故回归：card_id 未覆盖但同名有文档 → None（不兜底、不错挂）。"""
    lib = _library()
    assert effect_doc(lib, _item("双文鸟", "X-1")) is lib["X-1"]
    assert effect_doc(lib, _item("双文鸟", "X-9")) is None  # 同名异印刷，不错挂
    assert effect_doc(lib, _item("双文鸟", "X-2")).effects[0].actions[0].action == "shuffle_deck"


def test_effect_doc_朴素_dict_仍按卡名工作():
    """存量测试兼容路径：朴素 dict（卡名 → 文档）注入不变。"""
    doc = parse_card_doc(DRAW_YAML.format(cid="X-1"))
    effects = {"双文鸟": doc}
    assert effect_doc(effects, _item("双文鸟", "stub-双文鸟")) is doc
    assert effect_doc(effects, _item("别的卡", "stub-别的卡")) is None


def test_同名两文本合成对局_各自结算各自文档():
    """两只同名不同 card_id 的卡各自结算各自 DSL 文档（事件断言）。"""
    e = engine_at(main_state(p0_extra_hand=(
        inst(60, _item("双文鸟", "X-1")),
        inst(61, _item("双文鸟", "X-2")),
    )))
    e.card_effects = _library()
    plays = [a for a in e.legal_actions(0) if a.kind == "play_trainer"]
    assert {a.iid for a in plays} == {60, 61}
    e.apply(0, Action(kind="play_trainer", iid=60))  # X-1 文档：抽 1 张
    draws = [ev for ev in e.events if ev.kind == "effect_primitive"
             and ev.detail.get("action") == "draw"]
    assert len(draws) == 1
    assert len(e.state.players[0].hand) == 4  # 50/51/61 + 抽 1（60 已打出）
    e.apply(0, Action(kind="play_trainer", iid=61))  # X-2 文档：仅洗牌
    draws = [ev for ev in e.events if ev.kind == "effect_primitive"
             and ev.detail.get("action") == "draw"]
    assert len(draws) == 1  # 不再抽
    assert len(e.state.players[0].hand) == 3


def test_card_id_未覆盖_同名有文档_不枚举使用行动():
    """印刷未覆盖的卡不可使用其同名文档效果（不错挂，引擎层兜底）。"""
    e = engine_at(main_state(p0_extra_hand=(inst(60, _item("双文鸟", "X-9")),)))
    e.card_effects = _library()
    assert not [a for a in e.legal_actions(0) if a.kind == "play_trainer"]


# ── Runner 装配（experiment assemble_card_effects）────────

def test_prepare装配_按_card_id_过滤_同名两文本各挂各的():
    """prepare 按 card_id 过滤 card_effects；同名两文本分属两套卡组时各挂各的。"""
    from battlefrontier.runner.experiment import assemble_card_effects

    lib = _library()
    effects, warnings = assemble_card_effects(
        [[_item("双文鸟", "X-1")], [_item("双文鸟", "X-2")]], lib)
    assert isinstance(effects, CardLibrary)
    assert set(effects) == {"X-1", "X-2"}
    assert effects["X-1"].effects[0].actions[0].action == "draw"
    assert effects["X-2"].effects[0].actions[0].action == "shuffle_deck"
    assert warnings == []


def test_prepare装配_印刷未覆盖_同名有文档_进告警不硬报错():
    """覆盖告警（波波式 vanilla 印刷合法）：不进库、不抛错，warnings 透传。"""
    from battlefrontier.runner.experiment import assemble_card_effects

    effects, warnings = assemble_card_effects([[_item("双文鸟", "X-9")]], _library())
    assert set(effects) == set()  # 未挂载（不错挂）
    assert len(warnings) == 1 and "双文鸟" in warnings[0] and "X-9" in warnings[0]


def test_prepare装配_同名无文档_纯vanilla_无告警():
    from battlefrontier.runner.experiment import assemble_card_effects

    effects, warnings = assemble_card_effects([[_item("白板鸟", "W-1")]], _library())
    assert set(effects) == set() and warnings == []


def test_prepare_variant_换入卡按_card_id_补入文档_缺失带告警(monkeypatch):
    """换入卡不在 baseline 卡组：从定义库按 card_id 补入；印刷未覆盖且同名有文档 → 告警。"""
    import types

    import battlefrontier.runner.experiment as exp_mod
    from battlefrontier.runner.experiment import (
        PreparedExperiment,
        SwapCfg,
        VariantCfg,
        prepare_variant,
    )

    def fake_record(card_id: str, name: str):
        return types.SimpleNamespace(
            card_id=card_id, name_full=name, card_type="trainer", stage=None,
            hp=None, types=(), weakness=None, resistance=None, attacks=(),
            retreat_cost=0,
            rule_box_type=None, prize_cards=1, trainer_subtype="物品",
            provides=None, evolves_from_text=None, evolution_chain_id=None,
            is_basic_energy=False, is_ace_spec=False,
        )

    class FakeDb:
        def __init__(self, mapping):
            self._mapping = mapping

        def search_cards(self, name=None, limit=1):
            cid = self._mapping.get(name)
            return [types.SimpleNamespace(card_id=cid)] if cid else []

        def get_card(self, card_id):
            name = next(n for n, c in self._mapping.items() if c == card_id)
            return fake_record(card_id, name)

        def close(self):
            pass

    monkeypatch.setattr("ptcgdb.sdk.open_db",
                        lambda path: FakeDb({"双文鸟": "X-2", "异文鸟": "Y-9"}))
    lib = CardLibrary.from_docs([
        ("双文鸟-甲.yml", parse_card_doc(DRAW_YAML.format(cid="X-1"))),
        ("双文鸟-乙.yml", parse_card_doc(SHUFFLE_YAML.format(cid="X-2"))),
        ("异文鸟.yml", parse_card_doc(
            DRAW_YAML.replace("双文鸟", "异文鸟").format(cid="Y-1"))),
    ])
    monkeypatch.setattr(exp_mod, "load_card_dir", lambda cards_dir: lib)
    base_effects, _ = exp_mod.assemble_card_effects([[_item("双文鸟", "X-1")]], lib)
    prep = PreparedExperiment(
        deck_a=[_item("双文鸟", "X-1")], deck_b=[_item("白板鸟", "W-1")],
        card_effects=base_effects,
        deck_a_id="a", deck_b_id="b", data_version="test")

    # 换入印刷在库：按 card_id 补入文档
    variant = VariantCfg(name="v1", swaps=[SwapCfg(
        side="a", out="双文鸟", out_count=1, **{"in": "双文鸟", "in_count": 1})])
    new_prep = prepare_variant(prep, variant, ":memory:", cards_dir="unused")
    assert "X-2" in new_prep.card_effects
    assert new_prep.card_effects["X-2"].effects[0].actions[0].action == "shuffle_deck"
    assert not [w for w in new_prep.warnings if "X-2" in w]

    # 换入印刷不在库但同名有文档：告警透传，不硬报错
    variant2 = VariantCfg(name="v2", swaps=[SwapCfg(
        side="a", out="双文鸟", out_count=1, **{"in": "异文鸟", "in_count": 1})])
    new_prep2 = prepare_variant(prep, variant2, ":memory:", cards_dir="unused")
    assert "Y-9" not in new_prep2.card_effects
    assert any("异文鸟" in w and "Y-9" in w for w in new_prep2.warnings)


# ── 定义库审计（cards/ 收窄与出库断言，无 db 依赖）─────────

CARDS_DIR = Path(__file__).parent.parent / "cards"


def test_审计收窄_不服输头带_仅收同文本印刷():
    from battlefrontier.dsl.loader import load_card_doc

    doc = load_card_doc(CARDS_DIR / "不服输头带.yml")
    assert "CSV1C-117" in doc.card.card_ids      # 池内使用印刷保留
    assert "CSVH1aC-016" not in doc.card.card_ids  # 异文本印刷剔除


def test_审计收窄_朋友手册_仅收最多2张文本类():
    from battlefrontier.dsl.loader import load_card_doc

    doc = load_card_doc(CARDS_DIR / "朋友手册.yml")
    assert "CSV1C-111" in doc.card.card_ids        # 池内使用（G 标「最多2张」）
    assert "CSM1DC-246" not in doc.card.card_ids   # 「2张」异文本类剔除
    assert "SSP-NaN48" not in doc.card.card_ids


def test_退环境且池内零使用_文件出库():
    """彷徨夜灵（D 标 CS2.5C-018）/ 交替推车 / 捕获香氛：全印刷退环境 + 池内零使用。"""
    stems = {p.stem for p in CARDS_DIR.glob("*.yml")}
    assert "彷徨夜灵" not in stems
    assert "交替推车" not in stems
    assert "捕获香氛" not in stems


# ── db 依赖：prepare 集成 + 池内覆盖回归 ──────────────────

DB_PATH = Path(r"C:/Vibe Project/Pokearena/data/ptcg-cn.db")
POOL_DECKS = ["mik_moe:644634", "mik_moe:650353", "mik_moe:652967", "mik_moe:655545",
              "mik_moe:655776", "mik_moe:643572", "mik_moe:655513", "mik_moe:648346",
              "mik_moe:655512"]
# 波波 CSV4C-099「起风」白板印刷：同名异文本（「呼朋引伴」版有 DSL），合法不挂载、
# 装配走覆盖告警（不硬报错）；池内唯一一例同名有文档而未覆盖的印刷
VANILLA_UNCOVERED_OK = {"CSV4C-099"}

needs_db = pytest.mark.skipif(not DB_PATH.exists(), reason="本机无 ptcg-cn.db")


@needs_db
def test_prepare_experiment_真实卡组_按_card_id_挂载(tmp_path):
    """沙奈朵镜像 prepare：card_effects 键 = card_id；池内印刷精确挂载。"""
    from battlefrontier.runner.experiment import load_experiment, prepare_experiment

    exp = tmp_path / "exp.yml"
    exp.write_text(
        "name: mirror\ngames: 1\n"
        "decks:\n  a: {source: db, deck_id: \"mik_moe:644634\"}\n"
        "  b: {source: db, deck_id: \"mik_moe:644634\"}\n",
        encoding="utf-8")
    prep = prepare_experiment(load_experiment(exp), str(DB_PATH), cards_dir="cards")
    assert isinstance(prep.card_effects, CardLibrary)
    used = {c.card_id for c in (*prep.deck_a, *prep.deck_b)}
    assert set(prep.card_effects) <= used  # 按 card_id 过滤，不多挂
    ub = next(c for c in prep.deck_a if c.name == "高级球")
    assert ub.card_id in prep.card_effects  # 池内印刷精确挂载
    gardevoir = next(c for c in prep.deck_a if c.name == "沙奈朵ex")
    assert gardevoir.card_id in prep.card_effects


@needs_db
def test_池内卡组印刷覆盖回归():
    """池内 9 套卡组：同名有效果文档的印刷必须被库覆盖（波波白板印刷除外）。"""
    from ptcgdb.sdk import open_db

    lib = load_card_dir(CARDS_DIR)
    db = open_db(str(DB_PATH))
    try:
        for deck_id in POOL_DECKS:
            deck = db.get_deck(deck_id)
            for cid in sorted({c.card_id for c in deck.cards}):
                if cid in lib:
                    continue
                name = db.get_card(cid).name_full
                if lib.by_name(name):
                    assert cid in VANILLA_UNCOVERED_OK, (
                        f"{deck_id} 印刷 {cid}（{name}）同名有文档但未挂载")
    finally:
        db.close()
