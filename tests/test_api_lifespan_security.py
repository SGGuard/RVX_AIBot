import pytest

import config
import api_server


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        ValueError("Invalid test configuration"),
        RuntimeError("Unexpected validation failure"),
    ],
)
async def test_lifespan_stops_startup_when_config_validation_fails(monkeypatch, error):
    def fail_validation(**_kwargs):
        raise error

    monkeypatch.setattr(config, "validate_config", fail_validation)

    with pytest.raises(type(error), match=str(error)):
        async with api_server.lifespan(api_server.app):
            pytest.fail("Application startup continued after validation failure")
