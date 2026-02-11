"""
Example: Named Entity Recognition for Legal Documents

Demonstrates using the LegalNER module to extract parties, legal entities,
dates, and monetary values from contract text.

Requirements:
    pip install 'contractex[spacy]'
    python -m spacy download en_core_web_sm

Optional (for legal-specific model):
    pip install https://blackstone-model.s3-eu-west-1.amazonaws.com/en_blackstone_proto-0.0.1.tar.gz
"""

from contractex.core import LegalNER


def main():
    """Demonstrate NER extraction from contract text."""

    # Sample contract text
    contract_text = """
    This Agreement is entered into on January 15, 2024, between Acme Corporation,
    a Delaware corporation with offices at 123 Main Street, New York, NY 10001
    ("Company"), and Beta Industries LLC, a California limited liability company
    with offices at 456 Oak Avenue, San Francisco, CA 94102 ("Contractor").

    1. SERVICES AND PAYMENT
    Contractor shall provide software development services to Company for a fee
    of $150,000 payable in three installments of $50,000 each.

    2. TERM
    This Agreement shall commence on February 1, 2024 and continue until
    December 31, 2024, unless terminated earlier in accordance with Section 5.

    3. CONFIDENTIALITY
    Contractor agrees to maintain the confidentiality of Company's proprietary
    information and trade secrets during and after the term of this Agreement.

    4. GOVERNING LAW
    This Agreement shall be governed by the laws of the State of New York,
    without regard to its conflict of law provisions.
    """

    print("=" * 70)
    print("Named Entity Recognition Example")
    print("=" * 70)

    # Initialize NER with default English model
    print("\nInitializing NER...")
    ner = LegalNER(model_name="en_core_web_sm")
    print(f"Using model: {ner}")

    # Extract parties
    print("\n1. PARTIES IDENTIFIED:")
    print("-" * 70)
    parties = ner.extract_parties(contract_text)
    for i, party in enumerate(parties, 1):
        print(f"   {i}. {party}")

    # Extract dates
    print("\n2. DATES EXTRACTED:")
    print("-" * 70)
    dates = ner.extract_dates(contract_text)
    for date_info in dates:
        print(f"   - {date_info['text']} (position: {date_info['start']}-{date_info['end']})")

    # Extract monetary values
    print("\n3. MONETARY VALUES:")
    print("-" * 70)
    amounts = ner.extract_monetary_values(contract_text)
    for amount in amounts:
        print(f"   - {amount['text']}")

    # Extract all entities
    print("\n4. ALL ENTITIES:")
    print("-" * 70)
    all_entities = ner.extract_entities(contract_text)

    # Group by type
    by_type = {}
    for entity in all_entities:
        label = entity['label']
        if label not in by_type:
            by_type[label] = []
        by_type[label].append(entity['text'])

    for entity_type, values in sorted(by_type.items()):
        print(f"\n   {entity_type}:")
        for value in values[:5]:  # Show first 5 of each type
            print(f"      - {value}")
        if len(values) > 5:
            print(f"      ... and {len(values) - 5} more")

    # Comprehensive processing
    print("\n5. COMPREHENSIVE ANALYSIS:")
    print("-" * 70)
    results = ner.process_contract(contract_text)

    print(f"   Total entities found: {len(results['entities'])}")
    print(f"   Unique parties: {len(results['parties'])}")
    print(f"   Dates: {len(results['dates'])}")
    print(f"   Monetary values: {len(results['monetary_values'])}")
    print(f"   Legal entity categories: {len(results['legal_entities'])}")

    # Legal entities (if using Blackstone model)
    if results['legal_entities']:
        print("\n6. LEGAL ENTITIES (Blackstone model):")
        print("-" * 70)
        for entity_type, entities in results['legal_entities'].items():
            print(f"   {entity_type}: {entities}")

    print("\n" + "=" * 70)
    print("✓ NER extraction complete!")
    print("=" * 70)

    # Integration example with contract extraction
    print("\n" + "=" * 70)
    print("Integration with ContractExtractor")
    print("=" * 70)

    print("""
To use NER with the main contract extraction pipeline:

    from contractex import extract_contract
    from contractex.core import LegalNER

    # Extract contract
    contract = extract_contract("contract.pdf")

    # Apply NER to extract parties and entities
    ner = LegalNER()
    ner_results = ner.process_contract(contract.raw_text)

    # Access extracted information
    print(f"Parties: {ner_results['parties']}")
    print(f"Dates: {ner_results['dates']}")
    print(f"Amounts: {ner_results['monetary_values']}")
    """)


if __name__ == "__main__":
    try:
        main()
    except ImportError as e:
        print("=" * 70)
        print("ERROR: Missing dependencies")
        print("=" * 70)
        print(f"\n{str(e)}\n")
        print("To install spaCy support:")
        print("  pip install 'contractex[spacy]'")
        print("  python -m spacy download en_core_web_sm")
        print("\nFor legal-specific Blackstone model:")
        print("  pip install https://blackstone-model.s3-eu-west-1.amazonaws.com/en_blackstone_proto-0.0.1.tar.gz")
        print("=" * 70)
