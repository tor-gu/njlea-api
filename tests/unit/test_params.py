import pytest

from lea.app.params import (
    COUNTIES,
    InvalidRequest,
    NotFound,
    check_allowed,
    page_parameters,
    parse_agency_id,
    parse_county,
    parse_filters,
    parse_geoid,
    parse_level,
    parse_ori,
    parse_search_text,
    path_parameters,
    path_year,
    query_parameters,
    query_year,
)


def test_event_parameters_are_never_none():
    event = {"queryStringParameters": None, "pathParameters": None}
    assert query_parameters(event) == {}
    assert path_parameters(event) == {}
    assert query_parameters({}) == {}
    assert path_parameters({}) == {}


def test_check_allowed():
    check_allowed({"year": "2021"}, ["year"])
    check_allowed({}, [])
    with pytest.raises(InvalidRequest, match="Unknown query parameter colour"):
        check_allowed({"year": "2021", "colour": "red"}, ["year"])


def test_page_parameters():
    assert page_parameters({}) == {"page_number": 1, "page_size": 100}
    assert page_parameters({"page_number": "3", "page_size": "7"}) == {
        "page_number": 3,
        "page_size": 7,
    }


@pytest.mark.parametrize("name", ["page_number", "page_size"])
@pytest.mark.parametrize("value", ["0", "x", "-1", "1.5", "", "²", "9" * 5000])
def test_page_parameters_invalid(name, value):
    with pytest.raises(InvalidRequest):
        page_parameters({name: value})


def test_path_year():
    assert path_year("2020", 2020, 2026) == 2020
    assert path_year("2026", 2020, 2026) == 2026
    for year in ["2019", "2027", "0", "9" * 5000]:
        with pytest.raises(NotFound):
            path_year(year, 2020, 2026)
    for year in ["x", "", "-2021", "2021.0", "٢٠٢١"]:
        with pytest.raises(InvalidRequest):
            path_year(year, 2020, 2026)


def test_query_year():
    assert query_year("year", "2000", 2000, 2026) == 2000
    assert query_year("year", "2026", 2000, 2026) == 2026
    for year in ["1999", "2027", "x", "", "-2021", "٢٠٢١", "9" * 5000]:
        with pytest.raises(InvalidRequest, match="expected 2000 to 2026"):
            query_year("year", year, 2000, 2026)


@pytest.mark.parametrize(
    "value",
    [
        "Cape May",
        "Cape May County",
        "cape may",
        "CAPE MAY COUNTY",
        " cape may  county ",
    ],
)
def test_parse_county(value):
    assert parse_county("county", value) == "Cape May County"


@pytest.mark.parametrize("value", ["", "County", "Nowhere", "Cape May County County"])
def test_parse_county_invalid(value):
    with pytest.raises(InvalidRequest, match="Invalid county"):
        parse_county("county", value)


def test_every_county_parses():
    assert len(COUNTIES) == 21
    for county in COUNTIES:
        assert parse_county("county", county) == f"{county} County"


def test_parse_level():
    assert parse_level("agency_level", "State", ["County", "State"]) == "State"
    with pytest.raises(InvalidRequest, match="expected one of County, State"):
        parse_level("agency_level", "state", ["County", "State"])


@pytest.mark.parametrize(
    "parse,valid,invalid",
    [
        (
            parse_agency_id,
            "NJLEA0199",
            [
                "",
                "NJLEA199",
                "NJLEA01999",
                "njlea0199",
                "NJLEA١٢٣٤",
                "NJLEA0199\n",
            ],
        ),
        (
            parse_ori,
            "NJ0073000",
            ["", "NJ007300", "NJ00730000", "nj0073000", "NJ00730a0", "NJ0073000\n"],
        ),
        (
            parse_geoid,
            "3401369270",
            [
                "",
                "340136927",
                "34013692700",
                "3601369270",
                "34013a9270",
                "3401369270\n",
            ],
        ),
    ],
)
def test_identifiers(parse, valid, invalid):
    assert parse("x", valid) == valid
    for value in invalid:
        with pytest.raises(InvalidRequest):
            parse("x", value)


def test_parse_search_text():
    assert parse_search_text("q", "a") == "a"
    assert parse_search_text("q", "x" * 100) == "x" * 100
    with pytest.raises(InvalidRequest, match="Empty q"):
        parse_search_text("q", "")
    with pytest.raises(InvalidRequest, match="longer than 100"):
        parse_search_text("q", "x" * 101)


def test_parse_filters():
    values, link_params = parse_filters(
        {"county": "camden", "page_size": "5", "colour": "red"},
        {"county": parse_county, "agency_id": parse_agency_id},
    )
    # Converted for use; as given, and only checked ones, for the links
    assert values == {"county": "Camden County"}
    assert link_params == {"county": "camden"}
