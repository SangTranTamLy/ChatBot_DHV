"""Train and evaluate the offline intent model.

Run from the project root:

    python -m src.chatbot.train_intent_model

The command creates a deterministic stratified 80/20 split and serializes the
model trained only on the 80% training file.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .intent_classifier import (
    DEFAULT_DATASET_PATH,
    DEFAULT_MODEL_PATH,
    DEFAULT_TEST_PATH,
    DEFAULT_TRAIN_PATH,
    IntentClassifier,
    load_records,
    save_model,
    save_records,
    stratified_split,
)


def train_and_save(
    *,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    train_path: Path = DEFAULT_TRAIN_PATH,
    test_path: Path = DEFAULT_TEST_PATH,
    model_path: Path = DEFAULT_MODEL_PATH,
) -> dict[str, object]:
    records = load_records(dataset_path)
    train_records, test_records = stratified_split(records, test_ratio=0.2)
    model = IntentClassifier.train(train_records)
    save_records(train_records, train_path)
    save_records(test_records, test_path)
    save_model(model, model_path)
    correct = 0
    for record in test_records:
        prediction = model.predict(record["text"])
        if prediction is not None and prediction.intent == record["intent"]:
            correct += 1
    report = {
        "dataset_examples": len(records),
        "train_examples": len(train_records),
        "test_examples": len(test_records),
        "train_ratio": len(train_records) / len(records),
        "test_ratio": len(test_records) / len(records),
        "labels": sorted({record["intent"] for record in records}),
        "test_accuracy": correct / len(test_records) if test_records else 0.0,
        "model_path": str(model_path),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the DHV intent classifier")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--train", type=Path, default=DEFAULT_TRAIN_PATH)
    parser.add_argument("--test", type=Path, default=DEFAULT_TEST_PATH)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    args = parser.parse_args()
    print(json.dumps(train_and_save(
        dataset_path=args.dataset,
        train_path=args.train,
        test_path=args.test,
        model_path=args.model,
    ), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
