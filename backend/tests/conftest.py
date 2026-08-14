import pytest

from app import create_app
from app.extensions import db as _db
from app.services.seed_service import seed_permissions_and_roles


@pytest.fixture()
def app():
    application = create_app("testing")
    with application.app_context():
        _db.create_all()
        seed_permissions_and_roles()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def register(client, org_name="Acme Retail", email="owner@acme.test",
             password="Str0ngPassw0rd!", name="Jane Owner"):
    return client.post("/api/v1/auth/register", json={
        "organisationName": org_name,
        "email": email,
        "password": password,
        "name": name,
    })


def login(client, email="owner@acme.test", password="Str0ngPassw0rd!"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def auth_header(access_token):
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture()
def registered_owner(client):
    resp = register(client)
    body = resp.get_json()
    login_resp = login(client)
    login_body = login_resp.get_json()["data"]
    return {
        "organisationId": body["data"]["organisationId"],
        "userId": body["data"]["userId"],
        "accessToken": login_body["accessToken"],
        "refreshToken": login_body["refreshToken"],
    }
