import json
import os
import shutil

import pytest

from scripts import build_data

from .conftest import FIXTURE_DATA


@pytest.fixture
def built(fixture_build):
    with open(fixture_build, encoding="utf-8") as f:
        return json.load(f)


def row_ids(built, year):
    """The agency_id and multi_municipal of the year's agency entries"""
    table = built["tables"]["agency"]
    i = table["columns"].index("agency_id")
    return [(table["rows"][e[0]][i], e[1]) for e in built["years"][year]["agencies"]]


def test_header_values(built):
    assert built["min_year"] == 2020
    assert built["max_year"] == 2023
    assert built["min_geoid_year"] == 2000
    assert built["source"]["version"] == "0.0.0"
    assert built["counties"] == ["Atlantic County", "Camden County", "Essex County"]
    assert built["levels"]["link_type"] == ["Home", "Service"]
    assert built["levels"]["match"] == ["Name", "Hand"]
    assert built["levels"]["agency_level"][0] == "Municipal"
    assert built["levels"]["agency_function"][-1] == "Investigative"


def test_row_counts(built):
    assert {name: len(t["rows"]) for name, t in built["tables"].items()} == {
        "agency": 7,
        "agency_municipality": 7,
        "agency_alias": 8,
        "agency_ori": 4,
        "alias_source": 2,
        "municipalities": 6,
    }


def test_columns_are_typed(built):
    table = built["tables"]["agency"]
    assert dict(zip(table["columns"], table["rows"][4])) == {
        "agency_id": "NJLEA0004",
        "first_year": 2022,
        "final_year": None,
        "agency_name": "Youth Justice Commission",
        "county": None,
        "agency_level": "State",
        "agency_function": "Corrections",
        "note": "Renamed in 2022",
    }


def test_quoted_commas_survive(built):
    table = built["tables"]["agency"]
    assert table["rows"][1][-1] == "Formed in 2013, replacing the city's"


def test_every_year_is_built(built):
    assert list(built["years"]) == ["2020", "2021", "2022", "2023"]
    assert list(built["geoids"]) == [str(y) for y in range(2000, 2024)]


def test_agencies_are_ordered_by_id_not_file_order(built):
    assert row_ids(built, "2022") == [
        ("NJLEA0001", False),
        ("NJLEA0002", True),
        ("NJLEA0004", False),
        ("NJLEA0005", False),
        ("NJLEA0006", False),
    ]


def test_multi_municipal_by_year(built):
    assert dict(row_ids(built, "2020"))["NJLEA0002"] is False
    assert dict(row_ids(built, "2021"))["NJLEA0002"] is True
    assert dict(row_ids(built, "2021"))["NJLEA0003"] is False


def test_link_counts_by_year(built):
    assert [len(built["years"][str(y)]["links"]) for y in range(2020, 2024)] == [
        4,
        7,
        4,
        4,
    ]


def test_links_use_the_municipality_row_of_the_year(built):
    table = built["tables"]["agency_municipality"]
    munis = built["tables"]["municipalities"]
    municipality = munis["columns"].index("municipality")
    so_link = table["rows"].index(next(r for r in table["rows"] if r[0] == "NJLEA0005"))
    by_year = {
        year: dict(built["years"][year]["links"])[so_link] for year in ("2022", "2023")
    }
    assert munis["rows"][by_year["2022"]][municipality] == (
        "South Orange Village township"
    )
    assert munis["rows"][by_year["2023"]][municipality] == "South Orange village"


def test_geoids_hold_only_the_differences(built):
    assert built["geoids"]["2000"] == {}
    assert built["geoids"]["2021"] == {}
    assert built["geoids"]["2022"] == {"3400758920": None}
    assert built["geoids"]["2023"] == {
        "3400758920": None,
        "3401369274": "3401369270",
    }


def test_json_is_compact(fixture_build):
    with open(fixture_build, encoding="utf-8") as f:
        assert ", " not in f.read(100)


# Bad exports


@pytest.fixture
def fixture_copy(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(FIXTURE_DATA, data)
    return data


AGENCY_TAIL = '"X","Camden County","County","Police",'


@pytest.mark.parametrize(
    "file,line,message",
    [
        ("agency.csv", f'"NJLEA9",2020,,{AGENCY_TAIL}', "bad agency_id"),
        ("agency.csv", f'"NJLEA0009",2019,,{AGENCY_TAIL}', "first_year 2019"),
        ("agency.csv", f'"NJLEA0009",,,{AGENCY_TAIL}', "first_year None"),
        ("agency.csv", f'"NJLEA0009",2022,2021,{AGENCY_TAIL}', "ends before it starts"),
        (
            "agency.csv",
            f'"NJLEA0001",2020,2020,{AGENCY_TAIL}',
            "agency: duplicate keys",
        ),
        ("agency.csv", f'"NJLEA0001",2021,,{AGENCY_TAIL}', "agency in 2021: duplicate"),
        (
            "agency.csv",
            '"NJLEA0009",2020,,"X","Camden County","Regional","Police",',
            "agency row 8: 'Regional' is not a level",
        ),
        ("agency.csv", '"NJLEA0009",2020', "agency row 8: 2 fields"),
        (
            "agency_municipality.csv",
            '"NJLEA0999","3400100100",2020,,"Home",',
            "agency_municipality: unknown agency_id",
        ),
        (
            "agency_municipality.csv",
            '"NJLEA0001","3400100100",2020,2021,"Service",',
            "agency_municipality: duplicate keys",
        ),
        (
            "agency_municipality.csv",
            '"NJLEA0001","3400710000",2020,,"Visitor",',
            "not a level",
        ),
        (
            "agency_municipality.csv",
            '"NJLEA0001","3400000000",2020,,"Service",',
            "3400000000 has no municipality in 2020",
        ),
        # Pine Valley ends in 2021; a link can't outlast it
        (
            "agency_municipality.csv",
            '"NJLEA0001","3400758920",2020,,"Service",',
            "3400758920 has no municipality in 2022",
        ),
        (
            "agency_alias.csv",
            '"source-a","Atlantic","Other","NJLEA0999",,,',
            "agency_alias: unknown agency_id",
        ),
        (
            "agency_alias.csv",
            '"nope","Atlantic","Other","NJLEA0001",,,',
            "unknown source 'nope'",
        ),
        (
            "agency_alias.csv",
            '"source-a","Atlantic","Absecon City PD","NJLEA0002",,,',
            "agency_alias: duplicate keys",
        ),
        (
            "agency_ori.csv",
            '"NJLEA0999","NJ0000000",,2020,,"Name",',
            "agency_ori: unknown agency_id",
        ),
        ("agency_ori.csv", '"NJLEA0001","bad",,2020,,"Name",', "bad ori 'bad'"),
        (
            "agency_ori.csv",
            '"NJLEA0005","NJ0010100",,2020,,"Name",',
            "agency_ori: duplicate keys",
        ),
        (
            "alias_source.csv",
            '"source-a","Again",,,',
            "alias_source: duplicate keys",
        ),
        (
            "municipalities.csv",
            '"3400100100","3400100199","Atlantic County","Absecon city",2020,2020',
            "two rows for GEOID_Y2K 3400100100 in 2020",
        ),
    ],
)
def test_bad_export_fails(fixture_copy, tmp_path, file, line, message):
    with open(fixture_copy / file, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    with pytest.raises(build_data.BuildError, match=message):
        build_data.build(str(fixture_copy), str(tmp_path / "out"))
    assert not os.path.exists(tmp_path / "out")


def test_header_mismatch_fails(fixture_copy, tmp_path):
    path = fixture_copy / "alias_source.csv"
    lines = path.read_text().splitlines()
    path.write_text(
        "\n".join(['"source","name","url","coverage","retrieved"'] + lines[1:])
    )
    with pytest.raises(build_data.BuildError, match="alias_source: header"):
        build_data.build(str(fixture_copy), str(tmp_path / "out"))


@pytest.mark.parametrize("key", ["min_year", "max_year"])
def test_source_without_years_fails(fixture_copy, tmp_path, key):
    path = fixture_copy / "SOURCE"
    kept = [x for x in path.read_text().splitlines() if not x.startswith(key)]
    path.write_text("\n".join(kept) + "\n")
    with pytest.raises(build_data.BuildError, match="no min_year/max_year"):
        build_data.build(str(fixture_copy), str(tmp_path / "out"))


def test_table_missing_from_columns_fails(fixture_copy, tmp_path):
    path = fixture_copy / "columns.csv"
    lines = path.read_text().splitlines()
    path.write_text(
        "\n".join(x for x in lines if not x.startswith('"agency_ori"')) + "\n"
    )
    with pytest.raises(build_data.BuildError, match="agency_ori is not in columns.csv"):
        build_data.build(str(fixture_copy), str(tmp_path / "out"))


def test_main_reports_a_bad_export(fixture_copy, tmp_path):
    (fixture_copy / "SOURCE").write_text("")
    with pytest.raises(SystemExit, match="build_data: SOURCE has no"):
        build_data.main(["build_data.py", str(fixture_copy), str(tmp_path / "out")])


def test_main_writes_the_file(tmp_path, capsys):
    build_data.main(["build_data.py", FIXTURE_DATA, str(tmp_path)])
    assert os.path.exists(tmp_path / "lea" / "data" / "njlea.json")
    assert "Wrote" in capsys.readouterr().out
