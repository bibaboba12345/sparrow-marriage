"""Unit tests for RADS patient alerts."""

from app.routing.patient_alerts import (
    build_patient_alert,
    extract_name_patronymic,
    specialist_dative,
)


def test_extract_name_patronymic_full_fio():
    text = "ФИО пациента:\tИванова Анна Сергеевна\nУЗИ"
    assert extract_name_patronymic(text) == "Анна Сергеевна"


def test_extract_name_patronymic_empty():
    text = "ФИО пациента:\nУЗИ органов"
    assert extract_name_patronymic(text) is None


def test_rads3_month_alert_bi_rads():
    alert = build_patient_alert(
        {"BI_RADS_R": 3, "study_us_breast": 1, "рекомендация_маммолога": 1},
        text="ФИО пациента: Петров Пётр Иванович\nРекомендована консультация маммолога.",
        recommendation={"present": True, "specialists": ["маммолог"], "tokens": {}},
        patient={"sex": "M"},
    )
    assert alert is not None
    assert alert["level"] == "month"
    assert alert["rads_score"] == 3
    assert "в течение месяца" in alert["text"]
    assert "Пётр Иванович" in alert["text"]
    assert "маммологу" in alert["text"]
    assert "УЗИ молочных желез" in alert["text"]


def test_rads4_urgent_alert_o_rads():
    alert = build_patient_alert(
        {"O_RADS_L": 4, "O_RADS_R": 2},
        text="ФИО пациента: Сидорова Мария Петровна",
        recommendation={"present": True, "specialists": ["гинеколог"], "tokens": {}},
        patient={"sex": "F"},
    )
    assert alert is not None
    assert alert["level"] == "urgent"
    assert alert["rads_score"] == 4
    assert "необходимо срочно обратиться" in alert["text"]
    assert "Мария Петровна" in alert["text"]
    assert alert["text"].startswith("Уважаемая")
    assert "гинекологу" in alert["text"]


def test_max_score_wins_across_sides():
    alert = build_patient_alert(
        {"BI_RADS_R": 3, "BI_RADS_L": 5},
        recommendation={"present": True, "specialists": ["маммолог"], "tokens": {}},
        patient={"sex": "F"},
    )
    assert alert["level"] == "urgent"
    assert alert["rads_score"] == 5


def test_no_alert_below_3():
    assert build_patient_alert({"O_RADS_R": 1, "O_RADS_L": 2}) is None


def test_specialist_dative():
    assert specialist_dative("эндокринолог") == "эндокринологу"
