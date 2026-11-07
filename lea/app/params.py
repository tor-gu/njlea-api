"""Request parameters: errors, paging, years and the filter vocabularies"""

import re

from torguapi import TorguapiInvalidRequest, torguapi_get_page_parameters


class InvalidRequest(Exception):
    """A bad request (400)"""

    pass


class NotFound(Exception):
    """Nothing matches the request (404)"""

    pass


# As njlea:::county_name
COUNTIES = [
    "Atlantic",
    "Bergen",
    "Burlington",
    "Camden",
    "Cape May",
    "Cumberland",
    "Essex",
    "Gloucester",
    "Hudson",
    "Hunterdon",
    "Mercer",
    "Middlesex",
    "Monmouth",
    "Morris",
    "Ocean",
    "Passaic",
    "Salem",
    "Somerset",
    "Sussex",
    "Union",
    "Warren",
]
_COUNTY_KEYS = {c.lower(): f"{c} County" for c in COUNTIES}
_COUNTY_SUFFIX = re.compile(r"\s+county$", re.I)

PAGE_PARAMS = ["page_number", "page_size"]

AGENCY_ID_PATTERN = re.compile(r"^NJLEA[0-9]{4}$")
ORI_PATTERN = re.compile(r"^[A-Z]{2}[0-9A-Z]{7}$")
GEOID_PATTERN = re.compile(r"^34[0-9]{8}$")

MAX_QUERY_LENGTH = 100
MAX_YEAR_DIGITS = 9


def query_parameters(event):
    """The event's query parameters as a dict (never None)"""
    return event.get("queryStringParameters") or {}


def path_parameters(event):
    """The event's path parameters as a dict (never None)"""
    return event.get("pathParameters") or {}


def check_allowed(query, allowed):
    """InvalidRequest for any query parameter not in allowed"""
    unknown = sorted(set(query) - set(allowed))
    if unknown:
        raise InvalidRequest(f"Unknown query parameter {unknown[0]}")


def page_parameters(query):
    """page_number (default 1) and page_size (default 100) as ints"""
    try:
        params = torguapi_get_page_parameters(query)
    except TorguapiInvalidRequest as e:
        raise InvalidRequest(str(e))
    params.setdefault("page_number", 1)
    if params["page_number"] < 1:
        raise InvalidRequest(f"Invalid page_number {query.get('page_number')}")
    return params


def is_int(value):
    return value.isascii() and value.isdigit()


def year_in_range(value, min_year, max_year):
    """value (digits) is in range. int() refuses thousands of digits, hence the length"""
    return len(value) <= MAX_YEAR_DIGITS and min_year <= int(value) <= max_year


def path_year(value, min_year, max_year):
    """
    A year in the path, as njmunicipalities-api: not a number is a 400, a
    year outside min_year..max_year a 404 (no such resource)
    """
    if not is_int(value):
        raise InvalidRequest(f"Invalid year {value}")
    if not year_in_range(value, min_year, max_year):
        raise NotFound(f"Year {value} not found")
    return int(value)


def query_year(name, value, min_year, max_year):
    """A year given as a query parameter: anything outside the range is a 400"""
    if not is_int(value) or not year_in_range(value, min_year, max_year):
        raise InvalidRequest(
            f"Invalid {name} {value} (expected {min_year} to {max_year})"
        )
    return int(value)


def parse_county(name, value):
    """'Atlantic' or 'Atlantic County' (any case) -> 'Atlantic County'"""
    county = _COUNTY_KEYS.get(_COUNTY_SUFFIX.sub("", value.strip()).lower())
    if county is None:
        raise InvalidRequest(f"Invalid {name} {value}")
    return county


def parse_level(name, value, levels):
    if value not in levels:
        raise InvalidRequest(
            f"Invalid {name} {value} (expected one of {', '.join(levels)})"
        )
    return value


def parse_agency_id(name, value):
    if not AGENCY_ID_PATTERN.fullmatch(value):
        raise InvalidRequest(f"Invalid {name} {value} (expected NJLEA and 4 digits)")
    return value


def parse_ori(name, value):
    if not ORI_PATTERN.fullmatch(value):
        raise InvalidRequest(
            f"Invalid {name} {value} (expected 2 letters and 7 digits or capitals)"
        )
    return value


def parse_geoid(name, value):
    if not GEOID_PATTERN.fullmatch(value):
        raise InvalidRequest(f"Invalid {name} {value} (expected 34 and 8 digits)")
    return value


def parse_search_text(name, value):
    if value == "":
        raise InvalidRequest(f"Empty {name}")
    if len(value) > MAX_QUERY_LENGTH:
        raise InvalidRequest(f"{name} is longer than {MAX_QUERY_LENGTH} characters")
    return value


def parse_filters(query, parsers):
    """
    Checks and converts the query parameters that parsers names.

    Args:
        query: the query parameters
        parsers: dict of parameter name -> function(name, value)

    Returns:
        dict of the given parameters, converted
        dict of the same parameters as given, for the links (only parameters
        that were checked, as torguapi_make_links_and_meta asks)
    """
    values = {}
    link_params = {}
    for name, parse in parsers.items():
        if name in query:
            values[name] = parse(name, query[name])
            link_params[name] = query[name]
    return values, link_params
