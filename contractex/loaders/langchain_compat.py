"""LangChain document loader compatibility adapter."""

from typing import Any, TYPE_CHECKING

from contractex.loaders.base import DocumentLoader
from contractex.exceptions import DocumentLoadError

# Optional LangChain imports
try:
    from langchain_core.documents import Document  # type: ignore[import-not-found]
    HAS_LANGCHAIN = True
except ImportError:
    try:
        from langchain.schema import Document  # type: ignore[import-not-found]
        HAS_LANGCHAIN = True
    except ImportError:
        # LangChain not installed - define placeholder for type checking
        if TYPE_CHECKING:
            Document = Any  # type: ignore[misc]
        else:
            Document = None  # type: ignore[misc]
        HAS_LANGCHAIN = False


class LangChainDocumentAdapter(DocumentLoader):
    """
    Adapter to use LangChain document loaders with ContractEx.
    
    This allows using any LangChain document loader (PDF, HTML, web scrapers, etc.)
    with the ContractEx extraction pipeline.
    
    Requires: pip install langchain or pip install langchain-core
    """
    
    def __init__(self, langchain_loader: Any):
        """
        Initialize adapter with a LangChain document loader.
        
        Args:
            langchain_loader: Any LangChain document loader instance
                             (e.g., PyPDFLoader, UnstructuredPDFLoader, etc.)
        
        Raises:
            ImportError: If langchain is not installed
        """
        if not HAS_LANGCHAIN:
            raise ImportError(
                "LangChain is not installed. Install with: "
                "pip install langchain or pip install langchain-core"
            )
        self.langchain_loader = langchain_loader
    
    def load(self, source: str) -> str:
        """
        Load document using LangChain loader.
        
        Args:
            source: Path or URL to load
        
        Returns:
            Concatenated text from all pages/chunks
        
        Raises:
            DocumentLoadError: If loading fails
        """
        try:
            # LangChain loaders return List[Document]
            documents = self.langchain_loader.load()
            
            # Concatenate all document contents
            text_parts = [doc.page_content for doc in documents]
            full_text = "\n\n".join(text_parts)
            
            return full_text
            
        except Exception as e:
            raise DocumentLoadError(
                f"LangChain loader failed: {str(e)}"
            ) from e
    
    def get_metadata(self, source: str) -> dict:
        """
        Get metadata from LangChain documents.
        
        Args:
            source: Path or URL (not used, metadata comes from loaded documents)
        
        Returns:
            Combined metadata dictionary from all loaded documents
        """
        try:
            documents = self.langchain_loader.load()
            
            if documents:
                # Combine metadata from all documents
                combined_metadata: dict = {}
                for doc in documents:
                    combined_metadata.update(doc.metadata)
                
                return combined_metadata
            else:
                return {}
                
        except Exception:
            return super().get_metadata(source)
