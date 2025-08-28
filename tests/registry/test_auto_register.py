"""Tests for auto_register module functions."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from chuk_tool_processor.registry.auto_register import _auto_schema, register_fn_tool, register_langchain_tool

# Tests in this module use a mix of sync and async
# Mark async tests individually


class TestAutoSchema:
    """Tests for _auto_schema function."""

    def test_auto_schema_simple_function(self):
        """Test schema generation for simple function."""

        def simple_func(name: str, age: int) -> str:
            return f"{name} is {age}"

        schema = _auto_schema(simple_func)

        assert issubclass(schema, BaseModel)
        assert "name" in schema.model_fields
        assert "age" in schema.model_fields

    def test_auto_schema_no_annotations(self):
        """Test schema generation for function without annotations."""

        def no_annotations(name, age):
            return f"{name} is {age}"

        schema = _auto_schema(no_annotations)

        # Should default to str for unannotated params
        assert issubclass(schema, BaseModel)
        assert "name" in schema.model_fields
        assert "age" in schema.model_fields

    def test_auto_schema_with_defaults(self):
        """Test schema with default values."""

        def with_defaults(name: str, age: int = 25, active: bool = True):
            return name

        schema = _auto_schema(with_defaults)

        assert issubclass(schema, BaseModel)
        fields = schema.model_fields
        assert "name" in fields
        assert "age" in fields
        assert "active" in fields

    def test_auto_schema_complex_types(self):
        """Test schema with complex type annotations."""

        def complex_func(data: dict[str, Any], items: list[int]) -> dict:
            return data

        schema = _auto_schema(complex_func)

        assert issubclass(schema, BaseModel)
        assert "data" in schema.model_fields
        assert "items" in schema.model_fields

    def test_auto_schema_forward_ref(self):
        """Test schema with forward references."""

        def forward_ref_func(value: "SomeUnknownType") -> str:  # noqa: F821
            return str(value)

        schema = _auto_schema(forward_ref_func)

        # Should default to str for unresolvable types
        assert issubclass(schema, BaseModel)
        assert "value" in schema.model_fields

    def test_auto_schema_with_exception_in_hints(self):
        """Test schema when get_type_hints raises exception."""

        def problematic_func(value: "NonExistent") -> str:  # noqa: F821
            return str(value)

        # Mock get_type_hints to raise an exception
        with patch("chuk_tool_processor.registry.auto_register.get_type_hints", side_effect=Exception("Error")):
            schema = _auto_schema(problematic_func)

            assert issubclass(schema, BaseModel)
            assert "value" in schema.model_fields


class TestRegisterFnTool:
    """Tests for register_fn_tool function."""

    @pytest.fixture
    def mock_registry(self):
        """Create a mock registry."""
        registry = AsyncMock()
        registry.register_tool = AsyncMock()
        return registry

    @pytest.mark.asyncio
    async def test_register_sync_function(self, mock_registry):
        """Test registering a synchronous function."""

        def sync_func(name: str, value: int) -> dict:
            """A synchronous test function."""
            return {"name": name, "value": value}

        with patch(
            "chuk_tool_processor.registry.provider.ToolRegistryProvider.get_registry", return_value=mock_registry
        ):
            await register_fn_tool(sync_func)

            mock_registry.register_tool.assert_called_once()
            call_args = mock_registry.register_tool.call_args

            # Check the tool instance
            tool_instance = call_args[0][0]
            assert hasattr(tool_instance, "execute")

            # Check metadata
            kwargs = call_args[1]
            assert kwargs["name"] == "sync_func"
            assert kwargs["namespace"] == "default"
            assert "metadata" in kwargs
            assert kwargs["metadata"]["description"] == "A synchronous test function."
            assert kwargs["metadata"]["is_async"] is True
            assert kwargs["metadata"]["source"] == "function"

    @pytest.mark.asyncio
    async def test_register_async_function(self, mock_registry):
        """Test registering an asynchronous function."""

        async def async_func(name: str) -> str:
            """An async test function."""
            await asyncio.sleep(0.01)
            return f"Hello {name}"

        with patch(
            "chuk_tool_processor.registry.provider.ToolRegistryProvider.get_registry", return_value=mock_registry
        ):
            await register_fn_tool(async_func, name="custom_name", description="Custom description", namespace="custom")

            mock_registry.register_tool.assert_called_once()
            kwargs = mock_registry.register_tool.call_args[1]

            assert kwargs["name"] == "custom_name"
            assert kwargs["namespace"] == "custom"
            assert kwargs["metadata"]["description"] == "Custom description"

    @pytest.mark.asyncio
    async def test_register_function_execution(self, mock_registry):
        """Test that registered function can be executed."""

        def test_func(x: int, y: int) -> int:
            return x + y

        with patch(
            "chuk_tool_processor.registry.provider.ToolRegistryProvider.get_registry", return_value=mock_registry
        ):
            await register_fn_tool(test_func)

            # Get the registered tool instance
            tool_instance = mock_registry.register_tool.call_args[0][0]

            # Test execution
            result = await tool_instance.execute(x=5, y=3)
            assert result == 8

    @pytest.mark.asyncio
    async def test_register_async_function_execution(self, mock_registry):
        """Test that registered async function can be executed."""

        async def async_test(value: str) -> str:
            await asyncio.sleep(0.01)
            return value.upper()

        with patch(
            "chuk_tool_processor.registry.provider.ToolRegistryProvider.get_registry", return_value=mock_registry
        ):
            await register_fn_tool(async_test)

            tool_instance = mock_registry.register_tool.call_args[0][0]

            # Test async execution
            result = await tool_instance.execute(value="hello")
            assert result == "HELLO"

    @pytest.mark.asyncio
    async def test_register_function_no_docstring(self, mock_registry):
        """Test registering function without docstring."""

        def no_doc_func(x: int) -> int:
            return x * 2

        with patch(
            "chuk_tool_processor.registry.provider.ToolRegistryProvider.get_registry", return_value=mock_registry
        ):
            await register_fn_tool(no_doc_func)

            kwargs = mock_registry.register_tool.call_args[1]
            assert kwargs["metadata"]["description"] == ""

    @pytest.mark.asyncio
    async def test_register_function_with_schema(self, mock_registry):
        """Test that argument schema is properly generated."""

        def typed_func(name: str, age: int, active: bool = True) -> dict:
            return {"name": name, "age": age, "active": active}

        with patch(
            "chuk_tool_processor.registry.provider.ToolRegistryProvider.get_registry", return_value=mock_registry
        ):
            await register_fn_tool(typed_func)

            kwargs = mock_registry.register_tool.call_args[1]
            schema = kwargs["metadata"]["argument_schema"]

            assert "properties" in schema
            assert "name" in schema["properties"]
            assert "age" in schema["properties"]
            assert "active" in schema["properties"]


class TestRegisterLangchainTool:
    """Tests for register_langchain_tool function."""

    @pytest.fixture
    def mock_registry(self):
        """Create a mock registry."""
        registry = AsyncMock()
        registry.register_tool = AsyncMock()
        registry.get_tool = AsyncMock()
        registry.get_metadata = AsyncMock()
        return registry

    @pytest.mark.asyncio
    async def test_register_langchain_not_installed(self, mock_registry):
        """Test error when LangChain is not installed."""
        with (
            patch("chuk_tool_processor.registry.auto_register.BaseTool", None),
            pytest.raises(RuntimeError, match="requires LangChain"),
        ):
            await register_langchain_tool(MagicMock())

    @pytest.mark.asyncio
    async def test_register_langchain_wrong_type(self, mock_registry):
        """Test error when object is not a BaseTool."""
        # Mock BaseTool to exist
        with patch("chuk_tool_processor.registry.auto_register.BaseTool", MagicMock):
            wrong_obj = "not a tool"
            with pytest.raises(TypeError, match="Expected a langchain.tools.base.BaseTool"):
                await register_langchain_tool(wrong_obj)

    @pytest.mark.asyncio
    async def test_register_langchain_tool_sync(self, mock_registry):
        """Test registering a LangChain tool with sync run method."""
        # Create a mock LangChain tool
        mock_tool = MagicMock(spec=["name", "description", "run"])
        mock_tool.name = "langchain_tool"
        mock_tool.description = "A LangChain tool"
        mock_tool.run = MagicMock(return_value="result")
        mock_tool.run.__name__ = "run"  # Add __name__ attribute for _auto_schema
        mock_tool.run.__qualname__ = "LangChainTool.run"  # Add __qualname__ attribute

        # Mock the metadata
        from chuk_tool_processor.registry.metadata import ToolMetadata

        mock_metadata = ToolMetadata(name="langchain_tool", namespace="default", tags=set(), created_at=0, updated_at=0)
        mock_registry.get_metadata.return_value = mock_metadata

        # Make it look like a BaseTool
        with (
            patch("chuk_tool_processor.registry.auto_register.BaseTool", MagicMock),
            patch("chuk_tool_processor.registry.auto_register.isinstance", return_value=True),
            patch(
                "chuk_tool_processor.registry.provider.ToolRegistryProvider.get_registry",
                return_value=mock_registry,
            ),
        ):
            # Mock get_tool to return a mock tool for metadata update
            mock_registry.get_tool.return_value = AsyncMock()

            await register_langchain_tool(mock_tool)

            # Should have called register_tool twice (once in register_fn_tool, once for metadata update)
            assert mock_registry.register_tool.call_count == 2

    @pytest.mark.asyncio
    async def test_register_langchain_tool_async(self, mock_registry):
        """Test registering a LangChain tool with async arun method."""
        # Create a mock LangChain tool with arun
        mock_tool = MagicMock()
        mock_tool.name = "async_langchain_tool"
        mock_tool.description = "An async LangChain tool"

        async def mock_arun(*args, **kwargs):
            return "async_result"

        mock_tool.arun = mock_arun
        mock_tool.arun.__name__ = "arun"  # Add __name__ for _auto_schema
        mock_tool.arun.__qualname__ = "LangChainTool.arun"  # Add __qualname__ attribute
        mock_tool.run = MagicMock(return_value="sync_result")
        mock_tool.run.__name__ = "run"
        mock_tool.run.__qualname__ = "LangChainTool.run"

        # Mock the metadata
        from chuk_tool_processor.registry.metadata import ToolMetadata

        mock_metadata = ToolMetadata(
            name="async_langchain_tool", namespace="default", tags=set(), created_at=0, updated_at=0
        )
        mock_registry.get_metadata.return_value = mock_metadata

        with (
            patch("chuk_tool_processor.registry.auto_register.BaseTool", MagicMock),
            patch("chuk_tool_processor.registry.auto_register.isinstance", return_value=True),
            patch(
                "chuk_tool_processor.registry.provider.ToolRegistryProvider.get_registry",
                return_value=mock_registry,
            ),
        ):
            # Mock get_tool for metadata update
            mock_registry.get_tool.return_value = AsyncMock()

            await register_langchain_tool(mock_tool, namespace="langchain")

            # Check that it was registered
            assert mock_registry.register_tool.called

    @pytest.mark.asyncio
    async def test_register_langchain_custom_params(self, mock_registry):
        """Test registering LangChain tool with custom parameters."""
        mock_tool = MagicMock(spec=["name", "description", "run"])
        mock_tool.name = "original_name"
        mock_tool.description = "Original description"
        mock_tool.run = MagicMock()
        mock_tool.run.__name__ = "run"  # Add __name__ for _auto_schema
        mock_tool.run.__qualname__ = "LangChainTool.run"

        # Mock the metadata
        from chuk_tool_processor.registry.metadata import ToolMetadata

        mock_metadata = ToolMetadata(
            name="custom_tool_name", namespace="custom_ns", tags=set(), created_at=0, updated_at=0
        )
        mock_registry.get_metadata.return_value = mock_metadata

        with (
            patch("chuk_tool_processor.registry.auto_register.BaseTool", MagicMock),
            patch("chuk_tool_processor.registry.auto_register.isinstance", return_value=True),
            patch(
                "chuk_tool_processor.registry.provider.ToolRegistryProvider.get_registry",
                return_value=mock_registry,
            ),
        ):
            # Mock get_tool for metadata update
            mock_registry.get_tool.return_value = AsyncMock()

            await register_langchain_tool(
                mock_tool, name="custom_tool_name", description="Custom description", namespace="custom_ns"
            )

            # Verify custom params were used
            first_call_kwargs = mock_registry.register_tool.call_args_list[0][1]
            assert first_call_kwargs["name"] == "custom_tool_name"
            assert first_call_kwargs["namespace"] == "custom_ns"

    @pytest.mark.asyncio
    async def test_register_langchain_no_metadata(self, mock_registry):
        """Test registering LangChain tool when metadata is not found."""
        mock_tool = MagicMock(spec=["name", "description", "run"])
        mock_tool.name = "tool_without_metadata"
        mock_tool.description = "No metadata tool"
        mock_tool.run = MagicMock()
        mock_tool.run.__name__ = "run"  # Add __name__ for _auto_schema
        mock_tool.run.__qualname__ = "LangChainTool.run"

        # Return None for metadata
        mock_registry.get_metadata.return_value = None

        with (
            patch("chuk_tool_processor.registry.auto_register.BaseTool", MagicMock),
            patch("chuk_tool_processor.registry.auto_register.isinstance", return_value=True),
            patch(
                "chuk_tool_processor.registry.provider.ToolRegistryProvider.get_registry",
                return_value=mock_registry,
            ),
        ):
            await register_langchain_tool(mock_tool)

            # Should still register the tool
            assert mock_registry.register_tool.called
            # But only once (no metadata update)
            assert mock_registry.register_tool.call_count == 1
