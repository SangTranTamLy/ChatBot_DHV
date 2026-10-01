"""Train the Phase 5 intent model using only the development pool."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.chatbot.intent_classifier import IntentClassifier, save_model, save_records


MASTER = ROOT / "data" / "evaluation" / "qa_master_1000.jsonl"
TRAIN_OUT = ROOT / "data" / "evaluation" / "intent_train_640.jsonl"
DEV_OUT = ROOT / "data" / "evaluation" / "intent_dev_160.jsonl"
MODEL_OUT = ROOT / "models" / "phase5_intent_classifier.json"


def load_rows() -> list[dict[str, object]]:
    return [json.loads(line) for line in MASTER.read_text(encoding="utf-8").splitlines() if line.strip()]


def train_phase5_intent(
    *,
    master_path: Path = MASTER,
    train_path: Path = TRAIN_OUT,
    dev_path: Path = DEV_OUT,
    model_path: Path = MODEL_OUT,
) -> dict[str, object]:
    rows = [json.loads(line) for line in master_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    train_rows = [row for row in rows if row.get("split") == "train" and row.get("development_split") == "train"]
    dev_rows = [row for row in rows if row.get("split") == "train" and row.get("development_split") == "dev"]
    if len(train_rows) != 640 or len(dev_rows) != 160:
        raise ValueError(f"Expected 640/160 development split, got {len(train_rows)}/{len(dev_rows)}")

    train_records = [
        {"id": row["id"], "text": row["question"], "intent": row["intent"]}
        for row in train_rows
        if row.get("intent") not in {"GREETING", "SCHOOL_INFO"}
    ]
    dev_records = [
        {"id": row["id"], "text": row["question"], "intent": row["intent"]}
        for row in dev_rows
        if row.get("intent") not in {"GREETING", "SCHOOL_INFO"}
    ]
    labels = {str(record["intent"]) for record in train_records}
    if not labels:
        raise ValueError("no model-backed Phase 5 intents available")
    model = IntentClassifier.train(train_records)
    save_records(train_records, train_path)
    save_records(dev_records, dev_path)
    save_model(model, model_path)

    correct = 0
    for record in dev_records:
        prediction = model.predict(str(record["text"]))
        correct += int(prediction is not None and prediction.intent == record["intent"])
    report = {
        "train_examples": len(train_records),
        "dev_examples": len(dev_records),
        "labels": sorted(labels),
        "dev_accuracy": correct / len(dev_records) if dev_records else 0.0,
        "model_path": str(model_path),
        "test_rows_used": 0,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, default=MASTER)
    parser.add_argument("--train", type=Path, default=TRAIN_OUT)
    parser.add_argument("--dev", type=Path, default=DEV_OUT)
    parser.add_argument("--model", type=Path, default=MODEL_OUT)
    args = parser.parse_args()
    train_phase5_intent(
        master_path=args.master,
        train_path=args.train,
        dev_path=args.dev,
        model_path=args.model,
    )


if __name__ == "__main__":
    main()
