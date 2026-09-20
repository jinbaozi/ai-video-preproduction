"""Schema-governed local runtime for AI comic-drama workflows."""

from .v4 import V4Kernel as WorkflowKernel

__all__ = ["WorkflowKernel"]
__version__ = "0.4.0"
