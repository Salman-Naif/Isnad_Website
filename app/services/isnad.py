"""
What the page shows beside the verdict: how the visitor's text matches the source, the words
that differ from it (the شبهة), and the isnad tree.

The database sends each match's isnad as a tree (from the Prophet ﷺ to the compiler). The
same hadith often comes back from several books; their trees are merged here, so shared
narrators are drawn once and each book's chain branches off where it differs.
"""

import re
import unicodedata

from app.models.schemas import MatchType, Narrator, QueryWord, SanadNode

_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭـ]")
_LETTERS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه"})
_NOT_WORD = re.compile(r"[^\w]+")
# Matched with the similarity of the database's literal index, which scores a quote 1.0.
EXACT = 0.999


def normalize(word: str) -> str:
    """A word as compared: no diacritics or tatweel, one form of alef / ya / ta marbuta."""
    text = _DIACRITICS.sub("", unicodedata.normalize("NFKC", word)).translate(_LETTERS)
    return _NOT_WORD.sub("", text)


def _forms(word: str) -> set[str]:
    """The word, and the word without a leading و / ف («وإنما» is «إنما» in another sentence)."""
    forms = {word}
    if len(word) > 3 and word[0] in "وف":
        forms.add(word[1:])
    return forms


def compare_words(query: str, source: str) -> list[QueryWord]:
    """The visitor's words in order, each marked when it is not in the source text."""
    present: set[str] = set()
    for word in source.split():
        present |= _forms(normalize(word))
    words = []
    for word in query.split():
        key = normalize(word)
        changed = bool(key) and not (_forms(key) & present)
        words.append(QueryWord(word=word, changed=changed))
    return words


def match_type(similarity: float, words: list[QueryWord], same_text: bool, close: bool) -> MatchType:
    """How the visitor's text matches: word for word, nearly, reworded, or not at all."""
    if same_text and (similarity >= EXACT or (words and not any(w.changed for w in words))):
        return MatchType.EXACT
    if same_text:
        return MatchType.CLOSE
    if close:
        return MatchType.REWORDED
    return MatchType.NONE


def chain_tree(narrators: list[Narrator]) -> SanadNode | None:
    """A single chain as a tree (from a database that sends no tree)."""
    if not narrators:
        return None
    root = node = SanadNode(name=narrators[0].name, grade=narrators[0].grade)
    for narrator in narrators[1:]:
        child = SanadNode(name=narrator.name, grade=narrator.grade)
        node.children.append(child)
        node = child
    return root


def _key(name: str) -> str:
    return " ".join(w.removeprefix("ال") for w in _words(name))


def _words(text: str) -> list[str]:
    return [w for w in (normalize(word) for word in text.split()) if w]


def same_root(tree: SanadNode, other: SanadNode | None) -> bool:
    return other is not None and _key(tree.name) == _key(other.name)


def merge_trees(trees: list[SanadNode]) -> SanadNode | None:
    """One tree from the trees of several narrations of the same hadith.

    Only trees with the same root are merged (all from the Prophet ﷺ, say); a narration that
    starts elsewhere is a different chain and stays out.
    """
    if not trees:
        return None
    root = SanadNode(name=trees[0].name, grade=trees[0].grade)
    for tree in trees:
        if same_root(tree, root):
            _graft(root, tree)
    return root


def _same_pupil(a: str, b: str) -> bool:
    """Two names under the same teacher for one narrator: equal, or one the other in full
    («يحيى بن سعيد» / «يحيى بن سعيد الأنصاري»). A one-word name is too common to tell."""
    x, y = _key(a).split(), _key(b).split()
    short, long = sorted((x, y), key=len)
    return x == y or (len(short) >= 2 and long[: len(short)] == short)


def _graft(into: SanadNode, tree: SanadNode) -> None:
    for child in tree.children:
        target = next((c for c in into.children if _same_pupil(c.name, child.name)), None)
        if target is None:
            target = SanadNode(name=child.name, grade=child.grade)
            into.children.append(target)
        else:
            if len(child.name) > len(target.name):
                target.name = child.name  # the fuller name
            target.grade = target.grade or child.grade
        _graft(target, child)
