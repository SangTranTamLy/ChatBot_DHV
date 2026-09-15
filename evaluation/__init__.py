"""Offline evaluation contract for the DHV chatbot.

The dataset and scorer live outside the runtime chatbot path so evaluation never
changes routing, retrieval, prompting, or answer policy.
"""

from .evaluator import (
    EvaluationCase,
    aggregate_answer_metrics,
    aggregate_retrieval_metrics,
    calculate_retrieval_metrics,
    evaluate_answers,
    evaluate_intents,
    evaluate_retrieval,
    load_cases,
    score_answer_case,
    validate_dataset,
)

__all__ = [
    "EvaluationCase",
    "aggregate_answer_metrics",
    "aggregate_retrieval_metrics",
    "calculate_retrieval_metrics",
    "evaluate_answers",
    "evaluate_intents",
    "evaluate_retrieval",
    "load_cases",
    "score_answer_case",
    "validate_dataset",
]
