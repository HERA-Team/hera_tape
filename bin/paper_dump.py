
from paper_mtx import *
from paper_io import *
from paperdata import paperdb
from paper_debug import Debug

from random import randint
import os, shutil, sys

class Dump:

    def  __init__ (self, debug=False, pid=None):
        self.mtx_creds = '~/.my.mtx.cnf'
        self.paper_creds = '~/.my.papertape.cnf'
        self.pid = "%0.6d%0.3d" % (os.getpid(),randint(1,999)) if pid==None else pid

        self.queue_size = 0 ## each dump process should write one tape worth of data
        self.batch_size_mb = 12000 ## each dump process 6gb to /dev/shm (two can run at a time)
        self.tape_size = (1.5 * 1000 * 1000) - self.batch_size_mb ## (1.5Tb -1 batch)
        #self.tape_size = 13000
        self.debug = Debug(self.pid, debug=debug)

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

    def archive_to_tape(self):
        """master method to loop through files to write data to tape"""
        self.queue_pass = 0
        cumulative_catalog = []

        ## get a list of files, transfer to disk, write to tape
        while self.queue_size + self.batch_size_mb < self.tape_size:
            list, list_size = self.get_list(self.batch_size_mb)                  ## get a list of files
            if list: 
                self.files.build_archive(list)                                   ## copy the files to b5, generate a catalog file
                self.files.queue_archive(self.queue_pass, list)         ## pass files to tar on disk with catalog
                self.queue_size += list_size
                self.queue_pass += 1 
                cumulative_catalog.extend([self.queue_pass, list])
                self.debug.print("q:%s l:%s t:%s" % (self.queue_size, list_size, self.tape_size)) 

        self.files.gen_final_catalog(self.files.catalog_name,  cumulative_catalog)
        self.tar_archive(cumulative_catalog, self.files.catalog_name)

    def manual_to_tape(self, queue_pass, cumulative_catalog):
        """if the dump is interrupted, run the files to tape for the current_pid.

        This works only if you initialize your dump object with pid=$previous_run_pid."""
        self.queue_pass = queue_pass
        self.debug.print("manual to tape with vars - qp:%s, cn:%s" % (queue_pass, self.files.catalog_name))
        self.tar_archive(cumulative_catalog,self.files.catalog_name)
        self.debug.print("manual to tape complete")
       
    def get_list(self, limit=7500):

        ## get a 7.5 gb list of files to transfer
        new_list, list_size = self.db.get_new(limit)
        if new_list: 
            self.debug.print (str(list_size))
            self.db.claim_files(1, new_list)
        return new_list, list_size

    def tar_archive(self, cumulative_list, catalog_file):

        ## select ids
        tape_label_ids = self.labeldb.select_ids()
        self.labeldb.claim_ids(tape_label_ids)

        ## load up a fresh set of tapes
        self.tape.load_tape_pair(tape_label_ids)

        ## tar files to tape
        self.tape.prep_tape(catalog_file)
        for  _pass in range(self.queue_pass):
            self.debug.print('sending to tape', str(_pass))
            self.tape.write(_pass)
            
        self.tape.unload_tape_pair()

        ## write tape locations
        self.db.write_tape_location(cumulative_list, ','.join(tape_label_ids))


 

