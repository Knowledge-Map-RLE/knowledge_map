from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TokenInfo:
    idx: int
    text: str
    lemma: str
    pos: str
    tag: str
    dep: str
    head_idx: int
    morph: dict[str, str] = field(default_factory=dict)
    is_stop: bool = False
    is_punct: bool = False
    is_space: bool = False

    @property
    def is_noun(self) -> bool:
        return self.pos in ("NOUN", "PROPN")

    @property
    def is_verb(self) -> bool:
        return self.pos == "VERB"

    @property
    def is_adj(self) -> bool:
        return self.pos == "ADJ"

    @property
    def is_adverb(self) -> bool:
        return self.pos == "ADV"

    @property
    def is_aux(self) -> bool:
        return self.pos == "AUX"

    @property
    def is_determiner(self) -> bool:
        return self.pos == "DET"

    @property
    def is_adposition(self) -> bool:
        return self.pos == "ADP"


@dataclass
class DependencyTree:
    tokens: list[TokenInfo]
    _children: dict[int, list[TokenInfo]] = field(default_factory=dict, repr=False)
    _root: TokenInfo | None = field(default=None, repr=False)

    def __post_init__(self):
        self._token_map: dict[int, TokenInfo] = {}
        self._dep_index: dict[str, list[TokenInfo]] = {}
        self._pos_index: dict[str, list[TokenInfo]] = {}
        self._subtree_cache: dict[int, list[TokenInfo]] = {}

        for token in self.tokens:
            self._token_map[token.idx] = token
            if token.dep == "ROOT":
                self._root = token
            if token.head_idx != token.idx:
                self._children.setdefault(token.head_idx, []).append(token)

            self._dep_index.setdefault(token.dep, []).append(token)
            self._pos_index.setdefault(token.pos, []).append(token)

    @property
    def root(self) -> TokenInfo | None:
        return self._root

    def children(self, token_idx: int) -> list[TokenInfo]:
        return self._children.get(token_idx, [])

    def subtree_tokens(self, token_idx: int) -> list[TokenInfo]:
        cached = self._subtree_cache.get(token_idx)
        if cached is not None:
            return cached

        result = []
        stack = [token_idx]
        while stack:
            idx = stack.pop()
            t = self._token_map.get(idx)
            if t is not None:
                result.append(t)
            stack.extend(c.idx for c in self.children(idx))
        result.sort(key=lambda t: t.idx)
        self._subtree_cache[token_idx] = result
        return result

    def subtree_text(self, token_idx: int) -> str:
        return " ".join(t.text for t in self.subtree_tokens(token_idx) if not t.is_punct and not t.is_space)

    def head_text(self, token_idx: int) -> str:
        current = self._token_map.get(token_idx)
        if not current or current.dep == "ROOT":
            return ""
        head_t = self._token_map.get(current.head_idx)
        return head_t.lemma if head_t else ""

    def token_by_idx(self, idx: int) -> TokenInfo | None:
        return self._token_map.get(idx)

    def find_by_dep(self, dep: str) -> list[TokenInfo]:
        return self._dep_index.get(dep, [])

    def find_by_pos(self, pos: str) -> list[TokenInfo]:
        return self._pos_index.get(pos, [])

    @staticmethod
    def from_unified_sentence(sentence: dict) -> DependencyTree:
        tokens_data = sentence.get("tokens", []) or []
        deps_data = sentence.get("dependencies", []) or []

        dep_map: dict[int, tuple[int, str]] = {}
        for dep in deps_data:
            dep_map[dep["dependent_idx"]] = (dep["head_idx"], dep["relation"])

        tokens = []
        for tok in tokens_data:
            idx = tok.get("idx", 0)
            head_idx, dep_rel = dep_map.get(idx, (idx, "ROOT"))
            morph = dict(tok.get("morph", {}) or {})
            tokens.append(TokenInfo(
                idx=idx,
                text=tok.get("text", ""),
                lemma=tok.get("lemma", ""),
                pos=tok.get("pos", ""),
                tag=tok.get("pos_fine", ""),
                dep=dep_rel,
                head_idx=head_idx,
                morph=morph,
                is_stop=tok.get("is_stop", False),
                is_punct=tok.get("is_punct", False),
                is_space=tok.get("is_space", False),
            ))

        return DependencyTree(tokens=tokens)
