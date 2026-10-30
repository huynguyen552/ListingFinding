import pytest

from app.area_matching import AreaMatcher, text_matches

AREA = "đường huỳnh tấn phát, tân thuận, hồ chí minh"


@pytest.mark.parametrize(
    "address, expected",
    [
        ("228 Lê Trọng Tấn, khu phố 5, Tây Thạnh, Hồ Chí Minh, Việt Nam", True),
        ("440-440A Lê Trọng Tấn, Tây Thạnh, Hồ Chí Minh 700000", True),
        ("118/1 Lê Trọng Tấn, Tây Thạnh, Hồ Chí Minh", True),
        ("119 Lê Trọng Tấn, Tân Sơn Nhì, Hồ Chí Minh", False),
        ("45 Đường S9, Tây Thạnh, Hồ Chí Minh", False),
        ("228 Lê Trọng Tấn, Tây Thạnh, Đà Nẵng", False),
    ],
)
def test_bare_road_keeps_ward_and_city_constraints(address, expected):
    for area in (
        "lê trọng tấn, phường tây thạnh, hồ chí minh",
        "Lê Trọng Tấn, Tây Thạnh, TP.HCM",
    ):
        assert text_matches(address, area) is expected
        assert AreaMatcher(area).matches(address) is expected


def test_explicit_admin_label_cannot_match_street():
    assert not text_matches(
        "12 Đường Tây Thạnh, Phú Thọ Hòa, Tân Phú, Hồ Chí Minh",
        "Phường Tây Thạnh, Quận Tân Phú, Hồ Chí Minh",
    )
    assert text_matches(
        "12 Lê Trọng Tấn, Tây Thạnh, Tân Phú, Hồ Chí Minh",
        "Phường Tây Thạnh, Quận Tân Phú, Hồ Chí Minh",
    )


@pytest.mark.parametrize(
    "address",
    [
        "571 Huỳnh Tấn Phát, Tân Thuận, Hồ Chí Minh 700000, Việt Nam",
        "559 Đ. Huỳnh Tấn Phát, Tân Thuận, TP.HCM, Việt Nam",
        "đường Huỳnh Tấn Phát, Tân Thuận, Hồ Chí Minh, Việt Nam",
        "435/48 Huỳnh Tấn Phát, Tân Thuận, Hồ Chí Minh, Việt Nam",
        "538 A Huỳnh Tấn Phát, Tân Thuận, Hồ Chí Minh, Việt Nam",
        "538/2A, Huynh Tan Phat, Tan Thuan, Ho Chi Minh City",
        "Hẻm 538B Huỳnh Tấn Phát, Tân Thuận, Hồ Chí Minh, Việt Nam",
    ],
)
def test_street_prefix_and_house_variants(address):
    assert text_matches(address, AREA)
    assert AreaMatcher(AREA).matches(address)


def test_street_aliases_in_query():
    address = "571 Huỳnh Tấn Phát, Tân Thuận, Hồ Chí Minh"
    assert text_matches(address, "Đ. Huỳnh Tấn Phát, Phường Tân Thuận, TP.HCM")
    assert text_matches(address, "Street Huynh Tan Phat, Tan Thuan, Ho Chi Minh City")


def test_street_does_not_override_ward_or_city():
    assert not text_matches("1335 Huỳnh Tấn Phát, Phú Thuận, Hồ Chí Minh", AREA)
    assert not text_matches("571 Huỳnh Tấn Phát, Tân Thuận, Đà Nẵng", AREA)
    assert not text_matches("12 Đường Khác, Tân Thuận, Hồ Chí Minh", AREA)
    assert not text_matches(
        "12 Đường Khác, Phường Tân Thuận, Hồ Chí Minh", "Đường Tân Thuận, Hồ Chí Minh"
    )


def test_ward_named_like_street_does_not_activate_ward_geometry():
    matcher = AreaMatcher("Đường Tân Thuận, Hồ Chí Minh")
    assert matcher.boundary is None
    assert matcher.matches("12 Đường Tân Thuận, Phú Thuận, Hồ Chí Minh")
    assert AreaMatcher("Đường Hồ Chí Minh, Đà Nẵng").city_label != "Hồ Chí Minh"


def test_numbered_street_not_house_number_or_different_street():
    assert text_matches("12 Đ. Số 7, Đà Nẵng", "Đường số 7, Đà Nẵng")
    assert not text_matches("7 Nguyễn Văn Linh, Đà Nẵng", "Đường số 7, Đà Nẵng")
    assert not text_matches("12 Đường số 70, Đà Nẵng", "Đường số 7, Đà Nẵng")


def test_old_district_only_address_resolves_ward_by_real_place_coordinates():
    matcher = AreaMatcher(AREA)
    assert matcher.matches(
        "547 Huỳnh Tấn Phát, Quận 7, Hồ Chí Minh 77000, Việt Nam",
        "https://www.google.com/maps/place/test/data=!3d10.7432831!4d106.7298793",
    )
    assert not matcher.matches(
        "1335 Huỳnh Tấn Phát, Phú Thuận, Hồ Chí Minh, Việt Nam",
        "https://www.google.com/maps/place/test/data=!3d10.7168342!4d106.7369913",
    )
    assert not matcher.matches(
        "93 Đ. 14A, Tân Thuận, Hồ Chí Minh",
        "https://www.google.com/maps/place/test/data=!3d10.7487533!4d106.7182346",
    )


def test_skip_diagnostics_distinguish_road_and_ward():
    matcher = AreaMatcher(AREA)
    assert "tên đường" in matcher.evaluate("12 Nguyễn Văn Linh, Tân Thuận, Hồ Chí Minh")[1]
    assert (
        "ngoài phường"
        in matcher.evaluate(
            "1335 Huỳnh Tấn Phát, Phú Thuận, Hồ Chí Minh",
            "https://www.google.com/maps/place/test/data=!3d10.7168342!4d106.7369913",
        )[1]
    )
