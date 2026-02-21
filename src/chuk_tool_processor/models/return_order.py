# chuk_tool_processor/models/return_order.py
"""
Return order enum for tool execution results.
"""

from enum import StrEnum


class ReturnOrder(StrEnum):
    """
    Specifies the order in which tool results should be returned.

    Attributes:
        COMPLETION: Return results as each tool completes (faster tools return first)
        SUBMISSION: Return results in the same order as the original call list
    """

    COMPLETION = "completion"
    SUBMISSION = "submission"
