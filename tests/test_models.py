import pytest

from asnwero_bot.models import ProviderAuthError, ProviderRouter, TemporaryProviderError


class FakeProvider:
    def __init__(self, name, result=None, error=None):
        self.name = name
        self.model = f"{name}-model"
        self.result = result
        self.error = error
        self.calls = 0

    async def generate(self, source_text, tone, context=None):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


async def test_router_falls_back_after_temporary_error():
    first = FakeProvider("first", error=TemporaryProviderError("quota", retry_after=1))
    second = FakeProvider("second", result=["one", "two", "three"])
    router = ProviderRouter([first, second])

    result = await router.generate("hello", "short")

    assert result == ["one", "two", "three"]
    assert first.calls == 1
    assert second.calls == 1


async def test_router_disables_auth_failed_provider():
    first = FakeProvider("first", error=ProviderAuthError("bad key"))
    second = FakeProvider("second", result=["one", "two", "three"])
    router = ProviderRouter([first, second])

    await router.generate("hello", "short")

    assert router.statuses["first"].disabled is True


async def test_router_raises_when_all_providers_fail():
    router = ProviderRouter(
        [
            FakeProvider("first", error=TemporaryProviderError("quota")),
            FakeProvider("second", error=TemporaryProviderError("timeout")),
        ]
    )

    with pytest.raises(TemporaryProviderError):
        await router.generate("hello", "short")

