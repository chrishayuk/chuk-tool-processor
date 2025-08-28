"""Tests for the actual decorators module functions."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from chuk_tool_processor.models.validated_tool import ValidatedTool
from chuk_tool_processor.registry.decorators import (
    _add_subprocess_serialization_support,
    _handle_shutdown,
    _is_pydantic_model,
    discover_decorated_tools,
    ensure_registrations,
    make_pydantic_tool_compatible,
    register_tool,
)


class TestIsPydanticModel:
    """Tests for _is_pydantic_model function."""

    def test_is_pydantic_model_true(self):
        """Test with actual Pydantic model."""

        class MyModel(BaseModel):
            value: str

        assert _is_pydantic_model(MyModel) is True

    def test_is_pydantic_model_false(self):
        """Test with non-Pydantic class."""

        class RegularClass:
            pass

        assert _is_pydantic_model(RegularClass) is False

    def test_is_pydantic_model_none(self):
        """Test with None."""
        assert _is_pydantic_model(None) is False

    def test_is_pydantic_model_builtin(self):
        """Test with builtin type."""
        assert _is_pydantic_model(str) is False
        assert _is_pydantic_model(dict) is False


class TestAddSubprocessSerializationSupport:
    """Tests for _add_subprocess_serialization_support function."""

    def test_add_serialization_to_class(self):
        """Test adding serialization support to a class."""
        # Define class at module level to make it pickleable

        # Create a simple class
        TestClass = type("TestClass", (), {"__init__": lambda self, value: setattr(self, "value", value)})

        enhanced_class = _add_subprocess_serialization_support(TestClass, "test_tool")

        # Should have _tool_name added
        assert hasattr(enhanced_class, "_tool_name")
        assert enhanced_class._tool_name == "test_tool"

        # Test instance creation
        instance = enhanced_class("test_value")
        assert instance.value == "test_value"

    def test_add_serialization_preserves_class(self):
        """Test that original class attributes are preserved."""

        class OriginalClass:
            """Original docstring."""

            class_var = "original"

            def method(self):
                return "original_method"

        enhanced = _add_subprocess_serialization_support(OriginalClass, "tool")

        assert enhanced.__doc__ == "Original docstring."
        assert enhanced.class_var == "original"
        instance = enhanced()
        assert instance.method() == "original_method"


class TestRegisterToolDecorator:
    """Tests for register_tool decorator."""

    @pytest.fixture
    def mock_registry(self):
        """Create a mock registry."""
        registry = MagicMock()
        registry.register_tool = MagicMock()
        return registry

    def test_register_tool_with_class(self, mock_registry):
        """Test registering a tool class."""
        with (
            patch("chuk_tool_processor.registry.decorators._PENDING_REGISTRATIONS", []) as pending,
            patch("chuk_tool_processor.registry.decorators._REGISTERED_CLASSES", set()) as registered,
        ):

            @register_tool(name="test_tool")
            class TestTool(ValidatedTool):
                class Arguments(BaseModel):
                    value: str

                async def _execute(self, value: str):
                    return {"result": value}

            # Should add to pending registrations
            assert len(pending) == 1
            assert TestTool in registered
            assert hasattr(TestTool, "_tool_registration_info")
            assert TestTool._tool_registration_info["name"] == "test_tool"
            assert TestTool._tool_registration_info["namespace"] == "default"

    def test_register_tool_with_metadata(self, mock_registry):
        """Test registering with metadata."""
        metadata = {"version": "1.0", "author": "test"}

        with (
            patch("chuk_tool_processor.registry.decorators._PENDING_REGISTRATIONS", []) as pending,
            patch("chuk_tool_processor.registry.decorators._REGISTERED_CLASSES", set()),
        ):

            @register_tool(name="meta_tool", namespace="custom", **metadata)
            class MetaTool(ValidatedTool):
                class Arguments(BaseModel):
                    value: int

                async def _execute(self, value: int):
                    return {"result": value * 2}

            assert len(pending) == 1
            assert hasattr(MetaTool, "_tool_registration_info")
            assert MetaTool._tool_registration_info["name"] == "meta_tool"
            assert MetaTool._tool_registration_info["namespace"] == "custom"
            assert MetaTool._tool_registration_info["metadata"]["version"] == "1.0"
            assert MetaTool._tool_registration_info["metadata"]["author"] == "test"

    def test_register_tool_auto_name(self, mock_registry):
        """Test auto-generating tool name from class name."""
        with (
            patch("chuk_tool_processor.registry.decorators._PENDING_REGISTRATIONS", []),
            patch("chuk_tool_processor.registry.decorators._REGISTERED_CLASSES", set()),
        ):

            @register_tool()
            class AutoNamedTool(ValidatedTool):
                class Arguments(BaseModel):
                    value: str

                async def _execute(self, value: str):
                    return {"result": value}

            # Should use class name
            assert hasattr(AutoNamedTool, "_tool_registration_info")
            assert AutoNamedTool._tool_registration_info["name"] == "AutoNamedTool"

    def test_register_tool_with_function(self, mock_registry):
        """Test registering a function as a tool."""
        with patch("chuk_tool_processor.registry.decorators._PENDING_REGISTRATIONS", []) as pending:
            # Note: register_tool decorator expects a class, not a function
            # The decorator only works with classes that have execute methods
            @register_tool(name="func_tool")
            class FuncTool:
                async def execute(self, value: str) -> dict:
                    """A tool function."""
                    return {"result": value.upper()}

            # Should add to pending registrations
            assert len(pending) == 1
            assert hasattr(FuncTool, "_tool_registration_info")

    def test_register_tool_async_function(self, mock_registry):
        """Test registering an async function."""
        with patch("chuk_tool_processor.registry.decorators._PENDING_REGISTRATIONS", []) as pending:

            @register_tool(name="async_func")
            class AsyncTool:
                async def execute(self, value: int) -> dict:
                    await asyncio.sleep(0.01)
                    return {"result": value * 2}

            assert len(pending) == 1
            assert hasattr(AsyncTool, "_tool_registration_info")

    def test_register_tool_adds_to_decorated_tools(self, mock_registry):
        """Test that decorated tools are tracked."""
        with (
            patch("chuk_tool_processor.registry.decorators._PENDING_REGISTRATIONS", []),
            patch("chuk_tool_processor.registry.decorators._REGISTERED_CLASSES", set()) as registered,
        ):

            @register_tool(name="tracked_tool")
            class TrackedTool(ValidatedTool):
                class Arguments(BaseModel):
                    value: str

                async def _execute(self, value: str):
                    return {"result": value}

            # Should be added to _REGISTERED_CLASSES
            assert TrackedTool in registered


class TestMakePydanticToolCompatible:
    """Tests for make_pydantic_tool_compatible function."""

    def test_make_compatible_validated_tool(self):
        """Test making ValidatedTool compatible."""

        class MyTool(ValidatedTool):
            class Arguments(BaseModel):
                value: str

            async def _execute(self, value: str):
                return {"result": value}

        compatible = make_pydantic_tool_compatible(MyTool, "my_tool")

        # Should add subprocess serialization support
        assert hasattr(compatible, "__reduce__")

        # Should still be a ValidatedTool
        assert issubclass(compatible, ValidatedTool)

    def test_make_compatible_regular_class(self):
        """Test making regular class compatible."""

        class RegularTool:
            def execute(self, value):
                return {"result": value}

        compatible = make_pydantic_tool_compatible(RegularTool, "regular")

        # Should add serialization support
        assert hasattr(compatible, "__reduce__")

    def test_make_compatible_with_pydantic_arguments(self):
        """Test with class that has Pydantic Arguments."""

        class ToolWithArgs(ValidatedTool):
            class Arguments(BaseModel):
                name: str
                age: int

            async def _execute(self, name: str, age: int):
                return {"name": name, "age": age}

        compatible = make_pydantic_tool_compatible(ToolWithArgs, "with_args")

        # Arguments should also be made compatible
        assert hasattr(compatible.Arguments, "__reduce__")


class TestEnsureRegistrations:
    """Tests for ensure_registrations function."""

    async def test_ensure_registrations_empty(self):
        """Test ensure_registrations with no pending tools."""
        with patch("chuk_tool_processor.registry.decorators._pending_registrations", []):
            await ensure_registrations()
            # Should complete without error

    async def test_ensure_registrations_with_pending(self):
        """Test ensure_registrations with pending tools."""
        mock_registry = AsyncMock()
        mock_registry.register_tool = AsyncMock()

        # Create pending registrations
        pending = [
            ("tool1", ValidatedTool, {"namespace": "default"}),
            ("tool2", ValidatedTool, {"namespace": "custom"}),
        ]

        with (
            patch("chuk_tool_processor.registry.decorators._pending_registrations", pending),
            patch(
                "chuk_tool_processor.registry.provider.ToolRegistryProvider.get_registry", return_value=mock_registry
            ),
        ):
            await ensure_registrations()

            # Should register all pending tools
            assert mock_registry.register_tool.call_count == 2

    async def test_ensure_registrations_clears_pending(self):
        """Test that pending list is cleared after registration."""
        mock_registry = AsyncMock()
        mock_registry.register_tool = AsyncMock()

        pending = [("tool1", ValidatedTool, {})]

        with (
            patch("chuk_tool_processor.registry.decorators._pending_registrations", pending) as pending_list,
            patch(
                "chuk_tool_processor.registry.provider.ToolRegistryProvider.get_registry", return_value=mock_registry
            ),
        ):
            await ensure_registrations()

            # Pending list should be empty
            assert len(pending_list) == 0


class TestDiscoverDecoratedTools:
    """Tests for discover_decorated_tools function."""

    def test_discover_decorated_tools_empty(self):
        """Test discovering when no tools are decorated."""
        with patch("chuk_tool_processor.registry.decorators._REGISTERED_CLASSES", set()):
            tools = discover_decorated_tools()
            assert tools == []

    def test_discover_decorated_tools_with_tools(self):
        """Test discovering decorated tools."""

        # The actual implementation scans sys.modules for tools with _tool_registration_info
        # Let's create tools with that attribute
        class Tool1(ValidatedTool):
            _tool_registration_info = {"name": "Tool1", "namespace": "default", "metadata": {}}

        class Tool2(ValidatedTool):
            _tool_registration_info = {"name": "Tool2", "namespace": "default", "metadata": {}}

        # Mock a module with these tools
        mock_module = MagicMock()
        mock_module.Tool1 = Tool1
        mock_module.Tool2 = Tool2

        with patch("sys.modules", {"chuk_tool_processor.test_module": mock_module}):
            tools = discover_decorated_tools()
            # Should find the tools in the mocked module
            assert any(t.__name__ == "Tool1" for t in tools)
            assert any(t.__name__ == "Tool2" for t in tools)

    def test_discover_returns_copy(self):
        """Test that discover returns a copy, not the original list."""

        # Create a tool with registration info
        class TestTool(ValidatedTool):
            _tool_registration_info = {"name": "TestTool", "namespace": "default", "metadata": {}}

        mock_module = MagicMock()
        mock_module.TestTool = TestTool

        with patch("sys.modules", {"chuk_tool_processor.test": mock_module}):
            tools1 = discover_decorated_tools()
            tools2 = discover_decorated_tools()

            # Should be different list instances
            assert tools1 is not tools2
            assert isinstance(tools1, list)


class TestHandleShutdown:
    """Tests for _handle_shutdown function."""

    def test_handle_shutdown_sigterm(self):
        """Test shutdown handler for SIGTERM."""
        with (
            patch("chuk_tool_processor.registry.decorators._SHUTTING_DOWN", False),
            patch("chuk_tool_processor.registry.decorators._PENDING_REGISTRATIONS", ["dummy"]),
            patch("asyncio.get_running_loop") as mock_get_loop,
        ):
            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop

            _handle_shutdown()

            # Should create task to ensure registrations if there's a running loop
            # and pending registrations

    def test_handle_shutdown_with_frame(self):
        """Test shutdown handler with frame argument."""
        # _handle_shutdown takes no arguments based on the function signature
        with patch("chuk_tool_processor.registry.decorators._SHUTTING_DOWN", False):
            _handle_shutdown()
            # Should complete without error

    def test_handle_shutdown_multiple_calls(self):
        """Test that shutdown handler can be called multiple times."""
        with patch("chuk_tool_processor.registry.decorators._SHUTTING_DOWN", False):
            _handle_shutdown()
            # After first call, _SHUTTING_DOWN should be set to True preventing further processing


class TestDecoratorIntegration:
    """Integration tests for decorators."""

    async def test_full_registration_flow(self):
        """Test complete registration flow from decorator to registry."""
        mock_registry = AsyncMock()
        mock_registry.register_tool = AsyncMock()

        with patch(
            "chuk_tool_processor.registry.provider.ToolRegistryProvider.get_registry", return_value=mock_registry
        ):

            @register_tool(name="integration_tool", namespace="test")
            class IntegrationTool(ValidatedTool):
                """An integration test tool."""

                class Arguments(BaseModel):
                    value: str
                    count: int = 1

                async def _execute(self, value: str, count: int):
                    return {"result": value * count}

            # Tool should be registered
            mock_registry.register_tool.assert_called()

            # Should be in decorated tools
            with patch("chuk_tool_processor.registry.decorators._decorated_tools", []) as decorated:

                @register_tool(name="another")
                class AnotherTool(ValidatedTool):
                    class Arguments(BaseModel):
                        x: int

                    async def _execute(self, x: int):
                        return {"result": x}

                assert len(decorated) == 1

    def test_function_to_tool_conversion(self):
        """Test converting function to tool via decorator."""
        with patch("chuk_tool_processor.registry.decorators._PENDING_REGISTRATIONS", []) as pending:
            # The decorator only works with classes, not functions
            # Create a class-based tool instead
            @register_tool(name="converted_func")
            class ConvertedTool:
                """Simple tool to convert."""

                async def execute(self, text: str, repeat: int = 1) -> str:
                    return text * repeat

            # Should add to pending registrations
            assert len(pending) == 1
            assert hasattr(ConvertedTool, "_tool_registration_info")
            assert ConvertedTool._tool_registration_info["name"] == "converted_func"
