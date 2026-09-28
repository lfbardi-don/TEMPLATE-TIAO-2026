"""Relate the current evidence to completed and ongoing inspections."""

from datetime import timedelta

from tractor_usage.application.contracts import InspectionCase, InspectionEpisode


def inspection_workflow(
    cases: tuple[InspectionCase, ...], episodes: tuple[InspectionEpisode, ...]
) -> dict[str, object]:
    active = next((case for case in cases if case.status in ("OPEN", "IN_PROGRESS")), None)
    completed = max(
        (case for case in cases if case.status == "COMPLETED"),
        key=lambda case: case.evidence_as_of_utc,
        default=None,
    )
    # Match the episode membership rule used by the score: first window close.
    new_ids = [
        episode.id for episode in episodes
        if completed is None
        or episode.started_at_utc + timedelta(seconds=60) > completed.evidence_as_of_utc
    ]
    return {
        "active_case": {"id": active.id, "status": active.status} if active else None,
        "last_completed_case": {
            "id": completed.id,
            "evidence_as_of_utc": completed.evidence_as_of_utc.isoformat(),
            "completed_at_utc": completed.completed_at_utc.isoformat() if completed.completed_at_utc else None,
            "result": completed.result,
        } if completed else None,
        "new_episode_ids": new_ids,
        "can_open_case": active is None and bool(new_ids),
    }
