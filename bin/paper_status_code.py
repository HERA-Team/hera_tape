"""Dump status codes

   Various status codes that may be used to indicate the result of an operation.
"""
from enum import Enum, unique

@unique
class StatusCode(Enum):
    OK      = 0
    WARNING = 1
    ERROR   = 2
    UNKNOWN = 9999
