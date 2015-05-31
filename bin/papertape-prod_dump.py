"""test fast archive functionality"""

__author__ = 'dconover@sas.upenn.edu'

from paper_dump import TestDump

paper_creds = '/root/.my.papertape-prod.cnf'


x = TestDump(paper_creds, debug=True, drive_select=2, disk_queue=False,  debug_threshold=128)
x.batch_size_mb = 5000
x.tape_size = 1536000
x.test_fast_archive()

