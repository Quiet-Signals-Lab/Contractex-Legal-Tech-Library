"""Playbook rules and YAML round-trip (contractex.playbooks, RiskAnalyzer)."""

from __future__ import annotations

import pytest

from contractex.analysis import RiskAnalyzer
from contractex.exceptions import ContractExError
from contractex.playbooks import (
    Playbook,
    PlaybookRule,
    RiskSeverity,
    SaaSPlaybook,
    StandardNDAPlaybook,
)


def rule(**conditions) -> PlaybookRule:
    return PlaybookRule(
        id="t.rule",
        clause_type="x",
        description="d",
        severity=RiskSeverity.LOW,
        **conditions,
    )


class TestRequiredKeywords:
    def test_one_keyword_present_is_enough(self):
        r = rule(required_keywords=["each party", "mutual", "both parties"])
        assert r.matches("Each party shall indemnify the other party.") is False

    def test_fires_when_every_keyword_is_absent(self):
        r = rule(required_keywords=["each party", "mutual", "both parties"])
        assert r.matches("The Recipient shall indemnify the Discloser.") is True

    def test_other_conditions_unchanged(self):
        assert rule(forbidden_keywords=["unlimited"]).matches("Unlimited liability.") is True
        assert rule(required_pattern=r"\d+\s+days").matches("promptly") is True
        assert rule(forbidden_pattern=r"sole discretion").matches("at its sole discretion") is True
        assert rule().matches("anything") is False


class TestBuiltInPlaybooks:
    def test_nda_playbook_does_not_flag_compliant_clauses(self):
        clauses = [
            {
                "clause_type": "indemnification",
                "text": "Each party shall indemnify, defend and hold harmless the other party.",
            },
            {
                "clause_type": "expiration_date",
                "text": "This Agreement expires after a period of two (2) years.",
            },
            {
                "clause_type": "non_compete",
                "text": "The restriction applies for two years after termination.",
            },
            {"clause_type": "governing_law", "text": "New York law governs."},
            {
                "clause_type": "confidentiality",
                "text": "Excludes information in the public domain or independently developed. "
                "Recipient shall return or destroy all copies.",
            },
        ]
        assert RiskAnalyzer(StandardNDAPlaybook()).analyze(clauses) == []

    def test_nda_playbook_still_flags_one_sided_indemnity(self):
        clauses = [
            {"clause_type": "indemnification", "text": "Recipient shall indemnify Discloser."},
            {"clause_type": "governing_law", "text": "New York law governs."},
        ]
        flags = RiskAnalyzer(StandardNDAPlaybook()).analyze(clauses)
        assert [f.playbook_rule for f in flags] == ["nda.indemnification.must_be_bilateral"]

    def test_missing_clause_rules(self):
        flags = RiskAnalyzer(SaaSPlaybook()).analyze([])
        assert {f.playbook_rule for f in flags} == {
            "saas.liability.no_cap",
            "saas.change_of_control.missing",
            "saas.audit.missing",
        }


class TestYaml:
    def test_round_trip(self):
        original = StandardNDAPlaybook()
        loaded = Playbook.from_yaml(original.to_yaml())
        assert loaded.name == original.name
        assert loaded.required_clauses == original.required_clauses
        assert loaded.rules == original.rules

    def test_subclass_with_its_own_init_can_load_yaml(self):
        loaded = StandardNDAPlaybook.from_yaml(SaaSPlaybook().to_yaml())
        assert isinstance(loaded, StandardNDAPlaybook)
        assert loaded.name == SaaSPlaybook().name
        assert loaded.rules == SaaSPlaybook().rules

    @pytest.mark.parametrize(
        "text",
        [
            "name: x\nversion: '1'\nrules:\n  - id: a\n",  # rule missing fields
            "version: '1'\n",  # no name
            "[]",  # not a mapping
            "name: x\nversion: '1'\nrules:\n  - id: a\n    clause_type: c\n"
            "    description: d\n    severity: catastrophic\n",  # unknown severity
            "name: [unclosed",  # not YAML
        ],
    )
    def test_malformed_yaml_raises_a_contractex_error(self, text):
        with pytest.raises(ContractExError):
            Playbook.from_yaml(text)

    def test_null_lists_load_as_empty(self):
        loaded = Playbook.from_yaml(
            "name: x\nversion: '1'\nrequired_clauses:\nrules:\n  - id: a\n    clause_type: c\n"
            "    description: d\n    severity: low\n    forbidden_keywords:\n"
        )
        assert loaded.required_clauses == []
        assert loaded.rules[0].matches("anything") is False

    def test_files_are_utf8(self, tmp_path):
        pb = Playbook(name="Prüfung §4", version="1", description="“quoted”")
        path = tmp_path / "pb.yaml"
        path.write_text("name: Prüfung §4\nversion: '1'\ndescription: “quoted”\n", encoding="utf-8")
        assert Playbook.from_yaml_file(str(path)).description == pb.description
        out = tmp_path / "out.yaml"
        pb.to_yaml_file(str(out))
        assert Playbook.from_yaml(out.read_text(encoding="utf-8")).name == pb.name

    def test_malformed_file_raises_a_contractex_error(self, tmp_path):
        path = tmp_path / "bad.yaml"
        path.write_text("version: '1'\n", encoding="utf-8")
        with pytest.raises(ContractExError):
            Playbook.from_yaml_file(str(path))
