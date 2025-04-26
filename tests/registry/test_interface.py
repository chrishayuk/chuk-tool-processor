# tests/tool_processor/registry/test_interface.py
import inspect
import pytest

from chuk_tool_processor.registry.interface import ToolRegistryInterface


@pytest.mark.parametrize(
    "method_name, expected_args, expected_defaults",
    [
        (
            "register_tool",
            ["tool", "name", "namespace", "metadata"],
            {"name": None, "namespace": "default", "metadata": None},
        ),
        ("get_tool", ["name", "namespace"], {"namespace": "default"}),
        ("get_metadata", ["name", "namespace"], {"namespace": "default"}),
        ("list_tools", ["namespace"], {"namespace": None}),
        ("list_namespaces", [], {}),
    ],
)
def test_method_signature(method_name, expected_args, expected_defaults):
    # Method must exist
    method = getattr(ToolRegistryInterface, method_name, None)
    assert method is not None, f"{method_name} is not defined"

    sig = inspect.signature(method)
    # Skip the implicit 'self'
    params = list(sig.parameters.items())[1:]
    # Check parameter names
    names = [n for n, _ in params]
    assert names == expected_args, (
        f"{method_name} parameters {names} != expected {expected_args}"
    )
    # Each parameter needs a type annotation
    for name, param in params:
        assert param.annotation is not inspect._empty, (
            f"{method_name}.{name} needs a type annotation"
        )
    # Check default values for optional parameters
    for arg, default in expected_defaults.items():
        assert sig.parameters[arg].default == default, (
            f"{method_name}.{arg} default {sig.parameters[arg].default} != {default}"
        )


def test_docstrings_describe_return():
    # Only check the methods that actually return something
    for name in ("get_tool", "get_metadata", "list_tools", "list_namespaces"):
        method = getattr(ToolRegistryInterface, name)
        doc = inspect.getdoc(method) or ""
        assert (
            "Returns" in doc or "return" in doc.lower()
        ), f"{name} should document its return value"
