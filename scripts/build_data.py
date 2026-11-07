"""
Build the Lambda's data from the exported tables (make data).

Usage: python scripts/build_data.py [data dir] [repo root]

Reads data/ as written by scripts/export_data.R (<table>.csv, columns.csv,
levels.csv, SOURCE) and writes lea/data/njlea.json under the repo root. Only
the standard library is used.

The data is small (about 3,600 rows), so it is shipped whole as JSON and loaded
once at init. To keep init cheap, rows are lists (column names are given once
per table), and what the routes derive is computed here, once:

  years[y].agencies   get_agencies(y): [agency row index, multi_municipal],
                      ordered by agency_id
  years[y].links      the links held in y: [link row index, municipality row
                      index], the municipality being the njmunicipalities row
                      for that GEOID_Y2K in y
  geoids[gy]          a municipality row's GEOID as of geoid_year gy, for the
                      rows the links use: {row GEOID_Y2K: GEOID}, only where the
                      GEOID differs from the row's GEOID_Y2K; null = no GEOID
                      in gy

This follows njlea::get_agencies() and get_agency_municipalities(), which use
njmunicipalities::get_municipalities(); tests/parity checks the result against
R's own output for every year and geoid_year.
"""

import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict

OUT = os.path.join("lea", "data", "njlea.json")

TABLES = [
    "agency",
    "agency_municipality",
    "agency_alias",
    "agency_ori",
    "alias_source",
    "municipalities",
]

AGENCY_ID = re.compile(r"^NJLEA[0-9]{4}$")
ORI = re.compile(r"^[A-Z]{2}[0-9A-Z]{7}$")
MIN_GEOID_YEAR = 2000


class BuildError(Exception):
    pass


def read_csv(path):
    """Header and rows of a CSV file, as lists of strings"""
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        return header, list(reader)


def read_source(path):
    with open(path, encoding="utf-8") as f:
        return dict(line.rstrip("\n").split("=", 1) for line in f if "=" in line)


def converter(type_, levels):
    if type_ == "integer":
        return lambda v: int(v) if v != "" else None
    if type_ == "factor":

        def factor(v):
            if v == "":
                return None
            if v not in levels:
                raise BuildError(f"{v!r} is not a level ({levels})")
            return v

        return factor
    if type_ in ("character", "date"):
        return lambda v: v if v != "" else None
    raise BuildError(f"unknown column type {type_!r}")


def read_export(data_dir):
    """{table: {"columns": [...], "rows": [[...]]}}, the levels and SOURCE"""
    _, rows = read_csv(os.path.join(data_dir, "columns.csv"))
    types = defaultdict(list)
    for table, _, column, type_ in sorted(rows, key=lambda r: (r[0], int(r[1]))):
        types[table].append((column, type_))
    _, rows = read_csv(os.path.join(data_dir, "levels.csv"))
    levels = defaultdict(list)
    for table, column, _, level in sorted(rows, key=lambda r: (r[0], r[1], int(r[2]))):
        levels[(table, column)].append(level)

    tables = {}
    for table in TABLES:
        if table not in types:
            raise BuildError(f"{table} is not in columns.csv")
        names = [c for c, _ in types[table]]
        header, rows = read_csv(os.path.join(data_dir, f"{table}.csv"))
        if header != names:
            raise BuildError(
                f"{table}: header {header} doesn't match columns.csv {names}"
            )
        convert = [converter(t, levels.get((table, c), [])) for c, t in types[table]]
        out = []
        for i, row in enumerate(rows):
            if len(row) != len(convert):
                raise BuildError(f"{table} row {i + 1}: {len(row)} fields")
            try:
                out.append([f(v) for f, v in zip(convert, row)])
            except BuildError as e:
                raise BuildError(f"{table} row {i + 1}: {e}") from None
        tables[table] = {"columns": names, "rows": out}
    source = read_source(os.path.join(data_dir, "SOURCE"))
    return tables, levels, source


def records(table):
    """The table's rows as dicts (for the checks and the derivations)"""
    cols = table["columns"]
    return [dict(zip(cols, r)) for r in table["rows"]]


def in_year(row, year):
    return row["first_year"] <= year and (
        row["final_year"] is None or row["final_year"] >= year
    )


def check_unique(name, keys):
    dup = [k for k, n in Counter(keys).items() if n > 1]
    if dup:
        raise BuildError(f"{name}: duplicate keys {dup[:5]}")


def check(tables, min_year, max_year):
    agency = records(tables["agency"])
    ids = {r["agency_id"] for r in agency}
    for r in agency:
        if not AGENCY_ID.match(r["agency_id"]):
            raise BuildError(f"agency: bad agency_id {r['agency_id']!r}")
        if r["first_year"] is None or r["first_year"] < min_year:
            raise BuildError(f"agency: {r['agency_id']} first_year {r['first_year']}")
        if r["final_year"] is not None and r["final_year"] < r["first_year"]:
            raise BuildError(f"agency: {r['agency_id']} ends before it starts")
    check_unique("agency", [(r["agency_id"], r["first_year"]) for r in agency])
    for y in range(min_year, max_year + 1):
        check_unique(
            f"agency in {y}", [r["agency_id"] for r in agency if in_year(r, y)]
        )

    for name in ("agency_municipality", "agency_alias", "agency_ori"):
        for r in records(tables[name]):
            if r["agency_id"] not in ids:
                raise BuildError(f"{name}: unknown agency_id {r['agency_id']!r}")
    check_unique(
        "agency_municipality",
        [
            (r["agency_id"], r["GEOID_Y2K"], r["first_year"])
            for r in records(tables["agency_municipality"])
        ],
    )
    check_unique(
        "agency_alias",
        [
            (r["source"], r["source_county"], r["source_name"], r["first_year"])
            for r in records(tables["agency_alias"])
        ],
    )
    oris = records(tables["agency_ori"])
    check_unique("agency_ori", [r["ori"] for r in oris])
    for r in oris:
        if not ORI.match(r["ori"]):
            raise BuildError(f"agency_ori: bad ori {r['ori']!r}")
    sources = {r["source"] for r in records(tables["alias_source"])}
    check_unique("alias_source", [r["source"] for r in records(tables["alias_source"])])
    for r in records(tables["agency_alias"]):
        if r["source"] not in sources:
            raise BuildError(f"agency_alias: unknown source {r['source']!r}")


def geoid_reference(munis, gy):
    """{row GEOID_Y2K: GEOID} for the njmunicipalities rows of geoid year gy"""
    ref = {}
    for r in munis:
        if in_year(r, gy):
            if r["GEOID_Y2K"] in ref:
                raise BuildError(
                    f"municipalities: GEOID_Y2K {r['GEOID_Y2K']} twice in {gy}"
                )
            ref[r["GEOID_Y2K"]] = r["GEOID"]
    return ref


def derive(tables, min_year, max_year):
    """The per-year indexes and GEOID translations (see the module docstring)"""
    agency = records(tables["agency"])
    links = records(tables["agency_municipality"])
    munis = records(tables["municipalities"])
    ref2000 = geoid_reference(munis, MIN_GEOID_YEAR)

    years = {}
    used = set()  # municipality rows the links use
    for y in range(min_year, max_year + 1):
        # njlea's GEOID_Y2K -> the municipality row of year y (its y2k join)
        y2k = {}
        for i, m in enumerate(munis):
            if in_year(m, y):
                key = ref2000.get(m["GEOID_Y2K"])
                if key is None:
                    continue
                if key in y2k:
                    raise BuildError(
                        f"municipalities: two rows for GEOID_Y2K {key} in {y}"
                    )
                y2k[key] = i
        year_links = []
        served = defaultdict(set)
        for i, link in enumerate(links):
            if not in_year(link, y):
                continue
            served[link["agency_id"]].add(link["GEOID_Y2K"])
            m = y2k.get(link["GEOID_Y2K"])
            if m is None:
                raise BuildError(
                    f"agency_municipality: {link['agency_id']} {link['GEOID_Y2K']}"
                    f" has no municipality in {y}"
                )
            year_links.append([i, m])
            used.add(m)
        epochs = sorted(
            (r["agency_id"], i) for i, r in enumerate(agency) if in_year(r, y)
        )
        years[str(y)] = {
            "agencies": [[i, len(served.get(a, ())) > 1] for a, i in epochs],
            "links": year_links,
        }

    keys = {munis[m]["GEOID_Y2K"] for m in used}
    geoids = {}
    for gy in range(MIN_GEOID_YEAR, max_year + 1):
        ref = geoid_reference(munis, gy)
        geoids[str(gy)] = {k: ref.get(k) for k in sorted(keys) if ref.get(k) != k}
    return years, geoids


def counties(tables):
    return sorted({r["county"] for r in records(tables["municipalities"])})


def build(data_dir, root):
    tables, levels, source = read_export(data_dir)
    try:
        min_year = int(source["min_year"])
        max_year = int(source["max_year"])
    except (KeyError, ValueError):
        raise BuildError("SOURCE has no min_year/max_year") from None
    check(tables, min_year, max_year)
    years, geoids = derive(tables, min_year, max_year)
    out = {
        "source": source,
        "min_year": min_year,
        "max_year": max_year,
        "min_geoid_year": MIN_GEOID_YEAR,
        "levels": {
            "agency_level": levels[("agency", "agency_level")],
            "agency_function": levels[("agency", "agency_function")],
            "link_type": levels[("agency_municipality", "link_type")],
            "match": levels[("agency_ori", "match")],
        },
        "counties": counties(tables),
        "tables": tables,
        "years": years,
        "geoids": geoids,
    }
    path = os.path.join(root, OUT)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    return path


def main(argv):
    data_dir = argv[1] if len(argv) > 1 else "data"
    root = argv[2] if len(argv) > 2 else "."
    try:
        path = build(data_dir, root)
    except BuildError as e:
        sys.exit(f"build_data: {e}")
    print(f"Wrote {path} ({os.path.getsize(path):,} bytes)")


if __name__ == "__main__":
    main(sys.argv)
