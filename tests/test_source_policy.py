from __future__ import annotations

import pytest

from healthos.source_policy import SourceUse, assert_use_allowed, policy_for


def test_open_sources_are_machine_integrable() -> None:
    assert policy_for("usda_fdc").use is SourceUse.MACHINE_INTEGRATION
    assert policy_for("open_food_facts").use is SourceUse.MACHINE_INTEGRATION
    assert_use_allowed("usda_fdc", redistribution=True, commercial=True)
    assert_use_allowed("open_food_facts", redistribution=True, commercial=True)


def test_tbca_cannot_be_silently_redistributed_or_commercialized() -> None:
    assert policy_for("tbca").use is SourceUse.REFERENCE_ONLY
    with pytest.raises(PermissionError, match="redistribution"):
        assert_use_allowed("tbca", redistribution=True)
    with pytest.raises(PermissionError, match="commercial"):
        assert_use_allowed("tbca", commercial=True)


def test_unknown_sources_fail_closed() -> None:
    with pytest.raises(ValueError, match="unknown source policy"):
        policy_for("unknown")
