"""Rule-based extraction of abnormal findings from Russian medical text.

Natasha provides sentence segmentation and morphological normalization. The
rules deliberately extract text, not diagnoses or clinical recommendations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from natasha import Doc, MorphVocab, NewsEmbedding, NewsMorphTagger, Segmenter


Certainty = Literal["certain", "possible"]


@dataclass(frozen=True)
class MedicalFinding:
    """Одно найденное в тексте медицинского заключения отклонение или изменение.

    Атрибуты:
        text: Точное слово или фрагмент исходного текста, распознанный как находка.
        sentence: Предложение исходного текста, в котором найдена находка.
        category: Тип находки, например ``structural_finding`` или ``size_change``.
        certainty: ``"certain"`` для утверждения без маркеров сомнения;
            ``"possible"`` для находки, описанной предположительно.
        start: Начальный индекс находки в исходной строке (включительно).
        end: Конечный индекс находки в исходной строке (не включительно).

    Индексы ``start`` и ``end`` отсчитываются от нуля и используют диапазон
    ``[start, end)``, поэтому ``text[start:end]`` возвращает ``text`` находки.
    Класс неизменяемый: после создания его поля нельзя переназначить.
    """

    text: str
    sentence: str
    category: str
    certainty: Certainty
    start: int
    end: int


@dataclass(frozen=True)
class _Rule:
    lemma: str
    category: str


_RULES = (
    _Rule("патологический", "pathology"),
    _Rule("патология", "pathology"),
    _Rule("изменение", "change"),
    _Rule("измененный", "change"),
    _Rule("очаг", "focal_finding"),
    _Rule("образование", "structural_finding"),
    _Rule("узел", "structural_finding"),
    _Rule("киста", "structural_finding"),
    _Rule("полип", "structural_finding"),
    _Rule("конкремент", "structural_finding"),
    _Rule("камень", "structural_finding"),
    _Rule("выпот", "structural_finding"),
    _Rule("инфильтрат", "structural_finding"),
    _Rule("эрозия", "structural_finding"),
    _Rule("язва", "structural_finding"),
    _Rule("перелом", "structural_finding"),
    _Rule("тромб", "structural_finding"),
    _Rule("стеноз", "structural_finding"),
    _Rule("аневризма", "structural_finding"),
    _Rule("грыжа", "structural_finding"),
    _Rule("атрофия", "structural_finding"),
    _Rule("фиброз", "structural_finding"),
    _Rule("склероз", "structural_finding"),
    _Rule("кальцинат", "structural_finding"),
    _Rule("метастаз", "structural_finding"),
    _Rule("опухоль", "structural_finding"),
    _Rule("воспаление", "structural_finding"),
    _Rule("дистрофия", "structural_finding"),
    _Rule("дегенерация", "structural_finding"),
    _Rule("деструкция", "structural_finding"),
    _Rule("некроз", "structural_finding"),
    _Rule("ишемия", "structural_finding"),
    _Rule("отек", "structural_finding"),
    _Rule("асцит", "structural_finding"),
    _Rule("гематома", "structural_finding"),
    _Rule("деформация", "structural_change"),
    _Rule("смещение", "structural_change"),
    _Rule("расширить", "size_change"),
    _Rule("увеличить", "size_change"),
    _Rule("уменьшить", "size_change"),
    _Rule("сужать", "size_change"),
    _Rule("утолщить", "structural_change"),
    _Rule("истончить", "structural_change"),
    _Rule("повысить", "measurement_change"),
    _Rule("снизить", "measurement_change"),
    _Rule("нарушить", "structural_change"),
    _Rule("неоднородный", "structural_change"),
    _Rule("уплотнение", "structural_change"),
)

_CLAUSE_BREAK = re.compile(r"[,;:\n]+|\b(?:но|однако|при этом)\b", re.IGNORECASE)
_UNCERTAINTY = re.compile(
    r"\b(?:возможно|вероятно|вероятный|предположительно|подозрение|"
    r"нельзя\s+исключить|не\s+исключается|может\s+соответствовать|"
    r"может\s+быть)\b",
    re.IGNORECASE,
)
_NEGATION_BEFORE = re.compile(
    r"(?:\bне\s*$|\bне\s+(?:выявлен\w*|определя\w*|обнаружен\w*|"
    r"визуализир\w*|прослежива\w*|отмеча\w*|наблюда\w*|"
    r"расширен\w*|увеличен\w*|изменен\w*)|"
    r"\bбез(?:\s+\w+){0,2}|\bнет|\bотсутств(?:ует|уют|ие|ия))"
    r"\s*(?:\w+\s*){0,2}$",
    re.IGNORECASE,
)
_NEGATION_AFTER = re.compile(
    r"^\s*(?:не\s+(?:выявлен\w*|определя\w*|обнаружен\w*|"
    r"визуализир\w*|прослежива\w*|отмеча\w*|наблюда\w*)|"
    r"нет\b|отсутств(?:ует|уют))",
    re.IGNORECASE,
)
_NORMAL_CONTEXT = re.compile(
    r"\b(?:в\s+пределах\s+нормы|в\s+норме|норм(?:а|ы|е|альный|"
    r"альная|альное|альные))\b",
    re.IGNORECASE,
)
_CHANGE_CATEGORIES = {
    "change",
    "size_change",
    "measurement_change",
    "structural_change",
}


@lru_cache(maxsize=1)
def _natasha_components() -> tuple[Segmenter, NewsMorphTagger, MorphVocab]:
    segmenter = Segmenter()
    embedding = NewsEmbedding()
    return segmenter, NewsMorphTagger(embedding), MorphVocab()


def _normalize(value: str) -> str:
    return value.casefold().replace("ё", "е")


def _is_negated(clause: str, start: int, end: int) -> bool:
    before = clause[:start][-80:]
    after = clause[end:][:60]
    return bool(_NEGATION_BEFORE.search(before) or _NEGATION_AFTER.search(after))


def _is_normal_context(clause: str, start: int, end: int) -> bool:
    nearby = clause[max(0, start - 50) : min(len(clause), end + 50)]
    return bool(_NORMAL_CONTEXT.search(nearby))


def _clause_ranges(sentence: str, start: int) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    cursor = 0
    for boundary in _CLAUSE_BREAK.finditer(sentence):
        if sentence[cursor : boundary.start()].strip():
            ranges.append((start + cursor, start + boundary.start()))
        cursor = boundary.end()
    if sentence[cursor:].strip():
        ranges.append((start + cursor, start + len(sentence)))
    return ranges


def extract_findings(text: str) -> list[MedicalFinding]:
    """Extract likely abnormal findings while excluding negated normal results.

    The returned offsets are zero-based, half-open character offsets into
    ``text``. ``possible`` marks findings described with uncertain language.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if not text.strip():
        return []

    segmenter, morph_tagger, morph_vocab = _natasha_components()
    doc = Doc(text)
    doc.segment(segmenter)
    doc.tag_morph(morph_tagger)
    for token in doc.tokens:
        token.lemmatize(morph_vocab)

    findings: list[MedicalFinding] = []
    for sentence in doc.sents:
        sentence_text = text[sentence.start : sentence.stop]
        sentence_possible = bool(_UNCERTAINTY.search(sentence_text))
        for clause_start, clause_end in _clause_ranges(sentence_text, sentence.start):
            clause = text[clause_start:clause_end]
            clause_tokens = [
                token
                for token in doc.tokens
                if clause_start <= token.start
                and token.stop <= clause_end
                and token.lemma
                and re.search(r"\w", token.text)
            ]
            possible = sentence_possible or bool(_UNCERTAINTY.search(clause))
            seen: set[tuple[int, int, str]] = set()

            for token in clause_tokens:
                lemma = _normalize(token.lemma)
                for rule in _RULES:
                    if lemma != _normalize(rule.lemma):
                        continue
                    local_start = token.start - clause_start
                    local_end = token.stop - clause_start
                    if _is_negated(clause, local_start, local_end):
                        continue
                    if (
                        rule.category in _CHANGE_CATEGORIES
                        and _is_normal_context(clause, local_start, local_end)
                        and not possible
                    ):
                        continue
                    key = (token.start, token.stop, rule.category)
                    if key in seen:
                        continue
                    seen.add(key)
                    findings.append(
                        MedicalFinding(
                            text=text[token.start : token.stop],
                            sentence=sentence_text.strip(),
                            category=rule.category,
                            certainty="possible" if possible else "certain",
                            start=token.start,
                            end=token.stop,
                        )
                    )

    findings.sort(key=lambda finding: (finding.start, finding.end, finding.category))
    return findings
