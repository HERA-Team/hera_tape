
from paper_mtx import *
from paper_io import *
from paperdata import paperdb

from random import randint
import os, shutil

class dump:

    def  __init__ (self):
        self.mtx_creds = '~/.my.mtx.cnf'
        self.paper_creds = '~/.my.papertape.cnf'
        self.pid = "%0.6d%0.3d" % (os.getpid(),randint(1,999))

        self.setup_external_modules()


    def setup_external_modules(self):

        ## setup tape library
        self.labeldb = mtxdb(self.mtx_creds, self.pid)

        ## setup paperdb connection
        self.db = paperdb(self.paper_creds, self.pid)

        ## setup file access
        self.files = archive(self.pid)

        ## use the pid here to lock changer
        self.tape = changer(self.pid)


    def get_list(self, limit=7500):

        ## get a 7.5 gb list of files to transfer
        new_list = self.db.get_new(limit)
        self.db.claim_files(1, new_list)
        return new_list

    def prep_archive(self, new_list):
        ## copy files to /dev/shm and md5sumfiles
        self.files.build_archive(new_list)

        ## debug exit
        os.exit()

        ## tar files to tape
        tape_location = tape.write(files.archive)

        ## write tape locations
        db.write_tape_locations(tape_location)

    def write_catalog(self):
        """write a catalog file"""
        pass


