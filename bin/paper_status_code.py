"""Dump status codes

   Various status codes that may be used to indicate the result of an operation.
"""
from enum import Enum, unique

@unique
class StatusCode(Enum):
    OK      = 0
    WARNING = 1
    ERROR   = 2
    db_connect = 3
    file_missing = 4
    md5_mismatch = 5
    truncated_tape = 6
    db_credentials = 7
    taoe_self_check = 8

    UNKNOWN = 9999
