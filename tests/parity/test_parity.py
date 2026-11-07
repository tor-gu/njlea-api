"""
The API against R, on the full data (make data).

tests/parity/expected holds R's get_agencies(year) and
get_agency_municipalities(year, geoid_year) for every combination (written by
scripts/export_data.R). The handler must reproduce each one through its paged
replies: the same rows, order and values.

To keep the expected file small, municipality and county are stored only where
geoid_year == year, so they are compared only there: they depend on the year
alone. Logicals are TRUE/FALSE and NA is an empty field.
"""

import csv
import gzip
import json
import os
from collections import defaultdict

import pytest

from lea.app import lea_lib
from lea.app.lea_api import lea_handler

EXPECTED = os.path.join(os.path.dirname(__file__), "expected")


def load(name, *keys):
    """The rows of an expected file, as lists of dicts grouped by keys (ints)"""
    tables = defaultdict(list)
    path = os.path.join(EXPECTED, f"{name}.csv.gz")
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            tables[tuple(int(row.pop(k)) for k in keys)].append(row)
    return dict(tables)


AGENCIES = load("agencies", "year")
LINKS = load("agency_municipalities", "year", "geoid_year")


def as_csv(value):
    """A value of the reply as R's write.csv wrote it"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)


def all_pages(resource, year, query=None):
    """Every record of the route, following its next links"""
    records = []
    page_number = 1
    while True:
        reply = lea_handler(
            {
                "resource": f"/nj/lea{resource}",
                "pathParameters": {"year": str(year)},
                "queryStringParameters": {
                    **(query or {}),
                    "page_number": str(page_number),
                },
            },
            None,
        )
        body = json.loads(reply["body"])
        assert reply["statusCode"] == 200, body
        records += body["data"]
        if "next" not in body["links"]:
            assert body["meta"]["record_count"] == len(records)
            assert body["meta"]["page_count"] == page_number
            return records
        page_number += 1


def compare(records, expected, columns):
    assert [[as_csv(r[c]) for c in columns] for r in records] == [
        [r[c] for c in columns] for r in expected
    ]


@pytest.mark.parametrize("year", sorted(k[0] for k in AGENCIES))
def test_get_agencies(year):
    expected = AGENCIES[(year,)]
    records = all_pages("/agencies/{year}", year)
    assert set(records[0]) == set(expected[0])
    compare(records, expected, list(expected[0]))


@pytest.mark.parametrize("year,geoid_year", sorted(LINKS))
def test_get_agency_municipalities(year, geoid_year):
    expected = LINKS[(year, geoid_year)]
    records = all_pages(
        "/agency_municipalities/{year}", year, {"geoid_year": str(geoid_year)}
    )
    assert set(records[0]) == set(expected[0])
    columns = ["agency_id", "GEOID", "link_type"]
    if year == geoid_year:
        columns += ["municipality", "county"]
    compare(records, expected, columns)


def test_expected_files_cover_every_year():
    """So that a truncated or stale file can't pass by testing less"""
    data = lea_lib.get_data()
    years = range(data.min_year, data.max_year + 1)
    geoid_years = range(data.min_geoid_year, data.max_year + 1)
    assert set(AGENCIES) == {(y,) for y in years}
    assert set(LINKS) == {(y, gy) for y in years for gy in geoid_years}


def test_expected_municipality_and_county_are_kept_only_where_compared():
    for (year, geoid_year), rows in LINKS.items():
        stored = any(r["municipality"] or r["county"] for r in rows)
        assert stored == (year == geoid_year), (year, geoid_year)
