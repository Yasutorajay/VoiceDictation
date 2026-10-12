from app.performance import PerformanceMode, resolve_performance_profile


def test_speed_profile_keeps_all_models_ready() -> None:
    profile = resolve_performance_profile({"performance": {"mode": "speed"}})

    assert profile.mode is PerformanceMode.SPEED
    assert profile.load_main_on_start is True
    assert profile.load_punctuation_on_start is True
    assert profile.use_subprocess is False


def test_balanced_profile_keeps_main_model_and_defers_punctuation() -> None:
    profile = resolve_performance_profile({"performance": {"mode": "balanced"}})

    assert profile.mode is PerformanceMode.BALANCED
    assert profile.load_main_on_start is True
    assert profile.load_punctuation_on_start is False
    assert profile.use_subprocess is False


def test_low_memory_profile_defers_models_and_uses_subprocess() -> None:
    profile = resolve_performance_profile(
        {"performance": {"mode": "low_memory", "idle_unload_minutes": 5}}
    )

    assert profile.mode is PerformanceMode.LOW_MEMORY
    assert profile.load_main_on_start is False
    assert profile.load_punctuation_on_start is False
    assert profile.use_subprocess is True
    assert profile.idle_unload_seconds == 300


def test_unknown_profile_safely_falls_back_to_balanced() -> None:
    profile = resolve_performance_profile({"performance": {"mode": "unknown"}})

    assert profile.mode is PerformanceMode.BALANCED

