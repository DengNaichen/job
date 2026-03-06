from __future__ import annotations

from app.services.domain.location.resolution import GeoNamesResolver


def _write(path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_lookup_country_codes_from_local_geonames(tmp_path) -> None:
    _write(
        tmp_path / "countryInfo.txt",
        "\n".join(
            [
                "#ISO\tISO3\tISONumeric\tfips\tCountry",
                "US\tUSA\t840\tUS\tUnited States",
                "GB\tGBR\t826\tUK\tUnited Kingdom",
            ]
        ),
    )

    resolver = GeoNamesResolver(tmp_path)

    assert resolver.lookup_country_codes("United States") == {"US"}
    assert resolver.lookup_country_codes("US") == {"US"}
    assert resolver.lookup_country_codes("U.S.") == {"US"}
    # UK comes from GeoNames FIPS code in countryInfo.txt
    assert resolver.lookup_country_codes("UK") == {"GB"}


def test_resolve_city_with_region_name_or_code(tmp_path) -> None:
    _write(
        tmp_path / "countryInfo.txt",
        "\n".join(
            [
                "#ISO\tISO3\tISONumeric\tfips\tCountry",
                "US\tUSA\t840\tUS\tUnited States",
                "GB\tGBR\t826\tUK\tUnited Kingdom",
            ]
        ),
    )
    _write(
        tmp_path / "admin1CodesASCII.txt",
        "\n".join(
            [
                "US.CA\tCalifornia\tCalifornia\t5332921",
                "GB.ENG\tEngland\tEngland\t6269131",
            ]
        ),
    )
    _write(
        tmp_path / "cities15000.txt",
        "\n".join(
            [
                "5391959\tSan Francisco\tSan Francisco\t\t37.7749\t-122.4194\tP\tPPLA2\tUS\t\tCA\t075\t\t\t873965\t0\t0\tAmerica/Los_Angeles\t2024-01-01",
                "2643743\tLondon\tLondon\t\t51.5085\t-0.1257\tP\tPPLC\tGB\t\tENG\t\t\t\t8961989\t0\t0\tEurope/London\t2024-01-01",
                "6058560\tLondon\tLondon\t\t42.9834\t-81.233\tP\tPPLA\tCA\t\tON\t\t\t\t422324\t0\t0\tAmerica/Toronto\t2024-01-01",
            ]
        ),
    )

    resolver = GeoNamesResolver(tmp_path)

    by_region_code = resolver.resolve_city(city="San Francisco", region="CA")
    assert by_region_code is not None
    assert by_region_code.country_code == "US"
    assert by_region_code.admin1_code == "CA"

    by_region_name = resolver.resolve_city(city="San Francisco", region="California")
    assert by_region_name is not None
    assert by_region_name.country_code == "US"
    assert by_region_name.admin1_code == "CA"

    # Ambiguous city without region/country hints should stay unresolved.
    assert resolver.resolve_city(city="London") is None
