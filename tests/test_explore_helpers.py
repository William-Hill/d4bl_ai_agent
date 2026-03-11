from d4bl.app.explore_helpers import compute_national_avg, distinct_values


def test_compute_national_avg():
    rows = [
        {"state_fips": "06", "value": 10.0},
        {"state_fips": "36", "value": 20.0},
        {"state_fips": "48", "value": 30.0},
    ]
    assert compute_national_avg(rows) == 20.0


def test_compute_national_avg_empty():
    assert compute_national_avg([]) is None


def test_distinct_values():
    rows = [
        {"metric": "Asthma", "year": 2022},
        {"metric": "Obesity", "year": 2022},
        {"metric": "Asthma", "year": 2021},
    ]
    assert sorted(distinct_values(rows, "metric")) == ["Asthma", "Obesity"]
    assert sorted(distinct_values(rows, "year")) == [2021, 2022]
