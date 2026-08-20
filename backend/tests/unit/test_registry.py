import pytest

from tonemill.profiles.base import ExecutionPath, GradingProfile
from tonemill.profiles.registry import ProfileRegistry, resolve_auto


class _FakeProfile(GradingProfile):
    def __init__(self, name: str, execution_path: ExecutionPath, available: bool) -> None:
        self.name = name
        self.source_format = "HLG/BT.2020"
        self.execution_path = execution_path
        self.implemented = True
        self._available = available

    async def is_available(self) -> bool:
        return self._available

    async def build_command(self, source_path, output_path, *, max_quality=False):  # noqa: ANN001
        raise NotImplementedError


def _registry(gpu_available: bool, cpu_available: bool) -> ProfileRegistry:
    registry = ProfileRegistry()
    registry.register(_FakeProfile("hlg-gpu", "gpu", gpu_available))
    registry.register(_FakeProfile("hlg-cpu", "cpu", cpu_available))
    return registry


async def test_auto_prefers_gpu_when_available():
    # Given both a GPU and a CPU profile are available
    registry = _registry(gpu_available=True, cpu_available=True)

    # When resolving "auto"
    resolved = await resolve_auto(registry)

    # Then the GPU profile wins
    assert resolved.name == "hlg-gpu"


async def test_auto_falls_back_to_cpu_when_gpu_unavailable():
    # Given the GPU profile isn't available on this host
    registry = _registry(gpu_available=False, cpu_available=True)

    # When resolving "auto"
    resolved = await resolve_auto(registry)

    # Then it falls back to the CPU profile
    assert resolved.name == "hlg-cpu"


async def test_auto_raises_when_nothing_available():
    # Given neither profile is available
    registry = _registry(gpu_available=False, cpu_available=False)

    # When resolving "auto"
    # Then resolution fails loudly rather than silently picking an unusable profile
    with pytest.raises(RuntimeError):
        await resolve_auto(registry)
