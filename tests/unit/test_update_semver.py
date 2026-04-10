from core.update.service import _compare_versions, _parse_version, _is_prerelease


def test_parse_version_accepts_prerelease_and_build_metadata():
    assert _parse_version("v1.2.3-rc.5+build.77") == (1, 2, 3, ("rc", 5))


def test_compare_versions_stable_vs_prerelease_same_core():
    assert _compare_versions("1.0.0", "1.0.0-rc.5") > 0
    assert _compare_versions("1.0.0-rc.5", "1.0.0") < 0


def test_compare_versions_prerelease_progression():
    assert _compare_versions("1.0.0-rc.6", "1.0.0-rc.5") > 0
    assert _compare_versions("1.0.0-beta", "1.0.0-alpha") > 0


def test_compare_versions_core_version_still_dominates():
    assert _compare_versions("1.1.0-rc.1", "1.0.9") > 0


def test_compare_versions_equal_when_only_build_metadata_differs():
    assert _compare_versions("1.2.3+build.2", "1.2.3+build.1") == 0


def test_is_prerelease_detects_prerelease_tags():
    assert _is_prerelease("1.0.0-rc.1") is True
    assert _is_prerelease("v2.0.0-alpha") is True
    assert _is_prerelease("1.0.0-beta.2") is True


def test_is_prerelease_stable_tags():
    assert _is_prerelease("1.0.0") is False
    assert _is_prerelease("v2.1.3") is False
    assert _is_prerelease("1.0.0+build.5") is False
