from datetime import datetime, timezone

from app.extensions import db
from app.errors.exceptions import ValidationError, ConflictError
from app.models import Alert, Project, OrganisationMember
from app.models.alert import PRIORITIES, METRICS, OPERATORS as VALID_OPERATORS
from app.services.alert_evaluator import evaluate as evaluate_rule
from app.services.audit_service import log_action


def _validate_condition(condition):
    if condition.get("metric") not in METRICS:
        raise ValidationError(f"metric must be one of: {', '.join(METRICS)}")
    if condition.get("operator") not in VALID_OPERATORS:
        raise ValidationError(f"operator must be one of: {', '.join(VALID_OPERATORS)}")
    threshold = condition.get("threshold")
    if not isinstance(threshold, (int, float)):
        raise ValidationError("threshold must be a number")
    if condition["metric"].endswith("_percentage") and not (0 <= threshold <= 100):
        raise ValidationError("threshold for a percentage metric must be between 0 and 100")


def create_alert(project_id, actor_user_id, data):
    condition = {
        "name": data.get("name"),
        "metric": data["metric"],
        "operator": data["operator"],
        "threshold": data["threshold"],
        "timeWindowDays": data.get("timeWindowDays"),
        "keyword": data.get("keyword"),
        "aspectName": data.get("aspectName"),
    }
    _validate_condition(condition)

    organisation_id = db.session.get(Project, project_id).organisation_id
    alert = Alert(
        project_id=project_id, rule_condition=condition,
        priority=data.get("priority", "medium"), enabled=data.get("enabled", True),
    )
    db.session.add(alert)
    db.session.flush()
    log_action(organisation_id, actor_user_id, "alert.created", "alert", alert.id, {"metric": condition["metric"]})
    db.session.commit()
    return alert


def list_alerts(project_id, filters=None):
    filters = filters or {}
    query = Alert.query.filter_by(project_id=project_id)
    if filters.get("status"):
        query = query.filter(Alert.status == filters["status"])
    if filters.get("priority"):
        query = query.filter(Alert.priority == filters["priority"])
    if filters.get("enabled") is not None:
        query = query.filter(Alert.enabled == filters["enabled"])
    return query.order_by(Alert.created_at.desc()).all()


def update_alert(alert, data, actor_user_id):
    condition = dict(alert.rule_condition or {})
    for field in ("name", "metric", "operator", "threshold", "timeWindowDays", "keyword", "aspectName"):
        if field in data:
            condition[field] = data[field]
    if any(f in data for f in ("metric", "operator", "threshold")):
        _validate_condition(condition)
    alert.rule_condition = condition

    if "priority" in data:
        alert.priority = data["priority"]

    db.session.commit()
    log_action(alert.project.organisation_id, actor_user_id, "alert.updated", "alert", alert.id, {})
    db.session.commit()
    return alert


def set_enabled(alert, enabled, actor_user_id):
    alert.enabled = enabled
    db.session.commit()
    log_action(
        alert.project.organisation_id, actor_user_id,
        "alert.enabled" if enabled else "alert.disabled", "alert", alert.id,
    )
    db.session.commit()
    return alert


def evaluate_alert(alert, actor_user_id):
    """Evaluates one rule. Duplicate-trigger control: if the rule is already
    actively triggered (triggered_at set, status still 'open'), re-evaluating
    a still-true condition is a no-op — it does not reset triggered_at or
    write a second 'triggered' audit entry. This is the whole point of the
    schema's one-row-per-rule design (triggered_at IS NULL = not yet fired).
    """
    if not alert.enabled:
        return {"triggered": False, "currentValue": None, "message": "Alert rule is disabled.", "changed": False}

    result = evaluate_rule(alert.project_id, alert.rule_condition or {})
    condition = dict(alert.rule_condition or {})
    condition["lastEvaluation"] = {
        "message": result["message"], "currentValue": result["currentValue"],
        "evaluatedAt": datetime.now(timezone.utc).isoformat(),
    }
    alert.rule_condition = condition

    already_active = alert.triggered_at is not None and alert.status == "open"
    changed = False
    if result["triggered"] and not already_active:
        alert.triggered_at = datetime.now(timezone.utc)
        alert.status = "open"
        changed = True
        log_action(alert.project.organisation_id, actor_user_id, "alert.triggered", "alert", alert.id, {
            "metric": condition.get("metric"), "currentValue": result["currentValue"],
        })

    db.session.commit()
    log_action(alert.project.organisation_id, actor_user_id, "alert.evaluated", "alert", alert.id, {
        "triggered": result["triggered"],
    })
    db.session.commit()
    return {**result, "changed": changed}


def evaluate_project_alerts(project_id, actor_user_id):
    alerts = Alert.query.filter_by(project_id=project_id, enabled=True).all()
    return [{"alertId": str(a.id), **evaluate_alert(a, actor_user_id)} for a in alerts]


def acknowledge_alert(alert, actor_user_id):
    """No status change (status stays open/resolved per the approved schema)
    — acknowledging is an audited action that claims the alert for the
    acknowledging user if it isn't already assigned.
    """
    condition = dict(alert.rule_condition or {})
    condition["acknowledgedAt"] = datetime.now(timezone.utc).isoformat()
    condition["acknowledgedBy"] = str(actor_user_id)
    alert.rule_condition = condition
    if alert.assigned_to is None:
        alert.assigned_to = actor_user_id
    db.session.commit()
    log_action(alert.project.organisation_id, actor_user_id, "alert.acknowledged", "alert", alert.id)
    db.session.commit()
    return alert


def assign_alert(alert, user_id, actor_user_id):
    membership = OrganisationMember.query.filter_by(
        organisation_id=alert.project.organisation_id, user_id=user_id
    ).first()
    if membership is None:
        raise ValidationError("Assignee is not a member of this organisation")
    alert.assigned_to = user_id
    db.session.commit()
    log_action(alert.project.organisation_id, actor_user_id, "alert.assigned", "alert", alert.id, {"userId": user_id})
    db.session.commit()
    return alert


def resolve_alert(alert, resolution_notes, actor_user_id):
    if not resolution_notes or not resolution_notes.strip():
        raise ValidationError("resolutionNotes is required to resolve an alert")
    alert.status = "resolved"
    alert.resolution_notes = resolution_notes
    alert.resolved_at = datetime.now(timezone.utc)
    db.session.commit()
    log_action(alert.project.organisation_id, actor_user_id, "alert.resolved", "alert", alert.id)
    db.session.commit()
    return alert


def delete_alert(alert, actor_user_id):
    organisation_id = alert.project.organisation_id
    alert_id = alert.id
    db.session.delete(alert)
    db.session.commit()
    log_action(organisation_id, actor_user_id, "alert.deleted", "alert", alert_id)
    db.session.commit()
