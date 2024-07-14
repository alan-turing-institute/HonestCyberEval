import unittest.mock as mock
from pathlib import Path

from api.data_types import VulnerabilityWithSha

with mock.patch.dict("sys.modules", logger=mock.MagicMock()):
    from .vuln_discovery import remove_duplicate_vulns


def test_deduplication():
    v1 = VulnerabilityWithSha(
        harness_id="1", sanitizer_id="a", input_data="", input_file=Path(""), commit="abc", cp_source="test"
    )

    v2 = VulnerabilityWithSha(
        harness_id="1", sanitizer_id="a", input_data="", input_file=Path(""), commit="123", cp_source="test"
    )
    v3 = VulnerabilityWithSha(
        harness_id="1", sanitizer_id="b", input_data="", input_file=Path(""), commit="123", cp_source="test"
    )

    v4 = VulnerabilityWithSha(
        harness_id="1", sanitizer_id="a", input_data="", input_file=Path(""), commit="999", cp_source="test"
    )
    v5 = VulnerabilityWithSha(
        harness_id="1", sanitizer_id="b", input_data="", input_file=Path(""), commit="999", cp_source="test"
    )
    v6 = VulnerabilityWithSha(
        harness_id="1", sanitizer_id="c", input_data="", input_file=Path(""), commit="999", cp_source="test"
    )

    vulnerabilities = [v1, v2, v3, v4, v5, v6]
    deduped_vulns = remove_duplicate_vulns(vulnerabilities)

    assert set(deduped_vulns) == {v1, v3, v6}
