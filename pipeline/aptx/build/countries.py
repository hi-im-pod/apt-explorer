"""Country names and codes, so "Russia", "RU" and "Russian Federation" compare equal.

Sources give countries in three shapes. Malpedia and MISP's origin field use
ISO 3166-1 alpha-2 codes. ETDA writes short English names such as "USA" and
"UK". Some sources use UN-style wording such as "Iran
(Islamic Republic of)". Comparing them as raw text would report a conflict
between "RU" and "Russia", so assembly compares the ISO code instead.

Anything that is not a country returns None: "[Unknown]", "Worldwide", regions
such as "Southeast Asia", and victim descriptions such as "U.S. satellite and
aerospace sector". Callers drop those, because a region or a description is not
a country the site can show as one.
"""
import re
import unicodedata

# ISO 3166-1 alpha-2 codes with the English short name the site shows.
COUNTRIES: dict[str, str] = {
    "AD": "Andorra", "AE": "United Arab Emirates", "AF": "Afghanistan", "AG": "Antigua and Barbuda",
    "AI": "Anguilla", "AL": "Albania", "AM": "Armenia", "AO": "Angola", "AQ": "Antarctica",
    "AR": "Argentina", "AS": "American Samoa", "AT": "Austria", "AU": "Australia", "AW": "Aruba",
    "AX": "Åland Islands", "AZ": "Azerbaijan", "BA": "Bosnia and Herzegovina", "BB": "Barbados",
    "BD": "Bangladesh", "BE": "Belgium", "BF": "Burkina Faso", "BG": "Bulgaria", "BH": "Bahrain",
    "BI": "Burundi", "BJ": "Benin", "BL": "Saint Barthélemy", "BM": "Bermuda", "BN": "Brunei",
    "BO": "Bolivia", "BQ": "Bonaire, Sint Eustatius and Saba", "BR": "Brazil", "BS": "Bahamas",
    "BT": "Bhutan", "BV": "Bouvet Island", "BW": "Botswana", "BY": "Belarus", "BZ": "Belize",
    "CA": "Canada", "CC": "Cocos (Keeling) Islands", "CD": "Democratic Republic of the Congo",
    "CF": "Central African Republic", "CG": "Republic of the Congo", "CH": "Switzerland",
    "CI": "Côte d'Ivoire", "CK": "Cook Islands", "CL": "Chile", "CM": "Cameroon", "CN": "China",
    "CO": "Colombia", "CR": "Costa Rica", "CU": "Cuba", "CV": "Cabo Verde", "CW": "Curaçao",
    "CX": "Christmas Island", "CY": "Cyprus", "CZ": "Czechia", "DE": "Germany", "DJ": "Djibouti",
    "DK": "Denmark", "DM": "Dominica", "DO": "Dominican Republic", "DZ": "Algeria", "EC": "Ecuador",
    "EE": "Estonia", "EG": "Egypt", "EH": "Western Sahara", "ER": "Eritrea", "ES": "Spain",
    "ET": "Ethiopia", "FI": "Finland", "FJ": "Fiji", "FK": "Falkland Islands", "FM": "Micronesia",
    "FO": "Faroe Islands", "FR": "France", "GA": "Gabon", "GB": "United Kingdom", "GD": "Grenada",
    "GE": "Georgia", "GF": "French Guiana", "GG": "Guernsey", "GH": "Ghana", "GI": "Gibraltar",
    "GL": "Greenland", "GM": "Gambia", "GN": "Guinea", "GP": "Guadeloupe", "GQ": "Equatorial Guinea",
    "GR": "Greece", "GS": "South Georgia and the South Sandwich Islands", "GT": "Guatemala",
    "GU": "Guam", "GW": "Guinea-Bissau", "GY": "Guyana", "HK": "Hong Kong",
    "HM": "Heard Island and McDonald Islands", "HN": "Honduras", "HR": "Croatia", "HT": "Haiti",
    "HU": "Hungary", "ID": "Indonesia", "IE": "Ireland", "IL": "Israel", "IM": "Isle of Man",
    "IN": "India", "IO": "British Indian Ocean Territory", "IQ": "Iraq", "IR": "Iran", "IS": "Iceland",
    "IT": "Italy", "JE": "Jersey", "JM": "Jamaica", "JO": "Jordan", "JP": "Japan", "KE": "Kenya",
    "KG": "Kyrgyzstan", "KH": "Cambodia", "KI": "Kiribati", "KM": "Comoros", "KN": "Saint Kitts and Nevis",
    "KP": "North Korea", "KR": "South Korea", "KW": "Kuwait", "KY": "Cayman Islands", "KZ": "Kazakhstan",
    "LA": "Laos", "LB": "Lebanon", "LC": "Saint Lucia", "LI": "Liechtenstein", "LK": "Sri Lanka",
    "LR": "Liberia", "LS": "Lesotho", "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia",
    "LY": "Libya", "MA": "Morocco", "MC": "Monaco", "MD": "Moldova", "ME": "Montenegro",
    "MF": "Saint Martin", "MG": "Madagascar", "MH": "Marshall Islands", "MK": "North Macedonia",
    "ML": "Mali", "MM": "Myanmar", "MN": "Mongolia", "MO": "Macao", "MP": "Northern Mariana Islands",
    "MQ": "Martinique", "MR": "Mauritania", "MS": "Montserrat", "MT": "Malta", "MU": "Mauritius",
    "MV": "Maldives", "MW": "Malawi", "MX": "Mexico", "MY": "Malaysia", "MZ": "Mozambique",
    "NA": "Namibia", "NC": "New Caledonia", "NE": "Niger", "NF": "Norfolk Island", "NG": "Nigeria",
    "NI": "Nicaragua", "NL": "Netherlands", "NO": "Norway", "NP": "Nepal", "NR": "Nauru", "NU": "Niue",
    "NZ": "New Zealand", "OM": "Oman", "PA": "Panama", "PE": "Peru", "PF": "French Polynesia",
    "PG": "Papua New Guinea", "PH": "Philippines", "PK": "Pakistan", "PL": "Poland",
    "PM": "Saint Pierre and Miquelon", "PN": "Pitcairn Islands", "PR": "Puerto Rico", "PS": "Palestine",
    "PT": "Portugal", "PW": "Palau", "PY": "Paraguay", "QA": "Qatar", "RE": "Réunion", "RO": "Romania",
    "RS": "Serbia", "RU": "Russia", "RW": "Rwanda", "SA": "Saudi Arabia", "SB": "Solomon Islands",
    "SC": "Seychelles", "SD": "Sudan", "SE": "Sweden", "SG": "Singapore",
    "SH": "Saint Helena, Ascension and Tristan da Cunha", "SI": "Slovenia", "SJ": "Svalbard and Jan Mayen",
    "SK": "Slovakia", "SL": "Sierra Leone", "SM": "San Marino", "SN": "Senegal", "SO": "Somalia",
    "SR": "Suriname", "SS": "South Sudan", "ST": "São Tomé and Príncipe", "SV": "El Salvador",
    "SX": "Sint Maarten", "SY": "Syria", "SZ": "Eswatini", "TC": "Turks and Caicos Islands", "TD": "Chad",
    "TF": "French Southern Territories", "TG": "Togo", "TH": "Thailand", "TJ": "Tajikistan",
    "TK": "Tokelau", "TL": "Timor-Leste", "TM": "Turkmenistan", "TN": "Tunisia", "TO": "Tonga",
    "TR": "Türkiye", "TT": "Trinidad and Tobago", "TV": "Tuvalu", "TW": "Taiwan", "TZ": "Tanzania",
    "UA": "Ukraine", "UG": "Uganda", "UM": "United States Minor Outlying Islands", "US": "United States",
    "UY": "Uruguay", "UZ": "Uzbekistan", "VA": "Vatican City", "VC": "Saint Vincent and the Grenadines",
    "VE": "Venezuela", "VG": "British Virgin Islands", "VI": "U.S. Virgin Islands", "VN": "Vietnam",
    "VU": "Vanuatu", "WF": "Wallis and Futuna", "WS": "Samoa", "XK": "Kosovo", "YE": "Yemen",
    "YT": "Mayotte", "ZA": "South Africa", "ZM": "Zambia", "ZW": "Zimbabwe",
}

# Other wordings the sources use for a country. ETDA writes "USA", "UK" and
# "North Korea". Some sources use the UN's official forms, in which a
# comma or parenthesis moves the qualifier to the end.
_ALIASES: dict[str, str] = {
    "USA": "US", "U.S.": "US", "U.S.A.": "US", "United States of America": "US", "America": "US",
    "UK": "GB", "U.K.": "GB", "Great Britain": "GB", "Britain": "GB",
    "United Kingdom of Great Britain and Northern Ireland": "GB",
    "Russian Federation": "RU",
    "Iran (Islamic Republic of)": "IR", "Iran, Islamic Republic of": "IR", "Islamic Republic of Iran": "IR",
    "Korea (Republic of)": "KR", "Korea, Republic of": "KR", "Republic of Korea": "KR",
    "Korea (Democratic People's Republic of)": "KP", "Korea, Democratic People's Republic of": "KP",
    "Democratic People's Republic of Korea": "KP", "DPRK": "KP",
    "People's Republic of China": "CN", "China, People's Republic of": "CN", "PRC": "CN", "Mainland China": "CN",
    "Syrian Arab Republic": "SY", "Viet Nam": "VN", "Lao People's Democratic Republic": "LA",
    "Czech Republic": "CZ", "Turkey": "TR", "Turkiye": "TR", "Burma": "MM", "Myanmar (Burma)": "MM",
    "Holland": "NL", "UAE": "AE", "State of Palestine": "PS", "Palestinian Territories": "PS",
    "Palestine, State of": "PS", "Macau": "MO", "Hong Kong SAR": "HK", "Hong Kong, China": "HK",
    "Taiwan, Province of China": "TW", "Moldova, Republic of": "MD", "Republic of Moldova": "MD",
    "Tanzania, United Republic of": "TZ", "United Republic of Tanzania": "TZ",
    "Bolivia (Plurinational State of)": "BO", "Venezuela (Bolivarian Republic of)": "VE",
    "Brunei Darussalam": "BN", "Cape Verde": "CV", "Ivory Coast": "CI", "Cote d'Ivoire": "CI",
    "Congo, Democratic Republic of the": "CD", "DR Congo": "CD", "DRC": "CD", "Congo": "CG",
    "Swaziland": "SZ", "Macedonia": "MK", "East Timor": "TL", "Vatican": "VA", "Holy See": "VA",
    "Micronesia (Federated States of)": "FM", "Kyrgyz Republic": "KG", "Slovak Republic": "SK",
    "Falkland Islands (Malvinas)": "FK", "Saint Martin (French part)": "MF",
    "Sint Maarten (Dutch part)": "SX", "Curacao": "CW", "Reunion": "RE", "Aland Islands": "AX",
    "Sao Tome and Principe": "ST", "Saint Barthelemy": "BL",
}


def _key(text: str) -> str:
    """The comparison key for a name: no accents, case or punctuation, and no leading "the"."""
    text = unicodedata.normalize("NFKD", text.replace("&", " and "))
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return text[4:] if text.startswith("the ") else text


_BY_NAME: dict[str, str] = {}
for _code, _name in COUNTRIES.items():
    _BY_NAME[_key(_name)] = _code
for _name, _code in _ALIASES.items():
    _BY_NAME[_key(_name)] = _code
del _code, _name


def iso2(value: str | None) -> str | None:
    """The ISO 3166-1 alpha-2 code a country value stands for, or None when it is not a country.

    A two-letter value is a code only when ISO assigns it, so "UK", which ISO
    does not, is read as a name and comes out as GB.
    """
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if len(text) == 2 and text.isalpha() and text.upper() in COUNTRIES:
        return text.upper()
    return _BY_NAME.get(_key(text))


def country_name(code: str) -> str:
    """The English name the site shows for an ISO code."""
    return COUNTRIES[code]
