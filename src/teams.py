# -*- coding: utf-8 -*-
"""Team identity: map eloratings.net country codes <-> ESPN abbreviations, plus
Hebrew display names and host nations. ESPN 3-letter abbreviation is the canonical
key used throughout the engine."""

# eloratings.net 2-letter code -> ESPN 3-letter abbreviation (verified 1:1 for all 48)
ELO_CODE_TO_ABBR = {
    "AR": "ARG", "ES": "ESP", "FR": "FRA", "EN": "ENG", "CO": "COL", "PT": "POR",
    "BR": "BRA", "NL": "NED", "DE": "GER", "NO": "NOR", "JP": "JPN", "HR": "CRO",
    "MX": "MEX", "CH": "SUI", "BE": "BEL", "MA": "MAR", "EC": "ECU", "UY": "URU",
    "AT": "AUT", "US": "USA", "SN": "SEN", "PY": "PAR", "TR": "TUR", "AU": "AUS",
    "DZ": "ALG", "CA": "CAN", "KR": "KOR", "SQ": "SCO", "IR": "IRN", "EG": "EGY",
    "CI": "CIV", "SE": "SWE", "CZ": "CZE", "UZ": "UZB", "CD": "COD", "PA": "PAN",
    "JO": "JOR", "CV": "CPV", "BA": "BIH", "SA": "KSA", "IQ": "IRQ", "GH": "GHA",
    "TN": "TUN", "NZ": "NZL", "HT": "HAI", "ZA": "RSA", "CW": "CUW", "QA": "QAT",
}

# Host nations get a home-advantage Elo bump in the group stage.
HOSTS = {"USA", "CAN", "MEX"}

# ESPN abbreviation -> Hebrew name (for the dashboard).
HE_NAME = {
    "ARG": "ארגנטינה", "ESP": "ספרד", "FRA": "צרפת", "ENG": "אנגליה",
    "COL": "קולומביה", "POR": "פורטוגל", "BRA": "ברזיל", "NED": "הולנד",
    "GER": "גרמניה", "NOR": "נורבגיה", "JPN": "יפן", "CRO": "קרואטיה",
    "MEX": "מקסיקו", "SUI": "שווייץ", "BEL": "בלגיה", "MAR": "מרוקו",
    "ECU": "אקוודור", "URU": "אורוגוואי", "AUT": "אוסטריה", "USA": "ארה\"ב",
    "SEN": "סנגל", "PAR": "פרגוואי", "TUR": "טורקיה", "AUS": "אוסטרליה",
    "ALG": "אלג'יריה", "CAN": "קנדה", "KOR": "דרום קוריאה", "SCO": "סקוטלנד",
    "IRN": "איראן", "EGY": "מצרים", "CIV": "חוף השנהב", "SWE": "שוודיה",
    "CZE": "צ'כיה", "UZB": "אוזבקיסטן", "COD": "קונגו", "PAN": "פנמה",
    "JOR": "ירדן", "CPV": "כף ורדה", "BIH": "בוסניה", "KSA": "ערב הסעודית",
    "IRQ": "עיראק", "GHA": "גאנה", "TUN": "תוניסיה", "NZL": "ניו זילנד",
    "HAI": "האיטי", "RSA": "דרום אפריקה", "CUW": "קוראסאו", "QAT": "קטאר",
}


FLAG = {
    "ARG": "🇦🇷", "ESP": "🇪🇸", "FRA": "🇫🇷", "ENG": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "COL": "🇨🇴", "POR": "🇵🇹",
    "BRA": "🇧🇷", "NED": "🇳🇱", "GER": "🇩🇪", "NOR": "🇳🇴", "JPN": "🇯🇵", "CRO": "🇭🇷",
    "MEX": "🇲🇽", "SUI": "🇨🇭", "BEL": "🇧🇪", "MAR": "🇲🇦", "ECU": "🇪🇨", "URU": "🇺🇾",
    "AUT": "🇦🇹", "USA": "🇺🇸", "SEN": "🇸🇳", "PAR": "🇵🇾", "TUR": "🇹🇷", "AUS": "🇦🇺",
    "ALG": "🇩🇿", "CAN": "🇨🇦", "KOR": "🇰🇷", "SCO": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "IRN": "🇮🇷", "EGY": "🇪🇬",
    "CIV": "🇨🇮", "SWE": "🇸🇪", "CZE": "🇨🇿", "UZB": "🇺🇿", "COD": "🇨🇩", "PAN": "🇵🇦",
    "JOR": "🇯🇴", "CPV": "🇨🇻", "BIH": "🇧🇦", "KSA": "🇸🇦", "IRQ": "🇮🇶", "GHA": "🇬🇭",
    "TUN": "🇹🇳", "NZL": "🇳🇿", "HAI": "🇭🇹", "RSA": "🇿🇦", "CUW": "🇨🇼", "QAT": "🇶🇦",
}


def he(abbr, fallback=""):
    return HE_NAME.get(abbr, fallback or abbr)


def flag(abbr):
    return FLAG.get(abbr, "🏳️")
