from app.extensions import db
from app.models import AuditLog


def log_action(organisation_id, actor_id, action, entity_type, entity_id, metadata=None):
    entry = AuditLog(
        organisation_id=organisation_id,
        actor=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        event_metadata=metadata or {},
    )
    db.session.add(entry)
    return entry
