"""Project-specific exception hierarchy."""


class KlaveEngineError(Exception):
    """Base error for all Klave Engine failures."""


class ConversionError(KlaveEngineError):
    """DWG-to-DXF conversion failed."""


class ProjectManifestError(KlaveEngineError):
    """Project manifest is missing, invalid, or inconsistent."""


class DxfParseError(KlaveEngineError):
    """A DXF file could not be opened or read."""


class NormalizationError(KlaveEngineError):
    """A DXF entity could not be normalized."""


class GeometryError(KlaveEngineError):
    """A geometry operation received invalid input."""


class GraphBuildError(KlaveEngineError):
    """Drawing graph construction failed."""


class DetectionError(KlaveEngineError):
    """A structural detector failed."""


class ReportGenerationError(KlaveEngineError):
    """A quantity or risk report could not be generated."""
