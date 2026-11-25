"""Compare annual evidence decisions on identical, ordered candidates."""
import json
import re
from pathlib import Path

from app.evaluate_annual import evaluate
from app.services.annual_evidence import direct_topics

BACKEND = Path(__file__).resolve().parents[1]
DOCS = BACKEND.parent / "docs"
REVERSE_METRICS = {
    "revenue": "营业收入|营收",
    "profit": "归母净利润|归属于上市公司股东的净利润|归属于母公司所有者的净利润",
}
REVERSE = {
    topic: re.compile(
        rf".{{2,}}?(?:导致|带动|推动|使得|使)了?(?:公司)?(?:{metric})"
        r"(?:同比|较上年同期)?(?:增长|增加|减少|下降|上升|上涨|下滑)"
        r"(?:幅度较[大小]|\d+(?:\.\d+)?%)?"
    )
    for topic, metric in REVERSE_METRICS.items()
}
EXCLUDED = re.compile(r"未|没有|并非|不会|不再|可能|预计|若|假如|^上年同期|^上期")


def candidate_topics(text):
    topics = set(direct_topics(text))
    for clause in re.split(r"[。！？；;，,]", re.sub(r"\s+", "", text)):
        if EXCLUDED.search(clause):
            continue
        topics.update(topic for topic, pattern in REVERSE.items() if pattern.fullmatch(clause))
    return topics


def compare(cases):
    results = []
    for case in cases:
        gold = set(case["gold"])
        candidates = case["candidates"]
        row = {"id": case["id"], "topic": case["topic"], "gold": case["gold"],
               "fixed_order": [item["id"] for item in candidates]}
        if "source" in case:
            row["source"] = case["source"]
            row["page"] = case["page"]
            row["annotation"] = case["annotation"]
        for name, decide in (("before", direct_topics), ("after", candidate_topics)):
            selected = [item["id"] for item in candidates if case["topic"] in decide(item["text"])]
            row[name] = {"selected": selected, "unsupported": sorted(set(selected) - gold),
                         "supported": bool(gold.intersection(selected)) and set(selected) <= gold,
                         "abstained": not gold and not selected}
        results.append(row)
    summary = {"answerable": sum(bool(row["gold"]) for row in results),
               "unanswerable": sum(not row["gold"] for row in results)}
    for name in ("before", "after"):
        summary[name] = {
            "supported": sum(row[name]["supported"] for row in results),
            "correct_abstention": sum(row[name]["abstained"] for row in results),
            "unsupported": sum(len(row[name]["unsupported"]) for row in results),
        }
    return {"summary": summary, "cases": results}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    confirmation = read(BACKEND / "evals/annual_confirmation.json")
    baseline = evaluate(confirmation)
    frozen = []
    for case, result in zip(confirmation, baseline["cases"], strict=True):
        by_id = {item["id"]: item for item in case["candidates"]}
        frozen.append({**case, "candidates": [by_id[key] for key in result["proposed"]["top3"]]})
    reports = {
        "constructed_regression": compare(frozen),
        **{name: compare(cases) for name, cases in read(BACKEND / "evals/annual_decision_cases.json").items()},
    }
    (DOCS / "annual-decision-results.json").write_text(
        json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({name: report["summary"] for name, report in reports.items()}))


if __name__ == "__main__":
    main()
