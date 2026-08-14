from app.extensions import db
from app.errors.exceptions import NotFoundError, ConflictError, ValidationError
from app.models import Project, ProjectMember, User, OrganisationMember


def list_projects(organisation_id, status=None, search=None):
    query = Project.query.filter_by(organisation_id=organisation_id).filter(
        Project.deleted_at.is_(None)
    )
    if status:
        query = query.filter(Project.status == status)
    if search:
        query = query.filter(Project.name.ilike(f"%{search}%"))
    return query.order_by(Project.created_at.desc()).all()


def get_project_or_404(project_id, organisation_id):
    project = Project.query.filter_by(id=project_id, organisation_id=organisation_id).filter(
        Project.deleted_at.is_(None)
    ).first()
    if project is None:
        # Same NOT_FOUND for "doesn't exist" and "exists in another org" —
        # never leaks which project IDs belong to other tenants.
        raise NotFoundError("Project not found")
    return project


def create_project(organisation_id, creator_user_id, data):
    if data.get("startDate") and data.get("endDate"):
        if data["endDate"] < data["startDate"]:
            raise ValidationError("endDate must not be before startDate")

    existing = Project.query.filter_by(
        organisation_id=organisation_id, name=data["name"]
    ).filter(Project.deleted_at.is_(None)).first()
    if existing:
        raise ConflictError("A project with this name already exists in this organisation")

    project = Project(
        organisation_id=organisation_id,
        name=data["name"],
        description=data.get("description"),
        product_or_topic=data.get("productOrTopic"),
        start_date=data.get("startDate"),
        end_date=data.get("endDate"),
    )
    db.session.add(project)
    db.session.flush()
    db.session.add(ProjectMember(project_id=project.id, user_id=creator_user_id))
    db.session.commit()
    return project


def update_project(project, data):
    start_date = data.get("startDate", project.start_date)
    end_date = data.get("endDate", project.end_date)
    if start_date and end_date and end_date < start_date:
        raise ValidationError("endDate must not be before startDate")

    for field, attr in [
        ("name", "name"), ("description", "description"),
        ("productOrTopic", "product_or_topic"), ("startDate", "start_date"),
        ("endDate", "end_date"),
    ]:
        if field in data:
            setattr(project, attr, data[field])
    db.session.commit()
    return project


def archive_project(project, archived=True):
    project.status = Project.STATUS_ARCHIVED if archived else Project.STATUS_ACTIVE
    db.session.commit()
    return project


def soft_delete_project(project):
    from datetime import datetime, timezone
    project.deleted_at = datetime.now(timezone.utc)
    db.session.commit()


def list_project_members(project_id):
    return ProjectMember.query.filter_by(project_id=project_id).all()


def add_project_member(project_id, organisation_id, user_id):
    member = OrganisationMember.query.filter_by(
        organisation_id=organisation_id, user_id=user_id
    ).first()
    if member is None:
        raise ValidationError("User is not a member of this organisation")

    existing = ProjectMember.query.filter_by(project_id=project_id, user_id=user_id).first()
    if existing:
        raise ConflictError("User is already a member of this project")

    pm = ProjectMember(project_id=project_id, user_id=user_id)
    db.session.add(pm)
    db.session.commit()
    return pm


def remove_project_member(project_id, user_id):
    pm = ProjectMember.query.filter_by(project_id=project_id, user_id=user_id).first()
    if pm is None:
        raise NotFoundError("User is not a member of this project")
    db.session.delete(pm)
    db.session.commit()
