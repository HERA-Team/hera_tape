"""Dump files to tape

    The paperdata files located on disk and catalogued in te paperdata db can
be dumped to tape using this class.
"""

__version__ = 20150103

from paper_mtx import Changer, MtxDB
from paper_io import Archive
from paper_db import PaperDB
from paper_debug import Debug

from random import randint
import os

class Dump:
    """Coordinate a dump to tape based on deletable files in database"""

    def  __init__(self, credentials, debug=False, pid=None, drive_select=2, debug_threshold=255):
        """initialize"""

        self.version = __version__
        self.pid = "%0.6d%0.3d" % (os.getpid(), randint(1, 999)) if pid is None else pid
        self.debug = Debug(self.pid, debug=debug, debug_threshold=debug_threshold)

        self.mtx_creds = '~/.my.mtx.cnf'
        self.paper_creds = credentials

        self.tape_ids = ''

        ## each dump process 6gb to /dev/shm (two at a time)
        self.batch_size_mb = 12000

        ## (1.5Tb -1 batch)
        self.tape_size = (1.5 * 1000 * 1000) - self.batch_size_mb
        #self.tape_size = 13000

        ## setup PaperDB connection
        self.paperdb = PaperDB(self.version, self.paper_creds, self.pid, debug=True, debug_threshold=debug_threshold)

        ## setup tape library
        self.labeldb = MtxDB(self.version, self.mtx_creds, self.pid, debug=debug, debug_threshold=debug_threshold)

        ## setup file access
        self.files = Archive(self.version, self.pid, debug=debug, debug_threshold=debug_threshold)

        ## use the pid here to lock changer
        self.drive_select = drive_select
        self.tape = Changer(self.version, self.pid, self.tape_size, debug=True, drive_select=drive_select, debug_threshold=debug_threshold)

        self.dump_list = []
        self.queue_pass = 0
        self.queue_size = 0 ## each dump process should write one tape worth of data

    def archive_to_tape(self):
        """master method to loop through files to write data to tape"""

        ## get a list of files, transfer to disk, write to tape
        while self.queue_size + self.batch_size_mb < self.tape_size:

            ## get a list of files
            file_list, list_size = self.get_list(self.batch_size_mb)

            if file_list:
                ## copy files to b5, gen catalog file
                self.files.build_archive(file_list)

                ## files to tar on disk with catalog
                self.files.queue_archive(self.queue_pass, file_list)

                self.debug.print('catalog_list - %s' % self.files.catalog_list)
                self.debug.print('list - %s' % file_list)
                ## queue archive does the job of making the working list we need to update the cumulative_list
                self.files.cumulative_list.extend(self.files.catalog_list)
                self.debug.print("q:%s l:%s t:%s" % (self.queue_size, list_size, self.tape_size))

                self.queue_size += list_size
                self.queue_pass += 1

            else:
                self.debug.print('file list empty')
                break

        if self.queue_size > 0:
            self.debug.print('sending queued files to tar - %s, %s' % (len(self.files.cumulative_list), self.files.cumulative_list))
            self.files.gen_final_catalog(self.files.catalog_name, self.files.cumulative_list, self.paperdb.file_md5_dict)
            if self.drive_select == 2:
                self.tar_archive(self.files.catalog_name)
            else:
                self.tar_archive_single(self.files.catalog_name)

        else:
            self.debug.print('Abort - no files found')

    def verify_tape(self, catalog_list, tape_id):
        """given a list of files and a tape_id check the integrity of the tape

    1. tape write count - the number of files ("chunks") on tape
    2. tape catalog - file names, md5 hashes, and positional indexes are written
       to the first 32kb block of tape
    4. tar catalog - paths are read from the catalog on each tar "chunk"
    5. tar table - paths are read from the actual tar file containing data
    6. block md5sum - files are streamed to a hashing algorithm directly from
       tape but never written to disk
    7. file md5sum - files are written to disk then an md5sum is calculated

        """

        pass

    def test_build_archive(self, regex=False):
        """master method to loop through files to write data to tape"""

        self.batch_files(queue=True, regex=regex)
        self.files.gen_final_catalog(self.files.catalog_name, self.files.catalog_list, self.paperdb.file_md5_dict)

    def test_shm_archive(self, shm_pid):
        """send failed files stored in /papertape/shm/$shm_pid to tape

        useful when build_archive is invoked without queue_archive

        :param shm_pid: str
        """
        self.batch_files(pid=shm_pid, claim=False)
        for file_info in self.files.catalog_list:
            print(file_info)

    def batch_files(self, queue=False, regex=False, pid=False, claim=True):
        """populate self.catalog_list; transfer files to shm"""
        ## get files in batch size chunks
        while self.queue_size + self.batch_size_mb < self.tape_size:

            ## get a list of files smaller than our batch size
            file_list, list_size = self.get_list(self.batch_size_mb, regex=regex, pid=pid, claim=claim)
            self.debug.print("list_size %s" % list_size)

            if file_list:
                ## copy files to b5, gen catalog file
                if queue:
                    self.files.build_archive(file_list)
                    self.files.queue_archive(self.queue_pass, file_list)

                self.queue_size += list_size
                self.queue_pass += 1
                self.files.catalog_list.append([self.queue_pass, file_list])
                self.debug.print("queue list: %s, len(catalog_list): %s" % (str(self.queue_pass), len(self.files.catalog_list)))

            else:
                self.debug.print('file list empty')
                break

        self.debug.print("complete:%s:%s:%s:%s" % (queue, regex, pid, claim))
        return True if self.queue_size != 0 else False

    def test_fast_archive(self):
        """skip tar of local archive on disk

           send files to two tapes using a single drive."""
        if self.batch_files():
            self.debug.print('found %s files' % len(self.files.catalog_list))
            self.files.gen_final_catalog(self.files.catalog_name, self.files.catalog_list, self.paperdb.file_md5_dict)
            self.tar_archive_fast_single(self.files.catalog_name)
        else:
            self.debug.print("no files batched")

    def manual_resume_to_tape(self):
        """read in the cumulative list from file and send to tape"""

        self.queue_pass, catalog, md5_dict, pid = self.files.final_from_file()
        self.debug.print('pass: %s' % self.queue_pass)
        self.manual_to_tape(self.queue_pass, catalog)

    def manual_write_tape_location(self):
        """on a tape dump that fails after writing to tape, but before writing
        locations to tape, use this to resume writing locations to tape.

        The dump must be initialized with the pid of the queued files.
        """

        self.queue_pass, catalog, md5_dict, pid = self.files.final_from_file()
        self.tape_ids = self.files.tape_ids_from_file()
        self.debug.print('write tape location', ','.join(self.tape_ids))
        self.paperdb.write_tape_index(self.files.catalog_list, ','.join(self.tape_ids))
        self.paperdb.status = 0

    def manual_to_tape(self, queue_pass, cumulative_list):
        """if the dump is interrupted, run the files to tape for the current_pid.

        This only works if you initialize your dump object with pid=$previous_run_pid."""
        self.queue_pass = queue_pass
        self.debug.print("manual vars - qp:%s, cn:%s" % (queue_pass, cumulative_list))
        self.tar_archive_single(self.files.catalog_name)
        self.debug.print("manual to tape complete")

    def get_list(self, limit=7500, regex=False, pid=False, claim=True):
        """get a list less than limit size"""

        ## get a 7.5 gb list of files to transfer
        self.dump_list, list_size = self.paperdb.get_new(limit, regex=regex, pid=pid)
        if self.dump_list and claim:
            self.debug.print(str(list_size))
            self.paperdb.claim_files(1, self.dump_list)
        return self.dump_list, list_size

    def tar_archive(self, catalog_file):
        """send archives to tape drive pair using tar"""

        ## select ids
        tape_label_ids = self.labeldb.select_ids()
        self.labeldb.claim_ids(tape_label_ids)

        ## load up a fresh set of tapes
        self.tape.load_tape_pair(tape_label_ids)

        ## tar files to tape
        self.tape.prep_tape(catalog_file)
        for tar_index in range(self.queue_pass):
            self.debug.print('sending to tape file - %s' % str(tar_index))
            try:
                self.tape.write(tar_index)
            except:
                self.debug.print('tape writing exception')
                break

        self.tape.unload_tape_pair()

        ## write tape locations
        self.debug.print('writing tape_indexes - %s' % self.files.cumulative_list)
        self.paperdb.write_tape_index(self.files.cumulative_list, ','.join(tape_label_ids))
        self.debug.print('updating mtx.ids with date')
        self.labeldb.date_ids(tape_label_ids)
        self.paperdb.status = 0

    def tar_archive_fast_single(self, catalog_file):
        """Archive files directly to tape using only a single drive to write 2 tapes"""

        ## select ids
        tape_label_ids = self.labeldb.select_ids()
        self.labeldb.claim_ids(tape_label_ids)

        ## load up a fresh set of tapes
        for label_id in tape_label_ids:
            self.debug.print('printing to label_id: %s' % label_id)
            self.tape.load_tape_drive(label_id)

            ## tar files to tape
            self.tape.prep_tape(catalog_file)

            ## testing 201401123
            for _pass in range(self.queue_pass):
                self.debug.print('sending tar to single drive:', label_id, str(_pass))
                self.tape.write(_pass)

            self.tape.unload_tape_drive(label_id)

        self.debug.print('writing tape_indexes')
        self.paperdb.write_tape_index(self.files.catalog_list, ','.join(tape_label_ids))
        ## verify dumped files are on tape
        self.dump_verify(tape_label_ids)
        self.paperdb.status = 0

    def tar_archive_single(self, catalog_file):
        """send archives to single tape drive using tar"""

        ## select ids
        tape_label_ids = self.labeldb.select_ids()
        self.labeldb.claim_ids(tape_label_ids)

        ## load up a fresh set of tapes
        for label_id in tape_label_ids:
            self.debug.print('load tape', label_id, debug_level=128)
            self.tape.load_tape_drive(label_id)

            ## tar files to tape
            self.debug.print('prep tape', debug_level=128)
            self.tape.prep_tape(catalog_file)

            for tar_index in range(self.queue_pass):
                self.debug.print('sending tar to single drive', str(tar_index), debug_level=225)
                try:
                    self.tape.write(tar_index)
                    self.tape_self_check(tape_label_ids)
                except:
                    break

            ## verify dumped files are on tape
            self.tape_self_check(label_id)
            self.debug.print('unloading drive', label_id, debug_level=128)
            self.tape.unload_tape_drive(label_id)

        self.debug.print('write tape location',  )
        self.paperdb.write_tape_index(self.files.cumulative_list, ','.join(tape_label_ids))
        self.labeldb.date_ids(tape_label_ids)
        self.paperdb.status = 0

    def tape_self_check(self, tape_id):
        """process to take a tape and run integrity check without reference to external database"""

        ## assume there is a problem
        status = False

        ## read tape_catalog as list
        first_block = self.tape.read_tape_catalog(tape_id)

        ## parse the catalog_list
        ## build an file_md5_dict
        item_index, catalog_list, md5_dict, pid = self.io.final_from_file(catalog=first_block)

        ## last tape index is the first value of the last catalog entry
        tape_index = catalog_list[-1][0]
        ## count the number of files_on_tape
        count = self.tape.count_files()

        ## confirm that the largest tape_index in the tape_catalog matches files_on_tape
        if count != tape_index:
             self.debug.print('missing files on tape')

        self.debug.print('tape_index matches catalog entries')
        ## confirm that the md5sum from a random data_file in each archive matches file_md5_dict entry
        ## for each tape_index, select a random file_index and run block md5sum on the data file
        return status, item_index, self.catalog_list, md5_dict, pid

                                                                                                                                                                                                                                                                    
                                                                                                                                                                                                                                                                    
    def dump_verify(self, tape_label_ids):
        """take an existing tape run and verify that the tape contents match"""
