
from paper_mtx import *
from paper_io import *
from paperdata import paperdb
from paper_debug import debug

from random import randint
import os, shutil, sys

class dump:

    def  __init__ (self, debug=False):
        self.mtx_creds = '~/.my.mtx.cnf'
        self.paper_creds = '~/.my.papertape.cnf'
        self.pid = "%0.6d%0.3d" % (os.getpid(),randint(1,999))

        self.queue_size = 0 ## each dump process should write one tape worth of data
        self.batch_size_mb = 12000 ## each dump process 6gb to /dev/shm (two can run at a time)
        self.tape_size = (1.5 * 1000 * 1000) - self.batch_size_mb ## (1.5Tb -1 batch)
        #self.tape_size = 13000
        self.debug = debug(self.pid, debug=debug)

        self.setup_external_modules()


    def setup_external_modules(self):

        ## setup tape library
        self.labeldb = mtxdb(self.mtx_creds, self.pid)

        ## setup paperdb connection
        self.db = paperdb(self.paper_creds, self.pid, debug=True)

        ## setup file access
        self.files = archive(self.pid)

        ## use the pid here to lock changer
        self.tape = changer(self.pid, self.tape_size, debug=True)

    def debug_print(self, debug_output):
        if self.debug == True:
            print('debug:',debug_output)


    def archive_to_tape(self):
        """master method to loop through files to write data to tape"""
        self.queue_pass = 0
        cummulative_catalog = []

        ## get a list of files, transfer to disk, write to tape
        while self.queue_size + self.batch_size_mb < self.tape_size:
            list, list_size = self.get_list(self.batch_size_mb)                  ## get a list of files
            self.files.build_archive(list)                                   ## copy the files to b5, generate a catalog file
            self.files.queue_archive(self.queue_pass, list)         ## pass files to tar on disk with catalog
            self.queue_size += list_size
            self.queue_pass += 1 
            cummulative_catalog.extend(list)
            self.debug_print("q:%s l:%s t:%s" % (self.queue_size, list_size, self.tape_size)) 

        self.files.gen_catalog(self.files.catalog_name,  cummulative_catalog)
        sys.exit()
        self.tar_archive(self.files.catalog_name)

    def get_list(self, limit=7500):

        ## get a 7.5 gb list of files to transfer
        new_list, list_size = self.db.get_new(limit)
        self.debug_print (list_size)
        self.db.claim_files(1, new_list)
        return new_list, list_size

    def tar_archive(self, catalog_file):

        ## select ids
        tape_label_ids = self.labeldb.select_ids()
        self.labeldb.claim_ids(tape_label_ids)

        ## load up a fresh set of tapes
        self.tape.load_tape_pair(tape_label_ids)

        ## tar files to tape
        self.tape.prep_tape()
        for  _pass in range(self.queue_pass):
            self.tape.write(_pass)
            
        self.tape.unload_tape_pair()

        ## write tape locations
        self.db.write_tape_locations(','.join(tape_label_ids))


 

