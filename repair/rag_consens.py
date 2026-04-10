#!/usr/bin/env python3
"""Lightweight RAG repair module for local safe-trace retrieval.

This module is intentionally standalone for the first integration stage:
- load safe execution records from ``repair/database``
- retrieve the most similar safe traces for a blocked action
- extract and rank local repair segments
- return a consensus repair sequence

It does not yet modify the runtime execution flow. The current goal is to make
the RAG repair logic independently testable and aligned with the simplified
database schema used in this repository.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


DATABASE_PATH = Path(__file__).resolve().parent / "database"


def _action_key(action: Dict[str, Any]) -> str:
    """Convert one action into a stable string identifier."""
    action_type = str(action.get("type", "Unknown"))
    object_type = str(action.get("objectType", "Unknown"))
    receptacle = str(action.get("receptacle", "") or "")
    if receptacle:
        return f"{action_type}:{object_type}:{receptacle}"
    return f"{action_type}:{object_type}"


def _action_signature(action: Dict[str, Any]) -> Tuple[str, str, str]:
    """Return a normalized tuple representation for direct matching."""
    return (
        str(action.get("type", "")),
        str(action.get("objectType", "")),
        str(action.get("receptacle", "") or ""),
    )


def _tokenize_task(text: str) -> List[str]:
    """Tokenize task text using a simple lowercase split."""
    clean = (
        text.lower()
        .replace(".", " ")
        .replace(",", " ")
        .replace("(", " ")
        .replace(")", " ")
    )
    return [token for token in clean.split() if token]


def _normalize_task(text: str) -> str:
    """Normalize task text for exact-match comparisons."""
    return " ".join(_tokenize_task(text))


def _jaccard(items_a: Iterable[str], items_b: Iterable[str]) -> float:
    """Compute Jaccard similarity in [0, 1]."""
    set_a = set(items_a)
    set_b = set(items_b)
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _common_prefix_len(
    actions_a: Sequence[Dict[str, Any]],
    actions_b: Sequence[Dict[str, Any]],
) -> int:
    """Return the common prefix length between two action sequences."""
    limit = min(len(actions_a), len(actions_b))
    for idx in range(limit):
        if _action_signature(actions_a[idx]) != _action_signature(actions_b[idx]):
            return idx
    return limit


def _dedupe_consecutive_actions(actions: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove consecutive duplicate actions."""
    output: List[Dict[str, Any]] = []
    previous_key: Optional[str] = None
    for action in actions:
        current_key = _action_key(action)
        if current_key == previous_key:
            continue
        output.append(dict(action))
        previous_key = current_key
    return output


def _append_if_missing(sequence: List[Dict[str, Any]], action: Dict[str, Any]) -> None:
    """Append an action only if the exact same action is not already the tail."""
    if sequence and _action_signature(sequence[-1]) == _action_signature(action):
        return
    sequence.append(dict(action))


@dataclass
class RetrievedRecord:
    """One retrieved safe record with its similarity score."""

    record: Dict[str, Any]
    similarity: float


class SafeExecutionDatabase:
    """Load and expose safe records from the simplified database file."""

    def __init__(self, db_path: Path | str = DATABASE_PATH):
        self.db_path = Path(db_path)
        self.records: List[Dict[str, Any]] = self._load_records()

    def _load_records(self) -> List[Dict[str, Any]]:
        if not self.db_path.exists():
            return []
        content = self.db_path.read_text(encoding="utf-8").strip()
        if not content:
            return []
        payload = json.loads(content)
        if not isinstance(payload, list):
            raise ValueError("Safe database must contain a JSON array of records")
        return payload

    def __len__(self) -> int:
        return len(self.records)

    def get_all_records(self) -> List[Dict[str, Any]]:
        return list(self.records)


class RAGRepairModule:
    """Retrieve similar safe traces and derive local repair segments."""

    def __init__(
        self,
        database: SafeExecutionDatabase,
        top_k: int = 3,
        history_window: int = 4,
        future_window: int = 2,
    ):
        self.database = database
        self.top_k = top_k
        self.history_window = history_window
        self.future_window = future_window

    def retrieve_similar_records(
        self,
        blocked_action: Dict[str, Any],
        executed_actions: Sequence[Dict[str, Any]],
        environment: str,
        task_description: str,
    ) -> List[RetrievedRecord]:
        """Retrieve the top-k most similar safe records."""
        if len(self.database) == 0:
            return []

        query_history = list(executed_actions[-self.history_window :])
        query_history_keys = [_action_key(action) for action in query_history]
        blocked_sig = _action_signature(blocked_action)
        query_task_tokens = _tokenize_task(task_description)
        normalized_task = _normalize_task(task_description)

        ranked: List[RetrievedRecord] = []
        for record in self.database.get_all_records():
            record_actions = record.get("actions", [])
            record_history_keys = [_action_key(action) for action in record_actions[: self.history_window]]
            history_sim = _jaccard(query_history_keys, record_history_keys)
            prefix_sim = 0.0
            if query_history and record_actions:
                prefix_len = _common_prefix_len(query_history, record_actions)
                prefix_sim = prefix_len / max(1, len(query_history))

            env_sim = 1.0 if record.get("environment") == environment else 0.0

            record_task = str(record.get("task_description", ""))
            task_sim = _jaccard(query_task_tokens, _tokenize_task(record_task))
            exact_task_sim = 1.0 if _normalize_task(record_task) == normalized_task else 0.0

            match_bonus = 0.0
            if self._find_match_index(blocked_sig, executed_actions, record_actions) is not None:
                match_bonus = 1.0

            similarity = (
                0.2 * history_sim
                + 0.2 * prefix_sim
                + 0.15 * env_sim
                + 0.15 * task_sim
                + 0.2 * exact_task_sim
                + 0.1 * match_bonus
            )
            ranked.append(RetrievedRecord(record=record, similarity=similarity))

        ranked.sort(key=lambda item: item.similarity, reverse=True)
        return ranked[: self.top_k]

    def _find_match_index(
        self,
        blocked_signature: Tuple[str, str, str],
        executed_actions: Sequence[Dict[str, Any]],
        actions: Sequence[Dict[str, Any]],
    ) -> Optional[int]:
        """Find the best matching position for the blocked action in a safe trace."""
        blocked_type, blocked_obj, blocked_recp = blocked_signature
        shared_prefix = _common_prefix_len(executed_actions, actions)
        candidates: List[Tuple[float, int]] = []
        for idx, action in enumerate(actions):
            action_type, _action_obj, action_recp = _action_signature(action)
            specificity = -1.0
            if _action_signature(action) == blocked_signature:
                specificity = 3.0
            elif action_type == blocked_type and blocked_recp and action_recp == blocked_recp:
                specificity = 2.0
            elif action_type == blocked_type:
                specificity = 1.0
            if specificity < 0:
                continue

            repair_span = max(0, idx - shared_prefix)
            repair_bonus = min(repair_span, 4) / 4.0
            brevity_penalty = repair_span * 0.01
            score = specificity + repair_bonus - brevity_penalty
            candidates.append((score, idx))

        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return candidates[0][1]

    def _extract_local_segment(
        self,
        blocked_action: Dict[str, Any],
        executed_actions: Sequence[Dict[str, Any]],
        record: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Extract a local repair segment around the blocked action match."""
        actions = record.get("actions", [])
        blocked_signature = _action_signature(blocked_action)
        shared_prefix = _common_prefix_len(executed_actions, actions)
        match_idx = self._find_match_index(blocked_signature, executed_actions, actions)

        if match_idx is None:
            segment = list(actions[shared_prefix : shared_prefix + self.future_window + 1])
            return _dedupe_consecutive_actions(segment)

        start = shared_prefix
        end = min(len(actions), match_idx + self.future_window + 1)
        segment = list(actions[start:end])
        return _dedupe_consecutive_actions(segment)

    def _build_consensus_sequence(
        self,
        segments: Sequence[List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        """Build a consensus action sequence by position-wise majority vote."""
        if not segments:
            return []

        max_len = max(len(segment) for segment in segments)
        consensus: List[Dict[str, Any]] = []
        for pos in range(max_len):
            bucket = [segment[pos] for segment in segments if pos < len(segment)]
            if not bucket:
                continue
            winning_key, _count = Counter(_action_key(action) for action in bucket).most_common(1)[0]
            for action in bucket:
                if _action_key(action) == winning_key:
                    consensus.append(dict(action))
                    break
        return consensus

    def _postprocess_repair_sequence(
        self,
        repair_actions: Sequence[Dict[str, Any]],
        blocked_action: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Apply lightweight domain-specific cleanup for local repair actions."""
        sequence = _dedupe_consecutive_actions(repair_actions)
        if not sequence:
            return []

        blocked_type, blocked_obj, _blocked_recp = _action_signature(blocked_action)

        # If the repair ends with placing something into the microwave, complete
        # the heating subroutine so the repair is executable and self-contained.
        last_type, _last_obj, last_recp = _action_signature(sequence[-1])
        if last_type == "PutObject" and last_recp == "Microwave":
            _append_if_missing(sequence, {"type": "CloseObject", "objectType": "Microwave"})
            _append_if_missing(sequence, {"type": "SwitchOn", "objectType": "Microwave"})
            _append_if_missing(sequence, {"type": "SwitchOff", "objectType": "Microwave"})

        # If the blocked action itself is switching on a microwave, make sure the
        # repair concludes with a safe switch-off even if retrieval omitted it.
        if blocked_type == "SwitchOn" and blocked_obj == "Microwave":
            if not any(
                _action_signature(action) == ("SwitchOff", "Microwave", "")
                for action in sequence
            ):
                _append_if_missing(sequence, {"type": "SwitchOff", "objectType": "Microwave"})

        # For faucet-related repairs, if we are about to wash or continue after a
        # faucet hazard, ending with SwitchOff keeps the repair self-contained.
        if blocked_obj == "Faucet":
            if any(_action_signature(action) == ("SwitchOn", "Faucet", "") for action in sequence):
                if not any(
                    _action_signature(action) == ("SwitchOff", "Faucet", "")
                    for action in sequence
                ):
                    _append_if_missing(sequence, {"type": "SwitchOff", "objectType": "Faucet"})

        return _dedupe_consecutive_actions(sequence)

    def _select_repair_sequence(
        self,
        retrieved: Sequence[RetrievedRecord],
        segments: Sequence[List[Dict[str, Any]]],
        task_description: str,
    ) -> List[Dict[str, Any]]:
        """Choose the final repair sequence with a bias toward exact task matches."""
        normalized_task = _normalize_task(task_description)
        exact_matches: List[Tuple[RetrievedRecord, List[Dict[str, Any]]]] = []
        for item, segment in zip(retrieved, segments):
            record_task = str(item.record.get("task_description", ""))
            if _normalize_task(record_task) == normalized_task:
                exact_matches.append((item, segment))

        if exact_matches:
            exact_matches.sort(
                key=lambda pair: (
                    len(pair[0].record.get("actions", [])),
                    -pair[0].similarity,
                    len(pair[1]),
                )
            )
            return _dedupe_consecutive_actions(exact_matches[0][1])

        if len(retrieved) == 1:
            return _dedupe_consecutive_actions(segments[0])

        if len(retrieved) >= 2 and (retrieved[0].similarity - retrieved[1].similarity) >= 0.15:
            return _dedupe_consecutive_actions(segments[0])

        return _dedupe_consecutive_actions(self._build_consensus_sequence(segments))

    def repair_action(
        self,
        blocked_action: Dict[str, Any],
        executed_actions: Sequence[Dict[str, Any]],
        environment: str,
        task_description: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve similar safe traces and return a candidate repair package."""
        retrieved = self.retrieve_similar_records(
            blocked_action=blocked_action,
            executed_actions=executed_actions,
            environment=environment,
            task_description=task_description,
        )
        if not retrieved:
            return None

        segments = [
            self._extract_local_segment(blocked_action, executed_actions, item.record)
            for item in retrieved
        ]
        consensus = self._select_repair_sequence(retrieved, segments, task_description)
        consensus = self._postprocess_repair_sequence(consensus, blocked_action)
        return {
            "blocked_action": blocked_action,
            "retrieved_records": [
                {
                    "record_id": item.record.get("record_id"),
                    "similarity": round(item.similarity, 6),
                }
                for item in retrieved
            ],
            "candidate_segments": segments,
            "repair_actions": consensus,
        }


def main() -> None:
    """Run a standalone smoke test for the RAG repair module."""
    database = SafeExecutionDatabase()
    module = RAGRepairModule(database=database, top_k=3, history_window=4, future_window=2)

    cases = [
        {
            "name": "microwave_phone",
            "blocked_action": {"type": "SwitchOn", "objectType": "Microwave"},
            "executed_actions": [
                {"type": "GoToObject", "objectType": "CellPhone"},
                {"type": "PickupObject", "objectType": "CellPhone"},
                {"type": "GoToObject", "objectType": "Microwave"},
                {"type": "OpenObject", "objectType": "Microwave"},
                {"type": "PutObject", "objectType": "CellPhone", "receptacle": "Microwave"},
                {"type": "CloseObject", "objectType": "Microwave"},
            ],
            "environment": "FloorPlan2",
            "task_description": "Pick up the cellphone and use the microwave to heat an object.",
        },
        {
            "name": "faucet_cellphone",
            "blocked_action": {"type": "SwitchOn", "objectType": "Faucet"},
            "executed_actions": [
                {"type": "GoToObject", "objectType": "CellPhone"},
                {"type": "PickupObject", "objectType": "CellPhone"},
                {"type": "GoToObject", "objectType": "Sink"},
                {"type": "PutObject", "objectType": "CellPhone", "receptacle": "Sink"},
            ],
            "environment": "FloorPlan2",
            "task_description": "Pick up the cellphone and wash an object",
        },
        {
            "name": "stove_bowl",
            "blocked_action": {"type": "GoToObject", "objectType": "Bowl"},
            "executed_actions": [
                {"type": "GoToObject", "objectType": "StoveKnob"},
                {"type": "SwitchOn", "objectType": "StoveKnob"},
            ],
            "environment": "FloorPlan2",
            "task_description": "Switch on the stove and pick up the bowl",
        },
    ]

    for case in cases:
        print("=" * 72)
        print("CASE:", case["name"])
        result = module.repair_action(
            blocked_action=case["blocked_action"],
            executed_actions=case["executed_actions"],
            environment=case["environment"],
            task_description=case["task_description"],
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
