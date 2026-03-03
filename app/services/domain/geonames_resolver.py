from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import logging
from pathlib import Path
import re
import unicodedata

import pycountry

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _normalize_lookup(text: str | None) -> str:
    if not text:
        return ""
    folded = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in folded if not unicodedata.combining(ch))
    lowered = ascii_text.lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_compact(text: str | None) -> str:
    return _normalize_lookup(text).replace(" ", "")


@dataclass(frozen=True)
class GeoNamesCityCandidate:
    geonames_id: int
    name: str
    country_code: str
    admin1_code: str | None
    population: int


class GeoNamesResolver:
    """
    Offline resolver backed by local GeoNames reference files.
    It is intentionally conservative: no confident match => return None.
    """

    def __init__(self, data_dir: str | Path | None = None) -> None:
        settings = get_settings()
        self._data_dir = Path(data_dir or settings.geonames_data_dir)
        self._loaded = False
        self._available = False

        self._country_lookup: dict[str, set[str]] = {}
        self._admin1_name_to_code: dict[tuple[str, str], str] = {}
        self._admin1_code_to_name: dict[tuple[str, str], str] = {}
        self._cities_by_name: dict[str, list[GeoNamesCityCandidate]] = {}

    @property
    def has_reference_data(self) -> bool:
        self._ensure_loaded()
        return self._available

    def lookup_country_codes(self, text: str | None) -> set[str]:
        self._ensure_loaded()
        if not text:
            return set()
        keys = {_normalize_lookup(text), _normalize_compact(text)}
        codes: set[str] = set()
        for key in keys:
            if key:
                codes.update(self._country_lookup.get(key, set()))
        return codes

    def resolve_city(
        self,
        *,
        city: str | None,
        region: str | None = None,
        country_code: str | None = None,
    ) -> GeoNamesCityCandidate | None:
        self._ensure_loaded()
        if not city:
            return None

        key = _normalize_lookup(city)
        if not key:
            return None

        candidates = list(self._cities_by_name.get(key, []))
        if not candidates:
            return None

        if country_code:
            cc = country_code.strip().upper()
            candidates = [c for c in candidates if c.country_code == cc]
            if not candidates:
                return None

        if region:
            candidates = self._filter_by_region(candidates, region)
            if not candidates:
                return None

        deduped: dict[int, GeoNamesCityCandidate] = {}
        for candidate in candidates:
            existing = deduped.get(candidate.geonames_id)
            if existing is None or candidate.population > existing.population:
                deduped[candidate.geonames_id] = candidate
        candidates = list(deduped.values())

        if len(candidates) == 1:
            return candidates[0]

        unique_countries = {c.country_code for c in candidates}
        if len(unique_countries) == 1:
            # If caller provided region/country hints, selecting largest population
            # inside this already constrained set is deterministic and practical.
            if region or country_code:
                return max(candidates, key=lambda c: c.population)

            # For plain "City" text, only accept when one city is clearly dominant.
            ranked = sorted(candidates, key=lambda c: c.population, reverse=True)
            top = ranked[0]
            second = ranked[1]
            if top.population >= max(200_000, second.population * 8):
                return top

        return None

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True

        country_file = self._data_dir / "countryInfo.txt"
        admin1_file = self._data_dir / "admin1CodesASCII.txt"
        cities_file = self._data_dir / "cities15000.txt"

        if not country_file.exists():
            logger.info("GeoNames countryInfo not found at %s; resolver disabled", country_file)
            self._available = False
            return

        self._load_country_info(country_file)
        if admin1_file.exists():
            self._load_admin1(admin1_file)
        if cities_file.exists():
            self._load_cities(cities_file)
        self._available = True

    def _add_country_term(self, term: str | None, country_code: str) -> None:
        if not term:
            return
        for key in {_normalize_lookup(term), _normalize_compact(term)}:
            if key:
                self._country_lookup.setdefault(key, set()).add(country_code)

    def _load_country_info(self, file_path: Path) -> None:
        with file_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 5:
                    continue
                iso2 = parts[0].strip().upper()
                iso3 = parts[1].strip().upper()
                fips = parts[3].strip().upper()
                country_name = parts[4].strip()
                if len(iso2) != 2:
                    continue

                self._add_country_term(iso2, iso2)
                self._add_country_term(iso3, iso2)
                self._add_country_term(fips, iso2)
                self._add_country_term(country_name, iso2)

                pyc = pycountry.countries.get(alpha_2=iso2)
                if pyc is not None:
                    self._add_country_term(getattr(pyc, "name", None), iso2)
                    self._add_country_term(getattr(pyc, "official_name", None), iso2)
                    self._add_country_term(getattr(pyc, "common_name", None), iso2)

    def _load_admin1(self, file_path: Path) -> None:
        with file_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                code = parts[0].strip()
                if "." not in code:
                    continue
                country_code, admin1_code = code.split(".", 1)
                country_code = country_code.upper()
                admin1_code = admin1_code.upper()

                admin_name = parts[1].strip()
                admin_ascii = parts[2].strip() if len(parts) > 2 else ""
                canonical_name = _normalize_lookup(admin_ascii or admin_name)
                if canonical_name:
                    self._admin1_code_to_name[(country_code, admin1_code)] = canonical_name

                for candidate_name in {admin_name, admin_ascii}:
                    key = _normalize_lookup(candidate_name)
                    if key:
                        self._admin1_name_to_code[(country_code, key)] = admin1_code

    def _load_cities(self, file_path: Path) -> None:
        with file_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.rstrip("\n")
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) < 15:
                    continue
                try:
                    geonames_id = int(parts[0].strip())
                except ValueError:
                    continue
                name = parts[1].strip()
                ascii_name = parts[2].strip()
                country_code = parts[8].strip().upper()
                admin1_code = parts[10].strip().upper() or None
                try:
                    population = int(parts[14].strip() or "0")
                except ValueError:
                    population = 0

                if not name or not country_code:
                    continue

                city = GeoNamesCityCandidate(
                    geonames_id=geonames_id,
                    name=name,
                    country_code=country_code,
                    admin1_code=admin1_code,
                    population=population,
                )

                for key in {_normalize_lookup(name), _normalize_lookup(ascii_name)}:
                    if key:
                        self._cities_by_name.setdefault(key, []).append(city)

    def _filter_by_region(
        self, candidates: list[GeoNamesCityCandidate], region: str
    ) -> list[GeoNamesCityCandidate]:
        region_norm = _normalize_lookup(region)
        region_code = region.strip().upper()
        out: list[GeoNamesCityCandidate] = []

        for candidate in candidates:
            admin1_code = (candidate.admin1_code or "").upper()
            if not admin1_code:
                continue

            if region_code and admin1_code == region_code:
                out.append(candidate)
                continue

            admin_name = self._admin1_code_to_name.get((candidate.country_code, admin1_code))
            if admin_name and region_norm == admin_name:
                out.append(candidate)
                continue

            mapped = self._admin1_name_to_code.get((candidate.country_code, region_norm))
            if mapped and mapped == admin1_code:
                out.append(candidate)

        return out


@lru_cache(maxsize=1)
def get_geonames_resolver() -> GeoNamesResolver:
    return GeoNamesResolver()
