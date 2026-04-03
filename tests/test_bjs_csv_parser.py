"""Tests for BJS CSV parsing helpers."""

import csv
import io
import textwrap

from scripts.ingestion.bjs_csv_parser import (
    STATE_NAME_TO_ABBREV,
    clean_jurisdiction,
    clean_number,
    parse_admissions_releases,
    parse_appendix_table1,
    parse_table3_sentenced,
)


class TestCleanNumber:
    def test_plain_integer(self):
        assert clean_number("12345") == 12345.0

    def test_comma_formatted(self):
        assert clean_number("1,520,403") == 1520403.0

    def test_quoted_comma(self):
        assert clean_number('"1,520,403"') == 1520403.0

    def test_not_reported(self):
        assert clean_number("/") is None

    def test_not_applicable(self):
        assert clean_number("~") is None

    def test_less_than(self):
        assert clean_number("--") is None

    def test_empty(self):
        assert clean_number("") is None

    def test_float_value(self):
        assert clean_number("479") == 479.0


class TestCleanJurisdiction:
    def test_plain_state(self):
        assert clean_jurisdiction("Alabama") == "Alabama"

    def test_footnote_suffix(self):
        assert clean_jurisdiction("Alabama/d") == "Alabama"

    def test_multi_footnote(self):
        assert clean_jurisdiction("Illinois/d,g") == "Illinois"

    def test_quoted_with_footnote(self):
        assert clean_jurisdiction('"Illinois/d,g"') == "Illinois"

    def test_federal(self):
        assert clean_jurisdiction("Federal/c") == "Federal"

    def test_rhode_island_no_space(self):
        assert clean_jurisdiction("Rhode Islande") == "Rhode Island"

    def test_virginia_suffix(self):
        assert clean_jurisdiction("Virginial") == "Virginia"


class TestStateMapping:
    def test_all_50_states_plus_dc(self):
        assert len(STATE_NAME_TO_ABBREV) >= 51

    def test_alabama(self):
        assert STATE_NAME_TO_ABBREV["Alabama"] == "AL"

    def test_wyoming(self):
        assert STATE_NAME_TO_ABBREV["Wyoming"] == "WY"

    def test_dc(self):
        assert STATE_NAME_TO_ABBREV["District of Columbia"] == "DC"


# Minimal CSV content mimicking BJS format (8 header rows + blank + title + column header + data)
TABLE3_CSV = textwrap.dedent("""\
    Bureau of Justice Statistics,,,,,,,,,,,,,,,,,,,,,
    Filename: p23stt03.csv,,,,,,,,,,,,,,,,,,,,,
    Title,,,,,,,,,,,,,,,,,,,,,
    Report,,,,,,,,,,,,,,,,,,,,,
    Data source,,,,,,,,,,,,,,,,,,,,,
    Authors,,,,,,,,,,,,,,,,,,,,,
    Contact,,,,,,,,,,,,,,,,,,,,,
    Date,,,,,,,,,,,,,,,,,,,,,
    ,,,,,,,,,,,,,,,,,,,,,
    Title repeated,,,,,,,,,,,,,,,,,,,,,
    Year,,Total/a,,Federal/b,,State,,Male,,Female,,"White/c,d",,"Black/c,d",,Hispanic/d,,"American Indian/Alaska Native/c,d",,"Asian/c,d,e",
    2023,,"1,210,308",,"143,297",,"1,067,011",,"1,124,435",,"85,873",,"370,500",,"394,500",,"282,700",,"19,700",,"15,200",
    Percent change,,,,,,,,,,,,,,,,,,,,,
""")

APPENDIX_CSV = textwrap.dedent("""\
    Bureau of Justice Statistics,,,,,,,,,,,,,,,,,,,,,,,,,
    Filename,,,,,,,,,,,,,,,,,,,,,,,,,
    Title,,,,,,,,,,,,,,,,,,,,,,,,,
    Report,,,,,,,,,,,,,,,,,,,,,,,,,
    Source,,,,,,,,,,,,,,,,,,,,,,,,,
    Authors,,,,,,,,,,,,,,,,,,,,,,,,,
    Contact,,,,,,,,,,,,,,,,,,,,,,,,,
    Date,,,,,,,,,,,,,,,,,,,,,,,,,
    ,,,,,,,,,,,,,,,,,,,,,,,,,
    Title,,,,,,,,,,,,,,,,,,,,,,,,,
    Jurisdiction,,Total,White/a,Black/a,Hispanic,American Indian/Alaska Native/a,Asian/a,Native Hawaiian/Other Pacific Islander/a,Two or more races/a,Other/a,Unknown,Did not report,,,,,,,,,,,,,
    Federal/b,,"156,627","47,472","57,542","45,684","3,839","2,091",/,/,~,~,0,,,,,,,,,,,,,
    State,,,,,,,,,,,,,,,,,,,,,,,,,
    ,Alabama,"27,181","12,341","14,548",0,1,10,0,0,0,281,0,,,,,,,,,,,,,
    ,California,"95,962","19,150","26,520","44,166","1,111","1,145",336,~,"3,534",~,0,,,,,,,,,,,,,
    Note:,,,,,,,,,,,,,,,,,,,,,,,,,
""")

TABLE8_CSV = textwrap.dedent("""\
    Bureau of Justice Statistics,,,,,,,,,,
    Filename,,,,,,,,,,
    Title,,,,,,,,,,
    Report,,,,,,,,,,
    Source,,,,,,,,,,
    Authors,,,,,,,,,,
    Contact,,,,,,,,,,
    Date,,,,,,,,,,
    ,,,,,,,,,,
    Title,,,,,,,,,,
    Jurisdiction,,2022 total ,2023 total,Change,Percent change,,2022 new court commitments,2023 new court commitments,2022 conditional supervision violations/a,2023 conditional supervision violations/a
    ,U.S. total/b,"469,217","472,278","3,061",0.7,%,"346,518","350,628","112,045","111,385"
    Federal/c,,"44,873","42,221","-2,652",-5.9,%,"38,440","36,026","6,433","6,195"
    State/b,,"424,344","430,057","5,713",1.3,%,"308,078","314,602","105,612","105,190"
    ,Alabama/d,"9,515","9,786",271,2.8,,"7,363","7,885",496,348
    Note:,,,,,,,,,,
""")


class TestParseTable3:
    def test_basic_parsing(self):
        reader = csv.reader(io.StringIO(TABLE3_CSV))
        records = parse_table3_sentenced(reader, data_year=2023)
        assert len(records) > 0
        total_pop = [
            r
            for r in records
            if r["metric"] == "sentenced_population"
            and r["race"] == "total"
            and r["gender"] == "total"
            and r["year"] == 2023
        ]
        assert len(total_pop) == 1
        assert total_pop[0]["value"] == 1210308.0
        assert total_pop[0]["state_abbrev"] == "US"

    def test_race_breakdown(self):
        reader = csv.reader(io.StringIO(TABLE3_CSV))
        records = parse_table3_sentenced(reader, data_year=2023)
        black = [
            r
            for r in records
            if r["metric"] == "sentenced_population"
            and r["race"] == "black"
            and r["gender"] == "total"
            and r["year"] == 2023
        ]
        assert len(black) == 1
        assert black[0]["value"] == 394500.0


class TestParseAppendixTable1:
    def test_state_rows(self):
        reader = csv.reader(io.StringIO(APPENDIX_CSV))
        records = parse_appendix_table1(reader, data_year=2023)
        al_total = [r for r in records if r["state_abbrev"] == "AL" and r["race"] == "total"]
        assert len(al_total) == 1
        assert al_total[0]["value"] == 27181.0
        assert al_total[0]["metric"] == "total_population"

    def test_race_breakdown(self):
        reader = csv.reader(io.StringIO(APPENDIX_CSV))
        records = parse_appendix_table1(reader, data_year=2023)
        al_black = [r for r in records if r["state_abbrev"] == "AL" and r["race"] == "black"]
        assert len(al_black) == 1
        assert al_black[0]["value"] == 14548.0

    def test_skips_federal_and_state_header(self):
        reader = csv.reader(io.StringIO(APPENDIX_CSV))
        records = parse_appendix_table1(reader, data_year=2023)
        federal = [r for r in records if r["state_abbrev"] == "US"]
        assert len(federal) > 0
        state_header = [r for r in records if r["state_name"] == "State"]
        assert len(state_header) == 0

    def test_skip_sentinel_values(self):
        reader = csv.reader(io.StringIO(APPENDIX_CSV))
        records = parse_appendix_table1(reader, data_year=2023)
        ca_records = [r for r in records if r["state_abbrev"] == "CA"]
        for r in ca_records:
            assert r["value"] is not None


class TestParseAdmissionsReleases:
    def test_admissions(self):
        reader = csv.reader(io.StringIO(TABLE8_CSV))
        records = parse_admissions_releases(
            reader,
            metric_map={
                2: ("admissions_total", 2022),
                3: ("admissions_total", 2023),
                7: ("admissions_new_court_commitment", 2022),
                8: ("admissions_new_court_commitment", 2023),
                9: ("admissions_supervision_violations", 2022),
                10: ("admissions_supervision_violations", 2023),
            },
        )
        al_2023 = [
            r
            for r in records
            if r["state_abbrev"] == "AL" and r["year"] == 2023 and r["metric"] == "admissions_total"
        ]
        assert len(al_2023) == 1
        assert al_2023[0]["value"] == 9786.0
        assert al_2023[0]["race"] == "total"
        assert al_2023[0]["gender"] == "total"