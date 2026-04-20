"""
contractex.playbooks — Versioned, YAML-serializable contract analysis playbooks.

Usage::

    from contractex.playbooks import StandardNDAPlaybook, SaaSPlaybook, Playbook

    # Built-in playbooks
    nda_pb = StandardNDAPlaybook()
    saas_pb = SaaSPlaybook()

    # Load from YAML
    custom = Playbook.from_yaml_file("my_playbook.yaml")

    # Save to YAML
    nda_pb.to_yaml_file("nda_playbook.yaml")

    # Compose: inherit from base, override specific rules
    class MyNDAPlaybook(StandardNDAPlaybook):
        def __init__(self):
            super().__init__()
            self.version = "1.1"
            # Override or add rules
            self.rules.append(PlaybookRule(...))
"""

from contractex.playbooks.base import Playbook, PlaybookRule, RiskSeverity
from contractex.playbooks.nda import StandardNDAPlaybook
from contractex.playbooks.saas import SaaSPlaybook

__all__ = [
    "Playbook",
    "PlaybookRule",
    "RiskSeverity",
    "StandardNDAPlaybook",
    "SaaSPlaybook",
]
