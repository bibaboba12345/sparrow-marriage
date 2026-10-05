"""Strict LLM extract: patient demographics + clinical tokens from catalog; rest → junk."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .recommendations import (
    DISCLAIMER_REC,
    extract_recommendation,
    labels_for_tokens,
    recommendation_token_names,
)

PATIENT_KEYS = ("age_years", "height_cm", "weight_kg", "sex")


def _repo_root() -> Path:
    # back/app/routing/this.py → repo root
    return Path(__file__).resolve().parents[3]


def _catalog_path() -> Path:
    env = os.getenv("STRICT_TOKENS_PATH")
    if env:
        return Path(env)
    return _repo_root() / "СМ-Клиника-протоколы" / "strict_tokens_candidates.json"


@lru_cache(maxsize=1)
def load_token_catalog() -> dict[str, dict[str, Any]]:
    """name → {type, unit?, aliases?} from strict_tokens_candidates.json."""
    path = _catalog_path()
    # bust cache if file mtime changes
    mtime = path.stat().st_mtime
    return _load_token_catalog_at(str(path), mtime)


def _ingest_token_meta(out: dict[str, dict[str, Any]], name: str, meta: Any) -> None:
    if not isinstance(meta, dict):
        meta = {"type": "binary"}
    out[name] = {
        "type": meta.get("type") or "binary",
        "unit": meta.get("unit"),
        "aliases": list(meta.get("aliases") or []),
    }


@lru_cache(maxsize=4)
def _load_token_catalog_at(path_str: str, _mtime: float) -> dict[str, dict[str, Any]]:
    data = json.loads(Path(path_str).read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for mod in (data.get("modalities") or {}).values():
        if not isinstance(mod, dict):
            continue
        for bag in ("organ_tokens", "vessel_tokens", "tokens", "study_flags"):
            bagd = mod.get(bag) or {}
            if not isinstance(bagd, dict):
                continue
            for name, meta in bagd.items():
                _ingest_token_meta(out, name, meta)
    cc_tokens = (data.get("cross_cutting") or {}).get("tokens") or {}
    if isinstance(cc_tokens, dict):
        for name, meta in cc_tokens.items():
            _ingest_token_meta(out, name, meta)
    return out


# Служебные слова — не считаем совпадением с текстом протокола.
_CATALOG_STOPWORDS = frozenset(
    {
        "и",
        "или",
        "а",
        "но",
        "да",
        "же",
        "ли",
        "бы",
        "б",
        "в",
        "во",
        "на",
        "за",
        "с",
        "со",
        "по",
        "из",
        "для",
        "о",
        "об",
        "обо",
        "от",
        "до",
        "при",
        "без",
        "через",
        "над",
        "под",
        "к",
        "ко",
        "у",
        "между",
        "про",
        "перед",
        "после",
        "около",
        "также",
        "тоже",
        "как",
        "что",
        "это",
        "не",
        "ни",
        "то",
        "только",
        "уже",
        "ещё",
        "еще",
        "мм",
        "см",
        "кг",
        "мл",
        "куб",
        "of",
        "the",
        "a",
        "an",
        "and",
        "or",
        "in",
        "on",
        "for",
        "to",
        "with",
        "from",
        "by",
        # стороны / маркеры в именах токенов
        "l",
        "r",
        "s",
        "d",
        "max",
        "min",
        "pct",
        "axbxc",
    }
)

# Одно такое слово без второго якоря — слишком общее (киста_S, полип_ц/к…).
_WEAK_ALONE = frozenset(
    {
        "киста",
        "кисты",
        "узел",
        "узлы",
        "полип",
        "полипа",
        "полипы",
        "очаг",
        "очаги",
        "размеры",
        "размер",
        "контуры",
        "контур",
        "образование",
        "образования",
        "неоднородный",
        "неоднородная",
        "однородный",
        "однородная",
        "расширена",
        "расширен",
        "расширены",
        "кровоток",
        "признаки",
        "признак",
    }
)


def _split_ident_words(s: str) -> str:
    """CamelCase / цифры → пробелы: КистаЯичника_L → киста яичника l."""
    s = re.sub(r"([a-zа-я0-9])([A-ZА-Я])", r"\1 \2", s or "")
    s = re.sub(r"([A-ZА-Я]+)([A-ZА-Я][a-zа-я])", r"\1 \2", s)
    return s


def _normalize_catalog_text(s: str) -> str:
    s = _split_ident_words(s or "")
    s = s.lower().replace("ё", "е")
    s = s.replace("_", " ").replace("-", " ").replace("/", " ").replace(".", " ")
    return re.sub(r"\s+", " ", s).strip()


def _content_words(phrase: str) -> list[str]:
    """Значимые слова имени/alias (без союзов и служебных)."""
    words: list[str] = []
    for w in re.findall(r"[a-zа-я0-9]+", _normalize_catalog_text(phrase)):
        if w in _CATALOG_STOPWORDS:
            continue
        # короткие оставляем только как аббревиатуры (ОМТ, ЖП, TV…)
        if len(w) < 2:
            continue
        if len(w) == 2 and not re.fullmatch(r"[a-zа-я]{2}|\d{2}", w):
            continue
        words.append(w)
    return words


def _russian_word_variants(word: str) -> list[str]:
    """Частые падежные/числовые варианты (киста↔кисты, миома↔миомы, шейка↔шейки)."""
    w = word or ""
    out = {w}
    if len(w) < 4:
        return [w]
    if w.endswith("а"):
        stem = w[:-1]
        out.update({stem + "ы", stem + "у", stem + "е", stem + "ой", stem + "ами"})
    elif w.endswith("я"):
        stem = w[:-1]
        out.update({stem + "и", stem + "ю", stem + "е", stem + "ей", stem + "ями"})
    elif w.endswith("ы"):
        out.add(w[:-1] + "а")
    elif w.endswith("и") and not w.endswith(("ии", "ции", "сии")):
        out.add(w[:-1] + "а")
        out.add(w[:-1] + "я")
    return [x for x in out if x]


def _word_matches_text(word: str, text_low: str) -> bool:
    """Слово из токена/alias встречается в тексте (с допуском русских окончаний)."""
    if not word:
        return False
    # Короткие — только точное слово (или явные падежи для 4–5 букв вроде «киста»).
    if len(word) <= 4:
        return bool(re.search(rf"(?<![\w]){re.escape(word)}(?![\w])", text_low))
    for variant in _russian_word_variants(word):
        if re.search(rf"(?<![\w]){re.escape(variant)}(?![\w])", text_low):
            return True
    # Производные: полип→полипоз, узел→узелок (короткий суффикс после полного слова).
    if re.search(rf"(?<![\w]){re.escape(word)}\w{{1,4}}(?![\w])", text_low):
        return True
    # Более длинный стем: «миометри…», «эндоцервикс…»
    if len(word) >= 6:
        stem = word[:-2]
        if re.search(rf"(?<![\w]){re.escape(stem)}\w{{0,4}}(?![\w])", text_low):
            return True
    return False


def _phrase_overlaps_text(phrase: str, text_low: str) -> bool:
    """Фраза (canonical или alias) совпала: все её значимые слова есть в тексте."""
    words = _content_words(phrase)
    if not words:
        return False
    # «киста» / «полип» одни — не считаем совпадением alias'а
    if len(words) == 1 and words[0] in _WEAK_ALONE:
        return False
    return all(_word_matches_text(w, text_low) for w in words)


def _token_overlaps_text(name: str, meta: dict[str, Any], text_low: str) -> bool:
    """True, если canonical или любой alias совпал с текстом по словам."""
    phrases = [name, *list(meta.get("aliases") or [])]
    return any(_phrase_overlaps_text(str(ph), text_low) for ph in phrases)


def _catalog_entry_line(name: str, meta: dict[str, Any]) -> str:
    t = meta.get("type") or "binary"
    unit = meta.get("unit")
    head = f"{name}:{t}"
    if unit:
        head += f":{unit}"
    aliases = [str(a).strip() for a in (meta.get("aliases") or []) if str(a).strip()]
    hints: list[str] = []
    seen: set[str] = set()
    name_key = name.lower().replace("_", " ")
    for a in aliases:
        pretty = a.replace("_", " ")
        key = pretty.lower()
        if key in seen or key == name_key:
            continue
        seen.add(key)
        hints.append(pretty)
    if hints:
        return head + "  | hint: " + "; ".join(hints)
    return head


def catalog_prompt_block(*, text: str | None = None) -> str:
    """Каталог для LLM: canonical + все aliases.

    Если передан ``text`` — оставляем только токены, у которых хотя бы одно
    значимое слово canonical или alias совпало с текстом протокола.
    """
    header = (
        "# Формат: <canonical>:type[:unit]  | hint: <alias1>; <alias2>; ...\n"
        "# В tokens — ТОЛЬКО <canonical>. Поле hint = НАВОДКИ (синонимы/аббревиатуры), не жёсткий словарь.\n"
        "# Смысл в протоколе ≈ hint или canonical → верни canonical. Дословного совпадения не требуй.\n"
    )

    catalog = load_token_catalog()
    names = sorted(catalog)
    if text:
        text_low = _normalize_catalog_text(text)
        names = [n for n in names if _token_overlaps_text(n, catalog[n], text_low)]

    lines = [_catalog_entry_line(name, catalog[name]) for name in names]
    return header + "\n".join(lines)


def _build_system_prompt() -> str:
    from .organ_classes import organ_classes_prompt_block

    return f"""Ты парсер медицинских УЗИ/дуплекс протоколов.
Все объективные наблюдения диагноста нужно ПРИВЕСТИ к именам из каталога токенов.
Верни СТРОГО один JSON-объект (без markdown):

{{
  "patient": {{
    "age_years": number|null,
    "height_cm": number|null,
    "weight_kg": number|null,
    "sex": "м"|"ж"|null
  }},
  "tokens": {{
    "<token_name_from_catalog>": <value>
  }},
  "junk": string[]
}}

Правила patient:
- Возраст / рост / вес / пол, если ЯВНО есть. Иначе null. Не выдумывай.

{organ_classes_prompt_block()}

=== РАСШИФРОВКА СОКРАЩЕНИЙ (ОБЯЗАТЕЛЬНО, ДЛЯ ВСЕХ ОРГАНОВ) ===
Протоколы пишут компактно: аббревиатуры органов, сторон (D/S/R/L), V=, размеры a×b×c.
Алгоритм для КАЖДОЙ такой фразы:
  1) мысленно РАСКРОЙ сокращение → полное анатомическое имя;
  2) найди канонический ключ в каталоге (или alias);
  3) положи значение в tokens (см→мм если unit=mm);
  4) НИКОГДА не оставляй «D: …», «S: …», «V=…», «ЩЖ:…», «ЖП:…» в junk — это измерения/находки.

Стороны / доли (латынь, кириллица, латиница) — везде одинаково:
- D / Dex / Dexter / пр. / справа / прав. / R / _R → ПРАВАЯ сторона/доля
- S / Sin / Sinister / л. / слева / лев. / L / _L → ЛЕВАЯ сторона/доля
- bilat / с обеих сторон / обеих долях → оба (_R и _L), если в каталоге есть раздельные ключи
- В контексте ЩЖ буква D/S ПЕРЕД размерами = доля (не «диаметр»!);
  «S3 D 1.1x…» = сегмент/узел в ПРАВОЙ доле (D), не путать с «S:» левой доли.

Органы / зоны (раскрывай всегда):
- ЩЖ / щит.ж. / щит.железа → щитовидная железа
- ЖП / желч.пузырь → желчный пузырь
- ПЖ → поджелудочная (ОБП) ИЛИ предстательная (ТРУЗИ) — по контексту исследования
- ОБП / ОВП → органы брюшной полости
- МЖ → молочная железа; ВНК/ВВК/ННК/НВК → квадранты МЖ
- ОМТ → органы малого таза; ТВУЗИ/ТАУЗИ → доступ
- ЦДК / ЭД / УЗДГ / PW → режим кровотока (не junk)
- КВР / ККР / ПЗР / М-эхо → соответствующие *_мм ключи каталога

Объёмы / размеры (общий шаблон для любого органа):
- V / V= / Vol / объём / см3 / см³ / куб.см / см куб → *_объем_см3 / объем_*_см3
- a×b×c / aхbхc / a*b*c / a x b x c → triplet (*_размеры_мм); unit каталога мм + текст в см → ×10
- одно число + мм/см у органа → соответствующий *_мм / *_толщина_мм / *_диаметр_мм
- «общ. объем железы», «суммарный объем долей» → объем_щитовидной_см3 (или аналог в каталоге)

Щитовидная — эталон компактной строки (так же парси любые варианты порядка/разделителей):
  «ЩЖ: V=16.995 см3, D: 6.2x1.5x1.9 см S: 6.4x1.7x1.5 см, перешеек 5 мм»
  → объем_щитовидной_см3=16.995
  → ДоляПравая_размеры_мм="62x15x19"   (см→мм!)
  → ДоляЛевая_размеры_мм="64x17x15"
  → Перешеек_толщина_мм=5
  То же при «пр.доля / лев.доля / dexter / sinister / правая доля: … см».
Узел: «S3 D 1.1x1.14x1.0 см» / «узел D …» / «в правой доле … мм»
  → узел_щитовидной_R (или _L)=1; УзелЩЖ_R_мм / УзелЩЖ_L_мм / УзелЩЖ_max_мм = max сторона в мм
  «узловое образование … левой доли» / «гипоэхогенное … образование … левой доли»
    → узел_щитовидной_L: 1 (макрофолликул/киста — отдельно: расширенные_фолликулы)

Другие органы — тот же принцип расшифровки→каталог:
- ЖП: «ЖП 70x25 мм», «стенка ЖП …», «V ЖП=…» → ЖелчныйПузырь_* ключи
- ПЖ/печень/селезёнка: размеры/КВР/протоки → соответствующие *_мм / binary
- МЖ: сторона R/L, квадрант, BI-RADS, киста/узел → МЖ_* / киста_молочной_железы / …
- Сосуды НК: ОБА/ПБА/ГБА/ПкА/ЗББА/ПББА/ТАС/ОПА/НПА/БПВ/МПВ/СФС/СПС → ключи каталога
- ОМТ: матка/эндометрий/яичники R|L → Матка_* / Яичник* / …

Правила tokens:
- Разрешены ТОЛЬКО канонические имена из каталога (поле до «:» / до «| hint»).
- Поле «| hint:» — это НАВОДКИ, не закрытый список формулировок.
  Ориентируйся на смысл: если в протоколе та же находка другими словами / падежом /
  сокращением / перефразом — всё равно ставь КАНОНИЧЕСКИЙ ключ.
  Hint помогает узнать «о чём речь», но матчить нужно по смыслу, не строка-в-строку.
  Примеры (формулировка в тексте ≠ hint, ключ тот же):
  «жировая инфильтрация печени» / «стеатоз» ≈ hint «жировой гепатоз» → стеатоз_печени: 1
  «дискинезия желчевыводящих путей» ≈ hint «ДЖВП» → дискинезия_желчного_пузыря: 1
  «жидкость в позадиматочном пространстве» ≈ hint «Дуглас/ДП» → свободная_жидкость_за_маткой: 1
  (только если жидкость ЕСТЬ, не при отрицании)
  «диффузная форма внутреннего эндометриоза тела матки» ≈ hint «внутренний эндометриоз» → аденомиоз: 1
  (не путать с наружным эндометриоз)
  «шейка … неоднородная за счет анэхогенных … образований» / «ретенционные кисты» → киста_шейки_матки: 1
  (+ КистаШейки_max_мм = размер, если указан)
  «патология эндометрия (полип)» / «гиперэхогенное образование … эндометрия … с кровотоком»
    → полип_эндометрия: 1 (+ ПолипЭндометрия_мм); Эндометрий_неоднородный НЕ заменяет полип
  «косвенные признаки спаечного процесса в малом тазу» → спаечный_процесс_малого_таза: 1
  «желудок заполнен содержимым — гастростаз?» → гастростаз: 1
  «двусторонние фолликулярные кисты» / «фолликулярные кисты с двух сторон»
    → киста_яичника_R: 1 и киста_яичника_L: 1 (оба!)
  «несоответствие толщины эндометрия дню цикла» → Эндометрий_не_соответствует_дню_МЦ: 1
  «неправильной формы за счет фиксированного загиба» → ЖелчныйПузырь_перегиб: 1
    (+ ЖелчныйПузырь_деформирован: 1)
  «диффузные изменения … поджелудочной (по типу жировой инфильтрации)»
    → стеатоз_поджелудочной: 1 (+ диффузные_изменения_поджелудочной: 1)
  «гиперпневматоз кишечника» → повышенное_газообразование: 1
  «дивертикулы сигмовидной кишки» / «мешкообразные выпячивания» → дивертикулез_сигмовидной: 1
  «хронический холецистит (вне обострения)» → холецистит_хронический: 1
  Вены НК: СФС ≠ СПС. «сафено-подколенное/поплитеальное соустье несостоятельно»
    → СПС_несостоятельность: 1 (НЕ СФС_состоятельность).
  «стволовые клапаны МПВ несостоятельные» → МПВ_клапанная_недостаточность: 1
  «несостоятельность ствола БПВ» → БПВ_клапанная_недостаточность: 1
  «варикозная деформация притоков» → варикозная_деформация_притоков: 1
  *_состоятельность:1 только если соустье/клапаны ЯВНО состоятельны (норма).
  «умеренными фиброзными изменениями» (МЖ) → МЖ_фиброз: 1
  «диффузных изменений … по типу хронического простатита» → хронический_простатит: 1
  «инволютивные изменения семенных пузырьков» → СеменныеПузырьки_инволюция: 1
  «признаки увеличения и диффузных изменений ЩЖ … (признаки диффузного зоба)»
    → Щитовидная_увеличена: 1 (+ диффузные_изменения_щитовидной)
- Если смысл однозначно подходит к ключу каталога — ставь его, даже когда точной
  фразы из hint в тексте нет. Не откладывай такую находку в junk.
- ЗАКЛЮЧЕНИЕ / «УЗ-признаки …» / «Комментарий:» — главный источник binary. Не пропускай!
- «диффузные изменения миометрия» без слова «аденомиоз» → Миометрий_диффузно_неоднородный
  (аденомиоз:1 только если аденомиоз/внутренний эндометриоз ЯВНО назван).
- binary: 1 только при явном ПОДТВЕРЖДЁННОМ отклонении/находке. Норма → не включай.
- Если врач пишет находку с «?» («гастростаз?», «фолликулярная киста?») в описании/
  комментарии — это ВСЁ РАВНО находка → ставь binary. «?» = клиническая неуверенность,
  не отрицание и не «отсутствует».
- «Нельзя исключить X» / «не исключается X» → тоже ставь binary для X
  (пример: «нельзя исключить холецистит» → холецистит_хронический: 1).
- numeric: ВСЕ явные измерения (в т.ч. из компактных строк ЩЖ/ЖП/ПЖ/МЖ) → ключи каталога.
- Не выдумывай ключи вне каталога. Не возвращай hint-строки как ключи tokens.

=== ОТРИЦАНИЕ / ОТСУТСТВИЕ (КРИТИЧНО) ===
Сам распознай, что находка ОТРИЦАЕТСЯ или ОТСУТСТВУЕТ — формулировки любые,
не список шаблонов. Смотри смысл строки/ячейки целиком (заголовок + значение).
Если признак отрицается / не найден / не визуализируется / отсутствует / «без …» /
«данных за … нет» / норма / не расширен (когда речь о патологии) и т.п. —
НЕ ставь соответствующий binary в tokens (ключ отсутствует, не 0).
Типичная ловушка таблиц: «Свободная жидкость за маткой | Не визуализируется»
  → это ОТСУТСТВИЕ, НЕ свободная_жидкость_за_маткой:1.
То же для «кисты не выявлены», «конкрементов нет», «узлы не определяются» и любых
других способов сказать «нет». В tokens только то, что реально ЕСТЬ.

Правила рекомендаций:
- Направление к специалисту → отдельный binary-токен из каталога:
  рекомендация_гинеколога / _маммолога / _гастроэнтеролога / _уролога /
  _эндокринолога / _хирурга / _невролога / _сосудистого_хирурга.
  Пример: «рекомендуется консультация маммолога» → рекомендация_маммолога: 1
  Несколько врачей в одной фразе → несколько токенов.
- Общий дисклеймер («рекомендуется консультация специалиста», «не является диагнозом») → junk, без токена.

Правила junk:
- Только админ-шум: «Карта №…», ФИО, даты, клиника, аппарат, врач, дисклеймеры без конкретной рекомендации.
- НЕ клади в junk размеры/объёмы/D/S/V/перешеек/узлы/аббревиатуры органов/чёткие Рекомендовано: — это tokens.

Ответ — только JSON.
"""


SYSTEM_PROMPT = _build_system_prompt()


class PatientTokens(BaseModel):
    age_years: float | int | None = None
    height_cm: float | int | None = None
    weight_kg: float | int | None = None
    sex: str | None = None

    @field_validator("sex", mode="before")
    @classmethod
    def norm_sex(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        s = str(v).strip().lower().replace("ё", "е")
        if s in {"м", "муж", "мужской", "male", "m", "man"}:
            return "м"
        if s in {"ж", "жен", "женский", "female", "f", "woman"}:
            return "ж"
        return None

    @field_validator("age_years", "height_cm", "weight_kg", mode="before")
    @classmethod
    def num_or_none(cls, v: Any) -> float | int | None:
        if v is None or v == "":
            return None
        if isinstance(v, bool):
            return None
        if isinstance(v, (int, float)):
            return v
        try:
            s = str(v).strip().replace(",", ".")
            s = re.sub(r"[^\d.]+", "", s)
            if not s:
                return None
            num = float(s)
            return int(num) if num.is_integer() else num
        except (TypeError, ValueError):
            return None


class ProtocolTokenOut(BaseModel):
    patient: PatientTokens = Field(default_factory=PatientTokens)
    tokens: dict[str, Any] = Field(default_factory=dict)
    junk: list[str] = Field(default_factory=list)
    model: str | None = None
    source: str = "llm"


class ProtocolTokenError(Exception):
    pass


def _message_text(message: Any) -> str:
    """Текст ответа; для reasoning-моделей берём поле, где есть JSON-объект."""
    if message is None:
        return ""
    chunks: list[str] = []
    for attr in ("content", "reasoning", "reasoning_content"):
        val = getattr(message, attr, None)
        if isinstance(val, str) and val.strip():
            chunks.append(val)
    if not chunks:
        return ""
    for chunk in chunks:
        if "{" in chunk:
            return chunk
    return chunks[0]


def _extract_json_blob(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    if text.startswith("{"):
        return text
    match = re.search(r"\{[\s\S]*\}", text)
    return match.group(0) if match else ""


def _is_nonzero(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0 and not (isinstance(value, float) and value != value)
    if isinstance(value, str):
        t = value.strip()
        if not t or t in {"0", "false", "null", "None"}:
            return False
        return True
    return True


def _norm_alias_key(s: str) -> str:
    s = (s or "").strip().lower().replace("ё", "е")
    s = s.replace("-", "_").replace(" ", "_").replace("/", "_")
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def _alias_index(catalog: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Map canonical + alias keys (normalized) → canonical token name."""
    idx: dict[str, str] = {}
    for name, meta in catalog.items():
        idx[_norm_alias_key(name)] = name
        idx[name.lower()] = name
        for a in meta.get("aliases") or []:
            raw = str(a)
            idx[raw.lower()] = name
            idx[_norm_alias_key(raw)] = name
    return idx


@lru_cache(maxsize=4096)
def _phrase_to_flex_re(phrase: str) -> re.Pattern[str] | None:
    """Alias/name → regex tolerant to Russian case endings and separators."""
    p = (phrase or "").strip().lower().replace("ё", "е")
    p = p.replace("_", " ").replace("-", " ").replace("/", " ")
    p = re.sub(r"[:=]+$", "", p).strip()
    p = re.sub(r"\s+", " ", p)
    if len(p) < 4:
        return None
    # skip ultra-short / punctuation-only aliases like «D:», «V=»
    if re.fullmatch(r"[a-z]{1,2}\s*[:=]?", p):
        return None
    words = [w for w in p.split(" ") if w]
    if not words:
        return None
    parts: list[str] = []
    for w in words:
        if len(w) <= 5:
            # short aliases: whole-word only (avoid аденома ⊂ аденомиоз)
            parts.append(r"(?<![\w])" + re.escape(w) + r"(?![\w])")
        else:
            stem = w[:-2] if len(w) >= 8 else w[: max(5, len(w) - 2)]
            parts.append(r"(?<![\w])" + re.escape(stem) + r"\w{0,4}(?![\w])")
    return re.compile(r"(?i)" + r"[\s_\-/]+".join(parts))


_NEGATION_RE = re.compile(
    r"("
    r"не\s+выявл|не\s+определ|не\s+лоцир|не\s+визуализ|не\s+обнаруж|"
    r"не\s+найден|не\s+отмеча|не\s+видн|отрицает|"
    r"без\s+признак|отсутству|нет\s|не\s+содержит|"
    r"не\s+визуализир"  # «Не визуализируется» в таблице
    r")",
    flags=re.I,
)


def _window_negated(text: str, start: int, end: int, radius: int = 45) -> bool:
    """True if mention is negated nearby (incl. same table row: «признак\\tНе …»)."""
    n = len(text or "")
    if not n or start >= n:
        return False
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = n
    # Вся строка (ячейка значения после таба) + небольшой контекст слева/справа.
    left = max(0, min(line_start, start - radius))
    right = min(n, max(line_end, end + radius))
    window = text[left:right]
    return bool(_NEGATION_RE.search(window))


def _phrase_stems(phrase: str) -> tuple[str, ...]:
    p = (phrase or "").strip().lower().replace("ё", "е")
    p = p.replace("_", " ").replace("-", " ").replace("/", " ")
    p = re.sub(r"[:=]+$", "", p).strip()
    stems = []
    for w in p.split():
        if len(w) < 4:
            continue
        stems.append(w[:5] if len(w) >= 5 else w)
    return tuple(stems[:3])


@lru_cache(maxsize=2)
def _binary_alias_specs(
    path_str: str, mtime: float
) -> tuple[tuple[str, re.Pattern[str], tuple[str, ...]], ...]:
    """Precompiled (canonical, pattern, cheap_stems) for binary aliases, longest first."""
    catalog = _load_token_catalog_at(path_str, mtime)
    specs: list[tuple[int, str, re.Pattern[str], tuple[str, ...]]] = []
    for name, meta in catalog.items():
        if (meta.get("type") or "binary") != "binary":
            continue
        phrases = [name, *list(meta.get("aliases") or [])]
        for ph in phrases:
            pat = _phrase_to_flex_re(str(ph))
            if pat is None:
                continue
            stems = _phrase_stems(str(ph))
            if not stems:
                continue
            specs.append((len(str(ph)), name, pat, stems))
    specs.sort(key=lambda x: x[0], reverse=True)
    return tuple((name, pat, stems) for _, name, pat, stems in specs)


def _match_binaries_by_aliases(text: str, catalog: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Find binary tokens by scanning protocol text for catalog names/aliases."""
    del catalog  # specs come from cached catalog load
    out: dict[str, Any] = {}
    t = text or ""
    t_low = t.lower().replace("ё", "е")
    path = _catalog_path()
    specs = _binary_alias_specs(str(path), path.stat().st_mtime)
    for name, pat, stems in specs:
        if name in out:
            continue
        # cheap reject before regex
        if any(s not in t_low for s in stems):
            continue
        m = pat.search(t)
        if not m:
            continue
        if _window_negated(t, m.start(), m.end()):
            pos = m.end()
            found = False
            while True:
                m2 = pat.search(t, pos)
                if not m2:
                    break
                if not _window_negated(t, m2.start(), m2.end()):
                    found = True
                    break
                pos = m2.end()
            if not found:
                continue
        out[name] = 1
    return out


def filter_clinical_tokens(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only catalog keys with non-zero values; resolve aliases."""
    catalog = load_token_catalog()
    aliases = _alias_index(catalog)
    out: dict[str, Any] = {}
    if not isinstance(raw, dict):
        return out
    for key, val in raw.items():
        if not _is_nonzero(val):
            continue
        key_s = str(key)
        canon = aliases.get(key_s.lower()) or aliases.get(_norm_alias_key(key_s))
        if not canon:
            continue
        meta = catalog[canon]
        t = meta.get("type") or "binary"
        if t == "binary":
            out[canon] = 1
        elif t == "categorical":
            out[canon] = val
        else:
            # numeric-like
            if isinstance(val, (int, float)):
                out[canon] = val
            else:
                try:
                    s = str(val).strip().replace(",", ".")
                    # keep pair/triplet strings
                    if "x" in s.lower() or "х" in s.lower() or "*" in s:
                        out[canon] = str(val).strip()
                    else:
                        num = float(re.sub(r"[^\d.\-]+", "", s) or "nan")
                        if num != num:
                            continue
                        out[canon] = int(num) if float(num).is_integer() else num
                except (TypeError, ValueError):
                    out[canon] = str(val).strip()
    return out


def _binary_has_positive_mention(text: str, name: str) -> bool | None:
    """True = неотрицательное упоминание; False = только под отрицанием; None = нет в тексте."""
    path = _catalog_path()
    specs = _binary_alias_specs(str(path), path.stat().st_mtime)
    any_hit = False
    for tok, pat, _stems in specs:
        if tok != name:
            continue
        for m in pat.finditer(text or ""):
            any_hit = True
            if not _window_negated(text, m.start(), m.end()):
                return True
    if any_hit:
        return False
    return None


def strip_negated_binary_tokens(text: str, tokens: dict[str, Any]) -> dict[str, Any]:
    """Убрать binary=1, если в тексте упоминание только с отрицанием («Не визуализируется»)."""
    if not tokens:
        return tokens
    catalog = load_token_catalog()
    out = dict(tokens)
    for key in list(out):
        meta = catalog.get(key) or {}
        if (meta.get("type") or "binary") != "binary":
            continue
        if not _is_nonzero(out.get(key)):
            continue
        if _binary_has_positive_mention(text, key) is False:
            out.pop(key, None)
    return out


# Размер очага → бинарный флаг «есть находка» (LLM иногда ставит только *_мм).
_SIZE_IMPLIES_BINARY: dict[str, str] = {
    "КистаШейки_max_мм": "киста_шейки_матки",
    "КистаЯичника_R_мм": "киста_яичника_R",
    "КистаЯичника_L_мм": "киста_яичника_L",
    "ПолипЭндометрия_мм": "полип_эндометрия",
    "ПолипШейки_мм": "полип_шейки_матки",
    "ПолипЖП_мм": "полип_желчного_пузыря",
    "КистаМЖ_max_мм": "киста_молочной_железы",
    "КистаМЖ_R_мм": "киста_молочной_железы",
    "КистаМЖ_L_мм": "киста_молочной_железы",
    "УзелЩЖ_R_мм": "узел_щитовидной_R",
    "УзелЩЖ_L_мм": "узел_щитовидной_L",
    "МиоматозныйУзел_max_мм": "миома_матки",
    "КистаПростаты_мм": "киста_простаты",
}

# Подтип → родительский binary.
_SUBTYPE_IMPLIES_BINARY: dict[str, str] = {
    "дискинезия_ЖП_гипомоторная": "дискинезия_желчного_пузыря",
    "дискинезия_ЖП_гипермоторная": "дискинезия_желчного_пузыря",
}

# Любой ненулевой % стеноза артерии → стенозирующий атеросклероз.
_STENOSIS_PCT_IMPLIES = "стенозирующий_атеросклероз"


def ensure_binaries_from_lesion_sizes(tokens: dict[str, Any]) -> dict[str, Any]:
    """Размер очага / подтип / % стеноза → родительский binary из каталога."""
    if not tokens:
        return tokens
    catalog = load_token_catalog()
    out = dict(tokens)
    for size_key, bin_key in _SIZE_IMPLIES_BINARY.items():
        if bin_key not in catalog:
            continue
        if not _is_nonzero(out.get(size_key)):
            continue
        if not _is_nonzero(out.get(bin_key)):
            out[bin_key] = 1
    for sub_key, bin_key in _SUBTYPE_IMPLIES_BINARY.items():
        if bin_key not in catalog:
            continue
        if not _is_nonzero(out.get(sub_key)):
            continue
        if not _is_nonzero(out.get(bin_key)):
            out[bin_key] = 1
    if _STENOSIS_PCT_IMPLIES in catalog and not _is_nonzero(out.get(_STENOSIS_PCT_IMPLIES)):
        for k, v in out.items():
            if "стеноз_pct" in k and _is_nonzero(v):
                out[_STENOSIS_PCT_IMPLIES] = 1
                break
    return out


def _round_mm(v: float) -> float | int:
    v = round(v, 2)
    return int(v) if float(v).is_integer() else v


def _to_mm_triplet(a: str, b: str, c: str, unit: str | None) -> str:
    vals = [float(x.replace(",", ".")) for x in (a, b, c)]
    u = (unit or "").lower()
    if u.startswith("см") or u == "cm":
        vals = [v * 10 for v in vals]
    vals = [_round_mm(v) for v in vals]

    def fmt(v: float | int) -> str:
        return str(int(v)) if float(v).is_integer() else str(v)

    return f"{fmt(vals[0])}x{fmt(vals[1])}x{fmt(vals[2])}"


def _parse_thyroid_compact(text: str, catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Parse shorthand like D:/S:/V= for thyroid lobes."""
    out: dict[str, Any] = {}
    t = text or ""

    m = re.search(
        r"(?i)(?:\bV\s*=|(?:общ(?:ий)?|суммарн\w*)\s+объ[её]м(?:\s+железы|\s+долей|\s+ЩЖ)?\s*[:=]?)\s*"
        r"(\d+(?:[.,]\d+)?)\s*(?:см\s*(?:куб|3|³)|см3|см³|куб\.?\s*см)?",
        t,
    )
    if m and "объем_щитовидной_см3" in catalog:
        out["объем_щитовидной_см3"] = float(m.group(1).replace(",", "."))

    trip = (
        r"(\d+(?:[.,]\d+)?)\s*[xх×\*]\s*"
        r"(\d+(?:[.,]\d+)?)\s*[xх×\*]\s*"
        r"(\d+(?:[.,]\d+)?)\s*(см|mm|мм)?"
    )
    # D:/S:/dexter/sinister/пр.доля/лев.доля — размеры долей
    m = re.search(
        rf"(?i)(?:\bD\s*[:=]|(?:dex(?:ter)?|пр\.?\s*дол[яи]|правая\s+доля)\s*[:=]?)\s*{trip}",
        t,
    )
    if m and "ДоляПравая_размеры_мм" in catalog:
        out["ДоляПравая_размеры_мм"] = _to_mm_triplet(m.group(1), m.group(2), m.group(3), m.group(4))

    m = re.search(
        rf"(?i)(?:\bS\s*[:=]|(?:sin(?:ister)?|л\.?\s*дол[яи]|левая\s+доля)\s*[:=]?)\s*{trip}",
        t,
    )
    if m and "ДоляЛевая_размеры_мм" in catalog:
        out["ДоляЛевая_размеры_мм"] = _to_mm_triplet(m.group(1), m.group(2), m.group(3), m.group(4))

    m = re.search(r"(?i)перешеек\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(мм|mm|см|cm)?", t)
    if m and "Перешеек_толщина_мм" in catalog:
        val = float(m.group(1).replace(",", "."))
        unit = (m.group(2) or "мм").lower()
        if unit.startswith("см") or unit == "cm":
            val *= 10
        out["Перешеек_толщина_мм"] = int(val) if float(val).is_integer() else val

    # Node shorthand: «S3 D 1.1x1.14x1.0 см» / «узел D …» (не путать с «D:» доли)
    m_node_r = re.search(
        rf"(?i)(?:узел\s+|S\d+\s+)D(?!\s*:)\s*{trip}",
        t,
    )
    m_node_l = re.search(
        rf"(?i)(?:узел\s+)S(?!\s*:)\s*{trip}",
        t,
    )
    if m_node_r and "УзелЩЖ_R_мм" in catalog:
        trip_mm = _to_mm_triplet(
            m_node_r.group(1), m_node_r.group(2), m_node_r.group(3), m_node_r.group(4)
        )
        nums = [float(x) for x in trip_mm.split("x")]
        mx = _round_mm(max(nums))
        if "узел_щитовидной_R" in catalog:
            out["узел_щитовидной_R"] = 1
        out["УзелЩЖ_R_мм"] = mx
        if "УзелЩЖ_max_мм" in catalog:
            out["УзелЩЖ_max_мм"] = mx
    if m_node_l and "УзелЩЖ_L_мм" in catalog:
        trip_mm = _to_mm_triplet(
            m_node_l.group(1), m_node_l.group(2), m_node_l.group(3), m_node_l.group(4)
        )
        nums = [float(x) for x in trip_mm.split("x")]
        mx = _round_mm(max(nums))
        if "узел_щитовидной_L" in catalog:
            out["узел_щитовидной_L"] = 1
        out["УзелЩЖ_L_мм"] = mx
        if "УзелЩЖ_max_мм" in catalog:
            out["УзелЩЖ_max_мм"] = _round_mm(max(out.get("УзелЩЖ_max_мм") or 0, mx))

    return {k: v for k, v in out.items() if k in catalog}


def _heuristic_fallback(text: str) -> ProtocolTokenOut:
    patient = PatientTokens()
    tokens: dict[str, Any] = {}
    junk: list[str] = []
    t = text or ""

    m = re.search(r"(?i)возраст[^\d]{0,20}(\d{1,3})\s*(лет|г\.?|года|год)?", t)
    if not m:
        m = re.search(r"(?i)(\d{1,3})\s*лет", t)
    if m:
        patient.age_years = int(m.group(1))
    if patient.age_years is None:
        # «Дата рождения: 10 августа 1977 г.»
        m = re.search(
            r"(?i)дат[аы]\s*рожден\w*[^\d]{0,12}(\d{1,2})[./\s]+(?:января|февраля|марта|апреля|"
            r"мая|июня|июля|августа|сентября|октября|ноября|декабря|[01]?\d)[./\s]+(\d{4})",
            t,
        )
        if not m:
            m = re.search(
                r"(?i)дат[аы]\s*рожден\w*[^\d]{0,12}(\d{1,2})[./](\d{1,2})[./](\d{4})",
                t,
            )
            if m:
                year = int(m.group(3))
                if 1920 <= year <= 2026:
                    patient.age_years = 2026 - year
        elif m:
            year = int(m.group(2))
            if 1920 <= year <= 2026:
                patient.age_years = 2026 - year

    m = re.search(r"(?i)рост[^\d]{0,12}(\d{2,3}(?:[.,]\d+)?)\s*см?", t)
    if m:
        patient.height_cm = float(m.group(1).replace(",", "."))

    m = re.search(r"(?i)вес[^\d]{0,12}(\d{2,3}(?:[.,]\d+)?)\s*кг?", t)
    if m:
        patient.weight_kg = float(m.group(1).replace(",", "."))

    if re.search(r"(?i)\bженщин|\bженск|\bпол\s*[:\-]?\s*ж\b", t):
        patient.sex = "ж"
    elif re.search(r"(?i)\bмужчин|\bмужск|\bпол\s*[:\-]?\s*м\b", t):
        patient.sex = "м"

    # Lightweight clinical cues (only if catalog has the key)
    catalog = load_token_catalog()
    # Alias/name scan (handles «дугласовом пространстве» via flex endings)
    tokens.update(_match_binaries_by_aliases(t))

    cues = [
        (r"(?i)гепатомегал", "Печень_увеличена"),
        (r"(?i)жиров(ой|ая)\s+гепатоз|стеатоз\s+печени", "стеатоз_печени"),
        (r"(?i)конкремент|холецистолитиаз|холелитиаз|\bЖКБ\b", "конкременты_желчного_пузыря"),
        (r"(?i)полип[аы]?\s+желч|полип[аы]?\s+ЖП", "полип_желчного_пузыря"),
        (r"(?i)билиарн\w*\s+сладж|эховзвесь", "билиарный_сладж"),
        # Дуглас / за маткой / малый таз — НЕ брюшная полость
        (
            r"(?i)дуглас|жидкост\w*.{0,25}(за\s+матк|в\s+малом\s+таз)|\bДП\b.{0,15}жидкост|жидкост\w*.{0,15}\bДП\b",
            "свободная_жидкость_за_маткой",
        ),
        (
            r"(?i)свободн\w+\s+жидкост(?!.{0,40}(дуглас|за\s+матк|мал\w*\s+таз))|асцит",
            "свободная_жидкость_брюшной_полости",
        ),
        (r"(?i)дискинез", "дискинезия_желчного_пузыря"),
        (r"(?i)гипомоторн", "дискинезия_ЖП_гипомоторная"),
        (r"(?i)гипермоторн", "дискинезия_ЖП_гипермоторная"),
        (r"(?i)гастростаз", "гастростаз"),
        (r"(?i)сокращен|сокращение\s+жп", "ЖелчныйПузырь_сокращен"),
        (
            r"(?i)сохран(яется|илось)\s+сокращен|сокращен\w*\s+жп.{0,40}после\s+(приема\s+)?пищ|после\s+(приема\s+)?пищ.{0,40}сокращен",
            "ЖелчныйПузырь_постпрандиальное_сокращение_сохраняется",
        ),
        (r"(?i)деформац\w+\s+желч|форма\s+изменена", "ЖелчныйПузырь_деформирован"),
        (r"(?i)миом", "миома_матки"),
        (r"(?i)аденомиоз", "аденомиоз"),
        (r"(?i)мастопат|\bФКМ\b", "мастопатия"),
        (r"(?i)фиброаденом", "фиброаденома"),
        (r"(?i)узлов\w+\s+зоб", "узловой_зоб"),
        (r"(?i)ДГПЖ|гиперплази\w+\s+простат", "гиперплазия_простаты"),
    ]
    rec = extract_recommendation(t)
    for k, v in (rec.get("tokens") or {}).items():
        if k in catalog and _is_nonzero(v):
            tokens[k] = 1

    for pat, key in cues:
        if key not in catalog:
            continue
        matches = list(re.finditer(pat, t))
        if not matches:
            continue
        positive = False
        for m in matches:
            if _window_negated(t, m.start(), m.end()):
                continue
            positive = True
            break
        if positive:
            tokens[key] = 1

    # Common measurements
    m = re.search(r"(?i)КВР[^\d]{0,12}(\d{2,3}(?:[.,]\d+)?)\s*мм", t)
    if m and "Печень_ПраваяДоля_КВР_мм" in catalog:
        tokens["Печень_ПраваяДоля_КВР_мм"] = float(m.group(1).replace(",", "."))

    # Compact thyroid: «ЩЖ: V=16.9 см3, D: 6.2x1.5x1.9 см S: 6.4x1.7x1.5 см, перешеек 5 мм»
    tokens.update(_parse_thyroid_compact(t, catalog))

    for line in t.splitlines():
        line = line.strip()
        if not line:
            continue
        low = line.lower().replace("ё", "е")
        if re.search(r"(?i)рекомендован\w*|рекомендации\s*:", line):
            if not DISCLAIMER_REC.search(line) or (rec.get("tokens")):
                continue  # named referral kept as token, not junk
        if any(k in low for k in ("карта", "фио", "врач:", "не являются диагнозом")):
            junk.append(line[:200])
            continue
        if "рекоменд" in low and DISCLAIMER_REC.search(line) and not (rec.get("tokens")):
            junk.append(line[:200])

    cleaned = ensure_binaries_from_lesion_sizes(
        strip_negated_binary_tokens(t, filter_clinical_tokens(tokens))
    )
    return ProtocolTokenOut(
        patient=patient,
        tokens=cleaned,
        junk=junk[:40],
        source="heuristic",
    )


def enrich_tokenize_result(text: str, out: ProtocolTokenOut) -> dict[str, Any]:
    """Attach recommendation, by_organ, pathology, patient_alert to a tokenize result."""
    from .organ_groups import group_tokens_by_organ
    from .pathology import evaluate_pathology
    from .patient_alerts import build_patient_alert

    clinical = dict(out.tokens or {})
    rec = extract_recommendation(text)
    for k, v in (rec.get("tokens") or {}).items():
        if _is_nonzero(v):
            clinical[k] = 1
    # LLM may have set specialist tokens already
    rec_names = recommendation_token_names()
    llm_specs = [k for k in clinical if k in rec_names and _is_nonzero(clinical[k])]
    if llm_specs and not rec.get("present"):
        rec = {
            "present": True,
            "text": rec.get("text"),
            "specialists": labels_for_tokens(llm_specs),
            "tokens": {k: 1 for k in llm_specs},
        }
    elif llm_specs and rec.get("present"):
        # merge LLM + heuristic specialists
        merged = list(rec.get("specialists") or [])
        for lab in labels_for_tokens(llm_specs):
            if lab not in merged:
                merged.append(lab)
        rec["specialists"] = merged
        tok = dict(rec.get("tokens") or {})
        for k in llm_specs:
            tok[k] = 1
        rec["tokens"] = tok
    clinical = filter_clinical_tokens(clinical)

    patient_d = out.patient.model_dump() if out.patient else {}
    pathology = evaluate_pathology(clinical, patient_d)
    by_organ = group_tokens_by_organ(
        clinical,
        recommendation=rec,
        catalog=load_token_catalog(),
    )
    patient_alert = build_patient_alert(
        clinical,
        text=text,
        recommendation=rec,
        patient=patient_d,
    )
    return {
        "clinical": clinical,
        "recommendation": rec,
        "by_organ": by_organ,
        "organs_present": [x["label"] for x in by_organ],
        "pathology": pathology,
        "patient_alert": patient_alert,
    }


def tokenize_protocol_text(raw_text: str, *, filename: str | None = None) -> ProtocolTokenOut:
    text = (raw_text or "").strip()
    if not text:
        raise ProtocolTokenError("Empty text")

    from ..llm_client import chat_completion_kwargs, llm_configured, make_openai_client
    from ..llm_retry import _is_transient, with_retries

    # Always compute heuristic first — used as merge base and instant fallback.
    heuristic = _heuristic_fallback(text)

    if not llm_configured():
        return heuristic

    # Skip LLM when explicitly disabled (local/dev speed).
    if os.getenv("TOKENIZE_LLM", "1").strip().lower() in {"0", "false", "no", "off"}:
        return heuristic

    tok_timeout = float(os.getenv("TOKENIZE_TIMEOUT_SEC", os.getenv("LLM_TIMEOUT_SEC", "120")))
    # gpt-oss тратит бюджет на reasoning; 4k часто заканчивается finish_reason=length
    # с пустым content → нужен запас.
    tok_max_tokens = int(os.getenv("TOKENIZE_MAX_TOKENS", os.getenv("STRUCTURE_MAX_TOKENS", "16384")))
    tok_attempts = max(1, int(os.getenv("TOKENIZE_RETRY_ATTEMPTS", "3")))

    try:
        # max_retries=0: OpenAI SDK otherwise retries timeouts and multiplies wait.
        client, model = make_openai_client(timeout=tok_timeout, max_retries=0)
    except Exception:
        return heuristic

    # В промпт — только токены, у которых слово/alias пересеклось с текстом.
    catalog_block = catalog_prompt_block(text=text)
    user_blob = text
    if filename:
        user_blob = f"Файл: {filename}\n\n{user_blob}"
    max_chars = int(os.getenv("STRUCTURE_MAX_CHARS", "12000"))
    if len(user_blob) > max_chars:
        user_blob = user_blob[:max_chars] + "\n\n[... truncated ...]"

    kwargs: dict[str, Any] = chat_completion_kwargs(
        max_tokens=tok_max_tokens,
        model=model,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    SYSTEM_PROMPT
                    + "\n\nКАТАЛОГ ТОКЕНОВ (canonical:type[:unit]  | hint: aliases…):\n"
                    + "Используй hint только для сопоставления с текстом протокола; в JSON — только canonical.\n"
                    + catalog_block
                ),
            },
            {
                "role": "user",
                "content": f"Извлеки patient + tokens + junk из протокола:\n\n{user_blob}",
            },
        ],
    )

    def _once() -> ProtocolTokenOut:
        # One shot only — retrying after timeout doubles hang time.
        try:
            completion = client.chat.completions.create(
                **kwargs,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            msg = str(exc).lower()
            if "timeout" in msg or "timed out" in msg:
                raise
            # Some gateways reject response_format — single fallback, same timeout.
            completion = client.chat.completions.create(**kwargs)

        choices = getattr(completion, "choices", None) or []
        if not choices:
            raise ProtocolTokenError("empty choices")
        choice0 = choices[0]
        message = choice0.message
        raw_content = getattr(message, "content", None)
        finish = getattr(choice0, "finish_reason", None)
        # Reasoning-модель съела весь max_completion_tokens — JSON в content нет.
        if finish == "length" and not (isinstance(raw_content, str) and raw_content.strip()):
            raise ProtocolTokenError(
                "truncated reasoning (finish_reason=length, empty content)"
            )
        content = _extract_json_blob(_message_text(message))
        if not content:
            raise ProtocolTokenError("empty content")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProtocolTokenError(f"invalid json: {exc}") from exc
        if not isinstance(payload, dict):
            raise ProtocolTokenError("expected object")

        patient_raw = payload.get("patient")
        if not isinstance(patient_raw, dict):
            patient_raw = {
                "age_years": payload.get("age_years", payload.get("age")),
                "height_cm": payload.get("height_cm", payload.get("height")),
                "weight_kg": payload.get("weight_kg", payload.get("weight")),
                "sex": payload.get("sex"),
            }

        tokens_raw = payload.get("tokens")
        if not isinstance(tokens_raw, dict):
            tokens_raw = {}

        junk = payload.get("junk") or []
        if isinstance(junk, dict):
            flat: list[str] = []
            for v in junk.values():
                if isinstance(v, list):
                    flat.extend(str(x) for x in v if x)
                elif v:
                    flat.append(str(v))
            junk = flat
        if not isinstance(junk, list):
            junk = [str(junk)]

        clinical = filter_clinical_tokens(tokens_raw)
        catalog = load_token_catalog()
        # LLM сам решает negation/отсутствие. Heuristic binary НЕ дописываем:
        # иначе «Свободная жидкость… | Не визуализируется» снова станет 1 по заголовку.
        for k, v in heuristic.tokens.items():
            if k in clinical or not _is_nonzero(v):
                continue
            meta = catalog.get(k) or {}
            if (meta.get("type") or "binary") == "binary":
                continue
            clinical[k] = v

        patient = PatientTokens.model_validate(patient_raw)
        # Fill gaps from heuristic patient
        hp = heuristic.patient
        if patient.age_years is None:
            patient.age_years = hp.age_years
        if patient.height_cm is None:
            patient.height_cm = hp.height_cm
        if patient.weight_kg is None:
            patient.weight_kg = hp.weight_kg
        if patient.sex is None:
            patient.sex = hp.sex

        return ProtocolTokenOut(
            patient=patient,
            tokens=ensure_binaries_from_lesion_sizes(filter_clinical_tokens(clinical)),
            junk=[str(x)[:300] for x in junk if x][:80],
            model=getattr(completion, "model", None) or model,
            source="llm",
        )

    try:
        return with_retries(
            _once,
            attempts=tok_attempts,
            label="protocol_tokenize",
            retry_if=lambda exc: _is_transient(exc)
            or isinstance(exc, ProtocolTokenError)
            or isinstance(exc, json.JSONDecodeError),
        )
    except Exception as exc:
        # Не глотаем причину молча — иначе в тестах «source=heuristic» без объяснения.
        import logging

        logging.getLogger(__name__).warning(
            "protocol_tokenize fallback to heuristic: %s: %s",
            type(exc).__name__,
            exc,
        )
        heuristic.model = model
        heuristic.source = "heuristic"
        return heuristic


def tokens_as_important(patient: PatientTokens, clinical: dict[str, Any]) -> dict[str, Any]:
    vitals: dict[str, str] = {}
    if patient.height_cm is not None:
        vitals["height_cm"] = str(patient.height_cm)
    if patient.weight_kg is not None:
        vitals["weight_kg"] = str(patient.weight_kg)
    # put numeric clinical into vitals-like labs for storage
    labs = []
    diagnoses = []
    for k, v in clinical.items():
        catalog = load_token_catalog()
        meta = catalog.get(k) or {}
        t = meta.get("type") or "binary"
        if t == "binary" and _is_nonzero(v):
            diagnoses.append(k)
        elif t.startswith("numeric") or t == "categorical":
            labs.append(
                {
                    "name": k,
                    "value": str(v),
                    "unit": meta.get("unit"),
                    "ref_range": None,
                }
            )
    age = None
    if patient.age_years is not None:
        age = (
            int(patient.age_years)
            if float(patient.age_years).is_integer()
            else patient.age_years
        )
    return {
        "patient_name": None,
        "age": age,
        "sex": patient.sex,
        "symptoms": [],
        "diagnoses": diagnoses,
        "labs": labs,
        "medications": [],
        "vitals": vitals,
        "red_flags": [],
        "clinical_snippets": [],
    }


def non_null_token_list(
    patient: PatientTokens | dict[str, Any],
    clinical: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Flatten patient + clinical non-zero tokens for UI."""
    data = patient.model_dump() if hasattr(patient, "model_dump") else dict(patient or {})
    out: list[dict[str, Any]] = []
    labels = {
        "age_years": "возраст_лет",
        "height_cm": "рост_см",
        "weight_kg": "вес_кг",
        "sex": "пол",
    }
    for key in PATIENT_KEYS:
        val = data.get(key)
        if not _is_nonzero(val) and val != 0:
            # allow age 0? no — skip nulls only
            if val is None or val == "":
                continue
        if val is None or val == "":
            continue
        out.append({"key": key, "value": val, "label": labels.get(key, key)})
    for k, v in (clinical or {}).items():
        if not _is_nonzero(v):
            continue
        out.append({"key": k, "value": v, "label": k})
    return out
