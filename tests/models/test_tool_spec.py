# tests/models/test_tool_spec.py
"""Tests for ToolSpec formal schema layer."""

from pydantic import BaseModel, Field

from chuk_tool_processor.models.tool_spec import ToolCapability, ToolSpec, tool_spec
from chuk_tool_processor.models.validated_tool import ValidatedTool


class TestToolSpec:
    """Tests for ToolSpec model."""

    def test_basic_creation(self):
        """Test creating a basic ToolSpec."""
        spec = ToolSpec(
            name="test_tool",
            description="A test tool",
            parameters={
                "type": "object",
                "properties": {
                    "arg1": {"type": "string"},
                },
                "required": ["arg1"],
            },
        )

        assert spec.name == "test_tool"
        assert spec.description == "A test tool"
        assert spec.version == "1.0.0"
        assert spec.namespace == "default"

    def test_with_capabilities(self):
        """Test ToolSpec with capabilities."""
        spec = ToolSpec(
            name="cacheable_tool",
            description="A cacheable tool",
            parameters={"type": "object", "properties": {}},
            capabilities=[ToolCapability.CACHEABLE, ToolCapability.IDEMPOTENT],
        )

        assert spec.has_capability(ToolCapability.CACHEABLE)
        assert spec.has_capability(ToolCapability.IDEMPOTENT)
        assert not spec.has_capability(ToolCapability.STREAMING)
        assert spec.is_cacheable()
        assert spec.is_idempotent()
        assert not spec.is_streaming()

    def test_to_openai(self):
        """Test OpenAI export format."""
        spec = ToolSpec(
            name="search",
            description="Search the web",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        )

        openai_format = spec.to_openai()

        assert openai_format["type"] == "function"
        assert openai_format["function"]["name"] == "search"
        assert openai_format["function"]["description"] == "Search the web"
        assert "query" in openai_format["function"]["parameters"]["properties"]

    def test_to_anthropic(self):
        """Test Anthropic export format."""
        spec = ToolSpec(
            name="calculator",
            description="Calculate math",
            parameters={
                "type": "object",
                "properties": {
                    "operation": {"type": "string"},
                    "a": {"type": "number"},
                    "b": {"type": "number"},
                },
            },
        )

        anthropic_format = spec.to_anthropic()

        assert anthropic_format["name"] == "calculator"
        assert anthropic_format["description"] == "Calculate math"
        assert "input_schema" in anthropic_format

    def test_to_mcp(self):
        """Test MCP export format."""
        spec = ToolSpec(
            name="get_weather",
            description="Get current weather",
            parameters={
                "type": "object",
                "properties": {"location": {"type": "string"}},
            },
            returns={
                "type": "object",
                "properties": {
                    "temperature": {"type": "number"},
                    "conditions": {"type": "string"},
                },
            },
        )

        mcp_format = spec.to_mcp()

        assert mcp_format["name"] == "get_weather"
        assert mcp_format["description"] == "Get current weather"
        assert "inputSchema" in mcp_format
        assert "outputSchema" in mcp_format

    def test_from_validated_tool(self):
        """Test creating ToolSpec from ValidatedTool."""

        class TestTool(ValidatedTool):
            """A test tool for validation."""

            class Arguments(BaseModel):
                name: str = Field(..., description="User name")
                age: int = Field(..., description="User age")

            class Result(BaseModel):
                message: str

            async def _execute(self, name: str, age: int) -> Result:
                return self.Result(message=f"Hello {name}, you are {age}")

        spec = ToolSpec.from_validated_tool(TestTool, namespace="test")

        assert spec.name == "TestTool"
        assert "test tool for validation" in spec.description.lower()
        assert spec.namespace == "test"
        assert "name" in spec.parameters["properties"]
        assert "age" in spec.parameters["properties"]
        assert spec.returns is not None

    def test_from_function(self):
        """Test creating ToolSpec from plain function."""

        def my_function(text: str, count: int = 1) -> str:
            """Repeat text N times."""
            return text * count

        spec = ToolSpec.from_function(my_function)

        assert spec.name == "my_function"
        assert "repeat text" in spec.description.lower()
        assert "text" in spec.parameters["properties"]
        assert "count" in spec.parameters["properties"]
        assert "text" in spec.parameters["required"]
        assert "count" not in spec.parameters["required"]  # Has default

    def test_tool_spec_decorator(self):
        """Test @tool_spec decorator."""

        @tool_spec(
            version="2.0.0",
            capabilities=[ToolCapability.CACHEABLE],
            tags=["math", "computation"],
        )
        class DecoratedTool(ValidatedTool):
            """A decorated tool."""

            class Arguments(BaseModel):
                x: int

            class Result(BaseModel):
                result: int

            async def _execute(self, x: int) -> Result:
                return self.Result(result=x * 2)

        assert hasattr(DecoratedTool, "_tool_spec_version")
        assert DecoratedTool._tool_spec_version == "2.0.0"
        assert ToolCapability.CACHEABLE in DecoratedTool._tool_spec_capabilities
        assert "math" in DecoratedTool._tool_spec_tags

    def test_version_tracking(self):
        """Test version tracking."""
        spec_v1 = ToolSpec(
            name="api_tool",
            version="1.0.0",
            description="Version 1",
            parameters={"type": "object", "properties": {}},
        )

        spec_v2 = ToolSpec(
            name="api_tool",
            version="2.1.0",
            description="Version 2 with breaking changes",
            parameters={"type": "object", "properties": {}},
        )

        assert spec_v1.version != spec_v2.version
        assert spec_v1.name == spec_v2.name

    def test_metadata_fields(self):
        """Test optional metadata fields."""
        spec = ToolSpec(
            name="licensed_tool",
            description="A tool with metadata",
            parameters={"type": "object", "properties": {}},
            author="John Doe",
            license="MIT",
            documentation_url="https://example.com/docs",
            source_url="https://github.com/example/tool",
            estimated_duration_seconds=5.0,
            max_retries=3,
            tags=["external", "api"],
        )

        assert spec.author == "John Doe"
        assert spec.license == "MIT"
        assert spec.documentation_url == "https://example.com/docs"
        assert spec.estimated_duration_seconds == 5.0
        assert spec.max_retries == 3
        assert "external" in spec.tags

    def test_to_json_schema(self):
        """Test to_json_schema method (line 166)."""
        spec = ToolSpec(
            name="test",
            description="Test tool",
            parameters={
                "type": "object",
                "properties": {"arg": {"type": "string"}},
            },
        )

        json_schema = spec.to_json_schema()
        assert json_schema == spec.parameters
        assert "properties" in json_schema

    def test_to_dict(self):
        """Test to_dict method (line 175)."""
        spec = ToolSpec(
            name="test",
            description="Test tool",
            parameters={"type": "object", "properties": {}},
            version="1.2.3",
        )

        dict_export = spec.to_dict()
        assert dict_export["name"] == "test"
        assert dict_export["version"] == "1.2.3"
        assert "parameters" in dict_export

    def test_from_validated_tool_non_validated_tool_raises_error(self):
        """Test from_validated_tool raises TypeError for non-ValidatedTool (line 201)."""
        import pytest

        class NotAValidatedTool:
            """Not a ValidatedTool."""

            pass

        with pytest.raises(TypeError, match="must be a ValidatedTool subclass"):
            ToolSpec.from_validated_tool(NotAValidatedTool)

    def test_from_validated_tool_with_cacheable_attribute(self):
        """Test from_validated_tool detects _cacheable attribute (line 216)."""

        class CacheableTool(ValidatedTool):
            """A cacheable tool."""

            _cacheable = True

            class Arguments(BaseModel):
                x: int

            class Result(BaseModel):
                result: int

            async def _execute(self, x: int) -> Result:
                return self.Result(result=x)

        spec = ToolSpec.from_validated_tool(CacheableTool)
        assert ToolCapability.CACHEABLE in spec.capabilities

    def test_from_validated_tool_idempotent_detection(self):
        """Test from_validated_tool detects idempotent tools (line 220)."""

        class GetTool(ValidatedTool):
            """Get data tool."""

            class Arguments(BaseModel):
                id: str

            class Result(BaseModel):
                data: str

            async def _execute(self, id: str) -> Result:
                return self.Result(data=f"data-{id}")

        spec = ToolSpec.from_validated_tool(GetTool)
        assert ToolCapability.IDEMPOTENT in spec.capabilities

    def test_from_validated_tool_streaming_detection(self):
        """Test from_validated_tool detects streaming tools (line 226)."""
        from chuk_tool_processor.models.streaming_tool import StreamingTool

        class MyStreamingTool(StreamingTool):
            """A streaming tool."""

            class Arguments(BaseModel):
                query: str

            class Result(BaseModel):
                chunk: str

            async def _stream(self, query: str):
                yield self.Result(chunk="chunk1")

        spec = ToolSpec.from_validated_tool(MyStreamingTool)
        assert ToolCapability.STREAMING in spec.capabilities

    def test_from_function_with_self_parameter(self):
        """Test from_function skips 'self' parameter (line 271)."""

        class MyClass:
            def my_method(self, arg: str) -> str:
                """A method with self."""
                return arg

        obj = MyClass()
        spec = ToolSpec.from_function(obj.my_method)

        # self should not be in parameters
        assert "self" not in spec.parameters["properties"]
        assert "arg" in spec.parameters["properties"]

    def test_from_function_class_method_skips_self(self):
        """Test from_function properly skips self in class methods."""

        class TestClass:
            def instance_method(self, x: int, y: str) -> None:
                """Instance method."""
                pass

        # When we get the method from an instance, it still has self in signature
        spec = ToolSpec.from_function(TestClass.instance_method)

        # Verify self is skipped
        props = spec.parameters["properties"]
        assert "self" not in props
        assert "x" in props
        assert "y" in props

    def test_from_function_with_various_types(self):
        """Test from_function with various type annotations (lines 284-291)."""

        def typed_function(
            s: str,
            i: int,
            f: float,
            b: bool,
            lst: list,
            d: dict,
        ) -> str:
            """Function with various types."""
            return "result"

        spec = ToolSpec.from_function(typed_function)

        props = spec.parameters["properties"]
        assert props["s"]["type"] == "string"
        assert props["i"]["type"] == "integer"
        assert props["f"]["type"] == "number"
        assert props["b"]["type"] == "boolean"
        assert props["lst"]["type"] == "array"
        assert props["d"]["type"] == "object"


class TestToolCapability:
    """Tests for ToolCapability enum."""

    def test_capability_enum_values(self):
        """Test that all capabilities have correct values."""
        assert ToolCapability.STREAMING.value == "streaming"
        assert ToolCapability.CANCELLABLE.value == "cancellable"
        assert ToolCapability.IDEMPOTENT.value == "idempotent"
        assert ToolCapability.CACHEABLE.value == "cacheable"

    def test_capability_comparison(self):
        """Test capability comparison."""
        cap1 = ToolCapability.CACHEABLE
        cap2 = ToolCapability.CACHEABLE
        cap3 = ToolCapability.STREAMING

        assert cap1 == cap2
        assert cap1 != cap3
