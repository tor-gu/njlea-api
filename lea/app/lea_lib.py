"""
The registry, from lea/data/njlea.json (see scripts/build_data.py).

The file is loaded on first use and kept while the function is warm. Rows stay
lists, as stored; a route selects row indexes (cached by its validated
parameters, since the data never changes while warm) and makes dicts only for
the page it returns.
"""

import json
import os
from functools import lru_cache

from .params import NotFound

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DATA_FILE = "njlea.json"

AGENCY_COLUMNS = [
    "agency_id",
    "agency_name",
    "county",
    "agency_level",
    "agency_function",
    "multi_municipal",
]
LINK_COLUMNS = ["agency_id", "GEOID", "municipality", "county", "link_type"]
SEARCH_COLUMNS = ["agency_id", "agency_name", "county", "matched_on", "matched_text"]

# Enough for every (year, geoid_year) and the usual filter combinations
CACHE_SIZE = 512

# Loaded on first use and kept while the function is warm
_data = None


def get_data():
    global _data
    if _data is None:
        _data = LeaData(os.environ.get("DATA_DIR", DEFAULT_DATA_DIR))
    return _data


class Table:
    """A table of njlea.json: its columns and rows (lists)"""

    def __init__(self, table):
        self.columns = table["columns"]
        self.rows = table["rows"]
        self.index = {c: i for i, c in enumerate(self.columns)}

    def col(self, name):
        return self.index[name]

    def record(self, i):
        return dict(zip(self.columns, self.rows[i]))


class LeaData:
    def __init__(self, data_dir):
        with open(os.path.join(data_dir, DATA_FILE), encoding="utf-8") as f:
            d = json.load(f)
        self.source = d["source"]
        self.min_year = d["min_year"]
        self.max_year = d["max_year"]
        self.min_geoid_year = d["min_geoid_year"]
        self.levels = d["levels"]
        self.counties = d["counties"]
        self.agency = Table(d["tables"]["agency"])
        self.links = Table(d["tables"]["agency_municipality"])
        self.aliases = Table(d["tables"]["agency_alias"])
        self.oris = Table(d["tables"]["agency_ori"])
        self.sources = Table(d["tables"]["alias_source"])
        self.munis = Table(d["tables"]["municipalities"])
        self.years = {int(y): v for y, v in d["years"].items()}
        self.geoids = {int(y): v for y, v in d["geoids"].items()}
        self.source_names = [r[self.sources.col("source")] for r in self.sources.rows]
        a = self.oris.col("ori")
        self.ori_rows = {r[a]: i for i, r in enumerate(self.oris.rows)}
        # Per-instance caches, so a new LeaData starts empty
        self.agency_selection = lru_cache(CACHE_SIZE)(self._agency_selection)
        self.link_rows = lru_cache(CACHE_SIZE)(self._link_rows)
        self.link_selection = lru_cache(CACHE_SIZE)(self._link_selection)
        self.search_texts = lru_cache(None)(self._search_texts)
        self.search_selection = lru_cache(CACHE_SIZE)(self._search_selection)
        self.table_selection = lru_cache(CACHE_SIZE)(self._table_selection)

    # get_agencies(year)

    def agency_record(self, entry):
        i, multi = entry
        r = self.agency.record(i)
        return {c: (multi if c == "multi_municipal" else r[c]) for c in AGENCY_COLUMNS}

    def _agency_selection(self, year, county=None, level=None, function=None):
        """The year's [agency row, multi_municipal] entries matching the filters"""
        a = self.agency
        wanted = [
            (a.col("county"), county),
            (a.col("agency_level"), level),
            (a.col("agency_function"), function),
        ]
        wanted = [(c, v) for c, v in wanted if v is not None]
        return tuple(
            tuple(e)
            for e in self.years[year]["agencies"]
            if all(a.rows[e[0]][c] == v for c, v in wanted)
        )

    def agency_in_year(self, year, agency_id):
        """The agency's entry in year, or None"""
        c = self.agency.col("agency_id")
        for e in self.years[year]["agencies"]:
            if self.agency.rows[e[0]][c] == agency_id:
                return tuple(e)
        return None

    # get_agency_municipalities(year, geoid_year)

    def _link_rows(self, year, geoid_year):
        """
        The year's links as output tuples (LINK_COLUMNS), in R's order:
        agency_id, link_type by level order, then GEOID with null last
        """
        lk, m = self.links, self.munis
        geoids = self.geoids[geoid_year]
        type_order = {t: i for i, t in enumerate(self.levels["link_type"])}
        rows = []
        for link, muni in self.years[year]["links"]:
            lr, mr = lk.rows[link], m.rows[muni]
            key = mr[m.col("GEOID_Y2K")]
            rows.append(
                (
                    lr[lk.col("agency_id")],
                    geoids.get(key, key),
                    mr[m.col("municipality")],
                    mr[m.col("county")],
                    lr[lk.col("link_type")],
                )
            )
        rows.sort(key=lambda r: (r[0], type_order[r[4]], r[1] is None, r[1] or ""))
        return tuple(rows)

    def _link_selection(self, year, geoid_year, agency_id=None, geoid=None):
        return tuple(
            r
            for r in self.link_rows(year, geoid_year)
            if (agency_id is None or r[0] == agency_id)
            and (geoid is None or r[1] == geoid)
        )

    # Whole tables

    def _table_selection(self, name, filters=()):
        """Row indexes of a whole table, in its order, where filters (column, value) hold"""
        t = getattr(self, name)
        wanted = [(t.col(c), v) for c, v in filters]
        return tuple(
            i for i, r in enumerate(t.rows) if all(r[c] == v for c, v in wanted)
        )

    # find_agency()

    def _search_texts(self, year=None):
        """
        Every (agency_id, matched_on, matched_text) find_agency() searches,
        distinct and in its order, with the lower-cased text; and the name and
        county shown for each agency
        """
        a, al = self.agency, self.aliases
        aid, name = a.col("agency_id"), a.col("agency_name")
        first = a.col("first_year")
        if year is None:
            epochs = a.rows
            shown = {}
            for r in a.rows:  # the latest epoch (current name)
                if r[aid] not in shown or r[first] > shown[r[aid]][first]:
                    shown[r[aid]] = r
        else:
            epochs = [a.rows[e[0]] for e in self.years[year]["agencies"]]
            shown = {r[aid]: r for r in epochs}
        texts = {(r[aid], "name", r[name]) for r in epochs}
        texts.update(
            (r[al.col("agency_id")], r[al.col("source")], r[al.col("source_name")])
            for r in al.rows
            if r[al.col("agency_id")] in shown
        )
        ordered = sorted(texts, key=lambda t: (t[0], t[1] != "name", t[1], t[2]))
        county = a.col("county")
        return (
            tuple((t, t[2].lower()) for t in ordered),
            {k: (r[name], r[county]) for k, r in shown.items()},
        )

    def _search_selection(self, q, county=None, year=None):
        """find_agency(q, county, year) rows (SEARCH_COLUMNS), q a lower-case substring"""
        texts, shown = self.search_texts(year)
        out = []
        for (agency_id, on, text), lower in texts:
            if q in lower:
                name, agency_county = shown[agency_id]
                if county is None or agency_county == county:
                    out.append((agency_id, name, agency_county, on, text))
        return tuple(out)


def paged(rows, page, convert):
    """
    One page of rows.

    Returns:
        list of records, aux dict for torguapi_make_links_and_meta

    Raises:
        NotFound when there are no rows, or the page is past the last one
    """
    record_count = len(rows)
    page_number, page_size = page["page_number"], page["page_size"]
    if record_count == 0:
        raise NotFound("No matching records")
    page_count = (record_count - 1) // page_size + 1
    if page_number > page_count:
        raise NotFound(f"Page number {page_number} not found")
    start = (page_number - 1) * page_size
    records = [convert(r) for r in rows[start : start + page_size]]
    aux = {
        "page_number": page_number,
        "page_size": page_size,
        "record_count": record_count,
    }
    return records, aux


def get_agencies(data, year, page, county=None, level=None, function=None):
    rows = data.agency_selection(year, county, level, function)
    return paged(rows, page, data.agency_record)


def get_agency(data, year, agency_id):
    entry = data.agency_in_year(year, agency_id)
    if entry is None:
        raise NotFound(f"Agency {agency_id} not found in {year}")
    return [data.agency_record(entry)], {}


def get_agency_municipalities(data, year, geoid_year, page, agency_id=None, geoid=None):
    rows = data.link_selection(year, geoid_year, agency_id, geoid)
    return paged(rows, page, lambda r: dict(zip(LINK_COLUMNS, r)))


def get_table(data, name, page, filters=()):
    """A whole table (agency, aliases, oris, sources), filtered on (column, value)s"""
    rows = data.table_selection(name, tuple(filters))
    return paged(rows, page, getattr(data, name).record)


def get_ori(data, ori):
    i = data.ori_rows.get(ori)
    if i is None:
        raise NotFound(f"ORI {ori} not found")
    return [data.oris.record(i)], {}


def search(data, q, page, county=None, year=None):
    rows = data.search_selection(q.lower(), county, year)
    return paged(rows, page, lambda r: dict(zip(SEARCH_COLUMNS, r)))
