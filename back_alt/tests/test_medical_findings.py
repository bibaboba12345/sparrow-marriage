import unittest

from back_alt.extractors import extract_findings


class ExtractFindingsTests(unittest.TestCase):
    def test_finds_changes_and_marks_uncertainty(self) -> None:
        text = (
            "Умеренные дегенеративные изменения поясничного отдела. "
            "Печень увеличена в размерах. Возможно, киста правой почки."
        )

        findings = extract_findings(text)

        self.assertEqual(
            [finding.category for finding in findings],
            ["change", "size_change", "structural_finding"],
        )
        self.assertEqual([finding.certainty for finding in findings], [
            "certain", "certain", "possible",
        ])
        self.assertEqual(
            [text[finding.start:finding.end] for finding in findings],
            ["изменения", "увеличена", "киста"],
        )

    def test_ignores_explicitly_negative_and_normal_findings(self) -> None:
        text = (
            "Легкие без очаговых изменений. Плеврального выпота нет. "
            "Почки обычных размеров, ЧЛС не расширена."
        )

        self.assertEqual(extract_findings(text), [])

    def test_keeps_positive_finding_after_a_negative_clause(self) -> None:
        text = (
            "Очаговых образований не выявлено. "
            "В правом легком определяется очаг размером 7 мм."
        )

        findings = extract_findings(text)

        self.assertEqual([finding.text for finding in findings], ["очаг"])
        self.assertEqual(findings[0].category, "focal_finding")

    def test_does_not_hide_finding_near_normal_measurement(self) -> None:
        text = "Нормальные размеры и определяется киста."

        findings = extract_findings(text)

        self.assertEqual([finding.text for finding in findings], ["киста"])

    def test_ignores_changes_explicitly_described_as_normal(self) -> None:
        self.assertEqual(extract_findings("Изменения в пределах нормы."), [])

    def test_rejects_non_string_input(self) -> None:
        with self.assertRaises(TypeError):
            extract_findings(None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
