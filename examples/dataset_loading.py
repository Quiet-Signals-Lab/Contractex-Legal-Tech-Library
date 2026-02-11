"""
Example: Loading and Using Legal Contract Datasets

Demonstrates loading legal datasets for training, evaluation, and benchmarking:
- ACORD, CUAD, LePaRD (contracts and case law)
- CLERC, ECtHR-PCR, ALQA (case retrieval and legal Q&A)

Datasets display attribution messages on first load to comply with
license requirements. Use verbose=False to suppress.

Requirements:
    pip install 'contractex[datasets]'
"""

import pandas as pd

from contractex.data import (
    load_acord,
    load_alqa,
    load_clerc,
    load_cuad,
    load_ecthr_pcr,
    load_lepard,
)


def demo_acord():
    """Demonstrate ACORD dataset loading."""
    print("=" * 70)
    print("ACORD (Atticus Clause Retrieval Dataset)")
    print("=" * 70)

    try:
        # Load training data
        train_df = load_acord(split='train')

        print(f"\n✓ Loaded {len(train_df)} training examples")
        print(f"Columns: {train_df.columns.tolist()}")
        print("\nFirst row:")
        print(train_df.head(1).to_dict('records')[0])

        # Load test data
        test_df = load_acord(split='test')
        print(f"\n✓ Loaded {len(test_df)} test examples")

    except Exception as e:
        print(f"\n✗ Error loading ACORD: {e}")
        print("Install with: pip install datasets")


def demo_cuad():
    """Demonstrate CUAD dataset loading."""
    print("\n" + "=" * 70)
    print("CUAD (Contract Understanding Atticus Dataset)")
    print("=" * 70)
    print("\nNote: Attribution message will be shown on first load\n")

    try:
        # Load from HuggingFace (faster) - shows attribution
        df = load_cuad(split='train', use_huggingface=True)

        print(f"\n✓ Loaded {len(df)} contract examples")
        print(f"Columns: {df.columns.tolist()}")

        # Analyze clause types
        if 'question' in df.columns:
            clause_types = df['question'].unique()
            print(f"\nClause types: {len(clause_types)}")
            print("\nSample clause types:")
            for i, clause_type in enumerate(sorted(clause_types)[:5]):
                print(f"  {i+1}. {clause_type}")
            print(f"  ... and {len(clause_types) - 5} more")

        # Show a sample contract
        print("\nSample contract:")
        sample = df.iloc[0]
        print(f"  Title: {sample.get('title', 'N/A')}")
        if 'context' in sample:
            print(f"  Text length: {len(str(sample['context']))} characters")
            print(f"  Preview: {str(sample['context'])[:200]}...")

    except Exception as e:
        print(f"\n✗ Error loading CUAD: {e}")
        print("Install with: pip install datasets")


def demo_lepard():
    """Demonstrate LePaRD dataset loading."""
    print("\n" + "=" * 70)
    print("LePaRD (Legal Passage Retrieval Dataset)")
    print("=" * 70)

    try:
        # Try HuggingFace first
        df = load_lepard(use_huggingface=True)

        print(f"\n✓ Loaded {len(df)} legal passage examples")
        print(f"Columns: {df.columns.tolist()}")

        # Show statistics
        print("\nDataset statistics:")
        if 'court' in df.columns:
            print(f"  Unique courts: {df['court'].nunique()}")
        if 'date' in df.columns:
            print(f"  Date range: {df['date'].min()} to {df['date'].max()}")

        # Show sample
        print("\nSample passage:")
        sample = df.iloc[0]
        for col in ['passage_id', 'quote', 'court', 'date']:
            if col in sample:
                value = str(sample[col])
                if len(value) > 100:
                    value = value[:100] + "..."
                print(f"  {col}: {value}")

    except Exception as e:
        print(f"\n✗ Error loading LePaRD: {e}")
        print("Note: LePaRD may require manual download from:")
        print("  https://github.com/rmahari/LePaRD")


def demo_cuad_analysis():
    """Demonstrate CUAD dataset analysis with contractex."""
    print("\n" + "=" * 70)
    print("CUAD Analysis with ContractEx")
    print("=" * 70)

    try:
        # Note: Requires contractex package to be installed
        # from contractex import extract_contract

        # Load a small sample
        df = load_cuad(split='train', use_huggingface=True)

        # Take first contract
        sample = df.iloc[0]

        if 'context' in sample:
            contract_text = str(sample['context'])

            print(f"\nAnalyzing contract: {sample.get('title', 'Unknown')}")
            print(f"Text length: {len(contract_text)} characters")

            print("\n[Note: Actual extraction would require API keys]")
            print("Example:")
            print("  contract = extract_contract(contract_text)")
            print("  print(f'Extracted {len(contract.clauses)} clauses')")
            print("  print(f'Identified {len(contract.parties)} parties')")

            # Show what ground truth looks like
            if 'answers' in sample:
                answers = sample['answers']
                print(f"\nGround truth: {answers}")

    except ImportError:
        print("\ncontractex not installed")
    except Exception as e:
        print(f"\n✗ Error in analysis: {e}")


def demo_data_statistics():
    """Show statistics for all datasets."""
    print("\n" + "=" * 70)
    print("Dataset Statistics Summary")
    print("=" * 70)

    stats = []

    # ACORD
    try:
        train = load_acord(split='train')
        test = load_acord(split='test')
        stats.append({
            'Dataset': 'ACORD',
            'Train Size': len(train),
            'Test Size': len(test),
            'License': 'CC BY 4.0'
        })
    except Exception:
        stats.append({
            'Dataset': 'ACORD',
            'Train Size': 'Error',
            'Test Size': 'Error',
            'License': 'CC BY 4.0'
        })

    # CUAD
    try:
        train = load_cuad(split='train')
        test = load_cuad(split='test')
        stats.append({
            'Dataset': 'CUAD',
            'Train Size': len(train),
            'Test Size': len(test),
            'License': 'CC BY 4.0'
        })
    except Exception:
        stats.append({
            'Dataset': 'CUAD',
            'Train Size': 'Error',
            'Test Size': 'Error',
            'License': 'CC BY 4.0'
        })

    # LePaRD
    try:
        data = load_lepard()
        stats.append({
            'Dataset': 'LePaRD',
            'Train Size': len(data),
            'Test Size': 'N/A',
            'License': 'Academic'
        })
    except Exception:
        stats.append({
            'Dataset': 'LePaRD',
            'Train Size': 'Error',
            'Test Size': 'N/A',
            'License': 'Academic'
        })

    # Print table
    stats_df = pd.DataFrame(stats)
    print("\n" + stats_df.to_string(index=False))

    print("\n" + "=" * 70)
    print("License Information")
    print("=" * 70)
    print("\nCC BY 4.0 (ACORD, CUAD):")
    print("  ✓ Free to use, share, and adapt")
    print("  ✓ Must give appropriate credit")
    print("  ✓ Must provide link to license")
    print("  ✓ Must indicate if changes were made")
    print("\nAcademic (LePaRD):")
    print("  ✓ Cite the paper when using")
    print("  ✓ Check repository for usage terms")


def demo_clerc():
    """Demonstrate CLERC dataset loading."""
    print("\n" + "=" * 70)
    print("CLERC (Legal Case Retrieval and Analysis Generation)")
    print("=" * 70)
    print("\nNote: Attribution message will be shown on first load\n")

    try:
        # Load retrieval split
        retrieval_df = load_clerc(split='retrieval')

        print(f"\n✓ Loaded {len(retrieval_df)} retrieval examples")
        print(f"Columns: {retrieval_df.columns.tolist()}")

        # Try generation split
        try:
            gen_df = load_clerc(split='generation')
            print(f"✓ Loaded {len(gen_df)} generation examples")
        except Exception:
            print("(Generation split may require different handling)")

    except Exception as e:
        print(f"\n✗ Error loading CLERC: {e}")
        print("Install with: pip install 'contractex[datasets]'")


def demo_ecthr():
    """Demonstrate ECtHR-PCR dataset loading."""
    print("\n" + "=" * 70)
    print("ECtHR-PCR (European Court of Human Rights Prior Case Retrieval)")
    print("=" * 70)
    print("\nNote: Attribution message will be shown on first load\n")

    try:
        # Load training data
        train_df = load_ecthr_pcr(split='train')

        print(f"\n✓ Loaded {len(train_df)} training cases")
        print(f"Columns: {train_df.columns.tolist()}")

        # Show sample case
        if len(train_df) > 0:
            sample = train_df.iloc[0]
            print("\nSample ECHR case:")
            for col in ['case_id', 'facts', 'outcome']:
                if col in sample:
                    value = str(sample[col])
                    if len(value) > 100:
                        value = value[:100] + "..."
                    print(f"  {col}: {value}")

    except Exception as e:
        print(f"\n✗ Error loading ECtHR-PCR: {e}")
        print("Install with: pip install 'contractex[datasets]'")


def demo_alqa():
    """Demonstrate ALQA dataset loading."""
    print("\n" + "=" * 70)
    print("ALQA (Open Australian Legal QA)")
    print("=" * 70)
    print("\nNote: Attribution message will be shown on first load\n")

    try:
        # Load dataset
        df = load_alqa()

        print(f"\n✓ Loaded {len(df)} Q&A pairs")
        print(f"Columns: {df.columns.tolist()}")

        # Show sample Q&A
        if len(df) > 0:
            sample = df.iloc[0]
            print("\nSample Australian legal Q&A:")
            for col in ['question', 'answer']:
                if col in sample:
                    value = str(sample[col])
                    if len(value) > 150:
                        value = value[:150] + "..."
                    print(f"  {col}: {value}")

    except Exception as e:
        print(f"\n✗ Error loading ALQA: {e}")
        print("Install with: pip install 'contractex[datasets]'")


def demo_custom_cache():
    """Demonstrate custom cache directory usage."""
    print("\n" + "=" * 70)
    print("Custom Cache Directories")
    print("=" * 70)

    from pathlib import Path

    print("\nDefault cache location (platformdirs):")
    try:
        from platformdirs import user_cache_dir
        default_cache = Path(user_cache_dir('contractex', appauthor=False))
        print(f"  {default_cache / 'datasets'}")
    except ImportError:
        print("  ./data/ (fallback, platformdirs not installed)")

    print("\nOption 1: Environment variable (affects all loads)")
    print("  export CONTRACTEX_CACHE_DIR='/path/to/cache'")
    print("  # All datasets will be cached in /path/to/cache/")

    print("\nOption 2: Function parameter (per-call)")
    print("  df = load_cuad(cache_dir='./offline_data/cuad')")
    print("  # Only this call uses the custom directory")

    print("\nExample: Offline/development setup")
    print("-" * 70)
    print("""
    import os
    from contractex.data import load_cuad

    # Set local cache for offline work
    os.environ['CONTRACTEX_CACHE_DIR'] = './data'

    # All downloads go to ./data/
    cuad_df = load_cuad()  # -> ./data/cuad/
    acord_df = load_acord()  # -> ./data/acord/
    """)

    print("\nWhy separate from package?")
    print("  ✓ Keeps pip install fast (~few MB vs 100+ MB)")
    print("  ✓ No permission issues with site-packages")
    print("  ✓ Easy to manage and clean up")
    print("  ✓ Follows Python standards (like scikit-learn, datasets)")


def main():
    """Run all dataset demos."""
    print("\n" + "=" * 70)
    print("Legal Contract Datasets Demo")
    print("=" * 70)
    print("\nThis demo loads and explores popular legal contract datasets")
    print("used for training and evaluating contract analysis models.\n")

    # Run demos
    print("\n📋 Contract & Case Law Datasets:")
    demo_acord()
    demo_cuad()
    demo_lepard()

    print("\n📚 Additional Legal Datasets:")
    demo_clerc()
    demo_ecthr()
    demo_alqa()

    print("\n⚙️  Configuration & Usage:")
    demo_custom_cache()
    demo_cuad_analysis()
    demo_data_statistics()

    print("\n" + "=" * 70)
    print("Dataset Loading Complete!")
    print("=" * 70)
    print("\nNext steps:")
    print("  1. Use these datasets to train custom models")
    print("  2. Benchmark contractex extraction performance")
    print("  3. Fine-tune LLMs on domain-specific data")
    print("  4. Build retrieval systems for clause search")
    print("\nTip: Use verbose=False to suppress attribution in automated scripts")
    print("For more info: contractex.data.README.md")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user.")
    except Exception as e:
        print(f"\n\nError running demo: {e}")
        print("Make sure to install dependencies:")
        print("  pip install 'contractex[datasets]'")
        print("  # This installs: datasets, requests, platformdirs")
        print("Or install manually:")
        print("  pip install datasets requests pandas platformdirs")
