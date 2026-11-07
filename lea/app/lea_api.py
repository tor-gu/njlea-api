"""Lambda handler: routes /nj/lea/* events and builds the torguapi replies"""

import traceback
from dataclasses import dataclass
from functools import partial
from http import HTTPStatus

from torguapi import torguapi_http_error, torguapi_make_links_and_meta, torguapi_result

from . import lea_lib as lib
from .params import (
    PAGE_PARAMS,
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

ROOT = "/nj/lea"


@dataclass
class Reply:
    """
    What a route returns.

    records: list of dicts
    aux: for torguapi_make_links_and_meta; without page_number, the links
        have only "self" and there is no meta (single-record replies)
    query_params: the checked query parameters to carry in the links
    url_path: the path of the links, when it isn't the request's (a
        defaulted year links to the explicit one)
    """

    records: list
    aux: dict
    query_params: dict | None = None
    url_path: str | None = None


def make_handler(routes):
    """
    Returns a Lambda handler for routes, a dict of API Gateway resource
    (e.g. "/nj/lea/agencies/{year}") -> function(path, query) returning a
    Reply. path and query are the event's parameters as dicts.
    """

    def handler(event, context):
        resource = event.get("resource")
        route = routes.get(resource)
        if route is None:
            return torguapi_http_error(HTTPStatus.NOT_FOUND, f"No route for {resource}")
        path = path_parameters(event)
        query = query_parameters(event)
        try:
            reply = route(path, query)
            url_path = reply.url_path or resource.format(**path)
            links, meta = torguapi_make_links_and_meta(
                reply.aux, url_path.lstrip("/"), reply.query_params
            )
            return torguapi_result(reply.records, links, meta)
        except InvalidRequest as e:
            return torguapi_http_error(HTTPStatus.BAD_REQUEST, str(e))
        except NotFound as e:
            return torguapi_http_error(HTTPStatus.NOT_FOUND, str(e))
        except Exception:
            traceback.print_exc()
            return torguapi_http_error(
                HTTPStatus.INTERNAL_SERVER_ERROR, "Internal server error"
            )

    return handler


def year_of(data, path):
    """The path's year (404 outside the data's range), or the latest year"""
    if "year" in path:
        return path_year(path["year"], data.min_year, data.max_year)
    return data.max_year


def agency_filters(data):
    return {
        "county": parse_county,
        "agency_level": partial(parse_level, levels=data.levels["agency_level"]),
        "agency_function": partial(parse_level, levels=data.levels["agency_function"]),
    }


def agencies(path, query):
    data = lib.get_data()
    filters = agency_filters(data)
    check_allowed(query, list(filters) + PAGE_PARAMS)
    year = year_of(data, path)
    values, link_params = parse_filters(query, filters)
    records, aux = lib.get_agencies(
        data,
        year,
        page_parameters(query),
        values.get("county"),
        values.get("agency_level"),
        values.get("agency_function"),
    )
    return Reply(records, aux, link_params, f"{ROOT}/agencies/{year}")


def agency(path, query):
    data = lib.get_data()
    check_allowed(query, [])
    year = year_of(data, path)
    agency_id = parse_agency_id("agency_id", path["agency_id"])
    records, aux = lib.get_agency(data, year, agency_id)
    return Reply(records, aux)


def agency_epochs(path, query):
    data = lib.get_data()
    parsers = {"agency_id": parse_agency_id}
    check_allowed(query, list(parsers) + PAGE_PARAMS)
    values, link_params = parse_filters(query, parsers)
    records, aux = lib.get_table(data, "agency", page_parameters(query), values.items())
    return Reply(records, aux, link_params)


def agency_municipalities(path, query):
    data = lib.get_data()
    parsers = {
        "geoid_year": partial(
            query_year, min_year=data.min_geoid_year, max_year=data.max_year
        ),
        "agency_id": parse_agency_id,
        "GEOID": parse_geoid,
    }
    check_allowed(query, list(parsers) + PAGE_PARAMS)
    year = year_of(data, path)
    values, link_params = parse_filters(query, parsers)
    records, aux = lib.get_agency_municipalities(
        data,
        year,
        values.get("geoid_year", year),
        page_parameters(query),
        values.get("agency_id"),
        values.get("GEOID"),
    )
    return Reply(records, aux, link_params, f"{ROOT}/agency_municipalities/{year}")


def aliases(path, query):
    data = lib.get_data()
    parsers = {
        "source": partial(parse_level, levels=data.source_names),
        "agency_id": parse_agency_id,
    }
    check_allowed(query, list(parsers) + PAGE_PARAMS)
    values, link_params = parse_filters(query, parsers)
    records, aux = lib.get_table(
        data, "aliases", page_parameters(query), values.items()
    )
    return Reply(records, aux, link_params)


def oris(path, query):
    data = lib.get_data()
    parsers = {"agency_id": parse_agency_id}
    check_allowed(query, list(parsers) + PAGE_PARAMS)
    values, link_params = parse_filters(query, parsers)
    records, aux = lib.get_table(data, "oris", page_parameters(query), values.items())
    return Reply(records, aux, link_params)


def ori(path, query):
    data = lib.get_data()
    check_allowed(query, [])
    records, aux = lib.get_ori(data, parse_ori("ori", path["ori"]))
    return Reply(records, aux)


def sources(path, query):
    data = lib.get_data()
    check_allowed(query, PAGE_PARAMS)
    records, aux = lib.get_table(data, "sources", page_parameters(query))
    return Reply(records, aux)


def search(path, query):
    data = lib.get_data()
    parsers = {
        "q": parse_search_text,
        "county": parse_county,
        "year": partial(query_year, min_year=data.min_year, max_year=data.max_year),
    }
    check_allowed(query, list(parsers) + PAGE_PARAMS)
    if "q" not in query:
        raise InvalidRequest("Missing query parameter q")
    values, link_params = parse_filters(query, parsers)
    records, aux = lib.search(
        data,
        values["q"],
        page_parameters(query),
        values.get("county"),
        values.get("year"),
    )
    return Reply(records, aux, link_params)


ROUTES = {
    f"{ROOT}/agencies": agencies,
    f"{ROOT}/agencies/{{year}}": agencies,
    f"{ROOT}/agencies/{{year}}/{{agency_id}}": agency,
    f"{ROOT}/agency_epochs": agency_epochs,
    f"{ROOT}/agency_municipalities": agency_municipalities,
    f"{ROOT}/agency_municipalities/{{year}}": agency_municipalities,
    f"{ROOT}/aliases": aliases,
    f"{ROOT}/oris": oris,
    f"{ROOT}/oris/{{ori}}": ori,
    f"{ROOT}/sources": sources,
    f"{ROOT}/search": search,
}

lea_handler = make_handler(ROUTES)
