"""Build reviewed-format SFT and reward preference examples without training a model."""
import argparse
import json
import unicodedata
from collections import Counter
from pathlib import Path

from app.services.annual_evidence import TOPICS, direct_topics

EVALS = Path(__file__).resolve().parents[1] / "evals"


def normalized(text):
    return "".join(unicodedata.normalize("NFKC", text).split())


def build(cases, holdout):
    held_ids = {case["id"] for case in holdout}
    held_text = {normalized(row["text"]) for case in holdout for row in case["candidates"]}
    sft, rm, review = [], [], []
    seen_ids = set(held_ids)
    seen_prompts = set()
    for case in cases:
        if case["id"] in seen_ids or any(normalized(row["text"]) in held_text for row in case["evidence"]):
            raise ValueError(f"Duplicate case ID or evaluation evidence overlap: {case['id']}")
        seen_ids.add(case["id"])
        rows = {row["id"]: row for row in case["evidence"]}
        if len(rows) != len(case["evidence"]) or not rows:
            raise ValueError(f"Missing or duplicate evidence: {case['id']}")
        if any(row["symbol"] != case["symbol"] or row["year"] != case["year"] for row in rows.values()):
            raise ValueError(f"Evidence outside approved research scope: {case['id']}")
        topic = case["topic"]
        metric = TOPICS[topic][0]
        supporting = [row for row in rows.values() if topic in direct_topics(row["text"])]
        gold = case["gold"]
        if gold is None and supporting or gold is not None and gold not in {row["id"] for row in supporting}:
            raise ValueError(f"Gold label disagrees with evidence rules: {case['id']}")
        prompt = case["question"] + "\n资料：\n" + "\n".join(
            f"[{row['id']}] {row['text']}" for row in rows.values())
        prompt_key = normalized(case["question"]), tuple(sorted(normalized(row["text"]) for row in rows.values()))
        if prompt_key in seen_prompts:
            raise ValueError(f"Duplicate training prompt and evidence: {case['id']}")
        seen_prompts.add(prompt_key)
        chosen = f"根据 [{gold}]，原文说明：{rows[gold]['text']}" if gold else f"现有资料未直接说明{metric}变动的原因。"
        rejected = case["rejected"]
        if normalized(rejected) == normalized(chosen):
            raise ValueError(f"Preference pair has identical answers: {case['id']}")
        metadata = {"id": case["id"], "provenance": "synthetic", "gold_evidence_id": gold,
                    "symbol": case["symbol"], "year": case["year"], "topic": topic,
                    "stratum": case.get("stratum", "legacy")}
        messages = [{"role": "user", "content": prompt}]
        sft.append({**metadata, "messages": [*messages, {"role": "assistant", "content": chosen}]})
        rm.append({**metadata, "prompt": prompt, "chosen": chosen, "rejected": rejected})
        review.append({**metadata, "error_type": case["error_type"], "rationale": case["rationale"],
                       "review_status": "needs_human_review"})
    return {"sft": sft, "rm": rm, "review": review}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    cases = json.loads((EVALS / "annual_training_examples.json").read_text(encoding="utf-8"))
    holdout = json.loads((EVALS / "annual_confirmation.json").read_text(encoding="utf-8"))
    regression = json.loads((EVALS / "annual_evidence.json").read_text(encoding="utf-8"))
    exports = build(cases, holdout + regression)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in exports.items():
        (args.output_dir / f"{name}.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    manifest = {"counts": {key: len(rows) for key, rows in exports.items()},
                "strata": dict(Counter(row["stratum"] for row in exports["review"])),
                "answerable": sum(row["gold_evidence_id"] is not None for row in exports["review"]),
                "provenance": "synthetic", "human_review": "pending",
                "excluded_evaluation_cases": len(holdout) + len(regression)}
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(" | ".join(f"{name}: {len(rows)}" for name, rows in exports.items()))


if __name__ == "__main__":
    main()
