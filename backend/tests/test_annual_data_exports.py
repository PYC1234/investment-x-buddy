import json

import pytest

from app.build_annual_training_data import EVALS, build
from app.evaluate_annual import evaluate


def load(name):
    return json.loads((EVALS / name).read_text(encoding="utf-8"))


def test_exports_preserve_labels_and_keep_review_pending():
    cases = load("annual_training_examples.json")
    holdout = load("annual_confirmation.json") + load("annual_evidence.json")
    result = build(cases, holdout)
    assert len(result["sft"]) == len(result["rm"]) == len(result["review"]) == len(cases)
    assert all(row["review_status"] == "needs_human_review" for row in result["review"])
    for sft, rm in zip(result["sft"], result["rm"], strict=True):
        assert sft["messages"][0]["content"] == rm["prompt"]
        assert sft["messages"][1]["content"] == rm["chosen"]
    leaked = {"id": cases[0]["id"], "candidates": cases[0]["evidence"]}
    with pytest.raises(ValueError, match="overlap"):
        build(cases, [leaked])


def test_confirmation_distinguishes_retrieval_from_supported_decisions():
    result = evaluate(load("annual_confirmation.json"))
    for row in result["cases"]:
        if row["stratum"] in {"wrong_year", "wrong_symbol"}:
            assert row["scope_exclusions"] == 1
            assert row["proposed"]["correct_abstention"]
        if row["stratum"] == "reverse_causality":
            assert row["proposed"]["hit"]
            assert not row["proposed"]["supported_decision"]
