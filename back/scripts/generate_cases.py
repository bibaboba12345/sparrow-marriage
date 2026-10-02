#!/usr/bin/env python3
"""Generate synthetic routing cases.json from clinical clusters."""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "app" / "routing" / "cases.json"

# (id_suffix, title, active_features, routing, snippet)
CLUSTERS: list[tuple] = [
    (
        "acs-stemi",
        "ОКС / STEMI",
        ["symptom_chest_pain", "symptom_arm_pain", "lab_troponin_high", "flag_stemi_suspect", "flag_st_elevation"],
        {
            "priority": "emergency",
            "department": "Кардиология / ОРИТ",
            "specialists": ["Кардиолог", "Реаниматолог"],
            "required_tests": ["Тропонин I", "ЭКГ", "Д-димер"],
            "reasoning": ["Боль за грудиной + тропонин + ST → экстренная кардиомаршрутизация"],
        },
        "Боль за грудиной 40 мин, иррадиация, TnI↑, элевация ST.",
    ),
    (
        "acs-unstable",
        "Нестабильная стенокардия",
        ["symptom_chest_pain", "symptom_dyspnea", "flag_stemi_suspect"],
        {
            "priority": "emergency",
            "department": "Кардиология",
            "specialists": ["Кардиолог"],
            "required_tests": ["Тропонин I", "ЭКГ"],
            "reasoning": ["Клиника ОКС без подтверждённого подъёма маркеров — срочный кардиоосмотр"],
        },
        "Давящая боль в груди при нагрузке, одышка.",
    ),
    (
        "hf-acute",
        "Острая сердечная недостаточность",
        ["symptom_dyspnea", "symptom_edema", "lab_bnp_high", "vital_spo2_low"],
        {
            "priority": "urgent",
            "department": "Кардиология",
            "specialists": ["Кардиолог"],
            "required_tests": ["BNP", "ЭхоКГ", "SpO2"],
            "reasoning": ["Одышка + отёки + BNP↑"],
        },
        "Одышка в покое, отёки голеней, NT-proBNP повышен.",
    ),
    (
        "pe-suspect",
        "Подозрение ТЭЛА",
        ["symptom_dyspnea", "symptom_chest_pain", "lab_ddimer_high", "flag_pe_suspect"],
        {
            "priority": "emergency",
            "department": "Пульмонология / ОРИТ",
            "specialists": ["Пульмонолог", "Реаниматолог"],
            "required_tests": ["Д-димер", "КТ-ангиография"],
            "reasoning": ["Одышка + Д-димер↑ → исключить ТЭЛА"],
        },
        "Внезапная одышка, Д-димер повышен.",
    ),
    (
        "pneumonia",
        "Внебольничная пневмония",
        ["symptom_fever", "symptom_cough", "lab_crp_high", "vital_temp_high", "flag_pneumonia_suspect"],
        {
            "priority": "urgent",
            "department": "Пульмонология",
            "specialists": ["Пульмонолог", "Терапевт"],
            "required_tests": ["ОАК", "СРБ", "Рентген ОГК"],
            "reasoning": ["Лихорадка + кашель + СРБ↑"],
        },
        "Лихорадка 38.7, кашель с мокротой, СРБ 48.",
    ),
    (
        "bronchitis",
        "Острый бронхит",
        ["symptom_cough", "symptom_fever", "vital_temp_high"],
        {
            "priority": "routine",
            "department": "Терапия",
            "specialists": ["Терапевт"],
            "required_tests": ["ОАК"],
            "reasoning": ["Кашель/субфебрилитет без тяжёлых маркеров"],
        },
        "Кашель 5 дней, температура 37.4.",
    ),
    (
        "asthma-exacerbation",
        "Обострение астмы",
        ["symptom_dyspnea", "symptom_wheeze", "vital_spo2_low", "vital_rr_high"],
        {
            "priority": "urgent",
            "department": "Пульмонология",
            "specialists": ["Пульмонолог"],
            "required_tests": ["SpO2", "Пикфлоуметрия"],
            "reasoning": ["Свисты + одышка + SpO2↓"],
        },
        "Приступ удушья, свистящее дыхание.",
    ),
    (
        "uti",
        "Инфекция МВП",
        ["symptom_urine_pain", "symptom_fever", "lab_urine_leukocytes", "lab_urine_bacteria"],
        {
            "priority": "urgent",
            "department": "Урология",
            "specialists": ["Уролог", "Терапевт"],
            "required_tests": ["ОАМ", "Посев мочи"],
            "reasoning": ["Дизурия + лейкоцитурия"],
        },
        "Рези при мочеиспускании, лейкоциты в моче.",
    ),
    (
        "renal-colic",
        "Почечная колика",
        ["symptom_abdominal_pain", "symptom_back_pain", "lab_urine_blood", "flag_renal_colic"],
        {
            "priority": "urgent",
            "department": "Урология",
            "specialists": ["Уролог"],
            "required_tests": ["ОАМ", "УЗИ почек"],
            "reasoning": ["Боль в боку + гематурия"],
        },
        "Острая боль в пояснице, эритроциты в моче.",
    ),
    (
        "appendicitis",
        "Подозрение аппендицит",
        ["symptom_abdominal_pain", "symptom_nausea", "symptom_fever", "lab_wbc_high", "flag_appendicitis"],
        {
            "priority": "emergency",
            "department": "Хирургия",
            "specialists": ["Хирург"],
            "required_tests": ["ОАК", "УЗИ ОБП"],
            "reasoning": ["Боль в правой подвздошной + лейкоцитоз"],
        },
        "Боль в правой нижней части живота, тошнота, лейкоцитоз.",
    ),
    (
        "gastritis",
        "Острый гастрит / диспепсия",
        ["symptom_abdominal_pain", "symptom_nausea"],
        {
            "priority": "routine",
            "department": "Гастроэнтерология",
            "specialists": ["Гастроэнтеролог", "Терапевт"],
            "required_tests": ["ОАК", "УЗИ ОБП"],
            "reasoning": ["Эпигастралгия без red flags"],
        },
        "Боль в эпигастрии после еды, тошнота.",
    ),
    (
        "pancreatitis",
        "Панкреатит",
        ["symptom_abdominal_pain", "symptom_nausea", "lab_amylase_high", "lab_lipase_high"],
        {
            "priority": "emergency",
            "department": "Хирургия",
            "specialists": ["Хирург", "Гастроэнтеролог"],
            "required_tests": ["Амилаза", "Липаза", "УЗИ"],
            "reasoning": ["Опоясывающая боль + амилаза/липаза↑"],
        },
        "Опоясывающая боль, амилаза повышена.",
    ),
    (
        "hepatitis",
        "Гепатит / холестаз",
        ["symptom_jaundice", "symptom_weakness", "lab_alt_high", "lab_ast_high", "lab_bilirubin_high"],
        {
            "priority": "urgent",
            "department": "Гастроэнтерология",
            "specialists": ["Гастроэнтеролог", "Инфекционист"],
            "required_tests": ["АЛТ", "АСТ", "Билирубин", "Гепатиты"],
            "reasoning": ["Желтуха + цитолиз"],
        },
        "Желтушность склер, АЛТ/АСТ↑.",
    ),
    (
        "dm2-followup",
        "СД 2 типа — плановый контроль",
        ["flag_diabetes", "lab_hba1c_high", "lab_glucose_high"],
        {
            "priority": "routine",
            "department": "Эндокринология",
            "specialists": ["Эндокринолог"],
            "required_tests": ["HbA1c", "Глюкоза натощак"],
            "reasoning": ["Стабильный СД без острых осложнений"],
        },
        "HbA1c 7.2%, жалоб на острые состояния нет.",
    ),
    (
        "hypoglycemia",
        "Гипогликемия",
        ["symptom_weakness", "symptom_dizziness", "lab_glucose_low", "flag_diabetes"],
        {
            "priority": "emergency",
            "department": "Эндокринология / ОРИТ",
            "specialists": ["Эндокринолог", "Реаниматолог"],
            "required_tests": ["Глюкоза"],
            "reasoning": ["Симптомы + глюкоза↓"],
        },
        "Слабость, потливость, глюкоза 2.8.",
    ),
    (
        "thyroid-hyper",
        "Тиреотоксикоз",
        ["symptom_palpitations", "symptom_weight_loss", "lab_tsh_low", "vital_hr_high"],
        {
            "priority": "urgent",
            "department": "Эндокринология",
            "specialists": ["Эндокринолог"],
            "required_tests": ["ТТГ", "св.Т4"],
            "reasoning": ["Тахикардия + ТТГ↓"],
        },
        "Сердцебиение, похудение, ТТГ снижен.",
    ),
    (
        "anemia",
        "Анемия",
        ["symptom_weakness", "symptom_dizziness", "lab_hemoglobin_low"],
        {
            "priority": "urgent",
            "department": "Терапия / Гематология",
            "specialists": ["Терапевт", "Гематолог"],
            "required_tests": ["ОАК", "Ферритин"],
            "reasoning": ["Слабость + Hb↓"],
        },
        "Слабость, гемоглобин 95.",
    ),
    (
        "sepsis",
        "Подозрение сепсис",
        ["symptom_fever", "vital_temp_high", "vital_hr_high", "lab_wbc_high", "lab_procalcitonin_high", "flag_sepsis_suspect"],
        {
            "priority": "emergency",
            "department": "ОРИТ / Инфекционное",
            "specialists": ["Реаниматолог", "Инфекционист"],
            "required_tests": ["ОАК", "Прокальцитонин", "Посевы"],
            "reasoning": ["Лихорадка + тахикардия + PCT↑"],
        },
        "Лихорадка 39.2, ЧСС 120, прокальцитонин повышен.",
    ),
    (
        "stroke",
        "Острое нарушение мозгового кровообращения",
        ["symptom_speech", "symptom_numbness", "symptom_weakness", "flag_stroke_suspect"],
        {
            "priority": "emergency",
            "department": "Неврология / Инсультный центр",
            "specialists": ["Невролог"],
            "required_tests": ["КТ головного мозга", "Глюкоза"],
            "reasoning": ["Очаговая неврология → инсультный протокол"],
        },
        "Внезапная слабость руки, нарушена речь.",
    ),
    (
        "migraine",
        "Мигрень / цефалгия",
        ["symptom_headache", "symptom_nausea"],
        {
            "priority": "routine",
            "department": "Неврология",
            "specialists": ["Невролог"],
            "required_tests": [],
            "reasoning": ["Головная боль без очаговых знаков"],
        },
        "Пульсирующая головная боль, тошнота, без очага.",
    ),
    (
        "trauma-leg",
        "Травма ноги / подозрение перелом",
        ["symptom_leg_pain", "symptom_trauma", "flag_fracture"],
        {
            "priority": "urgent",
            "department": "Травматология",
            "specialists": ["Травматолог"],
            "required_tests": ["Рентген"],
            "reasoning": ["Травма + боль в ноге"],
        },
        "Упал, болит нога, отёк.",
    ),
    (
        "allergy",
        "Аллергическая реакция",
        ["symptom_rash", "symptom_itch", "symptom_allergy"],
        {
            "priority": "urgent",
            "department": "Аллергология / Терапия",
            "specialists": ["Аллерголог", "Терапевт"],
            "required_tests": [],
            "reasoning": ["Сыпь/зуд без анафилаксии"],
        },
        "Сыпь и зуд после препарата.",
    ),
    (
        "anaphylaxis",
        "Анафилаксия",
        ["symptom_allergy", "symptom_dyspnea", "vital_bp_low", "flag_anaphylaxis"],
        {
            "priority": "emergency",
            "department": "ОРИТ",
            "specialists": ["Реаниматолог"],
            "required_tests": [],
            "reasoning": ["Аллергия + гипотония/одышка"],
        },
        "Отёк, одышка, АД 80/50 после укуса.",
    ),
    (
        "hypertension",
        "Артериальная гипертензия",
        ["vital_bp_high", "symptom_headache"],
        {
            "priority": "urgent",
            "department": "Терапия / Кардиология",
            "specialists": ["Терапевт", "Кардиолог"],
            "required_tests": ["АД-мониторинг", "ОАК"],
            "reasoning": ["АД↑ + головная боль"],
        },
        "АД 170/100, головная боль.",
    ),
    (
        "hyperlipidemia",
        "Дислипидемия — плановый",
        ["lab_cholesterol_high", "lab_ldl_high"],
        {
            "priority": "routine",
            "department": "Кардиология / Терапия",
            "specialists": ["Кардиолог", "Терапевт"],
            "required_tests": ["Липидограмма"],
            "reasoning": ["Изолированная дислипидемия без клиники ОКС"],
        },
        "Холестерин 6.8, жалоб нет.",
    ),
    (
        "ckd",
        "ХБП / азотемия",
        ["lab_creatinine_high", "lab_urea_high", "lab_urine_protein"],
        {
            "priority": "urgent",
            "department": "Нефрология",
            "specialists": ["Нефролог"],
            "required_tests": ["Креатинин", "ОАМ", "УЗИ почек"],
            "reasoning": ["Креатинин/мочевина↑"],
        },
        "Креатинин 180, протеинурия.",
    ),
    (
        "ent-otitis",
        "Отит",
        ["symptom_ear_pain", "symptom_fever"],
        {
            "priority": "routine",
            "department": "ЛОР",
            "specialists": ["ЛОР"],
            "required_tests": [],
            "reasoning": ["Боль в ухе ± лихорадка"],
        },
        "Боль в ухе, температура 37.8.",
    ),
    (
        "dental",
        "Одонтогенная боль",
        ["symptom_tooth_pain"],
        {
            "priority": "routine",
            "department": "Стоматология",
            "specialists": ["Стоматолог"],
            "required_tests": [],
            "reasoning": ["Зубная боль без системных red flags"],
        },
        "Острая зубная боль.",
    ),
    (
        "oncology-suspect",
        "Онконастороженность",
        ["symptom_weight_loss", "symptom_night_sweats", "symptom_weakness", "flag_oncology"],
        {
            "priority": "urgent",
            "department": "Терапия / Онкология",
            "specialists": ["Терапевт", "Онколог"],
            "required_tests": ["ОАК", "Биохимия", "КТ"],
            "reasoning": ["B-симптомы / необъяснимая потеря веса"],
        },
        "Потеря веса 8 кг, ночная потливость.",
    ),
    (
        "anxiety",
        "Тревожное расстройство / паника",
        ["symptom_anxiety", "symptom_palpitations", "symptom_insomnia"],
        {
            "priority": "routine",
            "department": "Психиатрия / Неврология",
            "specialists": ["Психиатр", "Невролог"],
            "required_tests": ["ЭКГ"],
            "reasoning": ["Паника без кардиомаркеров"],
        },
        "Панические атаки, бессонница, тропонин норма.",
    ),
]

# Valid features only — drop unknown like lab_urine_bacteria if not in catalog
from app.routing.features import feature_index  # noqa: E402

IDX = feature_index()


def _clean(feats: list[str]) -> list[str]:
    return [f for f in feats if f in IDX]


def build_cases() -> list[dict]:
    cases = []
    n = 0
    for suffix, title, feats, routing, snippet in CLUSTERS:
        base = _clean(feats)
        # base case
        n += 1
        cases.append(
            {
                "id": f"case-{suffix}-01",
                "title": title,
                "active_features": base,
                "routing": routing,
                "epicrisis_snippet": snippet,
            }
        )
        # variants: drop one optional symptom if >2 features
        if len(base) >= 3:
            n += 1
            slim = base[:-1]
            cases.append(
                {
                    "id": f"case-{suffix}-02",
                    "title": f"{title} (усечённый)",
                    "active_features": slim,
                    "routing": routing,
                    "epicrisis_snippet": snippet + " (частичные признаки)",
                }
            )
        # variant with weakness add-on
        if "symptom_weakness" not in base:
            n += 1
            cases.append(
                {
                    "id": f"case-{suffix}-03",
                    "title": f"{title} + слабость",
                    "active_features": _clean(base + ["symptom_weakness"]),
                    "routing": routing,
                    "epicrisis_snippet": snippet + " Слабость.",
                }
            )
    # pad to ~100 with mild combinations
    extras = [
        (["symptom_cough"], "Кашель изолированный", "Терапия", "routine"),
        (["symptom_headache"], "Головная боль изолированная", "Неврология", "routine"),
        (["symptom_back_pain"], "Боль в спине", "Терапия", "routine"),
        (["symptom_joint_pain", "lab_esr_high"], "Артралгия + СОЭ↑", "Ревматология", "urgent"),
        (["lab_psa_high"], "ПСА↑ плановый", "Урология", "routine"),
        (["vital_hr_low"], "Брадикардия", "Кардиология", "urgent"),
        (["symptom_diarrhea", "symptom_fever"], "Гастроэнтерит", "Инфекционное", "urgent"),
        (["symptom_constipation", "symptom_abdominal_pain"], "Запор + абдоминалгия", "Гастроэнтерология", "routine"),
        (["symptom_runny_nose", "symptom_sore_throat"], "ОРВИ", "Терапия", "routine"),
        (["symptom_vision"], "Нарушение зрения", "Офтальмология", "urgent"),
        (["symptom_hearing"], "Нарушение слуха", "ЛОР", "routine"),
        (["symptom_seizure"], "Судороги", "Неврология", "emergency"),
        (["lab_inr_high", "flag_bleeding"], "Коагулопатия + кровотечение", "Гематология", "emergency"),
        (["lab_potassium_high"], "Гиперкалиемия", "Нефрология", "urgent"),
        (["lab_potassium_low"], "Гипокалиемия", "Терапия", "urgent"),
        (["lab_sodium_low"], "Гипонатриемия", "Терапия", "urgent"),
        (["flag_pregnancy", "symptom_abdominal_pain"], "Беременность + боль", "Акушерство", "urgent"),
        (["lab_platelets_low"], "Тромбоцитопения", "Гематология", "urgent"),
        (["lab_platelets_high"], "Тромбоцитоз", "Гематология", "routine"),
        (["lab_wbc_low", "symptom_fever"], "Нейтропения + лихорадка", "Гематология", "emergency"),
    ]
    for i, (feats, title, dept, prio) in enumerate(extras, 1):
        cases.append(
            {
                "id": f"case-extra-{i:02d}",
                "title": title,
                "active_features": _clean(feats),
                "routing": {
                    "priority": prio,
                    "department": dept,
                    "specialists": [dept.split("/")[0].strip()],
                    "required_tests": [],
                    "reasoning": [f"Синтетический кейс: {title}"],
                },
                "epicrisis_snippet": title,
            }
        )
    return cases


def main() -> None:
    cases = build_cases()
    payload = {"meta": {"count": len(cases), "generator": "generate_cases.py"}, "cases": cases}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(cases)} cases → {OUT}")


if __name__ == "__main__":
    main()
