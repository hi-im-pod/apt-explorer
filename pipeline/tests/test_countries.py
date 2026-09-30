import re

import pytest

from aptx.build.countries import COUNTRIES, country_name, iso2


@pytest.mark.parametrize("value,code", [
    # ETDA's wording
    ("USA", "US"), ("UK", "GB"), ("North Korea", "KP"), ("China", "CN"), ("Russia", "RU"), ("Iran", "IR"),
    # The UN's official wording
    ("Iran (Islamic Republic of)", "IR"), ("Korea (Republic of)", "KR"),
    ("Korea (Democratic People's Republic of)", "KP"), ("Russian Federation", "RU"),
    # The names the site shows
    ("United States", "US"), ("United Kingdom", "GB"), ("South Korea", "KR"),
    # Codes, in either case, as Malpedia and MISP write them
    ("RU", "RU"), ("cn", "CN"), (" ir ", "IR"),
    # Spelling variants
    ("The Netherlands", "NL"), ("Türkiye", "TR"), ("Turkey", "TR"), ("Côte d'Ivoire", "CI"), ("Viet Nam", "VN"),
])
def test_a_country_value_becomes_its_iso_code(value, code):
    assert iso2(value) == code


@pytest.mark.parametrize("value", [
    "[Unknown]", "Unknown", "Worldwide", "Southeast Asia", "Europe", "Middle East",
    "World Anti-Doping Agency", "U.S. satellite and aerospace sector", "", "  ", "EU", "XX", "Others",
])
def test_a_value_that_is_not_a_country_has_no_code(value):
    assert iso2(value) is None


def test_a_value_that_is_not_text_has_no_code():
    assert iso2(None) is None and iso2(7) is None


def test_uk_is_read_as_the_united_kingdom_not_as_an_iso_code():
    # ISO assigns GB to the United Kingdom and leaves UK unassigned.
    assert "UK" not in COUNTRIES and iso2("UK") == "GB"


def test_russia_and_ru_agree_and_ru_and_cn_do_not():
    assert iso2("Russia") == iso2("RU") != iso2("CN")


def test_every_code_has_a_name_that_maps_back_to_it():
    for code in COUNTRIES:
        assert re.fullmatch(r"[A-Z]{2}", code)
        assert iso2(country_name(code)) == code, code
        assert iso2(code) == code


def test_the_table_lists_every_iso_country():
    # ISO 3166-1 has 249 officially assigned codes, and Kosovo's XK is the usual user-assigned extra.
    assert len(COUNTRIES) == 250
