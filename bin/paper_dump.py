"""Dump files to tape

    The paperdata files located on disk and catalogued in te papaerdata db can
be dumped to tape using this class.
"""

from paper_mtx import Changer, MtxDB
from paper_io import Archive
from paperdata import PaperDB
from paper_debug import Debug

from random import randint
import os 

class Dump:
    "Coordinate a dump to tape based on deletable files in database"

    def  __init__(self, debug=False, pid=None, drive_select=2):
        "initialize"

        self.pid = "%0.6d%0.3d" % (os.getpid(), randint(1, 999)) if pid == None else pid
        self.debug = Debug(self.pid, debug=debug)

        self.mtx_creds = '~/.my.mtx.cnf'
        self.paper_creds = '~/.my.papertape.cnf'

        ## each dump process 6gb to /dev/shm (two at a time)
        self.batch_size_mb = 12000

        ## (1.5Tb -1 batch)
        self.tape_size = (1.5 * 1000 * 1000) - self.batch_size_mb
        #self.tape_size = 13000

        ## setup PaperDB connection
        self.paperdb = PaperDB(self.paper_creds, self.pid, debug=True)

        ## setup tape library
        self.labeldb = MtxDB(self.mtx_creds, self.pid)

        ## setup file access
        self.files = Archive(self.pid)

        ## use the pid here to lock changer
        self.tape = Changer(self.pid, self.tape_size, debug=True, drive_select=drive_select)

        self.dump_list = []
        self.queue_pass = 0
        self.queue_size = 0 ## each dump process should write one tape worth of data

    def archive_to_tape(self):
        """master method to loop through files to write data to tape"""
        cumulative_catalog = []

        ## get a list of files, transfer to disk, write to tape
        while self.queue_size + self.batch_size_mb < self.tape_size:

            ## get a list of files
            file_list, list_size = self.get_list(self.batch_size_mb)

            if file_list:
                ## copy files to b5, gen catalog file
                self.files.build_archive(file_list)

                ## files to tar on disk with catalog
                self.files.queue_archive(self.queue_pass, file_list)
                self.queue_size += list_size
                self.queue_pass += 1
                cumulative_catalog.extend([self.queue_pass, file_list])
                self.debug.print("q:%s l:%s t:%s" % (self.queue_size, list_size, self.tape_size))

        self.files.gen_final_catalog(self.files.catalog_name, cumulative_catalog)
        self.tar_archive(cumulative_catalog, self.files.catalog_name)

    def test_build_archive(self):
        """master method to loop through files to write data to tape"""
        cumulative_catalog = []

        ## get a list of files, transfer to disk, write to tape
        while self.queue_size + self.batch_size_mb < self.tape_size:

            ## get a list of files
            file_list, list_size = self.get_list(self.batch_size_mb)

            if file_list:
                ## copy files to b5, gen catalog file
                self.files.build_archive(file_list)

                ## files to tar on disk with catalog
                self.files.queue_archive(self.queue_pass, file_list)
                self.queue_size += list_size
                self.queue_pass += 1
                cumulative_catalog.extend([self.queue_pass, file_list])
                self.debug.print("q:%s l:%s t:%s" % (self.queue_size, list_size, self.tape_size))

        self.files.gen_final_catalog(self.files.catalog_name, cumulative_catalog)


    def manual_to_tape(self, queue_pass, cumulative_catalog):
        """if the dump is interrupted, run the files to tape for the current_pid.

        This works only if you initialize your dump object with pid=$previous_run_pid."""
        self.queue_pass = queue_pass
        self.debug.print("manual vars - qp:%s, cn:%s" % (queue_pass, self.files.catalog_name))
        self.tar_archive(cumulative_catalog, self.files.catalog_name)
        self.debug.print("manual to tape complete")

    def get_list(self, limit=7500):
        "get a list less than limit size"

        ## get a 7.5 gb list of files to transfer
        self.dump_list, list_size = self.paperdb.get_new(limit)
        if self.dump_list:
            self.debug.print(str(list_size))
            self.paperdb.claim_files(1, self.dump_list)
        return self.dump_list, list_size

    def tar_archive(self, catalog_file):
        "send archives to tape drive pair using tar"

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
        self.paperdb.write_tape_locations(self.files.catalog_list, ','.join(tape_label_ids))

    def tar_archive_single(self, catalog_file):
        "send archives to single tape drive using tar"

        ## select ids
        tape_label_ids = self.labeldb.select_ids()
        self.labeldb.claim_ids(tape_label_ids)

        ## load up a fresh set of tapes
        for label_id in tape_label_ids:
            self.tape.load_tape_drive(label_id)

            ## tar files to tape
            self.tape.prep_tape(catalog_file)

            for _pass in range(self.queue_pass):
                self.debug.print('sending tar to single drive', str(_pass))
                self.tape.write(_pass)

            self.tape.unload_tape_drive(label_id)

        self.paperdb.write_tape_locations(self.files.catalog_list, ','.join(tape_label_ids))
        self.paperdb.status = 0


    def __del__(self):
        if self.paperdb.status and self.dump_list:
            self.paperdb.unclaim_files(1, self.dump_list)


