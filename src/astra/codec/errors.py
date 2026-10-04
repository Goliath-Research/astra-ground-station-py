"""Failures while packing or unpacking an Astra payload."""


class CodecError(ValueError):
    """A layout or value cannot be packed or unpacked."""
