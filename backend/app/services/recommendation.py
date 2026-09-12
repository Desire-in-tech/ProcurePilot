from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.research import ResearchRun, ResearchTask
from app.research.states import ResearchTaskStatus, ResearchTaskType


def _recommendation_reason(offer: dict[str, Any]) -> str:
    reasons = [
        "meets the mandatory procurement requirements",
    ]

    if offer.get("price") is not None:
        reasons.append(
            f"has the best comparable price ranking ({offer['currency']})"
            if offer.get("price_rank") == 1
            else "has a comparable price"
        )

    if offer.get("evidence_count", 0) > 0:
        reasons.append(
            f"is supported by {offer['evidence_count']} evidence record(s)"
        )

    return "; ".join(reasons)


async def generate_recommendation(
    db: Session,
    run: ResearchRun,
    comparisons: list[dict[str, Any]],
) -> dict[str, Any]:
    task = ResearchTask(
        research_run_id=run.id,
        task_type=ResearchTaskType.GENERATE_RECOMMENDATION.value,
        status=ResearchTaskStatus.RUNNING.value,
        provider="internal",
        input_data={
            "comparison_count": len(comparisons),
        },
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    try:
        eligible = [
            comparison
            for comparison in comparisons
            if comparison.get("status") == "eligible"
        ]

        if not eligible:
            recommendation = {
                "status": "needs_human_input",
                "recommended_offer_id": None,
                "reason": (
                    "No supplier offer currently satisfies all mandatory "
                    "procurement requirements."
                ),
                "eligible_offer_count": 0,
                "alternative_offer_ids": [],
                "human_review_required": True,
            }
        else:
            selected = eligible[0]
            alternatives = [
                comparison["offer_id"]
                for comparison in eligible[1:]
            ]

            recommendation = {
                "status": "recommended",
                "recommended_offer_id": selected["offer_id"],
                "supplier_name": selected["supplier_name"],
                "product_name": selected["product_name"],
                "model": selected.get("model"),
                "price": selected.get("price"),
                "currency": selected.get("currency"),
                "reason": _recommendation_reason(selected),
                "eligible_offer_count": len(eligible),
                "alternative_offer_ids": alternatives,
                "human_review_required": False,
            }

        task.status = ResearchTaskStatus.COMPLETED.value
        task.output_data = recommendation
        db.commit()
        db.refresh(task)

        return recommendation

    except Exception as exc:
        db.rollback()

        failed_task = db.get(ResearchTask, task.id)

        if failed_task is not None:
            failed_task.status = ResearchTaskStatus.FAILED.value
            failed_task.error = str(exc)
            db.commit()

        raise
