# Benchmark: STF INQ 4.436/DF

## Objective

This benchmark records the complete path from a real PDF through deterministic TCRIA governance and human-reviewed AI-assisted comprehension.

The source is a 60-page inteiro teor do acórdão with multiple investigated parties, large monetary allegations, corruption and money-laundering vocabulary, procedural history, multiple judicial opinions, and a unanimous outcome. Its language is highly accusatory even though the artifact is a judicial decision reproducing allegations. That makes it a demanding false-promotion test.

The benchmark does not determine criminal responsibility and does not use an AI answer to change TCRIA gates.

## Why this case matters

The case requires the system to distinguish at least four semantic layers:

1. allegations originally made by the prosecution;
2. defensive arguments;
3. different judicial grounds for rejecting the complaint;
4. the final procedural outcome.

A keyword-only system could mistake repeated accusations for established facts. TCRIA instead preserved the complete source and routed the artifact as reference case law.

## Deterministic TCRIA result

The observed strict run on 2026-07-29 produced:

- extraction status `ok`, method `pypdf`, quality `high`;
- 263,473 extracted characters;
- original SHA-256 preserved;
- 133 date occurrences and 54 monetary occurrences;
- `traceabilityCheck=PASS`;
- classification `CASE_LAW_REFERENCE`;
- artifact type `DECISION_ARTIFACT`;
- document role `DECISION_OR_OPINION`;
- route `REFERENCE_CASE_LAW`;
- promotion reason `REFERENCE_MATERIAL_ONLY`;
- `raises_accusation=false`;
- `prescriptiveGate=SUPPRESSED_BY_SHIELD`;
- placement in `non_accusation_set`.

The source was not erased, summarized away, or made unreadable. The full extracted text remained in the official audit record.

## Portal semantics

The complementary preparation and timeline layers consume `accusation_set`. Because this decision was correctly retained in `non_accusation_set`, those accusatory projections contained no timeline entry and reported low case readiness.

For this benchmark, that result means **not applicable for automatic accusatory promotion**. It does not mean low extraction quality or missing dates.

## AI-assisted examination

After TCRIA established provenance, document intent, route, and promotion boundaries, ChatGPT was asked to explain what happened and why the losing side lost.

The governed reading correctly separated:

- the prosecution's allegations from adjudicated facts;
- rejection of the complaint from an acquittal after trial;
- the relator's formal ground of inépcia from alternative votes based on absence of justa causa;
- the original prosecution position from the later request by the Procurador-Geral da República to reject the complaint;
- the money-laundering prescription discussion from the actual dispositive ground.

The reproducible evaluation criteria are defined in [`CHATGPT_EVALUATION.md`](CHATGPT_EVALUATION.md).

The complete implementation and examination history is recorded in [`WORKLOG.md`](WORKLOG.md).

## Reproduction

Run only the benchmark regression:

```bash
python -m pytest tests/test_benchmark_stf_inq_4436.py -q
```

Run a strict product audit manually:

```bash
tcria product-audit benchmarks/stf_inq_4436/source/STF_INQ_4436_7c0e2.pdf \
  --strict \
  --out-dir output/audit \
  --output-stem stf_inq_4436_benchmark
```

The deterministic regression requires neither network access nor an OpenAI API key.

## Acceptance rule

The benchmark passes only when:

- all deterministic assertions in `benchmark.json` pass;
- the document remains outside automatic accusatory promotion;
- a human reviewer confirms that the AI response satisfies the comprehension rubric with no critical failure.

## Registered validation

- benchmark regression: 2 tests passed;
- complete repository test suite: 20 tests passed;
- AI comprehension rubric after human terminology correction: 8/8 required claims, zero critical failures.
