"""DSL 加载器：YAML → CardEffectDoc，词表校验，错误统一 DslError（带文件上下文）。"""

from importlib import resources
from pathlib import Path

import yaml
from pydantic import ValidationError

from battlefrontier.dsl.schema import ActionNode, CardEffectDoc

VOCAB_RESOURCE = "vocabularies.yml"


class DslError(Exception):
    """DSL 解析/校验统一错误，消息含来源文件上下文。"""


def _load_vocab_raw() -> dict[str, list[str]]:
    text = (
        resources.files("battlefrontier.dsl").joinpath(VOCAB_RESOURCE).read_text(encoding="utf-8")
    )
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise DslError(f"{VOCAB_RESOURCE}: 顶层必须是映射")
    return data


class Vocabulary:
    """词表（开放字符串的来源）：各段为tuple，加载时查重。"""

    def __init__(self, sections: dict[str, list[str]]) -> None:
        for name, words in sections.items():
            if not isinstance(words, list) or not all(isinstance(w, str) for w in words):
                raise DslError(f"{VOCAB_RESOURCE}: 段 {name} 必须是字符串列表")
            if len(words) != len(set(words)):
                raise DslError(f"{VOCAB_RESOURCE}: 段 {name} 有重复条目")
            setattr(self, name, tuple(words))
        self._sections = sections

    def check(self, section: str, word: str, source: str) -> None:
        """word 必须在 section 段词表内，否则 DslError（提示词表文件位置）。"""
        words = getattr(self, section, ())
        if word not in words:
            raise DslError(
                f"{source}: 未知{section}词 '{word}'"
                f"（不在词表 {section} 段；扩展请改 battlefrontier/dsl/{VOCAB_RESOURCE}）"
            )


def load_vocabularies() -> Vocabulary:
    """加载随包词表文件。"""
    return Vocabulary(_load_vocab_raw())


def _check_action(node: ActionNode, vocab: Vocabulary, source: str) -> None:
    vocab.check("actions", node.action, source)
    if node.selector is not None:
        vocab.check("selectors", node.selector, source)
    if isinstance(node.count, str):
        vocab.check("counters", node.count, source)
    if node.destination is not None:
        vocab.check("destinations", node.destination, source)


def _validate_vocab(doc: CardEffectDoc, vocab: Vocabulary, source: str) -> None:
    for effect in doc.effects:
        vocab.check("triggers", effect.trigger, source)
        if effect.limit is not None:
            vocab.check("limits", effect.limit, source)
        for node in (*effect.cost, *effect.actions):
            _check_action(node, vocab, source)


def parse_card_doc(text: str, source: str = "<string>") -> CardEffectDoc:
    """YAML 文本 → CardEffectDoc；任何解析/校验失败抛 DslError（含 source）。"""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DslError(f"{source}: YAML 解析失败：{exc}") from exc
    try:
        doc = CardEffectDoc.model_validate(data)
    except ValidationError as exc:
        raise DslError(f"{source}: schema 校验失败\n{exc}") from exc
    _validate_vocab(doc, load_vocabularies(), source)
    return doc


def load_card_doc(path: str | Path) -> CardEffectDoc:
    """从文件加载（UTF-8）。"""
    p = Path(path)
    return parse_card_doc(p.read_text(encoding="utf-8"), source=p.name)


class CardLibrary(dict[str, CardEffectDoc]):
    """DSL 定义库：dict 子类，键 = card_id 精确挂载（2026-09-06 决议）。

    归组口径 =（卡名 + 文本）等价类严格拆分：同名多文本文件可共存（card_ids
    不相交，由 from_docs 重复检查保证）；引擎侧仅按 card_id 取文档，无名字兜底
    （防同名异文本静默错挂）。
    """

    @classmethod
    def from_docs(cls, entries) -> "CardLibrary":
        """（来源名, 文档）序列 → CardLibrary；挂载键必填 + card_id 跨文件查重。"""
        lib = cls()
        sources: dict[str, str] = {}
        for source, doc in entries:
            if not doc.card.card_ids:
                raise DslError(
                    f"{source}: card_ids 为空——挂载键必填"
                    f"（装载键 = card_id 精确挂载，2026-09-06 决议）"
                )
            for cid in doc.card.card_ids:
                if cid in lib:
                    raise DslError(
                        f"{source}: card_id '{cid}' 与库内已有文档重复（{sources[cid]}）"
                    )
                lib[cid] = doc
                sources[cid] = source
        return lib

    def by_name(self, name: str) -> list[CardEffectDoc]:
        """按 name_group 取全部文档（同名多文本共存；工具/测试用，引擎不用）。

        同一文档按全部 card_ids 多点挂载，返回值按文档去重。
        """
        seen: dict[int, CardEffectDoc] = {}
        for doc in self.values():
            if doc.card.name_group == name:
                seen.setdefault(id(doc), doc)
        return list(seen.values())


def load_card_dir(path: str | Path) -> CardLibrary:
    """加载整个 DSL 定义库目录（一卡一 YAML）→ CardLibrary（键 = card_id）。"""
    return CardLibrary.from_docs(
        [(p.name, load_card_doc(p)) for p in sorted(Path(path).glob("*.yml"))]
    )
