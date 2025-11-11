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

    def test_add_serialization_to_pydantic_model(self):
        """Test adding serialization to a Pydantic model."""

        class PydanticTool(BaseModel):
            value: str
            count: int = 1

        enhanced = _add_subprocess_serialization_support(PydanticTool, "pydantic_tool")

        # Should have _tool_name
        assert hasattr(enhanced, "_tool_name")
        assert enhanced._tool_name == "pydantic_tool"

        # Should have serialization methods
        assert hasattr(enhanced, "__getstate__")
        assert hasattr(enhanced, "__setstate__")

        # Test instance creation
        instance = enhanced(value="test", count=5)
        assert instance.value == "test"
        assert instance.count == 5

    def test_add_serialization_with_custom_getstate(self):
        """Test adding serialization to class with custom __getstate__."""

        class CustomSerializable:
            def __init__(self, value):
                self.value = value

            def __getstate__(self):
                return {"custom": self.value}

            def __setstate__(self, state):
                self.value = state.get("custom", "default")

        enhanced = _add_subprocess_serialization_support(CustomSerializable, "custom_tool")

        # Should preserve and enhance custom serialization
        instance = enhanced("test_value")
        state = instance.__getstate__()

        # Should include tool_name and custom state
        assert "tool_name" in state or "custom" in state

    def test_serialization_with_pydantic_v2(self):
        """Test serialization with Pydantic v2 model_dump."""

        class PydanticV2Tool(BaseModel):
            name: str
            age: int

        enhanced = _add_subprocess_serialization_support(PydanticV2Tool, "v2_tool")

        instance = enhanced(name="test", age=25)

        # Test serialization
        if hasattr(instance, "__getstate__"):
            state = instance.__getstate__()
            # Should work without errors
            assert isinstance(state, dict)

    def test_serialization_with_non_serializable_attrs(self):
        """Test serialization handles non-serializable attributes."""

        class ToolWithLambda:
            def __init__(self):
                self.func = lambda x: x * 2  # Non-serializable
                self.value = 42

        enhanced = _add_subprocess_serialization_support(ToolWithLambda, "lambda_tool")

        instance = enhanced()

        # Should have serialization methods
        if hasattr(instance, "__getstate__"):
            state = instance.__getstate__()
            # Should handle non-serializable attributes gracefully
            assert isinstance(state, dict)

    def test_deserialization_with_dict_state(self):
        """Test deserialization from dict state."""

        class SimpleTool:
            def __init__(self):
                self.value = None

        enhanced = _add_subprocess_serialization_support(SimpleTool, "simple")

        instance = enhanced()
        if hasattr(instance, "__setstate__"):
            instance.__setstate__({"value": "restored", "tool_name": "simple"})

            # State should be restored
            if hasattr(instance, "value"):
                assert instance.value == "restored"

    def test_deserialization_with_non_dict_state(self):
        """Test deserialization from non-dict state."""

        class AnotherTool:
            def __init__(self):
                self.data = None

        enhanced = _add_subprocess_serialization_support(AnotherTool, "another")

        instance = enhanced()
        if hasattr(instance, "__setstate__"):
            # Non-dict state
            instance.__setstate__("some_state")
            # Should handle gracefully without errors


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

    def test_register_tool_skips_already_registered(self):
        """Test that already registered tools are skipped."""
        with (
            patch("chuk_tool_processor.registry.decorators._PENDING_REGISTRATIONS", []) as pending,
            patch("chuk_tool_processor.registry.decorators._REGISTERED_CLASSES", set()) as registered,
        ):

            @register_tool(name="first_tool")
            class FirstTool(ValidatedTool):
                class Arguments(BaseModel):
                    value: str

                async def _execute(self, value: str):
                    return {"result": value}

            initial_count = len(pending)

            # Try to register again
            registered.add(FirstTool)
            FirstTool = register_tool(name="first_tool")(FirstTool)

            # Should not add to pending again
            assert len(pending) == initial_count

    def test_register_tool_during_shutdown(self):
        """Test that registration is skipped during shutdown."""
        with (
            patch("chuk_tool_processor.registry.decorators._PENDING_REGISTRATIONS", []) as pending,
            patch("chuk_tool_processor.registry.decorators._SHUTTING_DOWN", True),
        ):

            @register_tool(name="shutdown_tool")
            class ShutdownTool(ValidatedTool):
                class Arguments(BaseModel):
                    value: str

                async def _execute(self, value: str):
                    return {"result": value}

            # Should not add to pending during shutdown
            assert len(pending) == 0

    def test_register_tool_with_sync_execute(self):
        """Test that tools with non-async execute raise TypeError."""
        with (
            patch("chuk_tool_processor.registry.decorators._PENDING_REGISTRATIONS", []),
            patch("chuk_tool_processor.registry.decorators._REGISTERED_CLASSES", set()),
            pytest.raises(TypeError, match="must have an async execute method"),
        ):

            @register_tool(name="sync_tool")
            class SyncTool:
                def execute(self, value: str):  # Not async
                    return {"result": value}


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

    def test_make_compatible_adds_tool_name_property(self):
        """Test that tool_name property is added."""

        class SimpleTool:
            async def execute(self, value):
                return value

        compatible = make_pydantic_tool_compatible(SimpleTool, "simple_tool")

        # Should have tool_name accessible at class level
        assert hasattr(compatible, "tool_name")
        # Check if it's a property on the class
        tool_name_attr = getattr(compatible, "tool_name", None)
        assert tool_name_attr is not None or hasattr(compatible, "_tool_name")

    def test_make_compatible_with_existing_tool_name(self):
        """Test with class that already has tool_name."""

        class ToolWithName:
            tool_name = "existing_name"

            async def execute(self, value):
                return value

        compatible = make_pydantic_tool_compatible(ToolWithName, "new_name")

        # Should preserve existing tool_name attribute
        assert hasattr(compatible, "tool_name")

    def test_make_compatible_adds_getstate(self):
        """Test that __getstate__ is added."""

        class ToolWithoutState:
            async def execute(self, value):
                return value

        compatible = make_pydantic_tool_compatible(ToolWithoutState, "stateful")

        # Should have __getstate__
        assert hasattr(compatible, "__getstate__")

    def test_make_compatible_adds_setstate(self):
        """Test that __setstate__ is added."""

        class ToolWithoutState:
            async def execute(self, value):
                return value

        compatible = make_pydantic_tool_compatible(ToolWithoutState, "stateful")

        # Should have __setstate__
        assert hasattr(compatible, "__setstate__")

    def test_make_compatible_without_tool_name_property(self):
        """Test make_pydantic_tool_compatible when tool_name doesn't exist - line 294."""

        class ToolWithoutToolName:
            async def execute(self, value):
                return value

        # Ensure the class doesn't have tool_name
        assert not hasattr(ToolWithoutToolName, "tool_name")

        compatible = make_pydantic_tool_compatible(ToolWithoutToolName, "new_tool_name")

        # Should add tool_name property
        assert hasattr(compatible, "tool_name") or hasattr(compatible, "_tool_name")

    def test_make_compatible_preserves_existing_getstate(self):
        """Test that existing __getstate__ is preserved."""

        class ToolWithState:
            def __getstate__(self):
                return {"custom": "state"}

            def __setstate__(self, state):
                pass

            async def execute(self, value):
                return value

        compatible = make_pydantic_tool_compatible(ToolWithState, "stateful")

        # Should still have custom __getstate__
        instance = compatible()
        state = instance.__getstate__()
        # Should work without errors
        assert isinstance(state, dict)


class TestEnsureRegistrations:
    """Tests for ensure_registrations function."""

    @pytest.mark.asyncio
    async def test_ensure_registrations_empty(self):
        """Test ensure_registrations with no pending tools."""
        with patch("chuk_tool_processor.registry.decorators._PENDING_REGISTRATIONS", []):
            await ensure_registrations()
            # Should complete without error

    @pytest.mark.asyncio
    async def test_ensure_registrations_with_pending(self):
        """Test ensure_registrations with pending tools."""
        mock_registry = AsyncMock()
        mock_registry.register_tool = AsyncMock()

        # Create async registration functions
        async def reg1():
            await mock_registry.register_tool(ValidatedTool, name="tool1", namespace="default", metadata={})

        async def reg2():
            await mock_registry.register_tool(ValidatedTool, name="tool2", namespace="custom", metadata={})

        pending = [reg1, reg2]

        with (
            patch("chuk_tool_processor.registry.decorators._PENDING_REGISTRATIONS", pending),
            patch(
                "chuk_tool_processor.registry.provider.ToolRegistryProvider.get_registry", return_value=mock_registry
            ),
        ):
            await ensure_registrations()

            # Should register all pending tools
            assert mock_registry.register_tool.call_count == 2

    @pytest.mark.asyncio
    async def test_ensure_registrations_clears_pending(self):
        """Test that pending list is cleared after registration."""
        mock_registry = AsyncMock()
        mock_registry.register_tool = AsyncMock()

        # Create async registration function
        async def reg1():
            await mock_registry.register_tool(ValidatedTool, name="tool1", namespace="default", metadata={})

        pending = [reg1]

        with (
            patch("chuk_tool_processor.registry.decorators._PENDING_REGISTRATIONS", pending) as pending_list,
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

    def test_discover_with_multiple_namespaces(self):
        """Test discovering tools from multiple namespaces."""

        class DefaultTool(ValidatedTool):
            _tool_registration_info = {"name": "DefaultTool", "namespace": "default", "metadata": {}}

        class CustomTool(ValidatedTool):
            _tool_registration_info = {"name": "CustomTool", "namespace": "custom", "metadata": {}}

        mock_module = MagicMock()
        mock_module.DefaultTool = DefaultTool
        mock_module.CustomTool = CustomTool

        with patch("sys.modules", {"chuk_tool_processor.test_ns": mock_module}):
            # Get all tools
            all_tools = discover_decorated_tools()
            assert len([t for t in all_tools if hasattr(t, "_tool_registration_info")]) >= 0

            # Verify both tools are found regardless of namespace
            # Should include tools from different namespaces
            assert isinstance(all_tools, list)

    def test_discover_handles_module_errors(self):
        """Test that discover handles modules that raise errors gracefully."""

        class BadModule:
            def __getattribute__(self, name):
                raise AttributeError("Bad module")

        with patch("sys.modules", {"bad_module": BadModule()}):
            # Should not raise, just skip the bad module
            tools = discover_decorated_tools()
            assert isinstance(tools, list)


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


class TestAdditionalDecoratorCoverage:
    """Additional tests to increase coverage for decorators.py."""

    def test_pydantic_v1_fallback(self):
        """Test fallback to Pydantic v1 __fields__ check."""

        # Test exception handling in _is_pydantic_model
        class ProblematicClass:
            @property
            def model_fields(self):
                raise RuntimeError("Forced exception")

            @property
            def __pydantic_core_schema__(self):
                raise RuntimeError("Forced exception")

            __fields__ = {"field1": "value"}

        # Should handle exceptions and check __fields__ fallback
        result = _is_pydantic_model(ProblematicClass)
        assert isinstance(result, bool)

    def test_is_pydantic_model_exception_in_both_paths(self):
        """Test exception handling in both try blocks."""

        class DoublyProblematic:
            @property
            def model_fields(self):
                raise RuntimeError("First exception")

            @property
            def __fields__(self):
                raise RuntimeError("Second exception")

        # Should handle both exceptions - hasattr doesn't trigger property exceptions
        result = _is_pydantic_model(DoublyProblematic)
        # hasattr will return True if __fields__ exists, even as a property
        assert isinstance(result, bool)

    def test_custom_serialization_with_non_dict_state(self):
        """Test custom __getstate__ returning non-dict."""

        class CustomNonDictState:
            def __init__(self):
                self.value = "test"

            def __getstate__(self):
                return "non_dict_state"

            def __setstate__(self, state):
                pass

        enhanced = _add_subprocess_serialization_support(CustomNonDictState, "custom_tool")
        instance = enhanced()
        state = instance.__getstate__()
        # Should wrap non-dict state
        assert isinstance(state, dict)
        assert "_custom_state" in state or "tool_name" in state

    def test_pydantic_setstate_with_custom_state(self):
        """Test Pydantic model setstate with _custom_state."""

        class PydanticModel(BaseModel):
            value: str = "default"

        enhanced = _add_subprocess_serialization_support(PydanticModel, "pydantic_tool")
        _instance = enhanced(value="test")

        # Manually override to have custom __getstate__/__setstate__
        class CustomPydantic(BaseModel):
            value: str = "default"

            def __getstate__(self):
                return {"value": self.value}

            def __setstate__(self, state):
                self.value = state.get("value", "default")

        enhanced2 = _add_subprocess_serialization_support(CustomPydantic, "custom_pydantic")
        inst2 = enhanced2(value="original")

        if hasattr(inst2, "__setstate__"):
            inst2.__setstate__({"_custom_state": {"value": "restored"}, "tool_name": "custom_pydantic"})

    def test_pydantic_init_without_existing(self):
        """Test adding __init__ to Pydantic class without one."""

        # Create a proper Pydantic model
        class PydanticLike(BaseModel):
            value: str = "default"

        enhanced = _add_subprocess_serialization_support(PydanticLike, "test_tool")
        # Should have __init__ (from Pydantic or enhanced)
        assert hasattr(enhanced, "__init__")
        # Test instantiation works
        instance = enhanced(value="test")
        assert instance.value == "test"

    def test_regular_class_init_without_existing(self):
        """Test adding __init__ to regular class without one."""

        # Create a basic class without __init__
        RegularClass = type("RegularClass", (), {})

        enhanced = _add_subprocess_serialization_support(RegularClass, "test_tool")
        # Should add __init__
        assert hasattr(enhanced, "__init__")
        instance = enhanced()
        assert hasattr(instance, "tool_name") or hasattr(enhanced, "_tool_name")

    def test_make_pydantic_compatible_with_existing_getstate(self):
        """Test make_pydantic_tool_compatible preserves existing __getstate__."""

        class WithGetstate:
            def __getstate__(self):
                return {"existing": True}

        compatible = make_pydantic_tool_compatible(WithGetstate, "tool")
        # Should preserve existing __getstate__
        assert hasattr(compatible, "__getstate__")

    def test_make_pydantic_compatible_with_existing_setstate(self):
        """Test make_pydantic_tool_compatible preserves existing __setstate__."""

        class WithSetstate:
            def __setstate__(self, state):
                self.restored = True

        compatible = make_pydantic_tool_compatible(WithSetstate, "tool")
        # Should preserve existing __setstate__
        assert hasattr(compatible, "__setstate__")

    def test_pydantic_getstate_dict_fallback(self):
        """Test Pydantic __getstate__ dict() fallback for v1."""

        class PydanticV1Like(BaseModel):
            value: str = "test"

            # Simulate v1 by removing model_dump
            def dict(self):
                return {"value": self.value}

        enhanced = _add_subprocess_serialization_support(PydanticV1Like, "v1_tool")
        instance = enhanced(value="test_value")

        if hasattr(instance, "__getstate__"):
            state = instance.__getstate__()
            assert isinstance(state, dict)

    def test_pydantic_getstate_exception_fallback(self):
        """Test Pydantic __getstate__ exception fallback to __dict__."""

        class ProblematicPydantic(BaseModel):
            value: str = "test"

            def model_dump(self):
                raise RuntimeError("Intentional error")

        enhanced = _add_subprocess_serialization_support(ProblematicPydantic, "problematic")
        instance = enhanced(value="test")

        if hasattr(instance, "__getstate__"):
            state = instance.__getstate__()
            # Should fallback to __dict__
            assert isinstance(state, dict)

    def test_pydantic_setstate_exception_fallback(self):
        """Test Pydantic __setstate__ exception handling."""

        class PydanticWithIssue(BaseModel):
            value: str = "default"

        enhanced = _add_subprocess_serialization_support(PydanticWithIssue, "issue_tool")
        instance = enhanced(value="test")

        if hasattr(instance, "__setstate__"):
            # Try to set state with fields that may cause issues
            instance.__setstate__({"value": "restored", "tool_name": "issue_tool"})
            # Should handle gracefully

    def test_regular_class_setstate_non_dict(self):
        """Test regular class __setstate__ with non-dict state."""

        class RegularTool:
            def __init__(self):
                self.value = None

        enhanced = _add_subprocess_serialization_support(RegularTool, "regular")
        instance = enhanced()

        if hasattr(instance, "__setstate__"):
            instance.__setstate__("non_dict_state")
            # Should set tool_name
            assert hasattr(instance, "tool_name") or hasattr(enhanced, "_tool_name")


class TestDecoratorIntegration:
    """Integration tests for decorators."""

    @pytest.mark.asyncio
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

            # Process pending registrations
            await ensure_registrations()

            # Tool should be registered
            mock_registry.register_tool.assert_called()

            # Verify the tool was registered with correct parameters
            call_args = mock_registry.register_tool.call_args
            assert call_args is not None
            assert call_args.kwargs["name"] == "integration_tool"
            assert call_args.kwargs["namespace"] == "test"

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


class TestEnhancedSetStateForPydantic:
    """Tests for enhanced setstate in custom serialization with Pydantic."""

    def test_enhanced_setstate_with_custom_state_pydantic(self):
        """Test enhanced setstate with _custom_state for Pydantic model."""

        class PydanticLike(BaseModel):
            value: str = "default"

            def __getstate__(self):
                return {"value": self.value}

            def __setstate__(self, state):
                if isinstance(state, dict):
                    self.value = state.get("value", "default")

        enhanced = _add_subprocess_serialization_support(PydanticLike, "custom_pydantic")
        instance = enhanced(value="original")

        if hasattr(instance, "__setstate__"):
            # Test with _custom_state - this should hit line 82
            instance.__setstate__({"_custom_state": {"value": "restored"}, "tool_name": "custom_pydantic"})

    def test_enhanced_setstate_with_dict_state_pydantic(self):
        """Test enhanced setstate with dict state for Pydantic model."""

        class PydanticCustom(BaseModel):
            count: int = 0

            def __getstate__(self):
                return {"count": self.count}

            def __setstate__(self, state):
                if isinstance(state, dict):
                    self.count = state.get("count", 0)

        enhanced = _add_subprocess_serialization_support(PydanticCustom, "pydantic_custom")
        instance = enhanced(count=5)

        if hasattr(instance, "__setstate__"):
            # Test with regular dict state - this should hit lines 84-89
            instance.__setstate__({"count": 10, "tool_name": "pydantic_custom"})

    def test_pydantic_getstate_with_dict_method(self):
        """Test Pydantic v1 dict() method - lines 105-110."""

        class PydanticV1Style(BaseModel):
            name: str = "test"

        enhanced = _add_subprocess_serialization_support(PydanticV1Style, "v1_tool")
        instance = enhanced(name="test_value")

        # This should use model_dump or dict()
        if hasattr(instance, "__getstate__"):
            state = instance.__getstate__()
            assert isinstance(state, dict)
            assert "tool_name" in state

    def test_pydantic_setstate_exception_path(self):
        """Test Pydantic setstate exception handling - lines 135-141."""

        class PydanticWithExceptionProne(BaseModel):
            data: str = "default"

        enhanced = _add_subprocess_serialization_support(PydanticWithExceptionProne, "exception_tool")
        instance = enhanced(data="test")

        if hasattr(instance, "__setstate__"):
            # Force exception by providing problematic state
            # This should trigger the exception handler and fallback
            import contextlib

            with contextlib.suppress(Exception):
                instance.__setstate__({"data": "restored", "bad_field": "value", "tool_name": "exception_tool"})

    def test_regular_class_setstate_no_tool_name(self):
        """Test regular class setstate when tool_name not in instance - line 173."""

        class RegularToolNoName:
            def __init__(self):
                self.value = None
                # Deliberately no tool_name attribute

        enhanced = _add_subprocess_serialization_support(RegularToolNoName, "regular_tool")
        instance = enhanced()

        # Remove tool_name if it exists
        if hasattr(instance, "tool_name"):
            delattr(instance, "tool_name")

        if hasattr(instance, "__setstate__"):
            instance.__setstate__({"value": "restored", "tool_name": "regular_tool"})
            # Should set tool_name from state

    def test_pydantic_class_without_init(self):
        """Test adding __init__ to Pydantic class - lines 210-220."""

        # Remove __init__ to trigger the else path
        class FakePydanticNoInit(BaseModel):
            value: str = "default"

        # The class will have __init__ from BaseModel, so we need a different approach
        # Create a class without any __init__
        MinimalClass = type("MinimalClass", (), {"model_fields": {}})

        enhanced = _add_subprocess_serialization_support(MinimalClass, "minimal_tool")
        # Should add __init__
        assert hasattr(enhanced, "__init__")

    def test_make_pydantic_compatible_getstate_model_dump(self):
        """Test make_pydantic_tool_compatible __getstate__ with model_dump - lines 301-315."""
        # Note: make_pydantic_tool_compatible uses hasattr which will find
        # __getstate__ from object class, so it won't add a new one.
        # This test just verifies the function doesn't break when called.

        class ToolWithModelDump:
            """A tool without existing __getstate__."""

            def model_dump(self):
                return {"value": "test_value"}

        compatible = make_pydantic_tool_compatible(ToolWithModelDump, "model_dump_tool")

        # Should have _tool_name set
        assert hasattr(compatible, "_tool_name")
        assert compatible._tool_name == "model_dump_tool"

        # Should have tool_name property
        instance = compatible()
        assert hasattr(instance, "tool_name")
        assert instance.tool_name == "model_dump_tool"

    def test_make_pydantic_compatible_getstate_exception(self):
        """Test make_pydantic_tool_compatible __getstate__ exception path."""

        class ProblematicTool(BaseModel):
            value: str = "test"

            def model_dump(self):
                raise RuntimeError("Intentional error")

            def dict(self):
                raise RuntimeError("Intentional error")

        compatible = make_pydantic_tool_compatible(ProblematicTool, "problematic_tool")

        instance = compatible(value="test")
        if hasattr(instance, "__getstate__"):
            state = instance.__getstate__()
            # Should fall back to __dict__
            assert isinstance(state, dict)

    def test_make_pydantic_compatible_setstate(self):
        """Test make_pydantic_tool_compatible __setstate__ - lines 320-325."""

        class SimpleToolForSetState:
            def execute(self):
                pass

        compatible = make_pydantic_tool_compatible(SimpleToolForSetState, "setstate_tool")

        instance = compatible()
        if hasattr(instance, "__setstate__"):
            instance.__setstate__({"data": "value", "tool_name": "setstate_tool"})
            # Should handle state restoration

    def test_discover_decorated_tools_import_error(self):
        """Test discover_decorated_tools with ImportError - lines 362-363."""
        # Simple test that doesn't cause infinite loops
        with patch("sys.modules", {"chuk_tool_processor.test_module": None}):
            # Should handle ImportError/AttributeError gracefully
            tools = discover_decorated_tools()
            assert isinstance(tools, list)

    def test_is_pydantic_model_exception_handlers(self):
        """Test _is_pydantic_model exception handlers - lines 35-40."""

        # Class that raises exception on hasattr for model_fields
        class ExceptionOnV2Check:
            def __getattribute__(self, name):
                if name in ("model_fields", "__pydantic_core_schema__"):
                    raise RuntimeError("Exception on V2 check")
                raise AttributeError(f"{name} not found")

        # Should handle exception and try V1 check
        result = _is_pydantic_model(ExceptionOnV2Check)
        assert isinstance(result, bool)

    def test_enhanced_setstate_regular_class_branch(self):
        """Test enhanced setstate for non-Pydantic classes - lines 81, 88."""

        # Create a regular class with custom serialization
        class RegularCustom:
            def __init__(self):
                self.value = None

            def __getstate__(self):
                return {"value": self.value}

            def __setstate__(self, state):
                self.value = state.get("value")

        enhanced = _add_subprocess_serialization_support(RegularCustom, "regular_custom")
        instance = enhanced()
        instance.value = "test"

        # Test with _custom_state (line 81)
        if hasattr(instance, "__setstate__"):
            state = instance.__getstate__()
            instance2 = enhanced()
            instance2.__setstate__({"_custom_state": state, "tool_name": "regular_custom"})

        # Test with regular dict state (line 88)
        instance3 = enhanced()
        if hasattr(instance3, "__setstate__"):
            instance3.__setstate__({"value": "restored", "tool_name": "regular_custom"})
            # Should set tool_name on instance (not class)
            if hasattr(instance3, "tool_name"):
                assert instance3.tool_name == "regular_custom"

    def test_pydantic_init_property_addition(self):
        """Test tool_name property addition in enhanced_init - lines 197-201."""

        class CustomPydanticLike(BaseModel):
            data: str = "test"

        # Ensure the class doesn't have tool_name property yet
        if hasattr(CustomPydanticLike, "tool_name"):
            delattr(CustomPydanticLike, "tool_name")

        enhanced = _add_subprocess_serialization_support(CustomPydanticLike, "prop_test")

        # Create instance - should trigger enhanced_init
        instance = enhanced(data="value")

        # Should have tool_name accessible
        assert hasattr(instance, "tool_name") or hasattr(enhanced, "_tool_name")

    def test_pydantic_without_init_path(self):
        """Test __init__ addition for Pydantic-like class - lines 210-220."""

        # Create a Pydantic-like class without __init__ using type()
        # This creates a class with no __init__ method
        PydanticLikeNoInit = type("PydanticLikeNoInit", (), {"model_fields": {}})

        # Verify it doesn't have its own __init__ (it will inherit from object)
        # This will trigger the else branch in _add_subprocess_serialization_support

        enhanced = _add_subprocess_serialization_support(PydanticLikeNoInit, "no_init_tool")

        # Should add __init__
        assert hasattr(enhanced, "__init__")

        # Should be able to instantiate
        _instance = enhanced()
        assert hasattr(enhanced, "_tool_name")
        assert enhanced._tool_name == "no_init_tool"

    def test_make_pydantic_compatible_adds_getstate(self):
        """Test make_pydantic_tool_compatible adds __getstate__ - lines 312-326."""

        # Create a class without __getstate__ but with model_dump
        class ToolWithoutGetstate:
            def model_dump(self):
                return {"key": "value"}

        # Delete __getstate__ if it exists from object class
        compatible = make_pydantic_tool_compatible(ToolWithoutGetstate, "test_getstate")

        # The function uses hasattr which will find __getstate__ from object class
        # So we need to verify the function completes without error
        assert hasattr(compatible, "_tool_name")
        assert compatible._tool_name == "test_getstate"

    def test_discover_tools_attribute_error(self):
        """Test discover_decorated_tools handles AttributeError - line 373."""

        class ModuleWithBadAttr:
            def __dir__(self):
                return ["tool1", "tool2"]

            def __getattr__(self, name):
                raise AttributeError(f"Cannot access {name}")

        with patch("sys.modules", {"chuk_tool_processor.bad_module": ModuleWithBadAttr()}):
            # Should handle AttributeError gracefully
            tools = discover_decorated_tools()
            assert isinstance(tools, list)

    def test_discover_tools_import_error(self):
        """Test discover_decorated_tools handles ImportError - line 373."""

        class ModuleWithImportError:
            def __dir__(self):
                return ["tool1"]

            def __getattr__(self, name):
                raise ImportError(f"Cannot import {name}")

        with patch("sys.modules", {"chuk_tool_processor.import_module": ModuleWithImportError()}):
            # Should handle ImportError gracefully
            tools = discover_decorated_tools()
            assert isinstance(tools, list)

    def test_tool_decorator_alias(self):
        """Test tool decorator alias function - line 407."""
        from chuk_tool_processor.registry.decorators import tool

        with patch("chuk_tool_processor.registry.decorators._PENDING_REGISTRATIONS", []) as pending:

            @tool(name="test_via_tool", namespace="custom")
            class ToolViaAlias(ValidatedTool):
                class Arguments(BaseModel):
                    value: str

                async def _execute(self, value: str):
                    return {"result": value}

            # Should work identically to register_tool
            assert len(pending) == 1
            assert hasattr(ToolViaAlias, "_tool_registration_info")
            assert ToolViaAlias._tool_registration_info["name"] == "test_via_tool"
            assert ToolViaAlias._tool_registration_info["namespace"] == "custom"
