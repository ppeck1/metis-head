from metis_head.startup_readiness import build_startup_readiness


def test_readiness_is_truthful_and_mce_stays_optional():
    report = build_startup_readiness({})
    by_name = {item["component"]: item for item in report["checks"]}
    assert report["ready_for_text"] is True
    assert report["selected_llm_provider"] == "mock"
    assert report["ready_for_browser_audio"] is False
    assert by_name["google"]["status"] == "disabled"
    assert by_name["project_atlas"]["status"] == "disabled"
    assert by_name["mce"] == {
        "component": "mce",
        "status": "disabled",
        "reason": "MCE is intentionally inactive and is not a startup dependency",
    }
    assert by_name["paid_usage"]["status"] == "disabled"
    assert by_name["language_model"]["status"] == "fixture_only"


def test_explicit_empty_environment_does_not_fall_back_to_process(monkeypatch):
    monkeypatch.setenv("METIS_MCP_ATLAS_ENABLED", "true")
    monkeypatch.setenv("METIS_MCP_ATLAS_COMMAND", "private-command")
    report = build_startup_readiness({})
    atlas = next(item for item in report["checks"] if item["component"] == "project_atlas")
    assert atlas["status"] == "disabled"


def test_google_readiness_uses_connected_record_not_client_secret_path():
    report = build_startup_readiness(
        {"METIS_GOOGLE_CLIENT_SECRETS": "configured-but-not-authorized"},
        connection_records=[{"provider": "google", "status": "connected", "account_id": "acct"}],
    )
    google = next(item for item in report["checks"] if item["component"] == "google")
    assert google["status"] == "configured"
    assert "connected account" in google["reason"]


def test_atlas_enabled_without_transport_is_unavailable():
    report = build_startup_readiness({
        "METIS_MCP_ENABLED": "true",
        "METIS_MCP_ATLAS_ENABLED": "true",
    })
    atlas = next(item for item in report["checks"] if item["component"] == "project_atlas")
    assert atlas["status"] == "unavailable"
    assert "remedy" in atlas


def test_service_mcp_gate_cannot_override_disabled_global_gate():
    report = build_startup_readiness({
        "METIS_MCP_ENABLED": "false",
        "METIS_MCP_ATLAS_ENABLED": "true",
        "METIS_MCP_ATLAS_COMMAND": "atlas-helper",
        "METIS_MCP_BOH_ENABLED": "true",
        "METIS_MCP_BOH_COMMAND": "boh-helper",
    })
    checks = {item["component"]: item for item in report["checks"]}
    assert checks["project_atlas"]["status"] == "disabled"
    assert "global" in checks["project_atlas"]["reason"]
    assert checks["boh"]["status"] == "disabled"
    assert "global" in checks["boh"]["reason"]


def test_openai_configuration_does_not_claim_disabled_route_is_ready():
    report = build_startup_readiness({
        "METIS_LLM_PROVIDER": "openai",
        "OPENAI_API_KEY": "fixture-not-used",
        "METIS_OPENAI_MODEL": "fixture-model",
        "METIS_PAID_BUDGET_USD": "1",
        "METIS_OPENAI_INPUT_USD_PER_MILLION": "1",
        "METIS_OPENAI_OUTPUT_USD_PER_MILLION": "1",
        "METIS_OPENAI_PRICING_VERSION": "fixture-v1",
    })
    model = next(item for item in report["checks"] if item["component"] == "language_model")
    assert report["ready_for_text"] is False
    assert model["status"] == "implemented_but_disabled"
    assert "guarded off" in model["reason"]


def test_effective_speech_selection_includes_engine_model_and_allow_gates(monkeypatch, tmp_path):
    monkeypatch.setattr("metis_head.startup_readiness.importlib.util.find_spec", lambda name: object())
    piper_exe = tmp_path / "piper.exe"
    piper_model = tmp_path / "voice.onnx"
    whisper_model = tmp_path / "whisper-small"
    whisper_model.mkdir()
    (whisper_model / "model.bin").write_bytes(b"fixture")
    piper_exe.write_bytes(b"fixture")
    piper_model.write_bytes(b"fixture")
    report = build_startup_readiness({
        "METIS_STT_ENGINE": "faster_whisper",
        "METIS_STT_MODEL": "small",
        "METIS_STT_MODEL_DIR": str(whisper_model),
        "METIS_STT_ALLOW_LOCAL": "true",
        "METIS_VOICE_ENABLED": "true",
        "METIS_VOICE_PROVIDER": "piper",
        "METIS_VOICE_ALLOW_PIPER": "true",
        "METIS_PIPER_EXE": str(piper_exe),
        "METIS_PIPER_MODEL": str(piper_model),
    })
    checks = {item["component"]: item for item in report["checks"]}
    assert report["selected_stt_provider"] == "faster_whisper"
    assert report["selected_tts_provider"] == "piper"
    assert checks["local_stt"]["status"] == "available"
    assert "small" in checks["local_stt"]["reason"]
    assert checks["local_tts"]["status"] == "available"
    assert report["ready_for_spoken_browser_loop"] is True


def test_piper_assets_do_not_make_tts_ready_without_effective_allow_gate(tmp_path):
    piper_exe = tmp_path / "piper.exe"
    piper_model = tmp_path / "voice.onnx"
    piper_exe.write_bytes(b"fixture")
    piper_model.write_bytes(b"fixture")
    report = build_startup_readiness({
        "METIS_VOICE_ENABLED": "true",
        "METIS_VOICE_PROVIDER": "piper",
        "METIS_VOICE_ALLOW_PIPER": "false",
        "METIS_PIPER_EXE": str(piper_exe),
        "METIS_PIPER_MODEL": str(piper_model),
    })
    tts = next(item for item in report["checks"] if item["component"] == "local_tts")
    assert tts["status"] == "disabled"
    assert "ALLOW_PIPER" in tts["reason"]


def test_whisper_dependency_without_confirmed_model_assets_is_only_configured(monkeypatch):
    monkeypatch.setattr("metis_head.startup_readiness.importlib.util.find_spec", lambda name: object())
    report = build_startup_readiness({
        "METIS_STT_ENGINE": "faster_whisper",
        "METIS_STT_MODEL": "small",
        "METIS_STT_ALLOW_LOCAL": "true",
    })
    stt = next(item for item in report["checks"] if item["component"] == "local_stt")
    assert stt["status"] == "configured"
    assert "not confirmed" in stt["reason"]
    assert report["ready_for_browser_audio"] is False


def test_readiness_uses_persisted_effective_settings_and_separates_evidence():
    setup = {
        "provider": {
            "choice": "ollama",
            "model": "saved-model:latest",
            "last_verification": {
                "status": "verified",
                "timestamp": "2026-09-16T12:00:00Z",
            },
        },
        "voice": {
            "enabled": True,
            "engine": "piper",
            "stt_provider": "faster_whisper",
            "last_verification": {
                "status": "verified",
                "timestamp": "2026-09-16T12:01:00Z",
            },
        },
    }

    report = build_startup_readiness({}, setup_state=setup)

    assert report["selected_llm_provider"] == "ollama"
    assert report["selected_stt_provider"] == "faster_whisper"
    assert report["selected_tts_provider"] == "piper"
    assert report["effective_configuration"]["llm"] == {
        "provider": "ollama",
        "model": "saved-model:latest",
        "source": "setup",
    }
    assert report["effective_configuration"]["stt"]["source"] == "setup"
    assert report["evidence"]["successful_local_execution"]["llm"].startswith("verified_local_probe:")
    assert report["evidence"]["operator_confirmed_physical_output"]["tts"].startswith("operator_confirmed:")
    assert report["evidence"]["successful_local_execution"]["stt"] == "not_recorded"
