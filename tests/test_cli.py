"""CLI stories: every invocation a single beat."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import lib_cli_exit_tools
import pytest
from click.testing import CliRunner, Result
from lib_layered_config import Config

from finanzonline_uid import __init__conf__
from finanzonline_uid import cli as cli_mod
from finanzonline_uid.enums import FileFormat


@dataclass(slots=True)
class CapturedRun:
    """Record of a single ``lib_cli_exit_tools.run_cli`` invocation.

    Attributes:
        command: Command object passed to ``run_cli``.
        argv: Argument vector forwarded to the command, when any.
        prog_name: Program name announced in the help output.
        signal_specs: Signal handlers registered by the runner.
        install_signals: ``True`` when the runner installed default signal handlers.
    """

    command: Any
    argv: Sequence[str] | None
    prog_name: str | None
    signal_specs: Any
    install_signals: bool


def _capture_run_cli(target: list[CapturedRun]) -> Callable[..., int]:
    """Return a stub that records lib_cli_exit_tools.run_cli invocations.

    Tests assert that the CLI delegates to lib_cli_exit_tools with the
    expected arguments; recording each call keeps those assertions readable.

    Args:
        target: Mutable list that will collect CapturedRun entries.

    Returns:
        Replacement callable for lib_cli_exit_tools.run_cli.
    """

    def _run(
        command: Any,
        argv: Sequence[str] | None = None,
        *,
        prog_name: str | None = None,
        signal_specs: Any = None,
        install_signals: bool = True,
    ) -> int:
        target.append(
            CapturedRun(
                command=command,
                argv=argv,
                prog_name=prog_name,
                signal_specs=signal_specs,
                install_signals=install_signals,
            )
        )
        return 42

    return _run


def _dependencies(
    *,
    load_config: cli_mod.ConfigLoader | None = None,
    deploy_configuration: cli_mod.ConfigDeployer | None = None,
) -> cli_mod.CliDependencies:
    """The production collaborators with the given ones swapped in, for Click's ``obj``."""
    production = cli_mod.production_dependencies()
    return dataclasses.replace(
        production,
        load_config=load_config or production.load_config,
        deploy_configuration=deploy_configuration or production.deploy_configuration,
    )


def _fixed_config(config: Any) -> cli_mod.ConfigLoader:
    """A configuration loader that returns ``config`` for every profile."""

    def load(*, profile: str | None = None) -> Any:
        return config

    return load


def _check_dependencies(
    fo_config: Any,
    use_case: Any,
    *,
    config: Config | None = None,
    email_sender: Any = None,
) -> cli_mod.CliDependencies:
    """Collaborators for a ``check`` run that never reaches FinanzOnline.

    Args:
        fo_config: What reading ``[finanzonline]`` returns, or the exception it raises.
        use_case: What every check attempt runs (its ``execute`` is called).
        config: The layered configuration (empty when omitted).
        email_sender: Replaces the email adapter; the real one when omitted.
    """
    production = cli_mod.production_dependencies()

    def read_fo_config(_config: Config) -> Any:
        if isinstance(fo_config, BaseException):
            raise fo_config
        return fo_config

    def build_uid_checker(_fo_config: Any, _notifier: Any) -> Any:
        return use_case

    def build_email_sender(_email_config: Any) -> Any:
        return email_sender

    return dataclasses.replace(
        production,
        load_config=_fixed_config(config if config is not None else Config({}, {})),
        load_finanzonline_config=read_fo_config,
        build_uid_checker=build_uid_checker,
        build_email_sender=build_email_sender if email_sender is not None else production.build_email_sender,
    )


@pytest.mark.os_agnostic
def test_when_we_snapshot_traceback_the_initial_state_is_quiet(isolated_traceback_config: None) -> None:
    """Verify snapshot_traceback_state returns (False, False) initially."""
    assert cli_mod.snapshot_traceback_state() == (False, False)


@pytest.mark.os_agnostic
def test_when_we_enable_traceback_the_config_sings_true(isolated_traceback_config: None) -> None:
    """Verify apply_traceback_preferences enables traceback flags."""
    cli_mod.apply_traceback_preferences(True)

    assert lib_cli_exit_tools.config.traceback is True
    assert lib_cli_exit_tools.config.traceback_force_color is True


@pytest.mark.os_agnostic
def test_when_we_restore_traceback_the_config_whispers_false(isolated_traceback_config: None) -> None:
    """Verify restore_traceback_state resets traceback flags to previous values."""
    previous = cli_mod.snapshot_traceback_state()
    cli_mod.apply_traceback_preferences(True)

    cli_mod.restore_traceback_state(previous)

    assert lib_cli_exit_tools.config.traceback is False
    assert lib_cli_exit_tools.config.traceback_force_color is False


@pytest.mark.os_agnostic
def test_when_info_runs_with_traceback_the_choice_is_shared(
    monkeypatch: pytest.MonkeyPatch,
    isolated_traceback_config: None,
    preserve_traceback_state: None,
) -> None:
    """Verify traceback flag is active during info command then restored."""
    notes: list[tuple[bool, bool]] = []

    def record() -> None:
        notes.append(
            (
                lib_cli_exit_tools.config.traceback,
                lib_cli_exit_tools.config.traceback_force_color,
            )
        )

    monkeypatch.setattr(cli_mod.__init__conf__, "print_info", record)

    exit_code = cli_mod.main(["--traceback", "info"])

    assert exit_code == 0
    assert notes == [(True, True)]
    assert lib_cli_exit_tools.config.traceback is False
    assert lib_cli_exit_tools.config.traceback_force_color is False


@pytest.mark.os_agnostic
def test_when_main_is_called_it_delegates_to_run_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify main() delegates to lib_cli_exit_tools.run_cli with correct args."""
    ledger: list[CapturedRun] = []
    monkeypatch.setattr(lib_cli_exit_tools, "run_cli", _capture_run_cli(ledger))

    result = cli_mod.main(["info"])

    assert result == 42
    assert ledger == [
        CapturedRun(
            command=cli_mod.cli,
            argv=["info"],
            prog_name=__init__conf__.shell_command,
            signal_specs=None,
            install_signals=True,
        )
    ]


@pytest.mark.os_agnostic
def test_when_cli_runs_without_arguments_help_is_printed(
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
) -> None:
    """Verify CLI with no arguments displays help text."""
    calls: list[str] = []

    def remember() -> None:
        calls.append("called")

    monkeypatch.setattr(cli_mod, "noop_main", remember)

    result = cli_runner.invoke(cli_mod.cli, [])

    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert calls == []


@pytest.mark.os_agnostic
def test_when_main_receives_no_arguments_cli_main_is_exercised(
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
    isolated_traceback_config: None,
) -> None:
    """Verify main with no args exercises CLI and shows help."""
    calls: list[str] = []
    outputs: list[str] = []

    def remember() -> None:
        calls.append("called")

    monkeypatch.setattr(cli_mod, "noop_main", remember)

    def fake_run_cli(
        command: Any,
        argv: Sequence[str] | None = None,
        *,
        prog_name: str | None = None,
        signal_specs: Any = None,
        install_signals: bool = True,
    ) -> int:
        args = [] if argv is None else list(argv)
        result: Result = cli_runner.invoke(command, args)
        if result.exception is not None:
            raise result.exception
        outputs.append(result.output)
        return result.exit_code

    monkeypatch.setattr(lib_cli_exit_tools, "run_cli", fake_run_cli)

    exit_code = cli_mod.main([])

    assert exit_code == 0
    assert calls == []
    assert outputs and "Usage:" in outputs[0]


@pytest.mark.os_agnostic
def test_when_traceback_is_requested_without_command_the_domain_runs(
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
) -> None:
    """Verify --traceback without command runs noop_main."""
    calls: list[str] = []

    def remember() -> None:
        calls.append("called")

    monkeypatch.setattr(cli_mod, "noop_main", remember)

    result = cli_runner.invoke(cli_mod.cli, ["--traceback"])

    assert result.exit_code == 0
    assert calls == ["called"]
    assert "Usage:" not in result.output


@pytest.mark.os_agnostic
def test_when_traceback_flag_is_passed_the_full_story_is_printed(
    isolated_traceback_config: None,
    capsys: pytest.CaptureFixture[str],
    strip_ansi: Callable[[str], str],
) -> None:
    """Verify --traceback displays full exception traceback on failure."""
    exit_code = cli_mod.main(["--traceback", "fail"])

    plain_err = strip_ansi(capsys.readouterr().err)

    assert exit_code != 0
    assert "Traceback (most recent call last)" in plain_err
    assert "RuntimeError: I should fail" in plain_err
    assert "[TRUNCATED" not in plain_err
    assert lib_cli_exit_tools.config.traceback is False
    assert lib_cli_exit_tools.config.traceback_force_color is False


@pytest.mark.os_agnostic
def test_when_hello_is_invoked_the_cli_smiles(cli_runner: CliRunner) -> None:
    """Verify hello command outputs Hello World greeting."""
    result: Result = cli_runner.invoke(cli_mod.cli, ["hello"])

    assert result.exit_code == 0
    assert "Hello World" in result.output


@pytest.mark.os_agnostic
@pytest.mark.parametrize("command", sorted(cli_mod.cli.commands))
def test_no_command_help_prints_a_literal_no_rewrap_marker(cli_runner: CliRunner, command: str) -> None:
    """A ``\\b`` inside a raw docstring reaches --help as two characters instead of click's marker."""
    result: Result = cli_runner.invoke(cli_mod.cli, [command, "--help"])

    assert result.exit_code == 0
    assert "\\b" not in result.output


@pytest.mark.os_agnostic
def test_when_fail_is_invoked_the_cli_raises(cli_runner: CliRunner) -> None:
    """Verify fail command raises RuntimeError."""
    result: Result = cli_runner.invoke(cli_mod.cli, ["fail"])

    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)


@pytest.mark.os_agnostic
def test_when_info_is_invoked_the_metadata_is_displayed(cli_runner: CliRunner) -> None:
    """Verify info command displays project metadata."""
    result: Result = cli_runner.invoke(cli_mod.cli, ["info"])

    assert result.exit_code == 0
    assert f"Info for {__init__conf__.name}:" in result.output
    assert __init__conf__.version in result.output


@pytest.mark.os_agnostic
def test_when_config_is_invoked_it_displays_configuration(cli_runner: CliRunner) -> None:
    """Verify config command displays configuration."""
    result: Result = cli_runner.invoke(cli_mod.cli, ["config"])

    assert result.exit_code == 0
    # With default config (all commented), output may be empty or show only log messages


@pytest.mark.os_agnostic
def test_when_config_is_invoked_with_json_format_it_outputs_json(cli_runner: CliRunner) -> None:
    """Verify config --format json outputs JSON."""
    result: Result = cli_runner.invoke(cli_mod.cli, ["config", "--format", "json"])

    assert result.exit_code == 0
    # JSON output should be valid (empty object if no config)
    assert "{" in result.output


@pytest.mark.os_agnostic
def test_when_config_is_invoked_with_nonexistent_section_it_fails(cli_runner: CliRunner) -> None:
    """Verify config with nonexistent section returns error."""
    result: Result = cli_runner.invoke(cli_mod.cli, ["config", "--section", "nonexistent_section_that_does_not_exist"])

    assert result.exit_code != 0
    assert "not found or empty" in result.output


@pytest.mark.os_agnostic
def test_when_config_is_invoked_with_mocked_data_it_displays_sections(
    cli_runner: CliRunner,
    mock_config_factory: Any,
    clear_config_cache: None,
) -> None:
    """Verify config displays sections from mocked configuration."""
    test_data = {
        "test_section": {
            "setting1": "value1",
            "setting2": 42,
        }
    }
    mock_config = mock_config_factory(test_data)

    def get_mock(**_kwargs: Any) -> Any:
        return mock_config

    result: Result = cli_runner.invoke(cli_mod.cli, ["config"], obj=_dependencies(load_config=get_mock))

    assert result.exit_code == 0
    assert "test_section" in result.output
    assert "setting1" in result.output
    assert "value1" in result.output


@pytest.mark.os_agnostic
def test_when_config_is_invoked_with_json_format_and_section_it_shows_section(
    cli_runner: CliRunner,
    mock_config_factory: Any,
    clear_config_cache: None,
) -> None:
    """Verify JSON format displays specific section content."""
    test_data = {
        "email": {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "test@example.com",
        }
    }
    mock_config = mock_config_factory(test_data)

    def get_mock(**_kwargs: Any) -> Any:
        return mock_config

    result: Result = cli_runner.invoke(cli_mod.cli, ["config", "--format", "json", "--section", "email"], obj=_dependencies(load_config=get_mock))

    assert result.exit_code == 0
    assert json.loads(result.output)["email"]["smtp_hosts"] == ["smtp.test.com:587"]


@pytest.mark.os_agnostic
def test_when_config_is_invoked_with_json_format_and_nonexistent_section_it_fails(
    cli_runner: CliRunner,
    mock_config_factory: Any,
    clear_config_cache: None,
) -> None:
    """Verify JSON format with nonexistent section returns error."""
    test_data = {
        "email": {
            "smtp_hosts": ["smtp.test.com:587"],
        }
    }
    mock_config = mock_config_factory(test_data)

    def get_mock(**_kwargs: Any) -> Any:
        return mock_config

    result: Result = cli_runner.invoke(cli_mod.cli, ["config", "--format", "json", "--section", "nonexistent"], obj=_dependencies(load_config=get_mock))

    assert result.exit_code != 0
    assert "not found or empty" in result.output


@pytest.mark.os_agnostic
def test_when_config_is_invoked_with_section_showing_complex_values(
    cli_runner: CliRunner,
    mock_config_factory: Any,
    clear_config_cache: None,
) -> None:
    """Verify human format with section containing lists and dicts."""
    test_data = {
        "email": {
            "smtp_hosts": ["smtp1.test.com:587", "smtp2.test.com:587"],
            "from_address": "test@example.com",
            "metadata": {"key1": "value1", "key2": "value2"},
            "timeout": 60.0,
        }
    }
    mock_config = mock_config_factory(test_data)

    def get_mock(**_kwargs: Any) -> Any:
        return mock_config

    result: Result = cli_runner.invoke(cli_mod.cli, ["config", "--section", "email"], obj=_dependencies(load_config=get_mock))

    assert result.exit_code == 0
    assert "[email]" in result.output
    smtp_hosts_line = next(line.strip() for line in result.output.splitlines() if line.strip().startswith("smtp_hosts"))
    assert smtp_hosts_line == 'smtp_hosts = ["smtp1.test.com:587", "smtp2.test.com:587"]'
    assert "metadata" in result.output
    assert '"test@example.com"' in result.output
    assert "60.0" in result.output


@pytest.mark.os_agnostic
def test_when_config_shows_all_sections_with_complex_values(
    cli_runner: CliRunner,
    mock_config_factory: Any,
    clear_config_cache: None,
) -> None:
    """Verify human format showing all sections with lists and dicts."""
    test_data = {
        "email": {
            "smtp_hosts": ["smtp.test.com:587"],
            "tags": {"environment": "test", "version": "1.0"},
        },
        "logging": {
            "level": "DEBUG",
            "handlers": ["console", "file"],
        },
    }
    mock_config = mock_config_factory(test_data)

    def get_mock(**_kwargs: Any) -> Any:
        return mock_config

    result: Result = cli_runner.invoke(cli_mod.cli, ["config"], obj=_dependencies(load_config=get_mock))

    assert result.exit_code == 0
    assert "[email]" in result.output
    assert "[logging]" in result.output
    assert "smtp_hosts" in result.output
    assert "handlers" in result.output
    assert "tags" in result.output


@pytest.mark.os_agnostic
def test_when_config_deploy_is_invoked_without_target_it_fails(cli_runner: CliRunner) -> None:
    """Verify config-deploy without --target option fails."""
    result: Result = cli_runner.invoke(cli_mod.cli, ["config-deploy"])

    assert result.exit_code != 0
    assert "Missing option" in result.output or "required" in result.output.lower()


@pytest.mark.os_agnostic
def test_when_config_deploy_is_invoked_it_deploys_configuration(
    cli_runner: CliRunner,
    tmp_path: Any,
) -> None:
    """Verify config-deploy creates configuration files."""
    from pathlib import Path

    deployed_path = tmp_path / "config.toml"
    deployed_path.touch()

    def mock_deploy(*, targets: Any, force: bool = False, profile: str | None = None) -> list[Path]:
        return [deployed_path]

    result: Result = cli_runner.invoke(cli_mod.cli, ["config-deploy", "--target", "user"], obj=_dependencies(deploy_configuration=mock_deploy))

    assert result.exit_code == 0
    assert "Configuration deployed successfully" in result.output
    assert str(deployed_path) in result.output


@pytest.mark.os_agnostic
def test_when_config_deploy_finds_no_files_to_create_it_informs_user(
    cli_runner: CliRunner,
) -> None:
    """Verify config-deploy reports when no files are created."""
    from pathlib import Path

    def mock_deploy(*, targets: Any, force: bool = False, profile: str | None = None) -> list[Path]:
        return []

    result: Result = cli_runner.invoke(cli_mod.cli, ["config-deploy", "--target", "user"], obj=_dependencies(deploy_configuration=mock_deploy))

    assert result.exit_code == 0
    assert "No files were created" in result.output
    assert "--force" in result.output


@pytest.mark.os_agnostic
def test_when_config_deploy_encounters_permission_error_it_handles_gracefully(
    cli_runner: CliRunner,
) -> None:
    """Verify config-deploy handles PermissionError gracefully."""

    def mock_deploy(*, targets: Any, force: bool = False, profile: str | None = None) -> list[Any]:
        raise PermissionError("Permission denied")

    result: Result = cli_runner.invoke(cli_mod.cli, ["config-deploy", "--target", "app"], obj=_dependencies(deploy_configuration=mock_deploy))

    assert result.exit_code != 0
    assert "Permission denied" in result.output
    assert "sudo" in result.output.lower()


@pytest.mark.os_agnostic
def test_when_config_deploy_supports_multiple_targets(
    cli_runner: CliRunner,
    tmp_path: Any,
) -> None:
    """Verify config-deploy accepts multiple --target options."""
    from pathlib import Path

    from finanzonline_uid.enums import DeployTarget

    path1 = tmp_path / "config1.toml"
    path2 = tmp_path / "config2.toml"
    path1.touch()
    path2.touch()

    def mock_deploy(*, targets: Any, force: bool = False, profile: str | None = None) -> list[Path]:
        target_values = [t.value if isinstance(t, DeployTarget) else t for t in targets]
        assert len(target_values) == 2
        assert "user" in target_values
        assert "host" in target_values
        return [path1, path2]

    result: Result = cli_runner.invoke(
        cli_mod.cli, ["config-deploy", "--target", "user", "--target", "host"], obj=_dependencies(deploy_configuration=mock_deploy)
    )

    assert result.exit_code == 0
    assert str(path1) in result.output
    assert str(path2) in result.output


@pytest.mark.os_agnostic
def test_when_config_deploy_is_invoked_with_profile_it_passes_profile(
    cli_runner: CliRunner,
    tmp_path: Any,
) -> None:
    """Verify config-deploy passes profile to deploy_configuration."""
    from pathlib import Path

    deployed_path = tmp_path / "config.toml"
    deployed_path.touch()
    captured_profile: list[str | None] = []

    def mock_deploy(*, targets: Any, force: bool = False, profile: str | None = None) -> list[Path]:
        captured_profile.append(profile)
        return [deployed_path]

    result: Result = cli_runner.invoke(
        cli_mod.cli, ["config-deploy", "--target", "user", "--profile", "production"], obj=_dependencies(deploy_configuration=mock_deploy)
    )

    assert result.exit_code == 0
    assert captured_profile == ["production"]
    assert "(profile: production)" in result.output


@pytest.mark.os_agnostic
def test_when_config_is_invoked_with_profile_it_passes_profile_to_get_config(
    cli_runner: CliRunner,
    mock_config_factory: Any,
    clear_config_cache: None,
) -> None:
    """Verify config command passes --profile to get_config."""
    captured_profiles: list[str | None] = []
    test_data = {"test_section": {"key": "value"}}
    mock_config = mock_config_factory(test_data)

    def get_mock(*, profile: str | None = None, **_kwargs: Any) -> Any:
        captured_profiles.append(profile)
        return mock_config

    result: Result = cli_runner.invoke(cli_mod.cli, ["config", "--profile", "staging"], obj=_dependencies(load_config=get_mock))

    assert result.exit_code == 0
    assert "staging" in captured_profiles


@pytest.mark.os_agnostic
def test_when_config_is_invoked_without_profile_it_passes_none(
    cli_runner: CliRunner,
    mock_config_factory: Any,
    clear_config_cache: None,
) -> None:
    """Verify config command passes None when no --profile specified."""
    captured_profiles: list[str | None] = []
    test_data = {"test_section": {"key": "value"}}
    mock_config = mock_config_factory(test_data)

    def get_mock(*, profile: str | None = None, **_kwargs: Any) -> Any:
        captured_profiles.append(profile)
        return mock_config

    result: Result = cli_runner.invoke(cli_mod.cli, ["config"], obj=_dependencies(load_config=get_mock))

    assert result.exit_code == 0
    assert None in captured_profiles


@pytest.mark.os_agnostic
def test_when_config_deploy_is_invoked_without_profile_it_passes_none(
    cli_runner: CliRunner,
    tmp_path: Any,
) -> None:
    """Verify config-deploy passes None when no --profile specified."""
    from pathlib import Path

    deployed_path = tmp_path / "config.toml"
    deployed_path.touch()
    captured_profiles: list[str | None] = []

    def mock_deploy(*, targets: Any, force: bool = False, profile: str | None = None) -> list[Path]:
        captured_profiles.append(profile)
        return [deployed_path]

    result: Result = cli_runner.invoke(cli_mod.cli, ["config-deploy", "--target", "user"], obj=_dependencies(deploy_configuration=mock_deploy))

    assert result.exit_code == 0
    assert captured_profiles == [None]
    assert "(profile:" not in result.output


@pytest.mark.os_agnostic
def test_when_config_command_profile_overrides_root_profile(
    cli_runner: CliRunner,
) -> None:
    """Verify command-level --profile overrides root --profile."""
    captured_profiles: list[str | None] = []

    _original_get_config = cli_mod.get_config

    def get_mock(*, profile: str | None = None, **_kwargs: Any) -> Any:
        captured_profiles.append(profile)
        return _original_get_config(profile=profile)

    # Root-level --profile is "root-profile", command-level is "command-profile"
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["--profile", "root-profile", "config", "--profile", "command-profile"],
        obj=_dependencies(load_config=get_mock),
    )

    assert result.exit_code == 0
    # Command-level profile should override root-level profile
    # The second call to get_config (from config command) should use "command-profile"
    assert "command-profile" in captured_profiles


@pytest.mark.os_agnostic
def test_a_click_obj_that_is_not_cli_dependencies_is_refused(cli_runner: CliRunner) -> None:
    """A foreign ``obj`` would otherwise be ignored and the real collaborators run in its place."""
    result: Result = cli_runner.invoke(cli_mod.cli, ["hello"], obj={"load_config": None})

    assert isinstance(result.exception, TypeError)
    assert "CliDependencies" in str(result.exception)


@pytest.mark.os_agnostic
def test_production_dependencies_are_the_real_collaborators() -> None:
    """Without an injected ``obj`` the CLI runs with these, so each must be the production object."""
    from finanzonline_uid import config as config_mod
    from finanzonline_uid.adapters.notification import EmailNotificationAdapter
    from finanzonline_uid.application.use_cases import CheckUidUseCase
    from finanzonline_uid.config_deploy import deploy_configuration
    from finanzonline_uid.domain.models import FinanzOnlineCredentials

    deps = cli_mod.production_dependencies()
    fo_config = config_mod.FinanzOnlineConfig(
        credentials=FinanzOnlineCredentials(tid="123456789", benid="TESTUSER", pin="testpin", herstellerid="ATU12345678"),
        uid_tn="ATU12345678",
    )

    assert deps.load_config is config_mod.get_config
    assert deps.load_finanzonline_config is config_mod.load_finanzonline_config
    assert deps.build_email_sender is EmailNotificationAdapter
    assert deps.deploy_configuration is deploy_configuration
    # Building the use case opens no connection: the SOAP clients connect on first use.
    assert isinstance(deps.build_uid_checker(fo_config, lambda _status: None), CheckUidUseCase)


@pytest.mark.os_agnostic
def test_when_an_unknown_command_is_used_a_helpful_error_appears(cli_runner: CliRunner) -> None:
    """Verify unknown command shows No such command error."""
    result: Result = cli_runner.invoke(cli_mod.cli, ["does-not-exist"])

    assert result.exit_code != 0
    assert "No such command" in result.output


@pytest.mark.os_agnostic
def test_when_restore_is_disabled_the_traceback_choice_remains(
    isolated_traceback_config: None,
    preserve_traceback_state: None,
) -> None:
    """Verify restore_traceback=False keeps traceback flags enabled."""
    cli_mod.apply_traceback_preferences(False)

    cli_mod.main(["--traceback", "hello"], restore_traceback=False)

    assert lib_cli_exit_tools.config.traceback is True
    assert lib_cli_exit_tools.config.traceback_force_color is True


# ======================== Check Command Tests ========================


@pytest.fixture
def mock_fo_config(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Mock FinanzOnline configuration."""
    from unittest.mock import MagicMock

    from finanzonline_uid.domain.models import FinanzOnlineCredentials

    mock_config = MagicMock()
    mock_config.uid_tn = "ATU12345678"
    mock_config.credentials = FinanzOnlineCredentials(
        tid="123456789",
        benid="TESTUSER",
        pin="testpin",
        herstellerid="ATU12345678",
    )
    mock_config.session_timeout = 30.0
    mock_config.query_timeout = 30.0
    mock_config.default_recipients = []
    mock_config.cache_results_hours = 0  # Disable cache in tests
    mock_config.cache_file = None
    mock_config.ratelimit_queries = 0  # Disable rate limiting in tests
    mock_config.ratelimit_hours = 24.0
    mock_config.ratelimit_file = None
    mock_config.output_dir = None  # Disable file output in tests
    mock_config.output_format = FileFormat.HTML  # Default file format
    return mock_config


@pytest.fixture
def mock_uid_result_valid() -> Any:
    """Mock valid UID check result."""
    from datetime import datetime, timezone

    from finanzonline_uid.domain.models import Address, UidCheckResult

    return UidCheckResult(
        uid="DE123456789",
        return_code=0,
        message="UID is valid",
        name="Test Company GmbH",
        address=Address(line1="Test Company GmbH", line2="Street 1", line3="12345 City"),
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def mock_uid_result_invalid() -> Any:
    """Mock invalid UID check result."""
    from datetime import datetime, timezone

    from finanzonline_uid.domain.models import UidCheckResult

    return UidCheckResult(
        uid="XX123456789",
        return_code=1,
        message="UID is invalid",
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.mark.os_agnostic
def test_when_check_succeeds_with_valid_uid_it_exits_zero(
    cli_runner: CliRunner,
    mock_fo_config: Any,
    mock_uid_result_valid: Any,
) -> None:
    """Verify check command exits 0 for valid UID."""
    from unittest.mock import MagicMock

    mock_config_obj = Config({}, {})

    mock_use_case = MagicMock()
    mock_use_case.execute.return_value = mock_uid_result_valid

    deps = _check_dependencies(mock_fo_config, mock_use_case, config=mock_config_obj)
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["check", "DE123456789", "--no-email"],
        obj=deps,
    )

    assert result.exit_code == 0
    assert "VALID" in result.output
    assert "DE123456789" in result.output


@pytest.mark.os_agnostic
def test_when_check_succeeds_with_invalid_uid_it_exits_one(
    cli_runner: CliRunner,
    mock_fo_config: Any,
    mock_uid_result_invalid: Any,
) -> None:
    """Verify check command exits 1 for invalid UID."""
    from unittest.mock import MagicMock

    mock_config_obj = Config({}, {})

    mock_use_case = MagicMock()
    mock_use_case.execute.return_value = mock_uid_result_invalid

    deps = _check_dependencies(mock_fo_config, mock_use_case, config=mock_config_obj)
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["check", "XX123456789", "--no-email"],
        obj=deps,
    )

    assert result.exit_code == 1
    assert "INVALID" in result.output


@pytest.mark.os_agnostic
def test_when_check_uses_json_format_it_outputs_json(
    cli_runner: CliRunner,
    mock_fo_config: Any,
    mock_uid_result_valid: Any,
) -> None:
    """Verify check command with --format json outputs JSON."""
    import json
    from unittest.mock import MagicMock

    mock_config_obj = Config({}, {})

    mock_use_case = MagicMock()
    mock_use_case.execute.return_value = mock_uid_result_valid

    deps = _check_dependencies(mock_fo_config, mock_use_case, config=mock_config_obj)
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["check", "DE123456789", "--format", "json", "--no-email"],
        obj=deps,
    )

    assert result.exit_code == 0
    json_start = result.output.find("{")
    assert json_start >= 0, f"No JSON object in output: {result.output!r}"
    parsed = json.loads(result.output[json_start:])
    assert parsed["uid"] == "DE123456789"
    assert parsed["is_valid"] is True


@pytest.mark.os_agnostic
def test_when_check_has_config_error_it_exits_two(
    cli_runner: CliRunner,
) -> None:
    """Verify check command exits 2 for ConfigurationError."""
    from finanzonline_uid.domain.errors import ConfigurationError

    mock_config_obj = Config({}, {})

    deps = _check_dependencies(ConfigurationError("Missing TID"), None, config=mock_config_obj)
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["check", "DE123456789", "--no-email"],
        obj=deps,
    )

    assert result.exit_code == 2
    assert "Missing TID" in result.output


@pytest.mark.os_agnostic
def test_when_check_has_auth_error_it_exits_three(
    cli_runner: CliRunner,
    mock_fo_config: Any,
) -> None:
    """Verify check command exits 3 for AuthenticationError."""
    from unittest.mock import MagicMock

    from finanzonline_uid.domain.errors import AuthenticationError

    mock_config_obj = Config({}, {})

    mock_use_case = MagicMock()
    mock_use_case.execute.side_effect = AuthenticationError("Not authorized", return_code=-4)

    deps = _check_dependencies(mock_fo_config, mock_use_case, config=mock_config_obj)
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["check", "DE123456789", "--no-email"],
        obj=deps,
    )

    assert result.exit_code == 3
    assert "Authentication Error" in result.output
    assert "Not authorized" in result.output


@pytest.mark.os_agnostic
def test_when_check_has_session_error_it_exits_four(
    cli_runner: CliRunner,
    mock_fo_config: Any,
) -> None:
    """Verify check command exits 4 for SessionError."""
    from unittest.mock import MagicMock

    from finanzonline_uid.domain.errors import SessionError

    mock_config_obj = Config({}, {})

    mock_use_case = MagicMock()
    mock_use_case.execute.side_effect = SessionError("Session expired", return_code=-1)

    deps = _check_dependencies(mock_fo_config, mock_use_case, config=mock_config_obj)
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["check", "DE123456789", "--no-email"],
        obj=deps,
    )

    assert result.exit_code == 4
    assert "Session Error" in result.output


@pytest.mark.os_agnostic
def test_when_check_has_query_error_it_exits_four(
    cli_runner: CliRunner,
    mock_fo_config: Any,
) -> None:
    """Verify check command exits 4 for QueryError."""
    from unittest.mock import MagicMock

    from finanzonline_uid.domain.errors import QueryError

    mock_config_obj = Config({}, {})

    mock_use_case = MagicMock()
    mock_use_case.execute.side_effect = QueryError("Rate limit exceeded", return_code=1513, retryable=True)

    deps = _check_dependencies(mock_fo_config, mock_use_case, config=mock_config_obj)
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["check", "DE123456789", "--no-email"],
        obj=deps,
    )

    assert result.exit_code == 4
    assert "Query Error" in result.output
    assert "temporary" in result.output.lower()


@pytest.mark.os_agnostic
def test_when_check_sends_email_on_success(
    cli_runner: CliRunner,
    mock_fo_config: Any,
    mock_uid_result_valid: Any,
) -> None:
    """Verify check command sends email notification on success."""
    from unittest.mock import MagicMock

    mock_config_obj = Config(
        {
            "email": {
                "smtp_hosts": ["smtp.test.com:587"],
                "from_address": "test@example.com",
            }
        },
        {},
    )

    mock_fo_config.default_recipients = ["admin@example.com"]

    mock_use_case = MagicMock()
    mock_use_case.execute.return_value = mock_uid_result_valid

    mock_adapter = MagicMock()
    mock_adapter.send_result.return_value = True

    deps = _check_dependencies(mock_fo_config, mock_use_case, config=mock_config_obj, email_sender=mock_adapter)
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["check", "DE123456789"],
        obj=deps,
    )

    assert result.exit_code == 0
    mock_adapter.send_result.assert_called_once()


@pytest.mark.os_agnostic
def test_when_check_sends_error_email_on_failure(
    cli_runner: CliRunner,
    mock_fo_config: Any,
) -> None:
    """Verify check command sends error email notification on failure."""
    from unittest.mock import MagicMock

    from finanzonline_uid.domain.errors import SessionError

    mock_config_obj = Config(
        {
            "email": {
                "smtp_hosts": ["smtp.test.com:587"],
                "from_address": "test@example.com",
            }
        },
        {},
    )

    mock_fo_config.default_recipients = ["admin@example.com"]

    mock_use_case = MagicMock()
    mock_use_case.execute.side_effect = SessionError("Connection failed", return_code=-3)

    mock_adapter = MagicMock()
    mock_adapter.send_error.return_value = True

    deps = _check_dependencies(mock_fo_config, mock_use_case, config=mock_config_obj, email_sender=mock_adapter)
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["check", "DE123456789"],
        obj=deps,
    )

    assert result.exit_code == 4
    mock_adapter.send_error.assert_called_once()


@pytest.mark.os_agnostic
def test_when_check_has_value_error_it_exits_two(
    cli_runner: CliRunner,
    mock_fo_config: Any,
) -> None:
    """Verify check command exits 2 for ValueError."""
    from unittest.mock import MagicMock

    mock_config_obj = Config({}, {})

    mock_use_case = MagicMock()
    mock_use_case.execute.side_effect = ValueError("Invalid UID format")

    deps = _check_dependencies(mock_fo_config, mock_use_case, config=mock_config_obj)
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["check", "INVALID", "--no-email"],
        obj=deps,
    )

    assert result.exit_code == 2
    assert "Invalid" in result.output


@pytest.mark.os_agnostic
def test_when_check_specifies_recipients_it_uses_them(
    cli_runner: CliRunner,
    mock_fo_config: Any,
    mock_uid_result_valid: Any,
) -> None:
    """Verify check command uses specified recipients."""
    from unittest.mock import MagicMock

    mock_config_obj = Config(
        {
            "email": {
                "smtp_hosts": ["smtp.test.com:587"],
                "from_address": "test@example.com",
            }
        },
        {},
    )

    mock_use_case = MagicMock()
    mock_use_case.execute.return_value = mock_uid_result_valid

    mock_adapter = MagicMock()
    mock_adapter.send_result.return_value = True

    deps = _check_dependencies(mock_fo_config, mock_use_case, config=mock_config_obj, email_sender=mock_adapter)
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["check", "DE123456789", "--recipient", "custom@example.com"],
        obj=deps,
    )

    assert result.exit_code == 0
    mock_adapter.send_result.assert_called_once()
    # Verify custom recipient was used (passed as positional or keyword arg)
    call_args = mock_adapter.send_result.call_args
    recipients: list[str] = call_args.kwargs.get("recipients") or (call_args.args[1] if len(call_args.args) > 1 else [])
    assert "custom@example.com" in recipients


@pytest.mark.os_agnostic
def test_when_check_without_uid_and_not_interactive_it_exits_two(
    cli_runner: CliRunner,
) -> None:
    """Verify check command exits 2 when UID is missing and not interactive."""
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["check"],
    )

    assert result.exit_code == 2
    assert "UID argument is required" in result.output
    assert "--interactive" in result.output


@pytest.mark.os_agnostic
def test_when_check_with_interactive_prompts_for_uid(
    cli_runner: CliRunner,
    mock_fo_config: Any,
    mock_uid_result_valid: Any,
) -> None:
    """Verify check command with --interactive prompts for UID."""
    from unittest.mock import MagicMock

    mock_config_obj = Config({}, {})

    mock_use_case = MagicMock()
    mock_use_case.execute.return_value = mock_uid_result_valid

    deps = _check_dependencies(mock_fo_config, mock_use_case, config=mock_config_obj)
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["check", "--interactive", "--no-email"],
        obj=deps,
        input="DE123456789\n",  # Simulated user input
    )

    assert result.exit_code == 0
    assert "VALID" in result.output
    assert "Enter EU VAT ID" in result.output


@pytest.mark.os_agnostic
def test_when_check_with_interactive_short_flag_prompts_for_uid(
    cli_runner: CliRunner,
    mock_fo_config: Any,
    mock_uid_result_valid: Any,
) -> None:
    """Verify check command with -i prompts for UID."""
    from unittest.mock import MagicMock

    mock_config_obj = Config({}, {})

    mock_use_case = MagicMock()
    mock_use_case.execute.return_value = mock_uid_result_valid

    deps = _check_dependencies(mock_fo_config, mock_use_case, config=mock_config_obj)
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["check", "-i", "--no-email"],
        obj=deps,
        input="DE123456789\n",  # Simulated user input
    )

    assert result.exit_code == 0
    assert "VALID" in result.output


# ======================== Retry Minutes Tests ========================


@pytest.mark.os_agnostic
def test_when_retryminutes_used_without_interactive_it_exits_two(
    cli_runner: CliRunner,
) -> None:
    """Verify --retryminutes without --interactive exits with error."""
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["check", "DE123456789", "--retryminutes", "1"],
    )

    assert result.exit_code == 2
    assert "--retryminutes requires --interactive" in result.output


@pytest.mark.os_agnostic
def test_when_retryminutes_with_interactive_is_accepted(
    cli_runner: CliRunner,
    mock_fo_config: Any,
    mock_uid_result_valid: Any,
) -> None:
    """Verify --retryminutes with --interactive succeeds on first attempt."""
    from unittest.mock import MagicMock

    mock_config_obj = Config({}, {})

    mock_use_case = MagicMock()
    mock_use_case.execute.return_value = mock_uid_result_valid

    deps = _check_dependencies(mock_fo_config, mock_use_case, config=mock_config_obj)
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["check", "--interactive", "--retryminutes", "1", "--no-email"],
        obj=deps,
        input="DE123456789\n",
    )

    assert result.exit_code == 0
    assert "VALID" in result.output


# ======================== UID Sanitization Tests ========================


@pytest.mark.os_agnostic
def test_when_uid_has_spaces_it_is_sanitized(
    cli_runner: CliRunner,
    mock_fo_config: Any,
    mock_uid_result_valid: Any,
) -> None:
    """Verify UID with spaces is sanitized before check."""
    from unittest.mock import MagicMock

    mock_config_obj = Config({}, {})
    captured_uid: list[str] = []

    mock_use_case = MagicMock()

    def capture_execute(*, credentials: Any, uid_tn: str, target_uid: str) -> Any:
        captured_uid.append(target_uid)
        return mock_uid_result_valid

    mock_use_case.execute.side_effect = capture_execute

    deps = _check_dependencies(mock_fo_config, mock_use_case, config=mock_config_obj)
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["check", "DE 123 456 789", "--no-email"],
        obj=deps,
    )

    assert result.exit_code == 0
    assert captured_uid == ["DE123456789"]


@pytest.mark.os_agnostic
def test_when_uid_is_lowercase_it_is_uppercased(
    cli_runner: CliRunner,
    mock_fo_config: Any,
    mock_uid_result_valid: Any,
) -> None:
    """Verify lowercase UID is uppercased before check."""
    from unittest.mock import MagicMock

    mock_config_obj = Config({}, {})
    captured_uid: list[str] = []

    mock_use_case = MagicMock()

    def capture_execute(*, credentials: Any, uid_tn: str, target_uid: str) -> Any:
        captured_uid.append(target_uid)
        return mock_uid_result_valid

    mock_use_case.execute.side_effect = capture_execute

    deps = _check_dependencies(mock_fo_config, mock_use_case, config=mock_config_obj)
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["check", "de123456789", "--no-email"],
        obj=deps,
    )

    assert result.exit_code == 0
    assert captured_uid == ["DE123456789"]


@pytest.mark.os_agnostic
def test_when_interactive_uid_has_artifacts_it_is_sanitized(
    cli_runner: CliRunner,
    mock_fo_config: Any,
    mock_uid_result_valid: Any,
) -> None:
    """Verify interactive UID input with copy-paste artifacts is sanitized."""
    from unittest.mock import MagicMock

    mock_config_obj = Config({}, {})
    captured_uid: list[str] = []

    mock_use_case = MagicMock()

    def capture_execute(*, credentials: Any, uid_tn: str, target_uid: str) -> Any:
        captured_uid.append(target_uid)
        return mock_uid_result_valid

    mock_use_case.execute.side_effect = capture_execute

    # Simulate input with tabs and extra spaces (common PDF copy-paste)
    deps = _check_dependencies(mock_fo_config, mock_use_case, config=mock_config_obj)
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["check", "--interactive", "--no-email"],
        obj=deps,
        input="  de 123\t456 789  \n",
    )

    assert result.exit_code == 0
    assert captured_uid == ["DE123456789"]


# --- Tests for _save_result_to_file ---


@pytest.mark.os_agnostic
def test_save_result_to_file_creates_txt_file(
    tmp_path: Any,
    mock_uid_result_valid: Any,
) -> None:
    """Verify _save_result_to_file creates a txt file with the result."""
    output_dir = tmp_path / "output"
    cli_mod._save_result_to_file(mock_uid_result_valid, output_dir, FileFormat.TXT)  # pyright: ignore[reportPrivateUsage]

    # Check file was created with correct extension
    expected_date = mock_uid_result_valid.timestamp.strftime("%Y-%m-%d")
    expected_file = output_dir / f"{mock_uid_result_valid.uid}_{expected_date}.txt"
    assert expected_file.exists()

    # Check content contains UID
    content = expected_file.read_text(encoding="utf-8")
    assert mock_uid_result_valid.uid in content


@pytest.mark.os_agnostic
def test_save_result_to_file_creates_json_file(
    tmp_path: Any,
    mock_uid_result_valid: Any,
) -> None:
    """Verify _save_result_to_file creates a json file with the result."""
    import json

    output_dir = tmp_path / "output"
    cli_mod._save_result_to_file(mock_uid_result_valid, output_dir, FileFormat.JSON)  # pyright: ignore[reportPrivateUsage]

    # Check file was created with correct extension
    expected_date = mock_uid_result_valid.timestamp.strftime("%Y-%m-%d")
    expected_file = output_dir / f"{mock_uid_result_valid.uid}_{expected_date}.json"
    assert expected_file.exists()

    # Check content is valid JSON containing UID
    content = expected_file.read_text(encoding="utf-8")
    data = json.loads(content)
    assert data["uid"] == mock_uid_result_valid.uid


@pytest.mark.os_agnostic
def test_save_result_to_file_creates_html_file(
    tmp_path: Any,
    mock_uid_result_valid: Any,
) -> None:
    """Verify _save_result_to_file creates an html file with the result."""
    output_dir = tmp_path / "output"
    cli_mod._save_result_to_file(mock_uid_result_valid, output_dir, FileFormat.HTML)  # pyright: ignore[reportPrivateUsage]

    # Check file was created with correct extension
    expected_date = mock_uid_result_valid.timestamp.strftime("%Y-%m-%d")
    expected_file = output_dir / f"{mock_uid_result_valid.uid}_{expected_date}.html"
    assert expected_file.exists()

    # Check content is HTML containing UID
    content = expected_file.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert mock_uid_result_valid.uid in content


@pytest.mark.os_agnostic
def test_save_result_to_file_creates_directory(
    tmp_path: Any,
    mock_uid_result_valid: Any,
) -> None:
    """Verify _save_result_to_file creates parent directories."""
    output_dir = tmp_path / "nested" / "output" / "dir"
    assert not output_dir.exists()

    cli_mod._save_result_to_file(mock_uid_result_valid, output_dir, FileFormat.HTML)  # pyright: ignore[reportPrivateUsage]

    assert output_dir.exists()


@pytest.mark.os_agnostic
def test_save_result_to_file_handles_permission_error(
    tmp_path: Any,
    mock_uid_result_valid: Any,
    capsys: Any,
) -> None:
    """Verify _save_result_to_file handles permission errors gracefully."""
    from pathlib import Path
    from unittest.mock import patch

    output_dir = tmp_path / "output"

    # Simulate permission error on mkdir
    with patch.object(Path, "mkdir", side_effect=PermissionError("Permission denied")):
        # Should not raise - just print warning
        cli_mod._save_result_to_file(mock_uid_result_valid, output_dir, FileFormat.HTML)  # pyright: ignore[reportPrivateUsage]

    captured = capsys.readouterr()
    assert "Warning" in captured.err or "Could not save" in captured.err


@pytest.mark.os_agnostic
def test_save_result_to_file_handles_write_error(
    tmp_path: Any,
    mock_uid_result_valid: Any,
    capsys: Any,
) -> None:
    """Verify _save_result_to_file handles write errors gracefully."""
    from pathlib import Path
    from unittest.mock import patch

    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Simulate write error
    with patch.object(Path, "write_text", side_effect=OSError("Disk full")):
        # Should not raise - just print warning
        cli_mod._save_result_to_file(mock_uid_result_valid, output_dir, FileFormat.HTML)  # pyright: ignore[reportPrivateUsage]

    captured = capsys.readouterr()
    assert "Warning" in captured.err or "Could not save" in captured.err


@pytest.mark.os_agnostic
def test_when_logging_shutdown_fails_main_still_returns_the_command_exit_code(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """A logging teardown failure must not replace the command's result.

    Measured: with an unreachable Graylog, lib_log_rich's shutdown() raised
    "Queue worker failed to stop within the allotted timeout" out of main(),
    so a finished check ended in a traceback and the wrong exit code.
    """
    import lib_log_rich.runtime

    ledger: list[CapturedRun] = []
    monkeypatch.setattr(lib_cli_exit_tools, "run_cli", _capture_run_cli(ledger))
    monkeypatch.setattr(lib_log_rich.runtime, "is_initialised", lambda: True)

    def _failing_shutdown() -> None:
        raise RuntimeError("Queue worker failed to stop within the allotted timeout")

    monkeypatch.setattr(lib_log_rich.runtime, "shutdown", _failing_shutdown)

    result = cli_mod.main(["info"])

    assert result == 42
    err = capsys.readouterr().err
    assert "Queue worker failed to stop within the allotted timeout" in err
    assert "Traceback" not in err


# ======================== Typed check outcome and error categories ========================


def _run_check(
    cli_runner: CliRunner,
    fo_config: Any,
    outcomes: list[object],
    args: list[str],
    *,
    stdin: str | None = None,
    config: Config | None = None,
    email_sender: Any = None,
) -> Result:
    """Run ``check`` with each FinanzOnline call returning (or raising) the next of ``outcomes``."""
    from unittest.mock import MagicMock

    use_case = MagicMock()
    use_case.execute.side_effect = outcomes
    deps = _check_dependencies(fo_config, use_case, config=config, email_sender=email_sender)
    return cli_runner.invoke(cli_mod.cli, ["check", *args], input=stdin, obj=deps)


def _error_cases() -> list[tuple[Exception, str, int]]:
    """Each exception the check can end with, its printed label and its exit code."""
    from finanzonline_uid.domain.errors import (
        AuthenticationError,
        ConfigurationError,
        QueryError,
        ServiceMaintenanceError,
        SessionError,
        UidCheckError,
    )

    return [
        (ConfigurationError("bad config"), "Configuration Error", 2),
        (AuthenticationError("bad login", return_code=-4), "Authentication Error", 3),
        (ServiceMaintenanceError("down for maintenance"), "Service Maintenance", 4),
        (SessionError("session gone", return_code=-1), "Session Error", 4),
        (QueryError("query failed", return_code=4), "Query Error", 4),
        (UidCheckError("other check failure"), "UID Check Error", 4),
        (ValueError("not a uid"), "Validation Error", 2),
    ]


@pytest.mark.os_agnostic
@pytest.mark.parametrize(
    ("error", "label", "exit_code"), _error_cases(), ids=lambda value: type(value).__name__ if isinstance(value, Exception) else str(value)
)
def test_check_error_prints_and_logs_the_category_label_not_the_enum_member(
    cli_runner: CliRunner,
    mock_fo_config: Any,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    label: str,
    exit_code: int,
) -> None:
    """The error line and the error log record carry the label, never ``ErrorKind.X``."""
    caplog.set_level("ERROR", logger="finanzonline_uid.cli")

    result = _run_check(cli_runner, mock_fo_config, [error], ["DE123456789", "--no-email"])

    assert result.exit_code == exit_code
    assert f"\n{label}: {error}" in result.stderr
    assert "ErrorKind" not in result.output
    assert label in [record.getMessage() for record in caplog.records]


@pytest.mark.os_agnostic
def test_check_error_line_shows_the_return_code_and_retry_hint(
    cli_runner: CliRunner,
    mock_fo_config: Any,
) -> None:
    """A retryable error with a return code reports both, read straight off the exception."""
    from finanzonline_uid.domain.errors import QueryError

    error = QueryError("Rate limit exceeded", return_code=1513, retryable=True)

    result = _run_check(cli_runner, mock_fo_config, [error], ["DE123456789", "--no-email"])

    assert result.exit_code == 4
    assert "Return code: 1513" in result.stderr
    assert "This error may be temporary. Try again later." in result.stderr


@pytest.mark.os_agnostic
def test_retry_mode_cancelled_before_any_attempt_finished_reports_cancelled(
    cli_runner: CliRunner,
    mock_fo_config: Any,
) -> None:
    """Ctrl+C during the first attempt ends with the Cancelled error."""
    result = _run_check(
        cli_runner,
        mock_fo_config,
        [KeyboardInterrupt()],
        ["--interactive", "--retryminutes", "0", "--no-email"],
        stdin="DE123456789\n",
    )

    assert result.exit_code == 4
    assert "\nCancelled: Check cancelled by user" in result.stderr


@pytest.mark.os_agnostic
def test_retry_mode_cancelled_after_a_retryable_error_reports_that_error(
    cli_runner: CliRunner,
    mock_fo_config: Any,
) -> None:
    """Ctrl+C after a retryable error ends with that error, not with Cancelled."""
    from finanzonline_uid.domain.errors import QueryError

    retryable = QueryError("Rate limit exceeded", return_code=1513, retryable=True)
    result = _run_check(
        cli_runner,
        mock_fo_config,
        [retryable, KeyboardInterrupt()],
        ["--interactive", "--retryminutes", "0", "--no-email"],
        stdin="DE123456789\n",
    )

    assert result.exit_code == 4
    assert "\nQuery Error: Rate limit exceeded" in result.stderr
    assert "Cancelled:" not in result.stderr


@pytest.mark.os_agnostic
def test_retry_mode_cancelled_after_a_retryable_result_reports_that_result(
    cli_runner: CliRunner,
    mock_fo_config: Any,
) -> None:
    """Ctrl+C after a result with a retryable return code ends with that result."""
    from datetime import datetime, timezone

    from finanzonline_uid.domain.models import UidCheckResult

    retryable_result = UidCheckResult(
        uid="DE123456789",
        return_code=1513,
        message="Rate limit",
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    result = _run_check(
        cli_runner,
        mock_fo_config,
        [retryable_result, KeyboardInterrupt()],
        ["--interactive", "--retryminutes", "0", "--no-email"],
        stdin="DE123456789\n",
    )

    assert result.exit_code == 1
    assert "Cancelled:" not in result.stderr
    assert "DE123456789" in result.stdout


@pytest.mark.os_agnostic
@pytest.mark.parametrize(("cli_value", "extension"), [("JSON", "json"), ("Txt", "txt"), ("html", "html"), (None, "html")])
def test_outputformat_is_case_insensitive_and_names_the_file_by_its_value(
    cli_runner: CliRunner,
    mock_fo_config: Any,
    mock_uid_result_valid: Any,
    tmp_path: Any,
    cli_value: str | None,
    extension: str,
) -> None:
    """Any case of --outputformat is accepted; without it the configured format applies."""
    args = ["DE123456789", "--no-email", "--outputdir", str(tmp_path)]
    if cli_value is not None:
        args += ["--outputformat", cli_value]

    result = _run_check(cli_runner, mock_fo_config, [mock_uid_result_valid], args)

    assert result.exit_code == 0
    assert [path.name for path in tmp_path.iterdir()] == [f"DE123456789_2025-01-01.{extension}"]


@pytest.mark.os_agnostic
def test_format_option_is_case_insensitive(
    cli_runner: CliRunner,
    mock_fo_config: Any,
    mock_uid_result_valid: Any,
) -> None:
    """``--format JSON`` selects JSON output as ``--format json`` does."""
    result = _run_check(cli_runner, mock_fo_config, [mock_uid_result_valid], ["DE123456789", "--no-email", "--format", "JSON"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["uid"] == "DE123456789"


@pytest.mark.os_agnostic
@pytest.mark.parametrize(
    ("outcome_is_error", "expected"),
    [(False, "Email notification skipped: no SMTP hosts configured"), (True, "Error notification skipped: no SMTP hosts configured")],
)
def test_skipped_notification_is_logged_with_the_kind_label(
    cli_runner: CliRunner,
    mock_fo_config: Any,
    mock_uid_result_valid: Any,
    caplog: pytest.LogCaptureFixture,
    outcome_is_error: bool,
    expected: str,
) -> None:
    """The notification kind reaches the log as its label, never ``NotificationKind.X``."""
    from finanzonline_uid.domain.errors import SessionError

    caplog.set_level("WARNING", logger="finanzonline_uid.cli")
    outcome: object = SessionError("session gone") if outcome_is_error else mock_uid_result_valid

    _run_check(cli_runner, mock_fo_config, [outcome], ["DE123456789"])

    assert expected in [record.getMessage() for record in caplog.records]


@pytest.mark.os_agnostic
def test_error_email_receives_the_check_error_info(
    cli_runner: CliRunner,
    mock_fo_config: Any,
) -> None:
    """The error email is sent with the typed error record and the resolved recipients."""
    from unittest.mock import MagicMock

    from finanzonline_uid.domain.errors import CheckErrorInfo, ErrorKind, SessionError

    adapter = MagicMock()
    adapter.send_error.return_value = True
    config = Config({"email": {"smtp_hosts": ["smtp.test.com:587"], "from_address": "test@example.com", "default_recipients": ["ops@example.com"]}}, {})

    _run_check(cli_runner, mock_fo_config, [SessionError("session gone", return_code=-1)], ["DE123456789"], config=config, email_sender=adapter)

    info, uid, recipients = adapter.send_error.call_args.args
    assert isinstance(info, CheckErrorInfo)
    assert (info.error_type, info.message, info.return_code) == (ErrorKind.SESSION, "session gone", -1)
    assert (uid, recipients) == ("DE123456789", ["ops@example.com"])


@pytest.mark.os_agnostic
def test_traceback_state_round_trips_by_field() -> None:
    """The snapshot names its fields, and restoring it reapplies both flags."""
    previous = cli_mod.snapshot_traceback_state()
    try:
        cli_mod.restore_traceback_state(cli_mod.TracebackState(enabled=True, force_color=False))
        assert cli_mod.snapshot_traceback_state() == cli_mod.TracebackState(enabled=True, force_color=False)
    finally:
        cli_mod.restore_traceback_state(previous)
