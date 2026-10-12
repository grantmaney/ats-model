import pandas as pd

from ats.teams import build_cfb_map, build_nfl_map, norm, to_canonical


def test_norm_strips_accents_and_punctuation():
    assert norm("San José State") == norm("San Jose State")
    assert norm("Hawai'i") == "hawaii"
    assert norm("Texas A&M") == "texas a and m"


def test_nfl_map():
    teams = pd.DataFrame({"team_abbr": ["KC", "LA"], "team_name": ["Kansas City Chiefs", "Los Angeles Rams"]})
    mapped, unmatched = to_canonical("NFL", pd.Series(["Kansas City Chiefs", "Los Angeles Rams", "Nope"]),
                                     build_nfl_map(teams))
    assert list(mapped[:2]) == ["KC", "LA"] and unmatched == ["Nope"]


def test_rams_override_beats_team_list_order():
    teams = pd.DataFrame({"team_abbr": ["LA", "LAR"], "team_name": ["Los Angeles Rams"] * 2})
    mapped, _ = to_canonical("NFL", pd.Series(["Los Angeles Rams"]), build_nfl_map(teams))
    assert mapped[0] == "LA"


def test_cfb_map_school_mascot_and_alternates():
    teams = pd.DataFrame({
        "school": ["Hawai'i", "Miami (OH)", "San José State"],
        "mascot": ["Rainbow Warriors", "RedHawks", "Spartans"],
        "alternateNames": [["Hawaii"], None, ["San Jose State"]],
    })
    m = build_cfb_map(teams)
    mapped, unmatched = to_canonical(
        "CFB", pd.Series(["Hawaii Rainbow Warriors", "Miami (OH) RedHawks", "San Jose State Spartans"]), m)
    assert list(mapped) == ["Hawai'i", "Miami (OH)", "San José State"] and not unmatched
