from tests.conftest import register, login, auth_header


def owner_context(client, org_name="Acme Retail", email="owner@acme.test"):
    reg = register(client, org_name=org_name, email=email).get_json()["data"]
    login_body = login(client, email=email).get_json()["data"]
    headers = {**auth_header(login_body["accessToken"]), "X-Organisation-Id": reg["organisationId"]}
    return reg["organisationId"], headers


def create_project(client, headers, name="Q3 Headphones"):
    resp = client.post("/api/v1/projects", json={"name": name}, headers=headers)
    return resp.get_json()["data"]["id"]


def create_reviews_directly(project_id, texts, **common_fields):
    """Inserts Review rows straight into the DB (bypassing the dataset upload
    pipeline) so sentiment/topic tests can control exact review text. Attaches
    them to a throwaway DataSource, since reviews require exactly one origin.
    """
    from app.extensions import db
    from app.models import DataSource, Review

    source = DataSource(project_id=project_id, type="review_site", url="https://example.test", keywords=[])
    db.session.add(source)
    db.session.flush()

    reviews = []
    for text in texts:
        fields = {"project_id": project_id, "data_source_id": source.id, "text": text}
        fields.update(common_fields)
        review = Review(**fields)
        db.session.add(review)
        reviews.append(review)
    db.session.commit()
    return reviews
