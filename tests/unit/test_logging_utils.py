import logging
from typing import List

import pytest

from langgraph_system_generator.utils.logging_utils import configure_logging


@pytest.fixture
def reset_root_logger():
    root = logging.getLogger()
    original_handlers: List[logging.Handler] = list(root.handlers)
    original_level = root.level
    for handler in list(root.handlers):
        root.removeHandler(handler)
    try:
        yield root
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in original_handlers:
            root.addHandler(handler)
        root.setLevel(original_level)


def test_configure_logging_adds_handler(reset_root_logger, caplog):
    configure_logging("DEBUG")

    root = logging.getLogger()
    non_capture_handlers = [
        handler
        for handler in root.handlers
        if handler.__class__.__name__ != "LogCaptureHandler"
    ]
    assert len(non_capture_handlers) == 1
    assert root.level == logging.DEBUG
    handler = non_capture_handlers[0]
    assert handler.level == logging.DEBUG

    caplog.set_level(logging.DEBUG)
    logger = logging.getLogger("test.logger")
    logger.info("hello world")
    assert any(record.message == "hello world" for record in caplog.records)


def test_configure_logging_reuses_existing_handler(reset_root_logger):
    root = logging.getLogger()
    existing_handler = logging.StreamHandler()
    root.addHandler(existing_handler)

    configure_logging("WARNING")

    non_capture_handlers = [
        handler
        for handler in root.handlers
        if handler.__class__.__name__ != "LogCaptureHandler"
    ]
    assert len(non_capture_handlers) == 1
    handler = non_capture_handlers[0]
    assert handler is existing_handler
    assert handler.level == logging.WARNING
    assert root.level == logging.WARNING
