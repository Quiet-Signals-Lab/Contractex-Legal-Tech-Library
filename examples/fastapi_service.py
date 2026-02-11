"""
FastAPI Service Example

Wrap ContractEx in a REST API for web applications.
"""

import tempfile
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile

from contractex import ContractExtractor

app = FastAPI(
    title="ContractEx API",
    description="Contract intelligence extraction API",
    version="0.1.0"
)

# Initialize extractor
extractor = ContractExtractor(
    llm_provider_name="gpt-4o",
    confidence_threshold=0.7
)


@app.post("/extract", response_model=dict)
async def extract_contract(
    file: UploadFile = File(...),
    analyze_risks: bool = True,
    extract_financial: bool = True
):
    """
    Extract contract data from uploaded document.

    Supports PDF and DOCX files.
    """
    # Check file type
    if not file.filename.endswith(('.pdf', '.docx')):
        raise HTTPException(
            status_code=400,
            detail="Only PDF and DOCX files are supported"
        )

    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Extract contract
        contract = extractor.extract(
            tmp_path,
            analyze_risks=analyze_risks,
            extract_financial=extract_financial
        )

        # Clean up temp file
        Path(tmp_path).unlink()

        # Return as JSON
        return contract.model_dump()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/extract/batch")
async def extract_batch(files: list[UploadFile] = File(...)):
    """Extract multiple contracts in batch."""
    results = []

    for file in files:
        try:
            # Save temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
                content = await file.read()
                tmp.write(content)
                tmp_path = tmp.name

            # Extract
            contract = extractor.extract(tmp_path)

            # Clean up
            Path(tmp_path).unlink()

            results.append({
                "filename": file.filename,
                "success": True,
                "data": contract.model_dump()
            })

        except Exception as e:
            results.append({
                "filename": file.filename,
                "success": False,
                "error": str(e)
            })

    return {"results": results}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "ContractEx API"}


@app.get("/info")
async def get_info():
    """Get API information."""
    return {
        "version": "0.1.0",
        "llm_provider": extractor.llm_provider.__class__.__name__,
        "supported_formats": ["pdf", "docx"],
        "features": [
            "clause_extraction",
            "party_identification",
            "financial_term_extraction",
            "risk_analysis",
            "CUAD_taxonomy"
        ]
    }


if __name__ == "__main__":
    # Run with: python fastapi_service.py
    uvicorn.run(app, host="0.0.0.0", port=8000)

    # Access API docs at: http://localhost:8000/docs
    # Test endpoint: curl -X POST -F "file=@contract.pdf" http://localhost:8000/extract
