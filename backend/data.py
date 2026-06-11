from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List


@dataclass(frozen=True)
class TeamProfile:
    code: str
    name: str
    confederation: str
    elo: float
    attack: float
    defense: float
    form: float
    squad_value_m_eur: float

    def to_dict(self) -> dict:
        row = asdict(self)
        row["flag"] = TEAM_FLAGS.get(self.code, "")
        row["squad_value_label"] = format_squad_value(self.squad_value_m_eur)
        return row


def format_squad_value(value_m_eur: float) -> str:
    if value_m_eur >= 1000:
        return f"€{value_m_eur / 1000:.2f}bn"
    return f"€{value_m_eur:.0f}m"


TEAM_FLAGS = {
    "ALG": "🇩🇿",
    "ARG": "🇦🇷",
    "AUS": "🇦🇺",
    "AUT": "🇦🇹",
    "BEL": "🇧🇪",
    "BIH": "🇧🇦",
    "BRA": "🇧🇷",
    "CAN": "🇨🇦",
    "CIV": "🇨🇮",
    "COD": "🇨🇩",
    "COL": "🇨🇴",
    "CPV": "🇨🇻",
    "CRO": "🇭🇷",
    "CUR": "🇨🇼",
    "CZE": "🇨🇿",
    "ECU": "🇪🇨",
    "EGY": "🇪🇬",
    "ENG": "🏴",
    "ESP": "🇪🇸",
    "FRA": "🇫🇷",
    "GER": "🇩🇪",
    "GHA": "🇬🇭",
    "HTI": "🇭🇹",
    "IRN": "🇮🇷",
    "IRQ": "🇮🇶",
    "JOR": "🇯🇴",
    "JPN": "🇯🇵",
    "KOR": "🇰🇷",
    "KSA": "🇸🇦",
    "MAR": "🇲🇦",
    "MEX": "🇲🇽",
    "NED": "🇳🇱",
    "NOR": "🇳🇴",
    "NZL": "🇳🇿",
    "PAN": "🇵🇦",
    "PAR": "🇵🇾",
    "POR": "🇵🇹",
    "QAT": "🇶🇦",
    "RSA": "🇿🇦",
    "SCO": "🏴",
    "SEN": "🇸🇳",
    "SUI": "🇨🇭",
    "SWE": "🇸🇪",
    "TUN": "🇹🇳",
    "TUR": "🇹🇷",
    "URU": "🇺🇾",
    "USA": "🇺🇸",
    "UZB": "🇺🇿",
}


# Team strength seed data for the qualified 2026 World Cup field.
# Ratings are local priors until a live ratings provider is connected.
TEAM_PROFILES: Dict[str, TeamProfile] = {
    "MEX": TeamProfile("MEX", "Mexico", "CONCACAF", 1944, 1.01, 1.00, 0.58, 220),
    "RSA": TeamProfile("RSA", "South Africa", "CAF", 1736, 0.92, 1.12, 0.52, 40),
    "KOR": TeamProfile("KOR", "Korea Republic", "AFC", 1879, 0.99, 1.02, 0.62, 190),
    "CZE": TeamProfile("CZE", "Czechia", "UEFA", 1856, 0.98, 1.03, 0.60, 165),
    "CAN": TeamProfile("CAN", "Canada", "CONCACAF", 1852, 1.00, 1.07, 0.58, 185),
    "BIH": TeamProfile("BIH", "Bosnia and Herzegovina", "UEFA", 1819, 0.98, 1.07, 0.56, 95),
    "QAT": TeamProfile("QAT", "Qatar", "AFC", 1768, 0.93, 1.11, 0.52, 25),
    "SUI": TeamProfile("SUI", "Switzerland", "UEFA", 1922, 0.99, 0.96, 0.61, 310),
    "BRA": TeamProfile("BRA", "Brazil", "CONMEBOL", 2068, 1.17, 0.92, 0.70, 1050),
    "MAR": TeamProfile("MAR", "Morocco", "CAF", 1932, 1.01, 0.92, 0.73, 360),
    "HTI": TeamProfile("HTI", "Haiti", "CONCACAF", 1668, 0.89, 1.17, 0.49, 35),
    "SCO": TeamProfile("SCO", "Scotland", "UEFA", 1828, 0.96, 1.05, 0.57, 240),
    "USA": TeamProfile("USA", "United States", "CONCACAF", 1936, 1.03, 1.01, 0.64, 360),
    "PAR": TeamProfile("PAR", "Paraguay", "CONMEBOL", 1794, 0.94, 1.03, 0.56, 120),
    "AUS": TeamProfile("AUS", "Australia", "AFC", 1858, 0.96, 1.04, 0.57, 55),
    "TUR": TeamProfile("TUR", "Türkiye", "UEFA", 1838, 1.01, 1.08, 0.60, 330),
    "GER": TeamProfile("GER", "Germany", "UEFA", 2004, 1.11, 0.95, 0.68, 900),
    "CUR": TeamProfile("CUR", "Curaçao", "CONCACAF", 1688, 0.90, 1.15, 0.54, 20),
    "CIV": TeamProfile("CIV", "Ivory Coast", "CAF", 1848, 0.99, 1.06, 0.61, 260),
    "ECU": TeamProfile("ECU", "Ecuador", "CONMEBOL", 1891, 0.98, 0.99, 0.63, 250),
    "NED": TeamProfile("NED", "Netherlands", "UEFA", 2037, 1.10, 0.90, 0.72, 850),
    "JPN": TeamProfile("JPN", "Japan", "AFC", 1916, 1.04, 0.98, 0.72, 300),
    "SWE": TeamProfile("SWE", "Sweden", "UEFA", 1844, 0.99, 1.04, 0.58, 260),
    "TUN": TeamProfile("TUN", "Tunisia", "CAF", 1816, 0.93, 1.03, 0.55, 55),
    "BEL": TeamProfile("BEL", "Belgium", "UEFA", 2010, 1.08, 0.96, 0.63, 520),
    "EGY": TeamProfile("EGY", "Egypt", "CAF", 1801, 0.97, 1.06, 0.57, 160),
    "IRN": TeamProfile("IRN", "Iran", "AFC", 1827, 0.96, 1.02, 0.60, 70),
    "NZL": TeamProfile("NZL", "New Zealand", "OFC", 1718, 0.90, 1.13, 0.51, 35),
    "ESP": TeamProfile("ESP", "Spain", "UEFA", 2094, 1.16, 0.88, 0.80, 1150),
    "CPV": TeamProfile("CPV", "Cape Verde", "CAF", 1742, 0.93, 1.10, 0.59, 45),
    "KSA": TeamProfile("KSA", "Saudi Arabia", "AFC", 1761, 0.92, 1.12, 0.51, 35),
    "URU": TeamProfile("URU", "Uruguay", "CONMEBOL", 1987, 1.05, 0.93, 0.71, 500),
    "FRA": TeamProfile("FRA", "France", "UEFA", 2106, 1.18, 0.86, 0.78, 1300),
    "SEN": TeamProfile("SEN", "Senegal", "CAF", 1902, 0.99, 0.97, 0.67, 320),
    "IRQ": TeamProfile("IRQ", "Iraq", "AFC", 1749, 0.93, 1.09, 0.58, 35),
    "NOR": TeamProfile("NOR", "Norway", "UEFA", 1894, 1.04, 1.04, 0.66, 520),
    "ARG": TeamProfile("ARG", "Argentina", "CONMEBOL", 2128, 1.21, 0.83, 0.82, 820),
    "ALG": TeamProfile("ALG", "Algeria", "CAF", 1797, 0.98, 1.07, 0.56, 210),
    "AUT": TeamProfile("AUT", "Austria", "UEFA", 1888, 1.02, 1.01, 0.69, 260),
    "JOR": TeamProfile("JOR", "Jordan", "AFC", 1716, 0.92, 1.12, 0.57, 20),
    "POR": TeamProfile("POR", "Portugal", "UEFA", 2059, 1.15, 0.91, 0.76, 1000),
    "COD": TeamProfile("COD", "Congo DR", "CAF", 1766, 0.94, 1.10, 0.58, 150),
    "UZB": TeamProfile("UZB", "Uzbekistan", "AFC", 1708, 0.91, 1.11, 0.56, 55),
    "COL": TeamProfile("COL", "Colombia", "CONMEBOL", 1962, 1.04, 0.98, 0.70, 330),
    "ENG": TeamProfile("ENG", "England", "UEFA", 2077, 1.13, 0.90, 0.75, 1500),
    "CRO": TeamProfile("CRO", "Croatia", "UEFA", 1969, 1.02, 0.94, 0.66, 300),
    "GHA": TeamProfile("GHA", "Ghana", "CAF", 1744, 0.94, 1.14, 0.49, 180),
    "PAN": TeamProfile("PAN", "Panama", "CONCACAF", 1748, 0.92, 1.13, 0.53, 35),
}


DEFAULT_GROUPS: Dict[str, List[str]] = {
    "A": ["MEX", "RSA", "KOR", "CZE"],
    "B": ["CAN", "BIH", "QAT", "SUI"],
    "C": ["BRA", "MAR", "HTI", "SCO"],
    "D": ["USA", "PAR", "AUS", "TUR"],
    "E": ["GER", "CUR", "CIV", "ECU"],
    "F": ["NED", "JPN", "SWE", "TUN"],
    "G": ["BEL", "EGY", "IRN", "NZL"],
    "H": ["ESP", "CPV", "KSA", "URU"],
    "I": ["FRA", "SEN", "IRQ", "NOR"],
    "J": ["ARG", "ALG", "AUT", "JOR"],
    "K": ["POR", "COD", "UZB", "COL"],
    "L": ["ENG", "CRO", "GHA", "PAN"],
}


TEAM_ALIASES = {
    "south korea": "KOR",
    "korea republic": "KOR",
    "czech republic": "CZE",
    "czechia": "CZE",
    "turkey": "TUR",
    "türkiye": "TUR",
    "ivory coast": "CIV",
    "cote d'ivoire": "CIV",
    "côte d'ivoire": "CIV",
    "dr congo": "COD",
    "congo dr": "COD",
    "bosnia": "BIH",
    "bosnia and herzegovina": "BIH",
    "usa": "USA",
    "united states": "USA",
    "cape verde": "CPV",
    "curacao": "CUR",
    "curaçao": "CUR",
}


def all_teams() -> List[TeamProfile]:
    return sorted(TEAM_PROFILES.values(), key=lambda team: team.elo, reverse=True)


def get_team(code_or_name: str) -> TeamProfile:
    query = code_or_name.strip().lower()
    if query in TEAM_ALIASES:
        return TEAM_PROFILES[TEAM_ALIASES[query]]
    for team in TEAM_PROFILES.values():
        if query in {team.code.lower(), team.name.lower()}:
            return team
    raise KeyError(f"Unknown team: {code_or_name}")


def validate_groups(groups: Dict[str, Iterable[str]]) -> None:
    seen: set[str] = set()
    for group, teams in groups.items():
        team_list = list(teams)
        if len(team_list) != 4:
            raise ValueError(f"Group {group} must contain exactly four teams.")
        for code in team_list:
            if code not in TEAM_PROFILES:
                raise ValueError(f"Group {group} contains unknown team code {code}.")
            if code in seen:
                raise ValueError(f"Team {code} appears in more than one group.")
            seen.add(code)


validate_groups(DEFAULT_GROUPS)
