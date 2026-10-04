"""Minor-frame rate rule from ``AstraTMEncoder/_AstraTMEncoder.pas``.

``BuildPacketStream`` (194-195) tests the rule before ``Inc(Sequence)``
(208). ``Sequence`` starts at 0 (145). A packet rate of 0 is always due.
An IRIG rate of 0 is a divide by zero.
"""


def minor_frame_packet_id(stage: int) -> int:
    """Return the packet id the decoder logs for ``stage``.

    ``TAstraStageDecoder.Create`` (AstraTMoIP/AstraDecoder.pas 138) sets
    ``FPacketID = 100 * (stage - 1) + 106``.
    """
    if isinstance(stage, bool) or not isinstance(stage, int) or stage < 1:
        raise ValueError(f"stage must be an integer >= 1, got {stage!r}")
    return 100 * (stage - 1) + 106


def frame_due(sequence: int, packet_rate: int, irig_rate: int) -> bool:
    """Return whether ``packet_rate`` is included at ``sequence``.

    The Delphi test is ``(Sequence = 0) or (Sequence * PacketRate mod
    IRIGRate = 0)``, using ``Sequence`` before it increments.
    """
    _require_non_negative("sequence", sequence)
    _require_non_negative("packet_rate", packet_rate)
    if isinstance(irig_rate, bool) or not isinstance(irig_rate, int) or irig_rate < 0:
        raise ValueError(f"irig_rate must be an integer >= 0, got {irig_rate!r}")
    if irig_rate == 0:
        raise ZeroDivisionError("irig_rate is 0")
    return sequence == 0 or (sequence * packet_rate) % irig_rate == 0


def _require_non_negative(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be an integer >= 0, got {value!r}")
