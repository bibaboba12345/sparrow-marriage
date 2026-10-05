"""Group clinical tokens by organ/structure from strict catalog."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _catalog_path() -> Path:
    import os

    env = os.getenv("STRICT_TOKENS_PATH")
    if env:
        return Path(env)
    return _repo_root() / "СМ-Клиника-протоколы" / "strict_tokens_candidates.json"


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


@lru_cache(maxsize=1)
def _flat_catalog_names() -> frozenset[str]:
    path = _catalog_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for mod in (data.get("modalities") or {}).values():
        if not isinstance(mod, dict):
            continue
        for bag in ("organ_tokens", "vessel_tokens", "tokens", "study_flags"):
            bagd = mod.get(bag) or {}
            if isinstance(bagd, dict):
                names.update(bagd.keys())
    for name in ((data.get("cross_cutting") or {}).get("tokens") or {}):
        names.add(name)
    return frozenset(names)


# Explicit snake_case / short names → organ
_EXPLICIT: dict[str, tuple[str, str, str]] = {
    # modality, organ, label
    "стеатоз_печени": ("us_abdomen_gb", "Печень", "Печень"),
    "диффузные_изменения_печени": ("us_abdomen_gb", "Печень", "Печень"),
    "гемангиома_печени": ("us_abdomen_gb", "Печень", "Печень"),
    "конкременты_желчного_пузыря": ("us_abdomen_gb", "ЖелчныйПузырь", "Желчный пузырь"),
    "конкременты_множественные": ("us_abdomen_gb", "ЖелчныйПузырь", "Желчный пузырь"),
    "полип_желчного_пузыря": ("us_abdomen_gb", "ЖелчныйПузырь", "Желчный пузырь"),
    "полипы_множественные_ЖП": ("us_abdomen_gb", "ЖелчныйПузырь", "Желчный пузырь"),
    "билиарный_сладж": ("us_abdomen_gb", "ЖелчныйПузырь", "Желчный пузырь"),
    "холестероз_желчного_пузыря": ("us_abdomen_gb", "ЖелчныйПузырь", "Желчный пузырь"),
    "холестаз": ("us_abdomen_gb", "ЖелчныйПузырь", "Желчный пузырь"),
    "холецистит_хронический": ("us_abdomen_gb", "ЖелчныйПузырь", "Желчный пузырь"),
    "холецистэктомия": ("us_abdomen_gb", "ЖелчныйПузырь", "Желчный пузырь"),
    "дискинезия_желчного_пузыря": ("us_abdomen_gb", "ЖелчныйПузырь", "Желчный пузырь"),
    "дискинезия_ЖП_гипомоторная": ("us_abdomen_gb", "ЖелчныйПузырь", "Желчный пузырь"),
    "дискинезия_ЖП_гипермоторная": ("us_abdomen_gb", "ЖелчныйПузырь", "Желчный пузырь"),
    "стеатоз_поджелудочной": ("us_abdomen_gb", "ПоджелудочнаяЖелеза", "Поджелудочная железа"),
    "диффузные_изменения_поджелудочной": ("us_abdomen_gb", "ПоджелудочнаяЖелеза", "Поджелудочная железа"),
    "свободная_жидкость_брюшной_полости": ("us_abdomen_gb", "СвободнаяЖидкость", "Свободная жидкость"),
    "лимфоузлы_брюшной_полости": ("us_abdomen_gb", "Лимфоузлы", "Лимфоузлы"),
    "коллатерали_портальные": ("us_abdomen_gb", "ВоротнаяВена", "Воротная вена"),
    "повышенное_газообразование": ("us_abdomen_gb", "Прочее", "Прочее (ОБП)"),
    "дивертикулез_сигмовидной": ("us_abdomen_gb", "Прочее", "Прочее (ОБП)"),
    "гастростаз": ("us_abdomen_gb", "Прочее", "Прочее (ОБП)"),
    "висцеральный_жир_выражен": ("us_abdomen_gb", "Прочее", "Прочее (ОБП)"),
    "миома_матки": ("us_pelvis_omt", "Миометрий", "Миометрий / миома"),
    "аденомиоз": ("us_pelvis_omt", "Миометрий", "Миометрий / миома"),
    "эндометриоз": ("us_pelvis_omt", "Миометрий", "Миометрий / миома"),
    "гиперплазия_эндометрия": ("us_pelvis_omt", "Эндометрий", "Эндометрий"),
    "полип_эндометрия": ("us_pelvis_omt", "Эндометрий", "Эндометрий"),
    "киста_шейки_матки": ("us_pelvis_omt", "ШейкаМатки", "Шейка матки"),
    "полип_шейки_матки": ("us_pelvis_omt", "ШейкаМатки", "Шейка матки"),
    "эндоцервицит_признаки": ("us_pelvis_omt", "Эндоцервикс", "Эндоцервикс"),
    "киста_яичника_R": ("us_pelvis_omt", "ЯичникПравый", "Яичник правый"),
    "киста_яичника_L": ("us_pelvis_omt", "ЯичникЛевый", "Яичник левый"),
    "параовариальная_киста_R": ("us_pelvis_omt", "ЯичникПравый", "Яичник правый"),
    "параовариальная_киста_L": ("us_pelvis_omt", "ЯичникЛевый", "Яичник левый"),
    "гидросальпинкс_R": ("us_pelvis_omt", "ТрубаПравая", "Труба правая"),
    "гидросальпинкс_L": ("us_pelvis_omt", "ТрубаЛевая", "Труба левая"),
    "снижение_овариального_резерва": ("us_pelvis_omt", "ЯичникПравый", "Яичники"),
    "мультифолликулярные_яичники": ("us_pelvis_omt", "ЯичникПравый", "Яичники"),
    "свободная_жидкость_за_маткой": ("us_pelvis_omt", "Матка", "Матка"),
    "серозометра": ("us_pelvis_omt", "Матка", "Матка"),
    "опущение_матки": ("us_pelvis_omt", "Матка", "Матка"),
    "дополнительные_образования_малого_таза": ("us_pelvis_omt", "Прочее", "Прочее (ОМТ)"),
    "спаечный_процесс_малого_таза": ("us_pelvis_omt", "Прочее", "Прочее (ОМТ)"),
    "мастопатия": ("us_breast", "МолочнаяЖелеза", "Молочная железа"),
    "диффузные_изменения_МЖ": ("us_breast", "МолочнаяЖелеза", "Молочная железа"),
    "фокальные_изменения_МЖ": ("us_breast", "МолочнаяЖелеза", "Молочная железа"),
    "жировая_инволюция_МЖ": ("us_breast", "МолочнаяЖелеза", "Молочная железа"),
    "киста_молочной_железы": ("us_breast", "Киста", "Кисты МЖ"),
    "фиброаденома": ("us_breast", "Фиброаденома", "Фиброаденома"),
    "фиброаденома_R": ("us_breast", "Фиброаденома", "Фиброаденома"),
    "фиброаденома_L": ("us_breast", "Фиброаденома", "Фиброаденома"),
    "мастит": ("us_breast", "МолочнаяЖелеза", "Молочная железа"),
    "импланты_МЖ": ("us_breast", "Имплант", "Имплант"),
    # мастопексия = подтяжка МЖ, не имплант
    "мастопексия": ("us_breast", "МолочнаяЖелеза", "Молочная железа"),
    "диффузные_изменения_щитовидной": ("us_thyroid", "ЩитовиднаяЖелеза", "Щитовидная железа"),
    "АИТ_признаки": ("us_thyroid", "ЩитовиднаяЖелеза", "Щитовидная железа"),
    "псевдоузлы_щитовидной": ("us_thyroid", "ЩитовиднаяЖелеза", "Щитовидная железа"),
    "узловой_зоб": ("us_thyroid", "Узел", "Узлы ЩЖ"),
    "узел_щитовидной": ("us_thyroid", "Узел", "Узлы ЩЖ"),
    "узел_щитовидной_R": ("us_thyroid", "Узел", "Узлы ЩЖ"),
    "узел_щитовидной_L": ("us_thyroid", "Узел", "Узлы ЩЖ"),
    "узел_перешейка": ("us_thyroid", "Перешеек", "Перешеек"),
    "узлы_множественные_щитовидной": ("us_thyroid", "Узел", "Узлы ЩЖ"),
    "киста_щитовидной": ("us_thyroid", "Киста", "Кисты ЩЖ"),
    "киста_щитовидной_R": ("us_thyroid", "Киста", "Кисты ЩЖ"),
    "киста_щитовидной_L": ("us_thyroid", "Киста", "Кисты ЩЖ"),
    "кальцинаты_щитовидной": ("us_thyroid", "Узел", "Узлы ЩЖ"),
    "микрокальцинаты_щитовидной": ("us_thyroid", "Узел", "Узлы ЩЖ"),
    "паращитовидные_образования": ("us_thyroid", "ПаращитовидныеЖелезы", "Паращитовидные железы"),
    "объем_щитовидной_см3": ("us_thyroid", "ЩитовиднаяЖелеза", "Щитовидная железа"),
    "линейная_гиперэхогенная_исчерченность": ("us_thyroid", "ЩитовиднаяЖелеза", "Щитовидная железа"),
    "расширенные_фолликулы": ("us_thyroid", "ЩитовиднаяЖелеза", "Щитовидная железа"),
    "гиперплазия_простаты": ("us_prostate_trusi", "ПредстательнаяЖелеза", "Предстательная железа"),
    "гиперплазия_переходных_зон": ("us_prostate_trusi", "ПереходнаяЗона", "Переходная зона"),
    "хронический_простатит": ("us_prostate_trusi", "ПредстательнаяЖелеза", "Предстательная железа"),
    "диффузные_изменения_простаты": ("us_prostate_trusi", "ПредстательнаяЖелеза", "Предстательная железа"),
    "узлы_простаты": ("us_prostate_trusi", "АденоматозныйУзел", "Аденоматозные узлы"),
    "киста_простаты": ("us_prostate_trusi", "Киста", "Кисты простаты"),
    "кисты_множественные_простаты": ("us_prostate_trusi", "Киста", "Кисты простаты"),
    "кальцинаты_простаты": ("us_prostate_trusi", "ПредстательнаяЖелеза", "Предстательная железа"),
    "микрокальцинаты_простаты": ("us_prostate_trusi", "ПредстательнаяЖелеза", "Предстательная железа"),
    "протоковая_система_расширена": ("us_prostate_trusi", "ПредстательнаяЖелеза", "Предстательная железа"),
    "нарушение_пассажа_мочи": ("us_prostate_trusi", "ПростатическаяУретра", "Простатическая уретра"),
    "остаточная_моча_повышена": ("us_prostate_trusi", "ОстаточнаяМоча", "Остаточная моча"),
    "объем_простаты_см3": ("us_prostate_trusi", "ПредстательнаяЖелеза", "Предстательная железа"),
    "варикозное_расширение_вен": ("duplex_lower_limb_veins", "ВеныНК", "Вены НК"),
    "варикозная_трансформация_БПВ": ("duplex_lower_limb_veins", "БПВ", "БПВ"),
    "СПС_несостоятельность": ("duplex_lower_limb_veins", "СПС", "СПС"),
    "МПВ_клапанная_недостаточность": ("duplex_lower_limb_veins", "МПВ", "МПВ"),
    "БПВ_клапанная_недостаточность": ("duplex_lower_limb_veins", "БПВ", "БПВ"),
    "варикозная_деформация_притоков": ("duplex_lower_limb_veins", "ВеныНК", "Вены НК"),
    "тромбоз_глубоких_вен": ("duplex_lower_limb_veins", "ГлубокиеВены", "Глубокие вены"),
    "тромбоз_поверхностных_вен": ("duplex_lower_limb_veins", "ПоверхностныеВены", "Поверхностные вены"),
    "клапанная_недостаточность": ("duplex_lower_limb_veins", "ВеныНК", "Вены НК"),
    "рефлюкс_клапанов": ("duplex_lower_limb_veins", "ВеныНК", "Вены НК"),
    "атеросклеротическая_бляшка": ("duplex_lower_limb_arteries", "АртерииНК", "Артерии НК"),
    "кальцинированная_АСБ": ("duplex_lower_limb_arteries", "АртерииНК", "Артерии НК"),
    "нестенозирующий_атеросклероз": ("duplex_lower_limb_arteries", "АртерииНК", "Артерии НК"),
    "стенозирующий_атеросклероз": ("duplex_lower_limb_arteries", "АртерииНК", "Артерии НК"),
    "гемодинамически_значимый_атеросклероз": ("duplex_lower_limb_arteries", "АртерииНК", "Артерии НК"),
    "кровоток_магистральный": ("duplex_lower_limb_arteries", "АртерииНК", "Артерии НК"),
    "кровоток_трехфазный": ("duplex_lower_limb_arteries", "АртерииНК", "Артерии НК"),
    "кровоток_магистральный_измененный": ("duplex_lower_limb_arteries", "АртерииНК", "Артерии НК"),
    "рекомендация_гинеколога": ("cross_cutting", "Рекомендация", "Рекомендация"),
    "рекомендация_маммолога": ("cross_cutting", "Рекомендация", "Рекомендация"),
    "рекомендация_гастроэнтеролога": ("cross_cutting", "Рекомендация", "Рекомендация"),
    "рекомендация_уролога": ("cross_cutting", "Рекомендация", "Рекомендация"),
    "рекомендация_эндокринолога": ("cross_cutting", "Рекомендация", "Рекомендация"),
    "рекомендация_хирурга": ("cross_cutting", "Рекомендация", "Рекомендация"),
    "рекомендация_невролога": ("cross_cutting", "Рекомендация", "Рекомендация"),
    "рекомендация_сосудистого_хирурга": ("cross_cutting", "Рекомендация", "Рекомендация"),
}

_PREFIX_ORGANS: list[tuple[str, str, str, str]] = [
    # prefix, modality, organ, label
    ("ЖелчныйПузырь_", "us_abdomen_gb", "ЖелчныйПузырь", "Желчный пузырь"),
    ("КонкрементЖП_", "us_abdomen_gb", "ЖелчныйПузырь", "Желчный пузырь"),
    ("ПолипЖП_", "us_abdomen_gb", "ЖелчныйПузырь", "Желчный пузырь"),
    ("Печень_", "us_abdomen_gb", "Печень", "Печень"),
    ("ВоротнаяВена_", "us_abdomen_gb", "ВоротнаяВена", "Воротная вена"),
    ("ПеченочныеВены_", "us_abdomen_gb", "ПеченочныеВены", "Печеночные вены"),
    ("НПВ_", "us_abdomen_gb", "НПВ", "НПВ"),
    ("Холедох_", "us_abdomen_gb", "Холедох", "Холедох"),
    ("ВнутрипеченочныеПротоки_", "us_abdomen_gb", "ВнутрипеченочныеПротоки", "Внутрипеченочные протоки"),
    ("Поджелудочная_", "us_abdomen_gb", "ПоджелудочнаяЖелеза", "Поджелудочная железа"),
    ("ВирсунговПроток_", "us_abdomen_gb", "ВирсунговПроток", "Вирсунгов проток"),
    ("Селезенка_", "us_abdomen_gb", "Селезенка", "Селезенка"),
    ("СелезеночнаяВена_", "us_abdomen_gb", "СелезеночнаяВена", "Селезеночная вена"),
    ("Аорта_", "us_abdomen_gb", "Аорта", "Аорта"),
    ("Матка_", "us_pelvis_omt", "Матка", "Матка"),
    ("Миометрий_", "us_pelvis_omt", "Миометрий", "Миометрий"),
    ("МиоматозныйУзел_", "us_pelvis_omt", "Миометрий", "Миометрий / миома"),
    ("Эндометрий_", "us_pelvis_omt", "Эндометрий", "Эндометрий"),
    ("ПолипЭндометрия_", "us_pelvis_omt", "Эндометрий", "Эндометрий"),
    ("ВМС_", "us_pelvis_omt", "ПолостьМатки", "Полость матки"),
    ("ПолостьМатки_", "us_pelvis_omt", "ПолостьМатки", "Полость матки"),
    ("ШейкаМатки_", "us_pelvis_omt", "ШейкаМатки", "Шейка матки"),
    ("КистаШейки_", "us_pelvis_omt", "ШейкаМатки", "Шейка матки"),
    ("ПолипШейки_", "us_pelvis_omt", "ШейкаМатки", "Шейка матки"),
    ("Эндоцервикс_", "us_pelvis_omt", "Эндоцервикс", "Эндоцервикс"),
    ("ЦервикальныйКанал_", "us_pelvis_omt", "ЦервикальныйКанал", "Цервикальный канал"),
    ("ЯичникПравый_", "us_pelvis_omt", "ЯичникПравый", "Яичник правый"),
    ("ЯичникЛевый_", "us_pelvis_omt", "ЯичникЛевый", "Яичник левый"),
    ("КистаЯичника_R", "us_pelvis_omt", "ЯичникПравый", "Яичник правый"),
    ("КистаЯичника_L", "us_pelvis_omt", "ЯичникЛевый", "Яичник левый"),
    ("O_RADS_R", "us_pelvis_omt", "ЯичникПравый", "Яичник правый"),
    ("O_RADS_L", "us_pelvis_omt", "ЯичникЛевый", "Яичник левый"),
    ("ТрубаПравая_", "us_pelvis_omt", "ТрубаПравая", "Труба правая"),
    ("ТрубаЛевая_", "us_pelvis_omt", "ТрубаЛевая", "Труба левая"),
    ("Гидросальпинкс_", "us_pelvis_omt", "ТрубаПравая", "Трубы"),
    ("ВеныМалогоТаза_", "us_pelvis_omt", "ВеныМалогоТаза", "Вены малого таза"),
    ("ВеныПараметральногоСплетения_", "us_pelvis_omt", "ВеныМалогоТаза", "Вены малого таза"),
    ("СвободнаяЖидкость_", "us_pelvis_omt", "Матка", "Матка"),
    ("МЖ_", "us_breast", "МолочнаяЖелеза", "Молочная железа"),
    ("BI_RADS_", "us_breast", "МолочнаяЖелеза", "Молочная железа"),
    ("МлечныеПротоки_", "us_breast", "МлечныеПротоки", "Млечные протоки"),
    ("эктазия_протоков_МЖ", "us_breast", "МлечныеПротоки", "Млечные протоки"),
    ("киста_МЖ_", "us_breast", "Киста", "Кисты МЖ"),
    ("КистаМЖ_", "us_breast", "Киста", "Кисты МЖ"),
    ("кисты_множественные_МЖ", "us_breast", "Киста", "Кисты МЖ"),
    ("мелкокистозный_компонент", "us_breast", "Киста", "Кисты МЖ"),
    ("узловое_образование_МЖ", "us_breast", "Очаг", "Очаг МЖ"),
    ("ОчагМЖ_", "us_breast", "Очаг", "Очаг МЖ"),
    ("Фиброаденома_", "us_breast", "Фиброаденома", "Фиброаденома"),
    ("кальцинаты_МЖ", "us_breast", "Очаг", "Очаг МЖ"),
    ("КальцинатМЖ_", "us_breast", "Очаг", "Очаг МЖ"),
    ("ЛокальныйФиброзМЖ_", "us_breast", "МолочнаяЖелеза", "Молочная железа"),
    ("локальный_фиброз_МЖ", "us_breast", "МолочнаяЖелеза", "Молочная железа"),
    ("Имплант_", "us_breast", "Имплант", "Имплант"),
    ("лимфузлы_аксиллярные_", "us_breast", "ЛимфоузлыАксиллярные", "Лимфоузлы аксиллярные"),
    ("ЛимфоузелАксиллярный_", "us_breast", "ЛимфоузлыАксиллярные", "Лимфоузлы аксиллярные"),
    ("лимфузлы_подключичные_", "us_breast", "ЛимфоузлыРегионарные", "Лимфоузлы регионарные"),
    ("лимфузлы_надключичные_", "us_breast", "ЛимфоузлыРегионарные", "Лимфоузлы регионарные"),
    ("лимфузлы_парастернальные_", "us_breast", "ЛимфоузлыРегионарные", "Лимфоузлы регионарные"),
    ("Щитовидная_", "us_thyroid", "ЩитовиднаяЖелеза", "Щитовидная железа"),
    ("ДоляПравая_", "us_thyroid", "ДоляПравая", "Доля правая"),
    ("ДоляЛевая_", "us_thyroid", "ДоляЛевая", "Доля левая"),
    ("Перешеек_", "us_thyroid", "Перешеек", "Перешеек"),
    ("УзелЩЖ_", "us_thyroid", "Узел", "Узлы ЩЖ"),
    ("КистаЩЖ_", "us_thyroid", "Киста", "Кисты ЩЖ"),
    ("TI_RADS", "us_thyroid", "Узел", "Узлы ЩЖ"),
    ("EU_TIRADS", "us_thyroid", "Узел", "Узлы ЩЖ"),
    ("лимфузлы_шейные_", "us_thyroid", "ЛимфоузлыРегионарные", "Лимфоузлы шейные"),
    ("ЛимфоузелШейный_", "us_thyroid", "ЛимфоузлыРегионарные", "Лимфоузлы шейные"),
    ("Простата_", "us_prostate_trusi", "ПредстательнаяЖелеза", "Предстательная железа"),
    ("ПереходнаяЗона_", "us_prostate_trusi", "ПереходнаяЗона", "Переходная зона"),
    ("АденоматозныйУзел_", "us_prostate_trusi", "АденоматозныйУзел", "Аденоматозные узлы"),
    ("УзелДГПЖ_", "us_prostate_trusi", "АденоматозныйУзел", "Аденоматозные узлы"),
    ("КистаПростаты_", "us_prostate_trusi", "Киста", "Кисты простаты"),
    ("КальцинатПростаты_", "us_prostate_trusi", "ПредстательнаяЖелеза", "Предстательная железа"),
    ("ПротоковаяСистема_", "us_prostate_trusi", "ПредстательнаяЖелеза", "Предстательная железа"),
    ("ПростатическаяУретра_", "us_prostate_trusi", "ПростатическаяУретра", "Простатическая уретра"),
    ("СеменныеПузырьки_", "us_prostate_trusi", "СеменныеПузырьки", "Семенные пузырьки"),
    ("ПерипростатическиеВены_", "us_prostate_trusi", "ПерипростатическиеВены", "Перипростатические вены"),
    ("ОстаточнаяМоча_", "us_prostate_trusi", "ОстаточнаяМоча", "Остаточная моча"),
    ("МочевойПузырь_", "us_prostate_trusi", "МочевойПузырь", "Мочевой пузырь"),
    ("ОбщаяБедреннаяАртерия_", "duplex_lower_limb_arteries", "ОБА", "ОБА"),
    ("ПоверхностнаяБедреннаяАртерия_", "duplex_lower_limb_arteries", "ПБА", "ПБА"),
    ("ГлубокаяБедреннаяАртерия_", "duplex_lower_limb_arteries", "ГБА", "ГБА"),
    ("ПодколеннаяАртерия_", "duplex_lower_limb_arteries", "ПкА", "ПкА"),
    ("ЗаднебольшеберцоваяАртерия_", "duplex_lower_limb_arteries", "ЗББА", "ЗББА"),
    ("ПереднебольшеберцоваяАртерия_", "duplex_lower_limb_arteries", "ПББА", "ПББА"),
    ("ТыльнаяАртерияСтопы_", "duplex_lower_limb_arteries", "ТАС", "ТАС"),
    ("ОбщаяПодвздошнаяАртерия_", "duplex_lower_limb_arteries", "ОПА", "ОПА"),
    ("НаружнаяПодвздошнаяАртерия_", "duplex_lower_limb_arteries", "НПА", "НПА"),
    ("ОБА_", "duplex_lower_limb_arteries", "ОБА", "ОБА"),
    ("БПВ_", "duplex_lower_limb_veins", "БПВ", "БПВ"),
    ("МПВ_", "duplex_lower_limb_veins", "МПВ", "МПВ"),
    ("СФС_", "duplex_lower_limb_veins", "СФС", "СФС"),
    ("СПС_", "duplex_lower_limb_veins", "СПС", "СПС"),
    ("глубокие_вены_", "duplex_lower_limb_veins", "ГлубокиеВены", "Глубокие вены"),
    ("перфорантные_вены_", "duplex_lower_limb_veins", "Перфоранты", "Перфоранты"),
    ("компрессия_", "duplex_lower_limb_veins", "ВеныНК", "Вены НК"),
]


# Грубое объединение подструктур → один орган/зона исследования.
# Ключ: (modality, fine_organ) → (coarse_organ, label)
_COARSE_ORGANS: dict[tuple[str, str], tuple[str, str]] = {
    # --- МЖ: кисты/очаги/протоки/импланты = молочная железа ---
    ("us_breast", "МолочнаяЖелеза"): ("МолочнаяЖелеза", "Молочная железа"),
    ("us_breast", "Киста"): ("МолочнаяЖелеза", "Молочная железа"),
    ("us_breast", "Фиброаденома"): ("МолочнаяЖелеза", "Молочная железа"),
    ("us_breast", "Очаг"): ("МолочнаяЖелеза", "Молочная железа"),
    ("us_breast", "МлечныеПротоки"): ("МолочнаяЖелеза", "Молочная железа"),
    ("us_breast", "Имплант"): ("МолочнаяЖелеза", "Молочная железа"),
    ("us_breast", "ЛимфоузлыАксиллярные"): ("Лимфоузлы", "Лимфоузлы"),
    ("us_breast", "ЛимфоузлыРегионарные"): ("Лимфоузлы", "Лимфоузлы"),
    # --- ЩЖ: доли/перешеек/узлы/кисты = щитовидная ---
    ("us_thyroid", "ЩитовиднаяЖелеза"): ("ЩитовиднаяЖелеза", "Щитовидная железа"),
    ("us_thyroid", "ДоляПравая"): ("ЩитовиднаяЖелеза", "Щитовидная железа"),
    ("us_thyroid", "ДоляЛевая"): ("ЩитовиднаяЖелеза", "Щитовидная железа"),
    ("us_thyroid", "Перешеек"): ("ЩитовиднаяЖелеза", "Щитовидная железа"),
    ("us_thyroid", "Узел"): ("ЩитовиднаяЖелеза", "Щитовидная железа"),
    ("us_thyroid", "Киста"): ("ЩитовиднаяЖелеза", "Щитовидная железа"),
    ("us_thyroid", "ПаращитовидныеЖелезы"): ("ЩитовиднаяЖелеза", "Щитовидная железа"),
    ("us_thyroid", "ЛимфоузлыРегионарные"): ("Лимфоузлы", "Лимфоузлы"),
    # --- ОМТ: матка целиком; яичники; трубы ---
    ("us_pelvis_omt", "Матка"): ("Матка", "Матка"),
    ("us_pelvis_omt", "Миометрий"): ("Матка", "Матка"),
    ("us_pelvis_omt", "Эндометрий"): ("Матка", "Матка"),
    ("us_pelvis_omt", "ПолостьМатки"): ("Матка", "Матка"),
    ("us_pelvis_omt", "ШейкаМатки"): ("Матка", "Матка"),
    ("us_pelvis_omt", "Эндоцервикс"): ("Матка", "Матка"),
    ("us_pelvis_omt", "ЦервикальныйКанал"): ("Матка", "Матка"),
    ("us_pelvis_omt", "ЯичникПравый"): ("Яичники", "Яичники"),
    ("us_pelvis_omt", "ЯичникЛевый"): ("Яичники", "Яичники"),
    ("us_pelvis_omt", "ТрубаПравая"): ("МаточныеТрубы", "Маточные трубы"),
    ("us_pelvis_omt", "ТрубаЛевая"): ("МаточныеТрубы", "Маточные трубы"),
    ("us_pelvis_omt", "ВеныМалогоТаза"): ("ВеныМалогоТаза", "Вены малого таза"),
    # Дуглас / за маткой — к матке; асцит брюшной полости остаётся отдельно
    ("us_pelvis_omt", "СвободнаяЖидкость"): ("Матка", "Матка"),
    # --- ОБП ---
    ("us_abdomen_gb", "Печень"): ("Печень", "Печень"),
    ("us_abdomen_gb", "ВоротнаяВена"): ("Печень", "Печень"),
    ("us_abdomen_gb", "ПеченочныеВены"): ("Печень", "Печень"),
    ("us_abdomen_gb", "ВнутрипеченочныеПротоки"): ("Печень", "Печень"),
    ("us_abdomen_gb", "ЖелчныйПузырь"): ("ЖелчныйПузырь", "Желчный пузырь"),
    ("us_abdomen_gb", "Холедох"): ("ЖелчныйПузырь", "Желчный пузырь"),
    ("us_abdomen_gb", "ПоджелудочнаяЖелеза"): ("ПоджелудочнаяЖелеза", "Поджелудочная железа"),
    ("us_abdomen_gb", "ВирсунговПроток"): ("ПоджелудочнаяЖелеза", "Поджелудочная железа"),
    ("us_abdomen_gb", "Селезенка"): ("Селезенка", "Селезенка"),
    ("us_abdomen_gb", "СелезеночнаяВена"): ("Селезенка", "Селезенка"),
    ("us_abdomen_gb", "НПВ"): ("СосудыОБП", "Сосуды ОБП"),
    ("us_abdomen_gb", "Аорта"): ("СосудыОБП", "Сосуды ОБП"),
    ("us_abdomen_gb", "Лимфоузлы"): ("Лимфоузлы", "Лимфоузлы"),
    ("us_abdomen_gb", "СвободнаяЖидкость"): ("СвободнаяЖидкость", "Свободная жидкость"),
    # --- ТРУЗИ ---
    ("us_prostate_trusi", "ПредстательнаяЖелеза"): ("ПредстательнаяЖелеза", "Предстательная железа"),
    ("us_prostate_trusi", "ПереходнаяЗона"): ("ПредстательнаяЖелеза", "Предстательная железа"),
    ("us_prostate_trusi", "АденоматозныйУзел"): ("ПредстательнаяЖелеза", "Предстательная железа"),
    ("us_prostate_trusi", "Киста"): ("ПредстательнаяЖелеза", "Предстательная железа"),
    ("us_prostate_trusi", "ПростатическаяУретра"): ("ПредстательнаяЖелеза", "Предстательная железа"),
    ("us_prostate_trusi", "СеменныеПузырьки"): ("СеменныеПузырьки", "Семенные пузырьки"),
    ("us_prostate_trusi", "ПерипростатическиеВены"): ("ПерипростатическиеВены", "Перипростатические вены"),
    ("us_prostate_trusi", "МочевойПузырь"): ("МочевойПузырь", "Мочевой пузырь"),
    ("us_prostate_trusi", "ОстаточнаяМоча"): ("МочевойПузырь", "Мочевой пузырь"),
    # --- Дуплекс НК ---
    ("duplex_lower_limb_arteries", "АртерииНК"): ("АртерииНК", "Артерии НК"),
    ("duplex_lower_limb_arteries", "ОБА"): ("АртерииНК", "Артерии НК"),
    ("duplex_lower_limb_arteries", "ПБА"): ("АртерииНК", "Артерии НК"),
    ("duplex_lower_limb_arteries", "ГБА"): ("АртерииНК", "Артерии НК"),
    ("duplex_lower_limb_arteries", "ПкА"): ("АртерииНК", "Артерии НК"),
    ("duplex_lower_limb_arteries", "ЗББА"): ("АртерииНК", "Артерии НК"),
    ("duplex_lower_limb_arteries", "ПББА"): ("АртерииНК", "Артерии НК"),
    ("duplex_lower_limb_arteries", "ТАС"): ("АртерииНК", "Артерии НК"),
    ("duplex_lower_limb_arteries", "ОПА"): ("АртерииНК", "Артерии НК"),
    ("duplex_lower_limb_arteries", "НПА"): ("АртерииНК", "Артерии НК"),
    ("duplex_lower_limb_veins", "ВеныНК"): ("ВеныНК", "Вены НК"),
    ("duplex_lower_limb_veins", "БПВ"): ("ВеныНК", "Вены НК"),
    ("duplex_lower_limb_veins", "МПВ"): ("ВеныНК", "Вены НК"),
    ("duplex_lower_limb_veins", "СФС"): ("ВеныНК", "Вены НК"),
    ("duplex_lower_limb_veins", "СПС"): ("ВеныНК", "Вены НК"),
    ("duplex_lower_limb_veins", "ГлубокиеВены"): ("ВеныНК", "Вены НК"),
    ("duplex_lower_limb_veins", "ПоверхностныеВены"): ("ВеныНК", "Вены НК"),
    ("duplex_lower_limb_veins", "Перфоранты"): ("ВеныНК", "Вены НК"),
}


def _humanize(name: str) -> str:
    s = re.sub(r"([a-zа-я])([A-ZА-Я])", r"\1 \2", name)
    return s.replace("_", " ")


def _apply_coarse(modality: str, organ: str, label: str) -> tuple[str, str, str]:
    hit = _COARSE_ORGANS.get((modality, organ))
    if hit:
        return modality, hit[0], hit[1]
    return modality, organ, label


@lru_cache(maxsize=1)
def _token_owner_map() -> dict[str, tuple[str, str, str]]:
    """token_name → (modality, organ, label) from catalog bags + heuristics."""
    path = _catalog_path()
    mtime = path.stat().st_mtime
    return _token_owner_map_at(str(path), mtime)


@lru_cache(maxsize=2)
def _token_owner_map_at(path_str: str, _mtime: float) -> dict[str, tuple[str, str, str]]:
    data = json.loads(Path(path_str).read_text(encoding="utf-8"))
    out: dict[str, tuple[str, str, str]] = {}
    for mod_name, mod in (data.get("modalities") or {}).items():
        if not isinstance(mod, dict):
            continue
        organs = list(mod.get("organs") or [])
        vessels = list(mod.get("vessels") or [])
        for bag in ("organ_tokens", "vessel_tokens", "tokens", "study_flags"):
            bagd = mod.get(bag) or {}
            if not isinstance(bagd, dict):
                continue
            for name in bagd:
                if name in _EXPLICIT:
                    out[name] = _EXPLICIT[name]
                    continue
                placed = False
                for pref, m, organ, label in _PREFIX_ORGANS:
                    if name.startswith(pref) or name == pref.rstrip("_"):
                        out[name] = (m, organ, label)
                        placed = True
                        break
                if placed:
                    continue
                # try match organ list as prefix
                for organ in organs:
                    if name.startswith(organ) or name.startswith(organ.replace("Железа", "")):
                        out[name] = (mod_name, organ, _humanize(organ))
                        placed = True
                        break
                if placed:
                    continue
                for v in vessels:
                    if v in name or name.startswith(v):
                        out[name] = (mod_name, v, v)
                        placed = True
                        break
                if not placed:
                    if str(name).startswith("study_"):
                        out[name] = (mod_name, "Исследование", "Исследование")
                    else:
                        out[name] = (mod_name, "Прочее", f"Прочее ({mod_name})")
    # cross_cutting
    for name, meta in ((data.get("cross_cutting") or {}).get("tokens") or {}).items():
        out[name] = _EXPLICIT.get(name, ("cross_cutting", "Прочее", "Прочее"))
    # fill any catalog token missing via prefixes / explicit
    for name in _flat_catalog_names():
        if name in out:
            continue
        if name in _EXPLICIT:
            out[name] = _EXPLICIT[name]
            continue
        for pref, m, organ, label in _PREFIX_ORGANS:
            if name.startswith(pref) or name == pref.rstrip("_"):
                out[name] = (m, organ, label)
                break
        else:
            out[name] = ("unknown", "Прочее", "Прочее")
    # Грубое деление: кисты/узлы/доли → родительский орган
    coarse: dict[str, tuple[str, str, str]] = {}
    for name, (mod, organ, label) in out.items():
        coarse[name] = _apply_coarse(mod, organ, label)
    return coarse


def resolve_organ(token_name: str) -> tuple[str, str, str]:
    return _token_owner_map().get(token_name, ("unknown", "Прочее", "Прочее"))


def group_tokens_by_organ(
    clinical_tokens: dict[str, Any] | None,
    *,
    recommendation: dict[str, Any] | None = None,
    catalog: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    cat = catalog or {}
    bags: dict[tuple[str, str], dict[str, Any]] = {}
    labels: dict[tuple[str, str], str] = {}

    for name, val in (clinical_tokens or {}).items():
        if str(name).startswith("рекомендация_"):
            continue
        if str(name).startswith("study_"):
            continue
        if not _is_nonzero(val):
            continue
        modality, organ, label = resolve_organ(name)
        key = (modality, organ)
        labels[key] = label
        slot = bags.setdefault(key, {"characteristics": {}, "suspicious": {}})
        meta = cat.get(name) or {}
        t = meta.get("type") or "binary"
        # Binary «норма» (anteflexio и т.п.) — в характеристики, не в подозрительные.
        # Подозрительные = binary-находки; numeric/categorical всегда характеристики.
        from .pathology import is_normal_token

        stored = 1 if (t == "binary" and val in (True, 1)) else val
        if t == "binary" and not is_normal_token(name):
            slot["suspicious"][name] = stored
        else:
            slot["characteristics"][name] = stored

    rec = recommendation or {}
    present = bool(rec.get("present"))
    out: list[dict[str, Any]] = []
    for (modality, organ), slot in sorted(bags.items(), key=lambda x: (x[0][0], x[0][1])):
        if not slot["characteristics"] and not slot["suspicious"]:
            continue
        out.append(
            {
                "modality": modality,
                "organ": organ,
                "label": labels.get((modality, organ), _humanize(organ)),
                "characteristics": slot["characteristics"],
                "suspicious": slot["suspicious"],
                "recommendation": {"present": present},
            }
        )
    return out
