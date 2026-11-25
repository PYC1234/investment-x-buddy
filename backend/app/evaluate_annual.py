"""Offline evaluation of annual filing ranking and evidence decisions."""
import argparse
import json
from pathlib import Path
from statistics import mean

from app.services.annual_evidence import TOPICS, direct_topics, ranked_passages

ARMS = ("baseline", "topic_keywords", "proposed")


def evaluate(cases):
    results = []
    for case in cases:
        candidates = [row for row in case["candidates"]
                      if row["symbol"] == case["symbol"] and row["year"] == case["year"]]
        topic = case["topic"]
        gold = set(case["gold"])
        ids = [row["id"] for row in case["candidates"]]
        if len(ids) != len(set(ids)) or not gold <= {row["id"] for row in candidates}:
            raise ValueError(f"Invalid gold references: {case['id']}")
        baseline = sorted(candidates, key=lambda row: sum(
            row["text"].count(term) for term in ("营收", "营业收入", "盈利", "净利润", "经营情况")
        ), reverse=True)[:3]
        proposed = ranked_passages(candidates, 3)[topic]
        topic_keywords = sorted(candidates, key=lambda row: sum(
            row["text"].count(term) for term in TOPICS[topic]
        ), reverse=True)[:3]
        result = {"id": case["id"], "topic": topic, "gold": case["gold"],
                  "stratum": case.get("stratum", "legacy"),
                  "scope_exclusions": len(case["candidates"]) - len(candidates)}
        for name, rows in zip(ARMS, (baseline, topic_keywords, proposed), strict=True):
            direct = [row["id"] for row in rows if topic in direct_topics(row["text"])]
            rank = next((i for i, row in enumerate(rows, 1) if row["id"] in gold), None)
            result[name] = {"top3": [row["id"] for row in rows], "direct": direct,
                            "hit": rank is not None, "reciprocal_rank": 1 / rank if rank else 0,
                            "supported_decision": bool(gold.intersection(direct)) and set(direct) <= gold,
                            "unsupported": sorted(set(direct) - gold),
                            "correct_abstention": not gold and not direct}
        results.append(result)
    summary = {}
    for name in ARMS:
        summary[name] = {
            "answerable": sum(bool(row["gold"]) for row in results),
            "hit_at_3": sum(row[name]["hit"] for row in results),
            "unanswerable": sum(not row["gold"] for row in results),
            "correct_abstentions": sum(row[name]["correct_abstention"] for row in results),
            "unsupported_excerpts": sum(len(row[name]["unsupported"]) for row in results),
            "supported_decisions": sum(row[name]["supported_decision"] for row in results),
            "mrr_at_3_answerable": round(mean(
                [row[name]["reciprocal_rank"] for row in results if row["gold"]] or [0]
            ), 4),
        }
    return {"summary": summary, "cases": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=Path(__file__).resolve().parents[1] / "evals/annual_evidence.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(json.loads(args.cases.read_text(encoding="utf-8")))
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
