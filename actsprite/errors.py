"""Errors the command line reports as a plain message (bad input, nothing usable in the clip)."""


class PipelineError(RuntimeError):
    """Something about the input that the user can fix; the message says how."""
