from llm.usage import Usage


def test_format_includes_tokens_cost_and_duration():
    usage = Usage(input_tokens=100, output_tokens=50, cost_usd=0.0123, duration_ms=800)

    formatted = usage.format()

    assert "100in/50out tokens" in formatted
    assert "$0.0123" in formatted
    assert "800ms" in formatted


def test_format_omits_fields_that_are_none():
    usage = Usage(input_tokens=100, output_tokens=50)

    formatted = usage.format()

    assert "100in/50out tokens" in formatted
    assert "$" not in formatted
    assert "ms" not in formatted


def test_format_with_nothing_known_says_unavailable():
    usage = Usage()

    assert usage.format() == "usage unavailable"


def test_format_treats_zero_tokens_as_known_not_missing():
    # input_tokens=0 is a real (if unusual) value, not "unknown" — only
    # None means unknown
    usage = Usage(input_tokens=0, output_tokens=10)

    formatted = usage.format()

    assert "0in/10out tokens" in formatted
