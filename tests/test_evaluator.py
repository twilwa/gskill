"""Tests for evaluator command selection."""

from __future__ import annotations

from src.evaluator import _build_test_command


def test_build_test_command_for_pytest_tasks():
    command, mode = _build_test_command(
        {
            "repo": "swesmith/pallets__jinja.ada0a9a6",
            "FAIL_TO_PASS": ["tests/test_nativetypes.py::test_constant_dunder"],
        }
    )

    assert mode == "pytest"
    assert "python -m pytest" in command
    assert "tests/test_nativetypes.py::test_constant_dunder" in command


def test_build_test_command_for_go_tasks():
    command, mode = _build_test_command(
        {
            "repo": "swesmith/blevesearch__bleve.f2876b5e",
            "FAIL_TO_PASS": ["TestGeoDistanceIssue1301", "ExampleNew"],
        }
    )

    assert mode == "go_test"
    assert "go test ./..." in command
    assert "TestGeoDistanceIssue1301|ExampleNew" in command
