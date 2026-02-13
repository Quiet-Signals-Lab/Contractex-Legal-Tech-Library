"""Schemas and metadata for clause types."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ClauseTypeSchema(BaseModel):
    """Schema for defining custom clause types."""

    name: str = Field(..., description="Unique name/identifier for the clause type")
    display_name: str = Field(..., description="Human-readable display name")
    description: str = Field(..., description="Description of what this clause type represents")

    # Optional metadata
    risk_level: Optional[str] = Field(None, description="Risk level (low, medium, high, critical)")
    keywords: list[str] = Field(
        default_factory=list, description="Keywords associated with this type"
    )
    examples: list[str] = Field(default_factory=list, description="Example clauses of this type")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "force_majeure",
                "display_name": "Force Majeure",
                "description": "Excuses performance due to unforeseeable circumstances",
                "risk_level": "medium",
                "keywords": ["force majeure", "act of god", "unforeseeable"],
                "examples": [
                    "Neither party shall be liable for failure to perform due to acts of God..."
                ],
            }
        }
    )


class CustomClauseRegistry:
    """Registry for managing custom clause types."""

    def __init__(self):
        """Initialize the registry."""
        self._registry: dict[str, ClauseTypeSchema] = {}

    def register(self, clause_type: ClauseTypeSchema) -> None:
        """
        Register a custom clause type.

        Args:
            clause_type: Clause type schema to register
        """
        self._registry[clause_type.name] = clause_type

    def get(self, name: str) -> Optional[ClauseTypeSchema]:
        """
        Get a clause type by name.

        Args:
            name: Clause type name

        Returns:
            ClauseTypeSchema if found, None otherwise
        """
        return self._registry.get(name)

    def get_all(self) -> list[ClauseTypeSchema]:
        """
        Get all registered clause types.

        Returns:
            List of all clause types
        """
        return list(self._registry.values())

    def unregister(self, name: str) -> bool:
        """
        Unregister a clause type.

        Args:
            name: Clause type name to remove

        Returns:
            True if removed, False if not found
        """
        if name in self._registry:
            del self._registry[name]
            return True
        return False


# Global registry instance
_global_registry = CustomClauseRegistry()


def register_clause_type(clause_type: ClauseTypeSchema) -> None:
    """Register a custom clause type globally."""
    _global_registry.register(clause_type)


def get_clause_type(name: str) -> Optional[ClauseTypeSchema]:
    """Get a clause type from the global registry."""
    return _global_registry.get(name)


def get_all_clause_types() -> list[ClauseTypeSchema]:
    """Get all registered clause types."""
    return _global_registry.get_all()
