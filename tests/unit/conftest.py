import json
import os

import pytest

from lea.app import lea_lib
from lea.app.lea_api import lea_handler
from scripts import build_data

FIXTURE_DATA = os.path.join(os.path.dirname(__file__), "..", "fixtures", "data")
ROOT = "/nj/lea"


@pytest.fixture(scope="session")
def fixture_build(tmp_path_factory):
    """The path of njlea.json built from the fixture data, once per session"""
    return build_data.build(FIXTURE_DATA, str(tmp_path_factory.mktemp("build")))


@pytest.fixture(autouse=True)
def fixture_data(monkeypatch, fixture_build):
    """Points the function at the fixture build, reloaded for each test"""
    monkeypatch.setenv("DATA_DIR", os.path.dirname(fixture_build))
    monkeypatch.setenv("API_ROOT", "https://api.example.com")
    monkeypatch.setattr(lea_lib, "_data", None)


def call(resource, path=None, query=None):
    """Calls the handler with a GET event; returns (status code, body)"""
    event = {
        "resource": ROOT + resource,
        "httpMethod": "GET",
        "pathParameters": path,
        "queryStringParameters": query,
    }
    reply = lea_handler(event, None)
    assert reply["headers"]["Content-Type"] == "application/vnd.api+json"
    return int(reply["statusCode"]), json.loads(reply["body"])
