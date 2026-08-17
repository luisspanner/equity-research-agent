"""Smoke tests for the package boundary."""


def test_package_can_be_imported() -> None:
    import equity_research_agent

    assert equity_research_agent is not None
