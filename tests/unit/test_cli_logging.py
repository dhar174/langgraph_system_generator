"""Unit tests for CLI logging controls."""

from __future__ import annotations

import logging

import langgraph_system_generator.cli as cli_module


def test_build_parser_accepts_log_level_flag():
    parser = cli_module.build_parser()
    args = parser.parse_args(["--log-level", "DEBUG", "generate", "test prompt"])

    assert args.log_level == "DEBUG"


def test_main_configures_logging_before_dispatch(monkeypatch):
    observed: dict[str, object] = {}

    def fake_configure_logging(level):
        observed["level"] = level
        logging.getLogger().setLevel(getattr(logging, level or "INFO"))
        return level or "INFO"

    def fake_run_generate(_args):
        observed["command_ran"] = True
        return 0

    monkeypatch.setattr(cli_module, "configure_logging", fake_configure_logging)
    monkeypatch.setattr(cli_module, "_run_generate", fake_run_generate)

    exit_code = cli_module.main(["--log-level", "WARNING", "generate", "hello"])

    assert exit_code == 0
    assert observed["level"] == "WARNING"
    assert observed["command_ran"] is True
    assert logging.getLogger().level == logging.WARNING
