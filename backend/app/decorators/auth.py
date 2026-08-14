from functools import wraps

from flask import g, request
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity

from app.errors.exceptions import UnauthenticatedError, ForbiddenError, NotFoundError
from app.models import User, OrganisationMember, Project
from app.services.permission_service import has_permission
from app.utils.query_helpers import is_valid_uuid


def _load_current_user():
    verify_jwt_in_request()
    user_id = get_jwt_identity()
    user = User.query.filter_by(id=user_id).first()
    if user is None or user.is_deleted:
        raise UnauthenticatedError("User account no longer exists")
    g.current_user = user
    return user


def jwt_required_custom(fn):
    """Thin wrapper so every protected route goes through the same identity check."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        _load_current_user()
        return fn(*args, **kwargs)
    return wrapper


def _resolve_organisation_id(kwargs):
    if "organisation_id" in kwargs:
        return kwargs["organisation_id"]
    header_org = request.headers.get("X-Organisation-Id")
    if header_org:
        return header_org
    return None


def organisation_member_required(fn):
    """Requires a valid JWT AND active membership in the target organisation.

    The organisation is taken from the route's `organisation_id` path param,
    or the `X-Organisation-Id` header for routes that aren't org-scoped in the URL.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _load_current_user()
        organisation_id = _resolve_organisation_id(kwargs)
        if organisation_id is None:
            raise ForbiddenError("No organisation context provided")
        if not is_valid_uuid(organisation_id):
            raise NotFoundError("Organisation not found")

        membership = OrganisationMember.query.filter_by(
            organisation_id=organisation_id, user_id=user.id
        ).first()
        if membership is None or membership.status != OrganisationMember.STATUS_ACTIVE:
            # Same response whether the org doesn't exist or the user just isn't in it.
            raise NotFoundError("Organisation not found")

        g.current_membership = membership
        g.current_organisation_id = organisation_id
        return fn(*args, **kwargs)
    return wrapper


def permission_required(permission_code):
    """Must be stacked under organisation_member_required (or project_access_required)."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            membership = getattr(g, "current_membership", None)
            if membership is None:
                raise ForbiddenError("No organisation membership context")
            if not has_permission(membership, permission_code):
                raise ForbiddenError(f"Missing required permission: {permission_code}")
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def project_access_required(fn):
    """Loads the project, confirms it belongs to an org the user actively belongs to.

    Sets g.current_project, g.current_membership, g.current_organisation_id.
    A project ID from another organisation always 404s — never a 403 — so callers
    can't use the response to discover project IDs outside their tenant.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _load_current_user()
        project_id = kwargs.get("project_id")
        if not is_valid_uuid(project_id):
            raise NotFoundError("Project not found")

        project = Project.query.filter_by(id=project_id).filter(
            Project.deleted_at.is_(None)
        ).first()
        if project is None:
            raise NotFoundError("Project not found")

        membership = OrganisationMember.query.filter_by(
            organisation_id=project.organisation_id, user_id=user.id
        ).first()
        if membership is None or membership.status != OrganisationMember.STATUS_ACTIVE:
            raise NotFoundError("Project not found")

        g.current_project = project
        g.current_membership = membership
        g.current_organisation_id = project.organisation_id
        return fn(*args, **kwargs)
    return wrapper


def _entity_access_required(model_cls, id_kwarg, g_attr, soft_delete=True):
    """Factory for decorators that scope a Phase-2 resource (source/dataset/review)
    through its project to the caller's organisation membership.

    Same 404-not-403 rule as project_access_required: a resource ID belonging to
    another organisation never distinguishes "doesn't exist" from "not yours".
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = _load_current_user()
            entity_id = kwargs.get(id_kwarg)
            if not is_valid_uuid(entity_id):
                raise NotFoundError(f"{model_cls.__name__} not found")
            query = model_cls.query.filter_by(id=entity_id)
            if soft_delete and hasattr(model_cls, "deleted_at"):
                query = query.filter(model_cls.deleted_at.is_(None))
            entity = query.first()
            if entity is None:
                raise NotFoundError(f"{model_cls.__name__} not found")

            membership = OrganisationMember.query.filter_by(
                organisation_id=entity.project.organisation_id, user_id=user.id
            ).first()
            if membership is None or membership.status != OrganisationMember.STATUS_ACTIVE:
                raise NotFoundError(f"{model_cls.__name__} not found")

            setattr(g, g_attr, entity)
            g.current_membership = membership
            g.current_organisation_id = entity.project.organisation_id
            g.current_project = entity.project
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def data_source_access_required(fn):
    from app.models import DataSource
    return _entity_access_required(DataSource, "source_id", "current_data_source", soft_delete=False)(fn)


def dataset_access_required(fn):
    from app.models import Dataset
    return _entity_access_required(Dataset, "dataset_id", "current_dataset")(fn)


def review_access_required(fn):
    from app.models import Review
    return _entity_access_required(Review, "review_id", "current_review")(fn)


def recommendation_access_required(fn):
    from app.models import Recommendation
    return _entity_access_required(
        Recommendation, "recommendation_id", "current_recommendation", soft_delete=False
    )(fn)


def ai_summary_access_required(fn):
    from app.models import AiSummary
    return _entity_access_required(AiSummary, "summary_id", "current_summary", soft_delete=False)(fn)


def alert_access_required(fn):
    from app.models import Alert
    return _entity_access_required(Alert, "alert_id", "current_alert", soft_delete=False)(fn)


def report_access_required(fn):
    from app.models import Report
    return _entity_access_required(Report, "report_id", "current_report", soft_delete=False)(fn)


def workflow_access_required(fn):
    from app.models import AgentWorkflow
    return _entity_access_required(AgentWorkflow, "workflow_id", "current_workflow", soft_delete=False)(fn)
