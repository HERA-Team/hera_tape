"""test fast archive functionality"""

__author__ = 'dconover@sas.upenn.edu'

from paper_dump import DumpFast

paper_creds = '/root/.my.papertape-prod.cnf'

## add comment
x = DumpFast(paper_creds, debug=True, drive_select=2, disk_queue=False,  debug_threshold=128)
x.batch_size_mb = 5000
x.tape_size = 1536000
x.fast_batch()

