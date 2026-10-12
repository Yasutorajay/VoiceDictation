from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_balanced_delivery_enables_live_preview_by_default() -> None:
    config = yaml.safe_load((ROOT / "config.default.yaml").read_text(encoding="utf-8-sig"))

    assert config["performance"]["mode"] == "balanced"
    assert config["live_preview"]["enabled"] is True


def test_delivery_can_disable_last_capture() -> None:
    config = yaml.safe_load((ROOT / "config.default.yaml").read_text(encoding="utf-8-sig"))

    assert config["recording"]["save_last_capture"] is False


def test_delivery_asr_thread_count_matches_portable_delivery() -> None:
    config = yaml.safe_load((ROOT / "config.default.yaml").read_text(encoding="utf-8-sig"))
    assert config["asr"]["num_threads"] == 4


def test_delivery_uses_automatic_language_detection() -> None:
    config = yaml.safe_load((ROOT / "config.default.yaml").read_text(encoding="utf-8-sig"))

    assert config["asr"]["language"] == "auto"
    assert config["postprocess"]["language_rule"] == "mixed"


def test_official_sensevoice_model_provenance_is_bundled() -> None:
    model_dir = ROOT / "data" / "models" / "sense-voice-int8"

    assert (model_dir / "LICENSE").is_file()
    provenance = (model_dir / "MODEL_PROVENANCE.md").read_text(encoding="utf-8")
    assert "iic/SenseVoiceSmall" in provenance
    assert "C71F0CE00BEC95B0" in provenance


def test_delivery_config_has_single_postprocess_section() -> None:
    text = (ROOT / "config.default.yaml").read_text(encoding="utf-8-sig")
    assert text.count("postprocess:") == 1
    config = yaml.safe_load(text)
    assert config["postprocess"].get("remove_fillers") is True
    assert config["postprocess"].get("polish_punctuation") is True
    assert config["postprocess"].get("summary_provider") == "disabled"


def test_build_uses_project_owned_models() -> None:
    script = (ROOT / "scripts" / "build_portable.ps1").read_text(encoding="utf-8-sig")

    assert 'Join-Path $ProjectRoot "data\\models"' in script
    assert '$env:LOCALAPPDATA' not in script


def test_build_explicitly_bundles_portaudio_runtime() -> None:
    script = (ROOT / "scripts" / "build_portable.ps1").read_text(encoding="utf-8-sig")

    assert "_sounddevice_data" in script
    assert "libportaudio64bit.dll" in script


def test_windows_build_has_product_identity_and_avoids_binary_compression() -> None:
    script = (ROOT / "scripts" / "build_portable.ps1").read_text(encoding="utf-8-sig")

    assert "--noupx" in script
    assert "--version-file" in script
    assert "VOICE_DICTATION_SIGN_THUMBPRINT" in script
    assert "Get-AuthenticodeSignature" in script


def test_readme_explains_that_audio_and_transcript_are_not_saved() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8-sig")

    assert "不会保存录音文件" in readme
    assert "不会保存识别文字文件" in readme
    assert "app.log" in readme


def test_standard_installer_uses_per_user_fixed_install_location() -> None:
    installer = (ROOT / "installer" / "VoiceDictation.iss").read_text(
        encoding="utf-8-sig"
    )

    assert "DefaultDirName={localappdata}\\Programs\\VoiceDictation" in installer
    assert "PrivilegesRequired=lowest" in installer
    assert "UninstallDisplayIcon={app}\\VoiceDictation.exe" in installer
    assert "Name: \"{autoprograms}\\VoiceDictation\"" in installer
    assert "Name: \"{autodesktop}\\VoiceDictation\"" in installer


def test_release_installer_build_requires_and_verifies_code_signing() -> None:
    script = (ROOT / "scripts" / "build_signed_installer.ps1").read_text(
        encoding="utf-8-sig"
    )

    assert "VOICE_DICTATION_SIGN_THUMBPRINT" in script
    assert "A trusted Authenticode certificate is required" in script
    assert "Get-AuthenticodeSignature" in script
    assert "SignatureStatus]::Valid" in script
    assert "SignedUninstaller=yes" in (ROOT / "installer" / "VoiceDictation.iss").read_text(
        encoding="utf-8-sig"
    )


def test_build_stages_before_publishing_and_never_deletes_existing_package() -> None:
    script = (ROOT / "scripts" / "build_portable.ps1").read_text(encoding="utf-8-sig")

    assert '[Guid]::NewGuid().ToString("N")' in script
    assert '[IO.FileMode]::CreateNew' in script
    assert 'if (Test-Path -LiteralPath $Dist)' in script
    assert 'if (Test-Path -LiteralPath $Zip)' in script
    assert 'Remove-Item -Recurse -Force $Dist' not in script
    assert '--distpath' in script
    assert '--workpath' in script
    assert '--specpath' in script


def test_build_cleans_its_verified_staging_directory() -> None:
    script = (ROOT / "scripts" / "build_portable.ps1").read_text(encoding="utf-8-sig")

    assert 'Test-SafeBuildDirectory' in script
    assert 'finally {' in script
    assert 'Remove-Item -LiteralPath $BuildRoot -Recurse -Force' in script
    assert '[IO.FileAttributes]::ReparsePoint' in script


def test_build_records_and_recovers_interrupted_two_file_publish() -> None:
    script = (ROOT / "scripts" / "build_portable.ps1").read_text(encoding="utf-8-sig")

    assert 'publish-state' in script
    assert 'An interrupted publish needs recovery' in script
    assert '$RollbackErrors' in script
    assert '$PublishedZip -and (Test-Path -LiteralPath $Zip)' in script
    assert 'Move-Item -LiteralPath $Dist -Destination $StagedDist' in script


def test_build_accepts_versioned_portable_output_names() -> None:
    script = (ROOT / "scripts" / "build_portable.ps1").read_text(encoding="utf-8-sig")

    assert "VoiceDictation-portable(?:-[A-Za-z0-9]" in script


def test_offline_bundle_uses_project_owned_models() -> None:
    script = (ROOT / "scripts" / "build_offline_bundle.ps1").read_text(encoding="utf-8-sig")

    assert 'Join-Path $ProjectRoot "data\\models"' in script
    assert '$env:LOCALAPPDATA' not in script
