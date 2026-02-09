"""LangChain document loader compatibility adapter."""

from typing import List, Optional

from contractex.loaders.base import DocumentLoader
from contractex.exceptions import DocumentLoadError


class LangChainDocumentAdapter(DocumentLoader):
    """
    Adapter to use LangChain document loaders with ContractEx.
    
    This allows using any LangChain document loader (PDF, HTML, web scrapers, etc.)
    with the ContractEx extraction pipeline.
    """
    
    def __init__(self, langchain_loader):
        """
        Initialize adapter with a LangChain document loader.
        
        Args:
            langchain_loader: Any LangChain document loader instance
                             (e.g., PyPDFLoader, UnstructuredPDFLoader, etc.)
        """
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
    
    def get_metadata(self, source: str):
        """Get metadata from LangChain documents."""
        try:
            documents = self.langchain_loader.load()
            
            if documents:
                # Combine metadata from all documents
                combined_metadata = {}
                for doc in documents:
                    combined_metadata.update(doc.metadata)
                
                return combined_metadata
            else:
                return {}
                
        except Exception:
            return super().get_metadata(source)
