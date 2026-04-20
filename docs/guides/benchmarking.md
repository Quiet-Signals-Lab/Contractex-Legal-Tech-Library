# Benchmark against CUAD

This guide shows how to measure ContractEx extraction quality against the CUAD dataset.

[CUAD](https://www.atticusprojectai.org/cuad) (Contract Understanding Atticus Dataset) contains
510 commercial contracts annotated across 41 clause types.

## Install benchmark dependencies

```bash
pip install "contractex[eval,datasets]"
```

## Run the benchmark

```python
from contractex.eval import CUADBenchmark
from contractex import ContractExtractor

extractor = ContractExtractor(llm_provider_name="gpt-4o")
bench = CUADBenchmark(extractor=extractor)

# Run against 50 contracts from the CUAD test split
results = bench.run(n_contracts=50, split="test", progress=True)

print(results.summary())
```

Example output:

```
CUAD Benchmark — ContractExtractor
Contracts: 50  |  Elapsed: 183.4s  |  Errors: 0

Clause Type                        Precision   Recall       F1
──────────────────────────────────────────────────────────────
governing_law                           0.94     0.91     0.92
termination_for_cause                   0.87     0.83     0.85
limitation_of_liability                 0.79     0.74     0.76
──────────────────────────────────────────────────────────────
Macro Average                           0.83     0.80     0.81
```

## Confidence calibration

```python
# Save a reliability diagram
results.calibration_plot(save_path="calibration.png")
```

## Build a calibration dataset from your own labels

```python
from contractex.eval import CalibrationAnalyzer

analyzer = CalibrationAnalyzer(n_bins=10)
analyzer.add(predicted_confidence=0.92, correct=True)
analyzer.add(predicted_confidence=0.61, correct=False)

cal = analyzer.analyze()
print(cal.ece())   # Expected Calibration Error
cal.plot(save_path="calibration.png")
```
