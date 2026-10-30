import pytest

from app.area_matching import AreaMatcher, canonical, text_matches


@pytest.mark.parametrize(
    "district", ["quận Tân Phú", "Q. Tân Phú", "District Tan Phu", "Tan Phu District"]
)
def test_named_district_aliases_preserve_level(district):
    area = f"Lê Trọng Tấn, {district}, TP.HCM"
    address = "508 Lê Trọng Tấn, Tây Thạnh, Hồ Chí Minh"
    assert canonical(district) == "quantanphu"
    assert text_matches(address, area)
    assert AreaMatcher(area).matches(
        address, "https://google.com/maps/data=!3d10.8097255!4d106.6144057"
    )


def test_district_uses_coordinates_and_still_requires_requested_road():
    matcher = AreaMatcher("Lê Trọng Tấn, quận Tân Phú, Hồ Chí Minh")
    assert matcher.matches(
        "433 Lê Trọng Tấn, Tân Sơn Nhì, Hồ Chí Minh",
        "https://google.com/maps/data=!3d10.8087715!4d106.6162889",
    )
    assert not matcher.matches(
        "14A Dương Đức Hiền, Tây Thạnh, Hồ Chí Minh",
        "https://google.com/maps/data=!3d10.8071253!4d106.6274422",
    )
    assert not matcher.matches(
        "677 - 679 Lê Trọng Tấn, Bình Hưng Hòa, Hồ Chí Minh",
        "https://google.com/maps/data=!3d10.8147438!4d106.6045706",
    )
    # Coordinates override even an explicitly supplied district in the address.
    assert not matcher.matches(
        "12 Lê Trọng Tấn, Quận Tân Phú, Hồ Chí Minh",
        "https://google.com/maps/data=!3d10.777!4d106.700",
    )


def test_ward_is_not_entire_former_district_and_narrower_ward_is_retained():
    address = "508 Lê Trọng Tấn, Tây Thạnh, Hồ Chí Minh"
    url = "https://google.com/maps/data=!3d10.8097255!4d106.6144057"
    assert not AreaMatcher("Phường Tân Phú, Hồ Chí Minh").matches(address, url)
    assert not AreaMatcher("Phường Tân Sơn Nhì, Quận Tân Phú, Hồ Chí Minh").matches(address, url)
    assert AreaMatcher("Phường Tây Thạnh, Quận Tân Phú, Hồ Chí Minh").matches(address, url)


def test_fallback_does_not_use_street_name_or_cross_district_ward():
    area = "Quận Tân Phú, TP.HCM"
    assert not text_matches("12 Đường Tây Thạnh, Bình Hưng Hòa, Hồ Chí Minh", area)
    assert not text_matches("12 Lê Trọng Tấn, Tây Thạnh, Đà Nẵng", area)
    assert not text_matches("677 Lê Trọng Tấn, Bình Hưng Hòa, Hồ Chí Minh", area)
    assert text_matches("12 Lê Trọng Tấn, Phường Phú Thọ Hòa, Hồ Chí Minh 700000", area)
