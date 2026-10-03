# Medical report text parser

FastAPI endpoint for extracting possible abnormalities and changes from Russian
medical report text. It returns matched phrases, their sentence, category,
certainty, and zero-based character offsets in the submitted text.

## Run

From the repository root:

```bash
python -m pip install -r back_alt/requirements.txt
uvicorn back_alt.main:app --reload
```

Open the interactive API documentation at <http://127.0.0.1:8000/docs>.

## Request

```bash
curl -X POST http://127.0.0.1:8000/api/v1/extract \
  -H 'Content-Type: application/json' \
  -d '{"text":"Печень увеличена. Возможно, киста правой почки."}'
```

The response contains a `count` and a `findings` array. An empty array means
that no matching findings were detected; this rule-based parser does not
provide a diagnosis or replace clinical review.
