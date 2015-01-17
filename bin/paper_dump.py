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
        self.tape_index = 0
        self.tape_used_size = 0 ## each dump process should write one tape worth of data

    def archive_to_tape(self):
        """master method to loop through files to write data to tape"""

        ## get a list of files, transfer to disk, write to tape
        while self.tape_used_size + self.batch_size_mb < self.tape_size:

            ## get a list of files
            archive_list, archive_size = self.get_list(self.batch_size_mb)

            if archive_list:
                ## copy files to b5, gen catalog file
                self.files.build_archive(archive_list)

                ## files to tar on disk with catalog
                self.files.queue_archive(self.tape_index, archive_list)

                ## Files in these lists should be identical, but catalog_list has extra data
                ## catalog_list: [[0, 1, 'test:/testdata/testdir'], [0, 2, 'test:/testdata/testdir2'], ... ]
                ## archive_list: ['test:/testdata/testdir', 'test:/testdata/testdir2', ... ]
                self.debug.output('catalog_list - %s' % self.files.catalog_list)
                self.debug.output('list - %s' % archive_list)

                ## queue archive does the job of making the catalog_list we need to update the tape_list
                self.files.tape_list.extend(self.files.catalog_list)
                self.debug.output("q:%s l:%s t:%s" % (self.tape_used_size, archive_size, self.tape_size))

                ## add archive_size to current tape_used_size
                self.tape_used_size += archive_size
                self.tape_index += 1

            else:
                self.debug.output('file list empty')
                break

        if self.tape_used_size > 0:
            self.debug.output('sending queued files to tar - %s, %s' % (len(self.files.tape_list), self.files.tape_list))
            self.files.gen_final_catalog(self.files.catalog_name, self.files.tape_list, self.paperdb.file_md5_dict)
            if self.drive_select == 2:
                ## use two tape drives to write data at the same time
                self.debug.output('using two drives')
                self.tar_archive(self.files.catalog_name)
            else:
                ## use one drive to write to two tapes serially
                self.debug.output('using one drive')
                self.tar_archive_single(self.files.catalog_name)

        else:
            ## no files found
            self.debug.output('Abort - no files found')

    def get_list(self, limit=7500, regex=False, pid=False, claim=True):
        """get a list less than limit size"""

        ## get a 7.5 gb list of files to transfer
        self.dump_list, list_size = self.paperdb.get_new(limit, regex=regex, pid=pid)

        ## claim the files so other jobs can request different files
        if self.dump_list and claim:
            self.debug.output(str(list_size))
            self.paperdb.claim_files(1, self.dump_list)
        return self.dump_list, list_size

    def tar_archive_single(self, catalog_file):
        """send archives to single tape drive using tar"""

        ## select ids
        tape_label_ids = self.labeldb.select_ids()
        self.labeldb.claim_ids(tape_label_ids)

        ## load up a fresh set of tapes
        for label_id in tape_label_ids:
            self.debug.output('load tape', label_id, debug_level=128)
            self.tape.load_tape_drive(label_id)

            ## tar files to tape
            self.debug.output('prep tape', debug_level=128)
            self.tape.prep_tape(catalog_file)

            for tape_index in range(self.tape_index):
                self.debug.output('sending tar to single drive', str(tape_index), debug_level=225)
                try:
                    self.tape.write(tape_index)
                except:
                    self.debug.output('tape write fail')
                    break

            if not self.dump_verify(label_id, self.files.tape_list):
                ## TODO(dconover): real exit from further processing
                self.debug.output('Fail: dump_verify')
                break

            self.debug.output('unloading drive', label_id, debug_level=128)
            self.tape.unload_tape_drive(label_id)

        self.debug.output('write tape location')
        self.files.save_tape_ids(','.join(tape_label_ids))
        self.paperdb.write_tape_index(self.files.tape_list, ','.join(tape_label_ids))
        self.labeldb.date_ids(tape_label_ids)

        ## TODO(dconover): cleanup queued files via self.files.status
        ## TODO(dconover): use the output status to cleanup claimed files in the db
        self.paperdb.status = 0

    def dump_verify(self, tape_id, tape_list):
        """take the tape_id and run a self check,
        then confirm the tape_list matches"""

        ## run a tape_self_check
        status, item_index, catalog_list, md5_dict, tape_pid = self.tape_self_check(tape_id)

        ## take output from tape_self_check and compare against current dump
        if status:

            self.debug.output('confirming %s' % "item_index")
            if self.files.item_index != int(item_index):
                self.debug.output("%s mismatch: %s, %s" % ("item_count", self.files.item_index, item_index ))

            self.debug.output('confirming %s' % "catalog")
            if self.files.tape_list != catalog_list:
                self.debug.output("%s mismatch: %s, %s" % ("catalog", self.files.tape_list, catalog_list ))

            self.debug.output('confirming %s' % "md5_dict")
            if self.paperdb.file_md5_dict != md5_dict:
                self.debug.output("%s mismatch: %s, %s" % ("md5_dict", self.pid, tape_pid ))

            self.debug.output('confirming %s' % "pid")
            if self.pid != str(tape_pid):
                self.debug.output("%s mismatch: %s, %s" % ("pid", self.pid, tape_pid ))
        else:
            self.debug.output('Fail: tape_self_check status: %s' % status)

        return status


    def tape_self_check(self, tape_id):
        """process to take a tape and run integrity check without reference to external database"""

        ## assume there is a problem
        status = False

        ## load the tape if necessary
        self.tape.load_tape_drive(tape_id)

        ## read tape_catalog as list
        self.debug.output('read catalog from tape: %s' % tape_id)
        first_block = self.tape.read_tape_catalog(tape_id)

        ## parse the catalog_list
        ## build an file_md5_dict
        item_index, catalog_list, md5_dict, tape_pid = self.files.final_from_file(catalog=first_block)

        ## last item_index = (first value of the last catalog entry)
        #item_index = catalog_list[-1][0] + 1

        status, reference = self.tape.tape_archive_md5(tape_id, tape_pid, catalog_list, md5_dict)
        if not status:
            self.debug.output("tape failed md5 inspection at index: %s" % reference)

        return status, item_index, catalog_list, md5_dict, tape_pid


    def test_build_archive(self, regex=False):
        """master method to loop through files to write data to tape"""

        self.batch_files(queue=True, regex=regex)
        self.files.gen_final_catalog(self.files.catalog_name, self.files.catalog_list, self.paperdb.file_md5_dict)

    def tar_archive(self, catalog_file):
        """send archives to tape drive pair using tar"""

        ## select ids
        tape_label_ids = self.labeldb.select_ids()
        self.labeldb.claim_ids(tape_label_ids)

        ## load up a fresh set of tapes
        self.tape.load_tape_pair(tape_label_ids)

        ## tar files to tape
        self.tape.prep_tape(catalog_file)
        for tar_index in range(self.tape_index):
            self.debug.output('sending to tape file - %s' % str(tar_index))
            try:
                self.tape.write(tar_index)
            except:
                self.debug.output('tape writing exception')
                break

        self.tape.unload_tape_pair()

        ## write tape locations
        self.debug.output('writing tape_indexes - %s' % self.files.tape_list)
        self.paperdb.write_tape_index(self.files.tape_list, ','.join(tape_label_ids))
        self.debug.output('updating mtx.ids with date')
        self.labeldb.date_ids(tape_label_ids)
        self.paperdb.status = 0

    def tar_archive_fast_single(self, catalog_file):
        """Archive files directly to tape using only a single drive to write 2 tapes"""

        ## select ids
        tape_label_ids = self.labeldb.select_ids()
        self.labeldb.claim_ids(tape_label_ids)

        ## load up a fresh set of tapes
        for label_id in tape_label_ids:
            self.debug.output('printing to label_id: %s' % label_id)
            self.tape.load_tape_drive(label_id)

            ## tar files to tape
            self.tape.prep_tape(catalog_file)

            ## testing 201401123
            for index_int in range(self.tape_index):
                self.debug.output('sending tar to single drive:', label_id, str(index_int))
                self.tape.write(index_int)

            self.tape.unload_tape_drive(label_id)

        self.debug.output('writing tape_indexes')
        self.paperdb.write_tape_index(self.files.catalog_list, ','.join(tape_label_ids))
        self.paperdb.status = 0

    def batch_files(self, queue=False, regex=False, pid=False, claim=True):
        """populate self.catalog_list; transfer files to shm"""
        ## get files in batch size chunks
        while self.tape_used_size + self.batch_size_mb < self.tape_size:

            ## get a list of files smaller than our batch size
            file_list, list_size = self.get_list(self.batch_size_mb, regex=regex, pid=pid, claim=claim)
            self.debug.output("list_size %s" % list_size)

            if file_list:
                ## copy files to b5, gen catalog file
                if queue:
                    self.files.build_archive(file_list)
                    self.files.queue_archive(self.tape_index, file_list)

                self.tape_used_size += list_size
                self.tape_index += 1
                self.files.catalog_list.append([self.tape_index, file_list])
                self.debug.output("queue list: %s, len(catalog_list): %s" % (str(self.tape_index), len(self.files.catalog_list)))

            else:
                self.debug.output('file list empty')
                break

        self.debug.output("complete:%s:%s:%s:%s" % (queue, regex, pid, claim))
        return True if self.tape_used_size != 0 else False

    def test_fast_archive(self):
        """skip tar of local archive on disk

           send files to two tapes using a single drive."""
        if self.batch_files():
            self.debug.output('found %s files' % len(self.files.catalog_list))
            self.files.gen_final_catalog(self.files.catalog_name, self.files.catalog_list, self.paperdb.file_md5_dict)
            self.tar_archive_fast_single(self.files.catalog_name)
        else:
            self.debug.output("no files batched")

    def manual_write_tape_location(self):
        """on a tape dump that fails after writing to tape, but before writing
        locations to tape, use this to resume writing locations to tape.

        The dump must be initialized with the pid of the queued files.
        """

        self.tape_index, catalog, md5_dict, pid = self.files.final_from_file()
        self.tape_ids = self.files.tape_ids_from_file()
        self.debug.output('write tape location', ','.join(self.tape_ids))
        self.paperdb.write_tape_index(self.files.catalog_list, ','.join(self.tape_ids))
        self.paperdb.status = 0

    def manual_resume_to_tape(self):
        """read in the cumulative list from file and send to tape"""

        self.tape_index, catalog, md5_dict, pid = self.files.final_from_file()
        self.debug.output('pass: %s' % self.tape_index)
        self.manual_to_tape(self.tape_index, catalog)

    def manual_to_tape(self, tape_index, cumulative_list):
        """if the dump is interrupted, run the files to tape for the current_pid.

        This only works if you initialize your dump object with pid=$previous_run_pid."""
        self.tape_index = tape_index
        self.debug.output("manual vars - qp:%s, cn:%s" % (tape_index, cumulative_list))
        self.tar_archive_single(self.files.catalog_name)
        self.debug.output("manual to tape complete")
