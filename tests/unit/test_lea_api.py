"""Every route through the handler, on the fixture data (tests/fixtures/data)"""

import pytest

from lea.app import lea_lib
from lea.app.lea_api import lea_handler

from .conftest import call

API = "https://api.example.com/nj/lea"


def get(resource, path=None, query=None):
    status, body = call(resource, path, query)
    assert status == 200, body
    return body


def ids(body):
    return [r["agency_id"] for r in body["data"]]


def agency(agency_id, name, county, level, function, multi=False):
    return {
        "agency_id": agency_id,
        "agency_name": name,
        "county": county,
        "agency_level": level,
        "agency_function": function,
        "multi_municipal": multi,
    }


ABSECON = agency(
    "NJLEA0001", "Absecon Police Department", "Atlantic County", "Municipal", "Police"
)
SOUTH_ORANGE = agency(
    "NJLEA0005",
    "South Orange Police Department",
    "Essex County",
    "Municipal",
    "Police",
)


# /agencies


def test_agencies_in_a_year():
    """In-year epochs by agency_id, names as of the year"""
    body = get("/agencies/{year}", {"year": "2021"})
    assert body["data"] == [
        ABSECON,
        agency(
            "NJLEA0002",
            "Camden County Police Department",
            "Camden County",
            "County",
            "Police",
            multi=True,
        ),
        agency(
            "NJLEA0003",
            "Woodlynne Police Department",
            "Camden County",
            "Municipal",
            "Police",
        ),
        agency(
            "NJLEA0004", "Juvenile Justice Commission", None, "State", "Corrections"
        ),
        SOUTH_ORANGE,
    ]
    assert body["links"] == {"self": f"{API}/agencies/2021?page_number=1&page_size=100"}
    assert body["meta"] == {"page_count": 1, "record_count": 5}


def test_agencies_follow_their_epochs():
    """0003 closes after 2021; 0004 is renamed and 0006 starts in 2022"""
    body = get("/agencies/{year}", {"year": "2022"})
    assert ids(body) == [
        "NJLEA0001",
        "NJLEA0002",
        "NJLEA0004",
        "NJLEA0005",
        "NJLEA0006",
    ]
    assert body["data"][2]["agency_name"] == "Youth Justice Commission"


def test_agencies_default_to_the_latest_year():
    body = get("/agencies")
    assert body["data"] == get("/agencies/{year}", {"year": "2023"})["data"]
    assert body["links"] == {"self": f"{API}/agencies/2023?page_number=1&page_size=100"}


@pytest.mark.parametrize(
    "year,expected",
    [("2020", False), ("2021", True), ("2022", True)],
)
def test_multi_municipal_depends_on_the_year(year, expected):
    """0002 has one municipality in 2020, more from 2021 (Home or Service)"""
    status, body = call(
        "/agencies/{year}/{agency_id}", {"year": year, "agency_id": "NJLEA0002"}
    )
    assert status == 200
    assert body["data"][0]["multi_municipal"] is expected


def test_multi_municipal_is_false_for_one_municipality_linked_twice():
    """0003 has Home and Service links to Woodlynne in 2021"""
    body = get(
        "/agencies/{year}/{agency_id}", {"year": "2021", "agency_id": "NJLEA0003"}
    )
    assert body["data"][0]["multi_municipal"] is False


def test_multi_municipal_is_false_without_links():
    body = get(
        "/agencies/{year}/{agency_id}", {"year": "2023", "agency_id": "NJLEA0004"}
    )
    assert body["data"][0]["multi_municipal"] is False


@pytest.mark.parametrize(
    "query,expected",
    [
        ({"county": "Essex"}, ["NJLEA0005", "NJLEA0006"]),
        ({"county": "essex county"}, ["NJLEA0005", "NJLEA0006"]),
        ({"agency_level": "State"}, ["NJLEA0004"]),
        ({"agency_function": "Sheriff"}, ["NJLEA0006"]),
        ({"county": "Essex", "agency_function": "Police"}, ["NJLEA0005"]),
    ],
)
def test_agency_filters(query, expected):
    assert ids(get("/agencies/{year}", {"year": "2022"}, query)) == expected


def test_links_carry_the_filters_as_given():
    body = get(
        "/agencies/{year}",
        {"year": "2022"},
        {"county": "camden", "agency_level": "County"},
    )
    assert ids(body) == ["NJLEA0002"]
    assert body["links"] == {
        "self": f"{API}/agencies/2022?agency_level=County&county=camden"
        "&page_number=1&page_size=100"
    }


def test_filters_with_no_match_are_404():
    status, body = call("/agencies", None, {"county": "Bergen"})
    assert status == 404
    assert body["errors"][0] == {"status": "404", "detail": "No matching records"}


# Paging


def test_pages():
    query = {"page_size": "2"}
    url = f"{API}/agencies/2022?page_number=%d&page_size=2"
    first = get("/agencies/{year}", {"year": "2022"}, query)
    assert ids(first) == ["NJLEA0001", "NJLEA0002"]
    assert first["links"] == {"self": url % 1, "next": url % 2}
    assert first["meta"] == {"page_count": 3, "record_count": 5}

    middle = get("/agencies/{year}", {"year": "2022"}, {**query, "page_number": "2"})
    assert ids(middle) == ["NJLEA0004", "NJLEA0005"]
    assert middle["links"] == {
        "self": url % 2,
        "previous": url % 1,
        "next": url % 3,
    }

    last = get("/agencies/{year}", {"year": "2022"}, {**query, "page_number": "3"})
    assert ids(last) == ["NJLEA0006"]
    assert last["links"] == {"self": url % 3, "previous": url % 2}


def test_page_past_the_last_is_404():
    status, body = call("/agencies", None, {"page_size": "2", "page_number": "4"})
    assert status == 404
    assert body["errors"][0]["detail"] == "Page number 4 not found"


@pytest.mark.parametrize("page_size", ["0", "x", "-1", "", "²", "9" * 5000])
def test_invalid_page_size_is_400(page_size):
    assert call("/agencies", None, {"page_size": page_size})[0] == 400


@pytest.mark.parametrize("page_number", ["0", "x", "-1", "", "²", "9" * 5000])
def test_invalid_page_number_is_400(page_number):
    assert call("/agencies", None, {"page_number": page_number})[0] == 400


# /agencies/{year}/{agency_id}


def test_agency():
    status, body = call(
        "/agencies/{year}/{agency_id}", {"year": "2022", "agency_id": "NJLEA0005"}
    )
    assert status == 200
    assert body["data"] == [SOUTH_ORANGE]
    assert body["links"] == {"self": f"{API}/agencies/2022/NJLEA0005"}
    assert "meta" not in body


@pytest.mark.parametrize(
    "year,agency_id,status,detail",
    [
        ("2021", "NJLEA0006", 404, "Agency NJLEA0006 not found in 2021"),
        ("2022", "NJLEA0003", 404, "Agency NJLEA0003 not found in 2022"),
        ("2022", "NJLEA9999", 404, "Agency NJLEA9999 not found in 2022"),
        ("2019", "NJLEA0001", 404, "Year 2019 not found"),
        ("x", "NJLEA0001", 400, "Invalid year x"),
        ("2022", "bad", 400, "Invalid agency_id bad (expected NJLEA and 4 digits)"),
    ],
)
def test_agency_errors(year, agency_id, status, detail):
    actual, body = call(
        "/agencies/{year}/{agency_id}", {"year": year, "agency_id": agency_id}
    )
    assert actual == status
    assert body["errors"][0] == {"status": str(status), "detail": detail}


# /agency_epochs


def test_agency_epochs():
    body = get("/agency_epochs")
    assert body["meta"] == {"page_count": 1, "record_count": 7}
    # The table's own order
    assert ids(body)[-2:] == ["NJLEA0006", "NJLEA0005"]


def test_agency_epochs_for_one_agency():
    body = get("/agency_epochs", None, {"agency_id": "NJLEA0004"})
    assert body["data"] == [
        {
            "agency_id": "NJLEA0004",
            "first_year": 2020,
            "final_year": 2021,
            "agency_name": "Juvenile Justice Commission",
            "county": None,
            "agency_level": "State",
            "agency_function": "Corrections",
            "note": None,
        },
        {
            "agency_id": "NJLEA0004",
            "first_year": 2022,
            "final_year": None,
            "agency_name": "Youth Justice Commission",
            "county": None,
            "agency_level": "State",
            "agency_function": "Corrections",
            "note": "Renamed in 2022",
        },
    ]
    assert body["links"] == {
        "self": f"{API}/agency_epochs?agency_id=NJLEA0004&page_number=1&page_size=100"
    }


# /agency_municipalities


def link(agency_id, geoid, municipality, county, link_type="Home"):
    return {
        "agency_id": agency_id,
        "GEOID": geoid,
        "municipality": municipality,
        "county": county,
        "link_type": link_type,
    }


CAMDEN = link("NJLEA0002", "3400710000", "Camden city", "Camden County")
WOODLYNNE = link(
    "NJLEA0002", "3400782450", "Woodlynne borough", "Camden County", "Service"
)


def links(year, query=None):
    return get("/agency_municipalities/{year}", {"year": str(year)}, query)


def test_links_in_a_year_in_order():
    """agency_id, then Home before Service (not file order), then GEOID"""
    assert links(2021)["data"] == [
        link("NJLEA0001", "3400100100", "Absecon city", "Atlantic County"),
        CAMDEN,
        link(
            "NJLEA0002",
            "3400758920",
            "Pine Valley borough",
            "Camden County",
            "Service",
        ),
        WOODLYNNE,
        link("NJLEA0003", "3400782450", "Woodlynne borough", "Camden County"),
        link(
            "NJLEA0003",
            "3400782450",
            "Woodlynne borough",
            "Camden County",
            "Service",
        ),
        link(
            "NJLEA0005",
            "3401369274",
            "South Orange Village township",
            "Essex County",
        ),
    ]


def test_links_follow_their_years():
    assert [r["agency_id"] for r in links(2020)["data"]] == [
        "NJLEA0001",
        "NJLEA0002",
        "NJLEA0003",
        "NJLEA0005",
    ]
    assert links(2022, {"agency_id": "NJLEA0002"})["data"] == [CAMDEN, WOODLYNNE]


def test_links_default_to_the_latest_year():
    body = get("/agency_municipalities")
    assert body["data"] == links(2023)["data"]
    assert body["links"] == {
        "self": f"{API}/agency_municipalities/2023?page_number=1&page_size=100"
    }


def test_geoid_year_defaults_to_the_year():
    """South Orange's GEOID and name both change in 2023"""
    query = {"agency_id": "NJLEA0005"}
    assert links(2022, query)["data"] == [
        link(
            "NJLEA0005",
            "3401369274",
            "South Orange Village township",
            "Essex County",
        )
    ]
    assert links(2023, query)["data"] == [
        link("NJLEA0005", "3401369270", "South Orange village", "Essex County")
    ]


def test_geoid_year_changes_the_geoid_but_not_the_name():
    assert links(2022, {"agency_id": "NJLEA0005", "geoid_year": "2023"})["data"] == [
        link(
            "NJLEA0005",
            "3401369270",
            "South Orange Village township",
            "Essex County",
        )
    ]
    body = links(2023, {"agency_id": "NJLEA0005", "geoid_year": "2000"})
    assert body["data"] == [
        link("NJLEA0005", "3401369274", "South Orange village", "Essex County")
    ]
    assert body["links"] == {
        "self": f"{API}/agency_municipalities/2023?agency_id=NJLEA0005"
        "&geoid_year=2000&page_number=1&page_size=100"
    }


def test_no_geoid_in_the_geoid_year_is_null_and_last():
    """Pine Valley ends in 2021, so its GEOID in 2023 is null: last, not first"""
    assert links(2021, {"agency_id": "NJLEA0002", "geoid_year": "2023"})["data"] == [
        CAMDEN,
        WOODLYNNE,
        link("NJLEA0002", None, "Pine Valley borough", "Camden County", "Service"),
    ]


def test_geoid_filter_uses_the_geoid_year():
    assert links(2023, {"GEOID": "3401369270"})["meta"]["record_count"] == 1
    status, _ = call(
        "/agency_municipalities/{year}", {"year": "2023"}, {"GEOID": "3401369274"}
    )
    assert status == 404
    body = links(2023, {"GEOID": "3401369274", "geoid_year": "2000"})
    assert [r["agency_id"] for r in body["data"]] == ["NJLEA0005"]
    assert body["links"]["self"].startswith(
        f"{API}/agency_municipalities/2023?GEOID=3401369274&geoid_year=2000&"
    )


def test_geoid_year_range():
    assert links(2023, {"geoid_year": "2000"})["meta"]["record_count"] == 4
    for geoid_year in ["1999", "2024", "x"]:
        status, body = call(
            "/agency_municipalities/{year}",
            {"year": "2023"},
            {"geoid_year": geoid_year},
        )
        assert status == 400
        assert body["errors"][0]["detail"] == (
            f"Invalid geoid_year {geoid_year} (expected 2000 to 2023)"
        )


# /aliases


def test_aliases_in_table_order():
    body = get("/aliases")
    assert body["meta"]["record_count"] == 8
    assert body["data"][0] == {
        "source": "source-a",
        "source_county": "Atlantic",
        "source_name": "Absecon City PD",
        "agency_id": "NJLEA0001",
        "first_year": None,
        "final_year": None,
        "source_type": "Municipal",
    }


def test_aliases_filters():
    assert get("/aliases", None, {"source": "source-b"})["meta"]["record_count"] == 4
    assert (
        get("/aliases", None, {"agency_id": "NJLEA0003"})["meta"]["record_count"] == 3
    )
    body = get("/aliases", None, {"source": "source-a", "agency_id": "NJLEA0003"})
    assert [r["source_name"] for r in body["data"]] == ["Woodlynne PD"]
    assert body["links"] == {
        "self": f"{API}/aliases?agency_id=NJLEA0003&source=source-a"
        "&page_number=1&page_size=100"
    }


# /oris


def test_oris():
    assert [r["ori"] for r in get("/oris")["data"]] == [
        "NJ0010100",
        "NJ0041800",
        "NJ0040000",
        "NJDOC0000",
    ]
    body = get("/oris", None, {"agency_id": "NJLEA0002"})
    assert [r["ori"] for r in body["data"]] == ["NJ0041800", "NJ0040000"]


def test_ori():
    status, body = call("/oris/{ori}", {"ori": "NJ0040000"})
    assert status == 200
    assert body["data"] == [
        {
            "agency_id": "NJLEA0002",
            "ori": "NJ0040000",
            "GEOID_Y2K": "3400710000",
            "first_year": 2020,
            "final_year": 2021,
            "match": "Hand",
            "note": None,
        }
    ]
    assert body["links"] == {"self": f"{API}/oris/NJ0040000"}
    assert "meta" not in body


# /sources


def test_sources():
    body = get("/sources")
    assert body["data"] == [
        {
            "source": "source-a",
            "title": "Source A",
            "url": "https://example.com/a",
            "coverage": "2021",
            "retrieved": "2026-01-02",
        },
        {
            "source": "source-b",
            "title": "Source B",
            "url": None,
            "coverage": "2021-2025",
            "retrieved": None,
        },
    ]
    assert body["meta"] == {"page_count": 1, "record_count": 2}


# /search


def found(query):
    """(agency_id, agency_name, matched_on, matched_text) of the replies"""
    body = get("/search", None, query)
    return [
        (r["agency_id"], r["agency_name"], r["matched_on"], r["matched_text"])
        for r in body["data"]
    ]


def test_search_record_and_links():
    body = get("/search", None, {"q": "absecon city", "county": "atlantic"})
    assert body["data"][0] == {
        "agency_id": "NJLEA0001",
        "agency_name": "Absecon Police Department",
        "county": "Atlantic County",
        "matched_on": "source-a",
        "matched_text": "Absecon City PD",
    }
    assert body["links"] == {
        "self": f"{API}/search?county=atlantic&q=absecon%20city"
        "&page_number=1&page_size=100"
    }


def test_search_is_case_insensitive_and_ordered():
    """agency_id, then the name before the aliases, by source"""
    assert found({"q": "WOODLYNNE"}) == [
        (
            "NJLEA0003",
            "Woodlynne Police Department",
            "name",
            "Woodlynne Police Department",
        ),
        ("NJLEA0003", "Woodlynne Police Department", "source-a", "Woodlynne PD"),
        # source-b has this text for two counties: one row
        ("NJLEA0003", "Woodlynne Police Department", "source-b", "Woodlynne PD"),
    ]
    assert [(r[0], r[2]) for r in found({"q": "pd"})] == [
        ("NJLEA0001", "source-a"),
        ("NJLEA0001", "source-b"),
        ("NJLEA0002", "source-a"),
        ("NJLEA0003", "source-a"),
        ("NJLEA0003", "source-b"),
    ]


def test_search_county():
    assert {r[0] for r in found({"q": "pd", "county": "Camden County"})} == {
        "NJLEA0002",
        "NJLEA0003",
    }
    assert call("/search", None, {"q": "pd", "county": "Bergen"})[0] == 404


def test_search_without_a_year_shows_current_names_and_finds_former_ones():
    assert found({"q": "juvenile"}) == [
        (
            "NJLEA0004",
            "Youth Justice Commission",
            "name",
            "Juvenile Justice Commission",
        ),
        ("NJLEA0004", "Youth Justice Commission", "source-b", "Juvenile Justice Comm"),
    ]


def test_search_with_a_year_uses_the_names_of_that_year():
    assert found({"q": "juvenile", "year": "2020"}) == [
        (
            "NJLEA0004",
            "Juvenile Justice Commission",
            "name",
            "Juvenile Justice Commission",
        ),
        (
            "NJLEA0004",
            "Juvenile Justice Commission",
            "source-b",
            "Juvenile Justice Comm",
        ),
    ]
    # The former name no longer matches, the alias still does
    assert found({"q": "juvenile", "year": "2022"}) == [
        ("NJLEA0004", "Youth Justice Commission", "source-b", "Juvenile Justice Comm"),
    ]
    assert call("/search", None, {"q": "youth", "year": "2021"})[0] == 404


def test_search_with_a_year_needs_the_agency_to_exist_then():
    assert call("/search", None, {"q": "sheriff", "year": "2021"})[0] == 404
    assert len(found({"q": "sheriff", "year": "2022"})) == 2
    assert call("/search", None, {"q": "woodlynne", "year": "2022"})[0] == 404


@pytest.mark.parametrize("q", [".", ".*", "(", "[a-z]", "^Absecon", "pd|police"])
def test_search_text_is_not_a_regex(q):
    status, body = call("/search", None, {"q": q})
    assert status == 404
    assert body["errors"][0]["detail"] == "No matching records"


def test_search_length_limit():
    assert call("/search", None, {"q": "x" * 100})[0] == 404
    assert call("/search", None, {"q": "x" * 101})[0] == 400


@pytest.mark.parametrize(
    "query,detail",
    [
        (None, "Missing query parameter q"),
        ({"county": "Camden"}, "Missing query parameter q"),
        ({"q": ""}, "Empty q"),
        ({"q": "pd", "year": "2019"}, "Invalid year 2019 (expected 2020 to 2023)"),
        ({"q": "pd", "year": "x"}, "Invalid year x (expected 2020 to 2023)"),
        ({"q": "pd", "county": "Nowhere"}, "Invalid county Nowhere"),
    ],
)
def test_search_errors(query, detail):
    status, body = call("/search", None, query)
    assert status == 400
    assert body["errors"][0] == {"status": "400", "detail": detail}


# Errors common to the routes


@pytest.mark.parametrize(
    "resource", ["/agencies/{year}", "/agency_municipalities/{year}"]
)
@pytest.mark.parametrize(
    "year,status,detail",
    [
        ("2019", 404, "Year 2019 not found"),
        ("2024", 404, "Year 2024 not found"),
        ("x", 400, "Invalid year x"),
        ("2020.0", 400, "Invalid year 2020.0"),
        ("٢٠٢٠", 400, "Invalid year ٢٠٢٠"),
    ],
)
def test_path_years(resource, year, status, detail):
    actual, body = call(resource, {"year": year})
    assert actual == status
    assert body["errors"][0] == {"status": str(status), "detail": detail}


def test_large_page_values_are_handled():
    """As many digits as int() takes: a page past the end, and a page of everything"""
    large = "9" * 4000
    assert call("/agencies", None, {"page_number": large})[0] == 404
    assert call("/agencies", None, {"page_size": large})[0] == 200


def test_huge_years():
    """Numeric, so not found in the path and out of range as a parameter"""
    huge = "9" * 5000
    assert call("/agencies/{year}", {"year": huge})[0] == 404
    assert call("/agency_municipalities", None, {"geoid_year": huge})[0] == 400
    assert call("/search", None, {"q": "pd", "year": huge})[0] == 400


@pytest.mark.parametrize(
    "resource,path",
    [
        ("/agencies", None),
        ("/agencies/{year}", {"year": "2021"}),
        ("/agencies/{year}/{agency_id}", {"year": "2021", "agency_id": "NJLEA0001"}),
        ("/agency_epochs", None),
        ("/agency_municipalities", None),
        ("/agency_municipalities/{year}", {"year": "2021"}),
        ("/aliases", None),
        ("/oris", None),
        ("/oris/{ori}", {"ori": "NJ0010100"}),
        ("/sources", None),
    ],
)
def test_unknown_parameter_is_400_on_every_route(resource, path):
    status, body = call(resource, path, {"colour": "red"})
    assert status == 400
    assert body["errors"][0]["detail"] == "Unknown query parameter colour"


def test_unknown_parameter_on_search():
    status, body = call("/search", None, {"q": "pd", "colour": "red"})
    assert status == 400
    assert body["errors"][0]["detail"] == "Unknown query parameter colour"


@pytest.mark.parametrize(
    "resource,path,query",
    [
        ("/agencies", None, {"year": "2021"}),
        ("/agencies", None, {"agency_id": "NJLEA0001"}),
        (
            "/agencies/{year}/{agency_id}",
            {"year": "2021", "agency_id": "NJLEA0001"},
            {"page_size": "1"},
        ),
        ("/agency_municipalities", None, {"year": "2021"}),
        ("/agency_municipalities", None, {"geoid": "3400100100"}),
        ("/oris/{ori}", {"ori": "NJ0010100"}, {"page_size": "1"}),
        ("/sources", None, {"agency_id": "NJLEA0001"}),
    ],
)
def test_parameters_of_other_routes_are_400(resource, path, query):
    assert call(resource, path, query)[0] == 400


@pytest.mark.parametrize(
    "resource,path,query",
    [
        ("/agency_epochs", None, {"agency_id": "bad"}),
        ("/agency_municipalities", None, {"agency_id": "bad"}),
        ("/agency_municipalities", None, {"GEOID": "123"}),
        ("/aliases", None, {"agency_id": "bad"}),
        ("/aliases", None, {"source": "nope"}),
        ("/agencies", None, {"county": "Nowhere"}),
        ("/agencies", None, {"agency_level": "county"}),
        ("/agencies", None, {"agency_function": "police"}),
        ("/oris", None, {"agency_id": "bad"}),
        ("/oris/{ori}", {"ori": "bad"}, None),
    ],
)
def test_invalid_values_are_400(resource, path, query):
    assert call(resource, path, query)[0] == 400


def test_trailing_newline_is_invalid():
    """Not the same value with a stray character: a 400, not a failed lookup"""
    assert call("/agency_epochs", None, {"agency_id": "NJLEA0001\n"})[0] == 400
    assert call("/oris/{ori}", {"ori": "NJ0010100\n"})[0] == 400
    assert call("/agency_municipalities", None, {"GEOID": "3400100100\n"})[0] == 400


def test_unknown_ids_are_404():
    assert call("/agency_epochs", None, {"agency_id": "NJLEA9999"})[0] == 404
    assert call("/aliases", None, {"agency_id": "NJLEA9999"})[0] == 404
    assert call("/oris", None, {"agency_id": "NJLEA9999"})[0] == 404
    status, body = call("/oris/{ori}", {"ori": "NJ9999999"})
    assert status == 404
    assert body["errors"][0]["detail"] == "ORI NJ9999999 not found"


def test_unknown_resource_is_404():
    assert call("/nowhere")[0] == 404
    assert int(lea_handler({}, None)["statusCode"]) == 404


def test_internal_errors_are_500_without_details(monkeypatch, capsys):
    def fail(*args):
        raise RuntimeError("something private")

    monkeypatch.setattr(lea_lib, "get_agencies", fail)
    status, body = call("/agencies")
    assert status == 500
    assert body["errors"][0] == {"status": "500", "detail": "Internal server error"}
    assert "something private" in capsys.readouterr().err  # in the logs only


def test_repeated_requests_agree():
    """The second reply comes from the caches"""
    query = {"q": "pd", "county": "Camden"}
    assert get("/search", None, query) == get("/search", None, query)
    assert links(2021) == links(2021)
    assert get("/agencies") == get("/agencies")
    assert get("/oris") == get("/oris")


def test_data_is_loaded_once():
    assert lea_lib.get_data() is lea_lib.get_data()
