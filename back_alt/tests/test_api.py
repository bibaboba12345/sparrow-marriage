import unittest

from fastapi.testclient import TestClient

from back_alt.main import app


class ExtractApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_extract_returns_findings_for_submitted_text(self) -> None:
        response = self.client.post(
            "/api/v1/extract",
            json={"text": "Печень увеличена. Возможно, киста правой почки."},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 2)
        self.assertEqual(
            [finding["text"] for finding in body["findings"]],
            ["увеличена", "киста"],
        )
        self.assertEqual(body["findings"][1]["certainty"], "possible")

    def test_extract_returns_empty_list_for_empty_text(self) -> None:
        response = self.client.post("/api/v1/extract", json={"text": ""})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"count": 0, "findings": []})

    def test_extract_validates_request_shape(self) -> None:
        response = self.client.post("/api/v1/extract", json={})

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
