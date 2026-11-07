"""
The OpenAPI spec against the full data (make data).

Each example's request is turned into an API Gateway event and passed to the
handler; the reply must equal the example: data, links and meta. After a data
refresh, the failures show the new values to copy into the spec. The spec's
vocabularies must also be the data's.
"""

import json
import re
from urllib.parse import parse_qsl, urlsplit

import pytest

from lea.app import lea_lib
from lea.app.lea_api import lea_handler
from lea.app.params import COUNTIES
from tests.spec_examples import load_examples, load_spec

API_ROOT = "https://api.tor-gu.com"


def event_for(resource, url):
    """The API Gateway event for a GET of url, served by resource"""
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}" == API_ROOT
    pattern = (
        "^" + re.sub(r"\\\{(\w+)\\\}", r"(?P<\1>[^/]+)", re.escape(resource)) + "$"
    )
    match = re.match(pattern, parts.path)
    assert match, f"{parts.path} doesn't match {resource}"
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    return {
        "resource": resource,
        "path": parts.path,
        "httpMethod": "GET",
        "pathParameters": match.groupdict() or None,
        "queryStringParameters": query or None,
    }


@pytest.mark.parametrize("resource,url,example", load_examples())
def test_spec_example(monkeypatch, resource, url, example):
    monkeypatch.setenv("API_ROOT", API_ROOT)
    reply = lea_handler(event_for(resource, url), None)
    body = json.loads(reply["body"])
    assert reply["statusCode"] == 200, body
    expected = {k: example[k] for k in ("data", "links", "meta") if k in example}
    actual = {k: body[k] for k in ("data", "links", "meta") if k in body}
    assert actual == expected, "actual reply:\n" + json.dumps(actual, indent=1)


def test_every_path_has_an_example():
    examples = {case.values[0] for case in load_examples()}
    assert examples == set(load_spec()["paths"])


@pytest.mark.parametrize(
    "schema,values",
    [
        ("agencyLevel", lambda d: d.levels["agency_level"]),
        ("agencyFunction", lambda d: d.levels["agency_function"]),
        ("linkType", lambda d: d.levels["link_type"]),
        ("oriMatch", lambda d: d.levels["match"]),
        ("county", lambda d: d.counties),
        ("sourceName", lambda d: d.source_names),
    ],
)
def test_spec_vocabularies_are_the_datas(schema, values):
    spec = load_spec()
    assert spec["components"]["schemas"][schema]["enum"] == values(lea_lib.get_data())


def test_county_parameter_covers_the_datas_counties():
    assert [f"{c} County" for c in COUNTIES] == lea_lib.get_data().counties
