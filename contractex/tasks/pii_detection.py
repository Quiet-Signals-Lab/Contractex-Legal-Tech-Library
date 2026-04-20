"""PII detection task — wraps PIIDetector as a pipeline stage."""

from __future__ import annotations

from contractex.core.document import LegalDoc
from contractex.core.legal_document import DocType
from contractex.privacy.detector import PIIDetector
from contractex.privacy.profile import PrivacyProfile
from contractex.tasks.base import LegalTask
from contractex.tasks.registry import TaskRegistry


class PIIDetectionTask(LegalTask):
    """
    Detect PII in a document's ``full_text`` and attach a ``PrivacyProfile``.

    After running this task:

    * ``doc.privacy_profile.contains_pii`` is set.
    * ``doc.privacy_profile.pii_entities_found`` lists detected entity types.
    * ``doc.extracted["pii_spans"]`` contains the raw ``PIISpan`` list.

    Parameters
    ----------
    entities:
        Entity types to detect.  ``None`` uses the detector's defaults.
    sensitivity:
        Sensitivity level to set on the document's PrivacyProfile when PII
        is detected.  Defaults to ``"confidential"``.
    """

    task_id = "pii_detection"
    doc_types: list[DocType] = []  # applies to all doc types
    requires_llm = False

    def __init__(
        self,
        entities: list[str] | None = None,
        sensitivity: str = "confidential",
    ) -> None:
        self._detector = PIIDetector(entities=entities)
        self._sensitivity = sensitivity

    def run(self, doc: LegalDoc, **kwargs: object) -> LegalDoc:
        if not doc.full_text:
            return doc

        language = doc.language or "en"
        spans = self._detector.detect(doc.full_text, language=language)

        # Attach / update PrivacyProfile
        profile = doc.privacy_profile
        if not isinstance(profile, PrivacyProfile):
            profile = PrivacyProfile(sensitivity="public")

        if spans:
            entity_types = list({s.entity_type for s in spans})
            profile = profile.model_copy(
                update={
                    "contains_pii": True,
                    "pii_entities_found": list(
                        dict.fromkeys(profile.pii_entities_found + entity_types)
                    ),
                    "sensitivity": (
                        self._sensitivity
                        if profile.sensitivity == "public"
                        else profile.sensitivity
                    ),
                }
            )
        else:
            profile = profile.model_copy(update={"contains_pii": False})

        doc = doc.model_copy(
            update={
                "privacy_profile": profile,
                "extracted": {**doc.extracted, "pii_spans": spans},
            }
        )
        return doc


# Self-register
TaskRegistry.default().register(PIIDetectionTask)
