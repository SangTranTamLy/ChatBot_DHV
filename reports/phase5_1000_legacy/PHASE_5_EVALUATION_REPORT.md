# PHASE 5 – DATASET AND END-TO-END EVALUATION REPORT

## 1. Dataset Summary

Total: 1000 | Development: 800 | Final test: 200 | Dev inside development: 160
Dataset valid: True

## 2. Data Quality and Split Leakage

Exact duplicates: 0; normalized duplicates: 0; near-duplicate flags: 0; family overlap: 0.

## 3. Intent Evaluation

Accuracy: 75.50%; Macro Precision: 67.46%; Macro Recall: 58.88%; Macro F1: 58.37%.
Frozen Phase 5 model — development train: {"cases": 636, "accuracy": 1, "macro_precision": 1.0, "macro_recall": 1.0, "macro_f1": 1.0, "per_intent": [{"intent": "DANH_SACH_NGANH", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 16}, {"intent": "HOI_CACH_TINH_DIEM", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 8}, {"intent": "HOI_CHUONG_TRINH", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 36}, {"intent": "HOI_DIEM_TRUNG_TUYEN", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 136}, {"intent": "HOI_HOC_BONG", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 60}, {"intent": "HOI_HOC_PHI", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 52}, {"intent": "HOI_HO_SO", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 60}, {"intent": "HOI_LICH_TUYEN_SINH", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 8}, {"intent": "HOI_NGANH", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 52}, {"intent": "HOI_NGUONG_DAU_VAO", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 72}, {"intent": "HOI_NHAP_HOC", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 28}, {"intent": "HOI_PHUONG_THUC_XET_TUYEN", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 44}, {"intent": "HOI_XET_TUYEN_BO_SUNG", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 48}, {"intent": "OUT_OF_SCOPE", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 16}]}; development dev: {"cases": 160, "accuracy": 0.9625, "macro_precision": 0.9577, "macro_recall": 0.9487, "macro_f1": 0.9487, "per_intent": [{"intent": "DANH_SACH_NGANH", "precision": 0.7, "recall": 0.875, "f1": 0.7778, "support": 8}, {"intent": "HOI_CACH_TINH_DIEM", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 4}, {"intent": "HOI_CHUONG_TRINH", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 8}, {"intent": "HOI_DIEM_TRUNG_TUYEN", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 32}, {"intent": "HOI_HOC_BONG", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 16}, {"intent": "HOI_HOC_PHI", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 8}, {"intent": "HOI_HO_SO", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 16}, {"intent": "HOI_NGANH", "precision": 0.9091, "recall": 0.8333, "f1": 0.8696, "support": 12}, {"intent": "HOI_NGUONG_DAU_VAO", "precision": 0.9524, "recall": 1.0, "f1": 0.9756, "support": 20}, {"intent": "HOI_NHAP_HOC", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 8}, {"intent": "HOI_PHUONG_THUC_XET_TUYEN", "precision": 0.8889, "recall": 1.0, "f1": 0.9412, "support": 8}, {"intent": "HOI_XET_TUYEN_BO_SUNG", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 12}, {"intent": "OUT_OF_SCOPE", "precision": 1.0, "recall": 0.625, "f1": 0.7692, "support": 8}]}; final test: {"cases": 196, "accuracy": 0.9745, "macro_precision": 0.9737, "macro_recall": 0.9392, "macro_f1": 0.9477, "per_intent": [{"intent": "DANH_SACH_NGANH", "precision": 0.8, "recall": 1.0, "f1": 0.8889, "support": 8}, {"intent": "HOI_CHUONG_TRINH", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 12}, {"intent": "HOI_DIEM_TRUNG_TUYEN", "precision": 0.9756, "recall": 1.0, "f1": 0.9877, "support": 40}, {"intent": "HOI_HOC_BONG", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 20}, {"intent": "HOI_HOC_PHI", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 14}, {"intent": "HOI_HO_SO", "precision": 0.9091, "recall": 1.0, "f1": 0.9524, "support": 20}, {"intent": "HOI_NGANH", "precision": 1.0, "recall": 0.9375, "f1": 0.9677, "support": 16}, {"intent": "HOI_NGUONG_DAU_VAO", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 26}, {"intent": "HOI_NHAP_HOC", "precision": 1.0, "recall": 0.8333, "f1": 0.9091, "support": 12}, {"intent": "HOI_PHUONG_THUC_XET_TUYEN", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 12}, {"intent": "HOI_XET_TUYEN_BO_SUNG", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 12}, {"intent": "OUT_OF_SCOPE", "precision": 1.0, "recall": 0.5, "f1": 0.6667, "support": 4}]}.
Per-intent metrics and confusion matrix are in `intent_metrics.csv` and `confusion_matrix.csv`.

## 4. Retrieval Evaluation

| Retriever | Hit@1 | Hit@3 | Hit@5 | Recall@1 | Recall@3 | Recall@5 | MRR |
|---|---:|---:|---:|---:|---:|---:|---:|
| Dense | 55.43% | 61.41% | 63.04% | 55.43% | 61.41% | 63.04% | 0.5862 |
| BM25 | 61.96% | 65.76% | 67.93% | 61.96% | 65.76% | 67.93% | 0.6404 |
| Hybrid/RRF | 60.87% | 65.22% | 69.02% | 60.87% | 65.22% | 69.02% | 0.6358 |

## 5. Evidence, Deterministic Facts and Answers

Evidence: {"eligible_cases": 188, "evidence_precision": 0.2252, "evidence_recall": 0.5798, "evidence_hit_rate": 0.5798}
Deterministic facts: {"fact_selection_accuracy": 0.5745, "method_mapping_accuracy": 1, "major_mapping_accuracy": 0.92, "year_accuracy": 0.985}
Answer: {"cases": 200, "answer_correctness": 0.585, "status_accuracy": 0.7, "groundedness": 0.9309, "faithfulness": 0.9309, "unsupported_claim_rate": 0, "required_fact_accuracy": 0.5745, "safety_guarantee_violations": 0}

## 6. Abstention and Clarification

NO_DATA: {"expected": 4, "predicted": 49, "precision": 0.0204, "recall": 0.25, "accuracy": 0.25}
OUT_OF_SCOPE: {"expected": 4, "predicted": 16, "precision": 0.25, "recall": 1.0, "accuracy": 1}
CLARIFICATION: {"expected": 4, "predicted": 4, "precision": 1.0, "recall": 1.0, "accuracy": 1}

## 7. Multi-turn, Year Isolation and Safety

Multi-turn: {"conversations": 2, "state_retention_accuracy": 1, "entity_carry_over_accuracy": 1, "method_carry_over_accuracy": 1, "score_carry_over_accuracy": 1, "context_relevance_accuracy": 1}
Wrong-year leakage: {"explicit_non_target_year_cases": 4, "wrong_year_answers": 0}
Admission guarantee violations: 0

## 8. Failure Breakdown

| Failure Type | Count | Percentage |
|---|---:|---:|
| EVIDENCE_ERROR | 34 | 35.42% |
| INTENT_ERROR | 49 | 51.04% |
| VALIDATOR_ERROR | 13 | 13.54% |

## 9. Environment and Execution Notes

Dense retrieval backend: {"backend": "sentence-transformers", "model": "BAAI/bge-m3", "local_only": true, "embedding_dimension": 1024, "corpus_chunks": 247}.
Generation was evaluated with the deterministic evidence-echo adapter because this run does not require Ollama. Retrieval/evidence/router/planner/validator call paths were executed. No test-set rule, threshold, prompt, retrieval configuration or model tuning was performed after reading final-test results.

## 10. Final Test Results

The final-test section contains only the locked 200-row holdout. Development results are reported separately in `summary.json` under `development_baseline`.

## 11. Evaluation Status: EVALUATION_READY

EVALUATION_READY: dataset valid, split valid, evaluator ran, and final metrics were generated. See the separate quality verdict below.

## 12. Quality Verdict: NEEDS_IMPROVEMENT

PASS means no failed holdout cases were reported; NEEDS_IMPROVEMENT means the evaluation completed but the holdout still contains actionable failures; BLOCKED means the evaluation could not be completed.
