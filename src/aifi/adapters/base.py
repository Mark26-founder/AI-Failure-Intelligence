from abc import ABC, abstractmethod
from typing import Any, Dict, Union

from aifi.trace.schema import Trace
from aifi.trace.serialization import trace_from_dict
from aifi.trace.validator import validate_trace


class AdapterValidationError(Exception):
    """Raised when external data cannot be converted into a valid AIFI trace."""
    pass


class BaseAdapter(ABC):
    """
    Abstract Base Class for AIFI Adapters.

    An adapter translates an external execution data format (dict or parsed structure)
    into a normalized, valid AIFI Trace object.
    """

    @abstractmethod
    def adapt(self, external_data: Dict[str, Any]) -> Trace:
        """
        Convert external execution data into a normalized AIFI Trace.

        Must raise AdapterValidationError if the external_data is invalid,
        unsupported, or malformed.
        """
        pass


class GenericAdapter(BaseAdapter):
    """
    Generic Adapter for already structured execution data.

    Accepts structured dictionaries or raw trace structures, validates them against
    the AIFI schema, and returns a normalized Trace object.
    """

    def adapt(self, external_data: Dict[str, Any]) -> Trace:
        if not isinstance(external_data, dict):
            raise AdapterValidationError("External data must be a dictionary")

        try:
            # Validate dict format using core validator
            validate_trace(external_data)
            # Convert to Trace dataclass instance
            trace_obj = trace_from_dict(external_data)
            return trace_obj
        except Exception as exc:
            raise AdapterValidationError(f"Failed to adapt generic external data to AIFI Trace: {exc}") from exc
