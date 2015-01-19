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
    tape_self_check = 8
    dump_verify_pid = 9
    dump_verify_item_index = 10
    dump_verify_catalog = 11
    dump_verify_md5_dict = 12
    tar_archive_single_dump_verify = 13
    tar_archive_single_log_label_ids = 14
    write_tape_index_mysql = 15
    tape_archive_md5_mismatch = 16
    date_ids_mysql = 17
    UNKNOWN = 9999
