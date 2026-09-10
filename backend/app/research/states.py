from enum import Enum


class ProcurementStatus(str, Enum):
    DRAFT = "draft"
    READY_FOR_RESEARCH = "ready_for_research"
    RESEARCHING = "researching"
    EVALUATING = "evaluating"
    RECOMMENDATION_READY = "recommendation_ready"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    BLOCKED = "blocked"
    NEEDS_HUMAN_INPUT = "needs_human_input"


class ResearchRunStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


class ResearchTaskType(str, Enum):
    SEARCH_SUPPLIERS = "search_suppliers"
    SEARCH_PRODUCTS = "search_products"
    SCRAPE_SOURCE = "scrape_source"
    VERIFY_OFFER = "verify_offer"
    COMPARE_OFFERS = "compare_offers"
    GENERATE_RECOMMENDATION = "generate_recommendation"


PROCUREMENT_TRANSITIONS: dict[ProcurementStatus, set[ProcurementStatus]] = {
    ProcurementStatus.DRAFT: {
        ProcurementStatus.READY_FOR_RESEARCH,
        ProcurementStatus.REJECTED,
    },
    ProcurementStatus.READY_FOR_RESEARCH: {
        ProcurementStatus.RESEARCHING,
        ProcurementStatus.BLOCKED,
    },
    ProcurementStatus.RESEARCHING: {
        ProcurementStatus.EVALUATING,
        ProcurementStatus.FAILED,
        ProcurementStatus.BLOCKED,
        ProcurementStatus.NEEDS_HUMAN_INPUT,
    },
    ProcurementStatus.EVALUATING: {
        ProcurementStatus.RECOMMENDATION_READY,
        ProcurementStatus.FAILED,
        ProcurementStatus.NEEDS_HUMAN_INPUT,
    },
    ProcurementStatus.RECOMMENDATION_READY: {
        ProcurementStatus.AWAITING_APPROVAL,
        ProcurementStatus.FAILED,
    },
    ProcurementStatus.AWAITING_APPROVAL: {
        ProcurementStatus.APPROVED,
        ProcurementStatus.REJECTED,
    },
    ProcurementStatus.APPROVED: {
        ProcurementStatus.COMPLETED,
        ProcurementStatus.FAILED,
    },
    ProcurementStatus.COMPLETED: set(),
    ProcurementStatus.REJECTED: set(),
    ProcurementStatus.FAILED: set(),
    ProcurementStatus.BLOCKED: {
        ProcurementStatus.READY_FOR_RESEARCH,
        ProcurementStatus.NEEDS_HUMAN_INPUT,
    },
    ProcurementStatus.NEEDS_HUMAN_INPUT: {
        ProcurementStatus.READY_FOR_RESEARCH,
        ProcurementStatus.BLOCKED,
    },
}


RESEARCH_RUN_TRANSITIONS: dict[ResearchRunStatus, set[ResearchRunStatus]] = {
    ResearchRunStatus.PENDING: {
        ResearchRunStatus.PLANNING,
        ResearchRunStatus.CANCELLED,
    },
    ResearchRunStatus.PLANNING: {
        ResearchRunStatus.EXECUTING,
        ResearchRunStatus.FAILED,
        ResearchRunStatus.CANCELLED,
    },
    ResearchRunStatus.EXECUTING: {
        ResearchRunStatus.EVALUATING,
        ResearchRunStatus.FAILED,
        ResearchRunStatus.CANCELLED,
    },
    ResearchRunStatus.EVALUATING: {
        ResearchRunStatus.COMPLETED,
        ResearchRunStatus.FAILED,
    },
    ResearchRunStatus.COMPLETED: set(),
    ResearchRunStatus.FAILED: set(),
    ResearchRunStatus.CANCELLED: set(),
}


RESEARCH_TASK_TRANSITIONS: dict[ResearchTaskStatus, set[ResearchTaskStatus]] = {
    ResearchTaskStatus.PENDING: {
        ResearchTaskStatus.RUNNING,
        ResearchTaskStatus.SKIPPED,
    },
    ResearchTaskStatus.RUNNING: {
        ResearchTaskStatus.COMPLETED,
        ResearchTaskStatus.FAILED,
        ResearchTaskStatus.RETRYING,
    },
    ResearchTaskStatus.RETRYING: {
        ResearchTaskStatus.RUNNING,
        ResearchTaskStatus.FAILED,
    },
    ResearchTaskStatus.COMPLETED: set(),
    ResearchTaskStatus.FAILED: set(),
    ResearchTaskStatus.SKIPPED: set(),
}


def can_transition(
    current: str,
    target: str,
    transitions: dict[Enum, set[Enum]],
) -> bool:
    try:
        current_state = next(
            state for state in transitions if state.value == current
        )
        target_state = type(current_state)(target)
    except (StopIteration, ValueError):
        return False

    return target_state in transitions[current_state]


def validate_transition(
    current: str,
    target: str,
    transitions: dict[Enum, set[Enum]],
) -> None:
    if not can_transition(current, target, transitions):
        raise ValueError(
            f"Invalid state transition: {current!r} -> {target!r}"
        )
