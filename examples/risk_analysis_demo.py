"""
Risk Analysis Demo

Demonstrates comprehensive risk detection and analysis capabilities.
"""

from contractex import extract_contract
from contractex.core.analyzers import RiskAnalyzer
from contractex.core.models import RiskSeverity

# Extract contract with risk analysis
contract = extract_contract(
    "contract.pdf",
    llm="gpt-4o",
    analyze_risks=True
)

print("=== Risk Analysis Report ===\n")
print(f"Contract: {contract.metadata.filename}")
print(f"Type: {contract.contract_type}")
print(f"Parties: {', '.join([p.name for p in contract.parties])}\n")

# Group risks by severity
risks_by_severity = {
    RiskSeverity.CRITICAL: [],
    RiskSeverity.HIGH: [],
    RiskSeverity.MEDIUM: [],
    RiskSeverity.LOW: [],
}

for risk in contract.risks:
    risks_by_severity[risk.severity].append(risk)

# Display critical risks
if risks_by_severity[RiskSeverity.CRITICAL]:
    print("🔴 CRITICAL RISKS (Immediate attention required)\n")
    for risk in risks_by_severity[RiskSeverity.CRITICAL]:
        print(f"• {risk.risk_type.upper()}")
        print(f"  Description: {risk.description}")
        print(f"  Location: {risk.clause_reference}")
        print(f"  Impact: {risk.impact}")
        print(f"  ✓ Recommendation: {risk.recommendation}")
        print(f"  Confidence: {risk.confidence:.0%}\n")

# Display high risks
if risks_by_severity[RiskSeverity.HIGH]:
    print("\n🟠 HIGH RISKS (Should be addressed)\n")
    for risk in risks_by_severity[RiskSeverity.HIGH]:
        print(f"• {risk.risk_type.replace('_', ' ').title()}")
        print(f"  {risk.description}")
        print(f"  → {risk.recommendation}\n")

# Display medium risks
if risks_by_severity[RiskSeverity.MEDIUM]:
    print(f"\n🟡 MEDIUM RISKS ({len(risks_by_severity[RiskSeverity.MEDIUM])} identified)")
    for risk in risks_by_severity[RiskSeverity.MEDIUM]:
        print(f"  • {risk.risk_type}: {risk.description}")

# Display low risks count
if risks_by_severity[RiskSeverity.LOW]:
    print(f"\n🟢 LOW RISKS ({len(risks_by_severity[RiskSeverity.LOW])} identified)\n")

# Create risk summary
print("\n" + "="*60)
print("SUMMARY")
print("="*60 + "\n")

total_risks = len(contract.risks)
print(f"Total Risks Identified: {total_risks}")
print(f"  Critical: {len(risks_by_severity[RiskSeverity.CRITICAL])}")
print(f"  High: {len(risks_by_severity[RiskSeverity.HIGH])}")
print(f"  Medium: {len(risks_by_severity[RiskSeverity.MEDIUM])}")
print(f"  Low: {len(risks_by_severity[RiskSeverity.LOW])}")

# Overall assessment
critical_count = len(risks_by_severity[RiskSeverity.CRITICAL])
high_count = len(risks_by_severity[RiskSeverity.HIGH])

if critical_count > 0:
    print("\n⚠️  RECOMMENDATION: Do NOT sign - contains critical risks")
elif high_count >= 3:
    print("\n⚠️  RECOMMENDATION: Negotiate - multiple high-risk items")
elif high_count > 0:
    print("\n✓ RECOMMENDATION: Review high-risk items before signing")
else:
    print("\n✓ RECOMMENDATION: Low risk - acceptable to sign with standard review")

# Export detailed report
contract.to_excel("risk_analysis_report.xlsx")
print("\nDetailed report exported to: risk_analysis_report.xlsx")

# Custom risk analysis with playbook
print("\n" + "="*60)
print("CUSTOM RISK PLAYBOOK ANALYSIS")
print("="*60 + "\n")

# Create custom risk playbook
custom_playbook = {
    "data_breach_liability": {
        "keywords": ["data breach", "security incident", "cyber attack"],
        "severity": "critical",
        "description": "Potential unlimited liability for data breaches",
        "recommendation": "Add data breach liability cap and cyber insurance requirement"
    },
    "ip_assignment": {
        "keywords": ["all intellectual property", "assign all rights", "work for hire"],
        "severity": "high",
        "description": "Broad IP assignment may transfer valuable IP",
        "recommendation": "Limit IP assignment to deliverables only"
    }
}

# Save custom playbook
import json
with open("custom_playbook.json", "w") as f:
    json.dump(custom_playbook, f, indent=2)

# Analyze with custom playbook
custom_analyzer = RiskAnalyzer(playbook_path="custom_playbook.json")
custom_risks = custom_analyzer.analyze(contract)

print(f"Custom analysis identified {len(custom_risks)} additional risks")
for risk in custom_risks:
    if risk not in contract.risks:  # New risks not already found
        print(f"  • {risk.risk_type}: {risk.description}")
