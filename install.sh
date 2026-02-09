#!/bin/bash
# ContractEx Installation Script
# This script helps you set up ContractEx for development or usage

set -e  # Exit on error

echo "🚀 ContractEx Installation Script"
echo "=================================="
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
REQUIRED_VERSION="3.9.0"

echo "✓ Found Python $PYTHON_VERSION"

# Version comparison function
version_ge() {
    printf '%s\n%s' "$2" "$1" | sort -V -C
}

if ! version_ge "$PYTHON_VERSION" "$REQUIRED_VERSION"; then
    echo "❌ Error: Python 3.9+ required, found $PYTHON_VERSION"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo "⚡ Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "📦 Upgrading pip..."
pip install --upgrade pip setuptools wheel

# Ask user what to install
echo ""
echo "Installation options:"
echo "1) Basic (core dependencies only)"
echo "2) Development (includes testing and linting tools)"
echo "3) All features (includes OCR, LangChain, spaCy, etc.)"
echo "4) Custom (choose specific features)"
echo ""
read -p "Select option [1-4]: " install_option

case $install_option in
    1)
        echo "📦 Installing core dependencies..."
        pip install -e .
        ;;
    2)
        echo "📦 Installing with development tools..."
        pip install -e ".[dev]"
        ;;
    3)
        echo "📦 Installing all features..."
        pip install -e ".[all]"
        ;;
    4)
        echo ""
        echo "Available features:"
        echo "  - ocr: OCR support (Tesseract, Pillow)"
        echo "  - cloud: Cloud OCR (Azure, AWS)"
        echo "  - langchain: LangChain integration"
        echo "  - spacy: spaCy NER support"
        echo "  - local: Local LLM support (Ollama)"
        echo "  - dev: Development tools"
        echo ""
        read -p "Enter features (comma-separated, e.g., 'ocr,langchain'): " features
        echo "📦 Installing with features: $features..."
        pip install -e ".[$features]"
        ;;
    *)
        echo "❌ Invalid option"
        exit 1
        ;;
esac

# Set up environment file
if [ ! -f ".env" ]; then
    echo ""
    echo "📝 Setting up environment variables..."
    cp .env.example .env
    echo "✓ Created .env file from template"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env and add your API keys:"
    echo "   - OPENAI_API_KEY (for OpenAI models)"
    echo "   - ANTHROPIC_API_KEY (for Claude models)"
    echo ""
    read -p "Open .env for editing now? [y/N]: " edit_env
    if [[ $edit_env =~ ^[Yy]$ ]]; then
        ${EDITOR:-nano} .env
    fi
else
    echo "✓ .env file already exists"
fi

# Run quick smoke test
echo ""
read -p "Run smoke test to verify installation? [Y/n]: " run_test
if [[ ! $run_test =~ ^[Nn]$ ]]; then
    echo "🧪 Running smoke test..."
    python3 -c "
import sys
try:
    from contractex import __version__
    from contractex.core.models import Contract, Party, Clause
    from contractex.llm.base import LLMProvider
    from contractex.loaders.base import DocumentLoader
    print(f'✓ ContractEx v{__version__} installed successfully!')
    print(f'✓ Core modules imported correctly')
    sys.exit(0)
except Exception as e:
    print(f'❌ Import error: {e}')
    sys.exit(1)
"
    if [ $? -eq 0 ]; then
        echo "✓ Installation verified!"
    else
        echo "❌ Installation verification failed"
        exit 1
    fi
fi

echo ""
echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Activate the virtual environment: source .venv/bin/activate"
echo "  2. Configure API keys in .env file"
echo "  3. Try an example: python examples/basic_extraction.py"
echo "  4. Read the documentation: cat README.md"
echo ""
echo "Quick test:"
echo "  python3 -c 'from contractex import extract_contract; print(extract_contract.__doc__)'"
echo ""
