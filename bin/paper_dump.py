
from paper_mtx import *
from paperdata import paperdb

from random import randint
import os

mtx_creds = '~/.my.mtx.cnf'
paper_creds = '~/.my.papertape.cnf'
pid = "%0.6d%0.3d" % (os.getpid(),randint(1,999))

## setup tape library
labeldb = mtxdb(mtx_creds, pid)

## setup paperdb connection
db = paperdb(paper_creds, pid)

new_list = db.get_new(50)
db.claim_files(1, new_list)

## copy files to /dev/shm
files.copy(new_list)
## md5sumfiles
files.md5sum(new_list)
## tar files to tape

## write tape locations
db.write_tape_locations()


