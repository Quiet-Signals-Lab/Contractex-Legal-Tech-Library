"""contractex.taxonomy: CUAD clause types and authority levels."""

from __future__ import annotations

from contractex.core.classifiers import CUADClassifier
from contractex.taxonomy import AuthorityLevel, AuthorityProfile, CUADClauseType


class TestCUADClauseType:
    def test_only_clause_types_are_members(self):
        assert len(CUADClauseType) == 41
        assert all(m.value == m.name.lower() for m in CUADClauseType)
        assert CUADClauseType.get_all_types()[-1] is CUADClauseType.MISCELLANEOUS

    def test_to_storage_type(self):
        assert CUADClauseType.to_storage_type(CUADClauseType.VENUE) == "dispute_resolution"
        assert CUADClauseType.to_storage_type(CUADClauseType.CAP_ON_LIABILITY) == "liability"
        assert CUADClauseType.to_storage_type(CUADClauseType.PARTIES) == "other"

    def test_classifier_default_types_are_clause_types(self):
        types = CUADClassifier().clause_types
        assert len(types) == 41
        assert all(t.isidentifier() for t in types)


class TestAuthority:
    def test_agency_guidance_is_not_binding(self):
        assert AuthorityLevel.AGENCY_GUIDANCE.is_binding() is False
        assert AuthorityLevel.TRIAL_COURT.is_binding() is True
        assert AuthorityLevel.SECONDARY_TREATISE.is_binding() is False

    def test_profile_derives_is_binding_when_not_supplied(self):
        assert AuthorityProfile(level=AuthorityLevel.SUPREME_COURT).is_binding is True
        assert AuthorityProfile(level=AuthorityLevel.LAW_REVIEW).is_binding is False
        assert AuthorityProfile(level=AuthorityLevel.AGENCY_GUIDANCE).is_binding is False

    def test_profile_keeps_an_explicit_is_binding(self):
        # e.g. a foreign supreme court cited as persuasive authority
        persuasive = AuthorityProfile(level=AuthorityLevel.SUPREME_COURT, is_binding=False)
        assert persuasive.is_binding is False
        assert AuthorityProfile(level=AuthorityLevel.LAW_REVIEW, is_binding=True).is_binding is True

    def test_for_level(self):
        assert AuthorityProfile.for_level(AuthorityLevel.REGULATION).is_binding is True
        assert AuthorityProfile.for_level(55).is_binding is False
