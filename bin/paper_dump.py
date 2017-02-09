"""Dump files to tape

    The paperdata files located on disk and catalogued in the paperdata db can
be dumped to tape using this class.
"""

__author__ = 'dconover@sas.upenn.edu'
__version__ = 20170203

from threading import Thread
from random import randint
from os import getpid
from sys import exit

from enum import Enum, unique

from paper_mtx import Changer, MtxDB
from paper_io import Archive
from paper_db import PaperDB
#from paper_db import TestPaperDB
from paper_debug import Debug
from paper_status_code import StatusCode


class Dump(object):
    """Coordinate a dump to tape based on deletable files in database"""

    def  __init__(self, credentials='/papertape/etc/.my.papertape-test.cnf', mtx_credentials='home2/obs/.my.mtx.cnf', debug=False, pid=None, disk_queue=True, drive_select=2, debug_threshold=255):
        """initialize"""

        self.version = __version__
        self.pid = "%0.6d%0.3d" % (getpid(), randint(1, 999)) if pid is None else pid
        self.debug = Debug(self.pid, debug=debug, debug_threshold=debug_threshold)

        self.status_code = StatusCode
        self.mtx_creds = mtx_credentials
        self.debug.output(credentials)
        self.paper_creds = credentials

        self.tape_ids = ''

        ## each dump process 6gb to /dev/shm (two at a time)
        self.batch_size_mb = 12000

        ## (1.5Tb -1 batch)
        self.tape_size = (1.5 * 1000 * 1000) - self.batch_size_mb
        #self.tape_size = 13000

        ## setup PaperDB connection
        self.paperdb = PaperDB(self.version, self.paper_creds, self.pid, debug=True, debug_threshold=debug_threshold)
        ## test database
        #self.paperdb = TestPaperDB(self.version, self.paper_creds, self.pid, debug=True, debug_threshold=debug_threshold)
        ## reload test data
        #self.paperdb.load_sample_data()

        ## setup tape library
        self.labeldb = MtxDB(self.version, self.mtx_creds, self.pid, debug=debug, debug_threshold=debug_threshold)

        ## setup file access
        self.files = Archive(self.version, self.pid, debug=debug, debug_threshold=debug_threshold)

        ## use the pid here to lock changer
        self.drive_select = drive_select
        self.tape = Changer(self.version, self.pid, self.tape_size, debug=True, drive_select=drive_select, disk_queue=disk_queue, debug_threshold=debug_threshold)

        self.dump_list = []
        self.tape_index = 0
        self.tape_used_size = 0 ## each dump process should write one tape worth of data
        self.dump_state_code = DumpStateCode
        self.dump_state = self.dump_state_code.initialize

    def archive_to_tape(self):
        """master method to loop through files to write data to tape"""

        ## get a file_list of files, transfer to disk, write to tape
        while self.tape_used_size + self.batch_size_mb < self.tape_size:

            ## get a file_list of files to dump
            archive_list, archive_size = self.get_list(self.batch_size_mb)

            if archive_list:
                try:
                    ## copy files to b5, gen catalog file
                    self.files.build_archive(archive_list)

                    ## files to tar on disk with catalog
                    self.files.queue_archive(self.tape_index, archive_list)

                    ## mark where we are
                    self.dump_state = self.dump_state_code.dump_queue

                except Exception as error:
                    self.debug.output('archive build/queue error {}'.format(error))
                    self.close_dump()

                ## Files in these lists should be identical, but archive_list has extra data
                ## archive_list: [[0, 1, 'test:/testdata/testdir'], [0, 2, 'test:/testdata/testdir2'], ... ]
                ## archive_list: ['test:/testdata/testdir', 'test:/testdata/testdir2', ... ]
                self.debug.output('archive_list - %s' % self.files.archive_list)
                self.debug.output('file_list - %s' % archive_list)

                ## queue archive does the job of making the archive_list we need to update the tape_list
                self.files.tape_list.extend(self.files.archive_list)
                self.debug.output("q:%s l:%s t:%s" % (self.tape_used_size, archive_size, self.tape_size))

                ## add archive_size to current tape_used_size
                self.tape_used_size += archive_size
                self.tape_index += 1

            else:
                ## we ran out of files
                self.debug.output('file file_list empty')
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

        self.close_dump()

    def get_list(self, limit=7500, regex=False, pid=False, claim=True):
        """get a file_list less than limit size"""

        ## get a 7.5 gb file_list of files to transfer
        self.dump_list, list_size = self.paperdb.get_new(limit, regex=regex, pid=pid)

        ## claim the files so other jobs can request different files
        if self.dump_list and claim:
            self.debug.output(str(list_size))
            self.paperdb.claim_files(self.dump_list)
        return self.dump_list, list_size

    def tar_archive_single(self, catalog_file):
        """send archives to single tape drive using tar"""

        ## track how many copies are written
        tape_copy = 1
        tar_archive_single_status = self.status_code.OK

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
                except Exception as error:
                    self.debug.output('tape write fail {}'.format(error))
                    self.close_dump()
                    break

            ## we have written two copies
            if tape_copy == 2:
                ## update the dump state
                self.dump_state = self.dump_state_code.dump_write

            dump_verify_status = self.dump_verify(label_id)
            if dump_verify_status is not self.status_code.OK:
                self.debug.output('Fail: dump_verify {}'.format(dump_verify_status))
                tar_archive_single_status = self.status_code.tar_archive_single_dump_verify
                self.close_dump()
                break

            if tape_copy == 2:
                self.dump_state = self.dump_state_code.dump_verify

            self.debug.output('unloading drive', label_id, debug_level=128)
            self.tape.unload_tape_drive(label_id)

            ## track tape copy
            tape_copy += 1


        ## update the current dump state
        if tar_archive_single_status is self.status_code.OK:
            log_label_ids_status = self.log_label_ids(tape_label_ids, self.files.tape_list)
            if log_label_ids_status is not self.status_code.OK:
                self.debug.output('problem writing labels out: {}'.format(log_label_ids_status))
        else:
            self.debug.output("Abort dump: {}".format(tar_archive_single_status))

        self.close_dump()

    def log_label_ids(self, tape_label_ids, tape_list):
        """send label ids to db"""
        log_label_ids_status = self.status_code.OK
        log_label_ids_status = self.paperdb.write_tape_index(self.files.tape_list, ','.join(tape_label_ids))
        if log_label_ids_status is not self.status_code.OK:
            self.debug.output('problem writing label: {}'.format(log_label_ids_status))
            self.files.save_tape_ids(','.join(tape_label_ids))

        log_label_ids_status = self.labeldb.date_ids(tape_label_ids)
        if log_label_ids_status is not self.status_code.OK:
            self.debug.output('problem dating labels: {}'.format(log_label_ids_status))

        return log_label_ids_status

    def dump_verify(self, tape_id):
        """take the tape_id and run a self check,
        then confirm the tape_list matches

        """
        dump_verify_status = self.status_code.OK

        ## we update the dump state so self.dump_close() knows what actions to take
        self.dump_state = self.dump_state_code.dump_verify

        ## run a tape_self_check
        self_check_status, item_index, catalog_list, md5_dict, tape_pid = self.tape_self_check(tape_id)

        ## take output from tape_self_check and compare against current dump
        if self_check_status is self.status_code.OK:

            self.debug.output('confirming item_count {} == {}'.format(self.files.item_index, int(item_index)))
            if self.files.item_index != int(item_index):
                self.debug.output("%s mismatch: %s, %s" % ("item_count", self.files.item_index, item_index))
                dump_verify_status = self.status_code.dump_verify_item_index

            self.debug.output('confirming %s' % "catalog")
            if self.files.tape_list != catalog_list:
                self.debug.output("%s mismatch: %s, %s" % ("catalog", self.files.tape_list, catalog_list))
                dump_verify_status = self.status_code.dump_verify_catalog

            self.debug.output('confirming %s' % "md5_dict")
            if self.paperdb.file_md5_dict != md5_dict:
                self.debug.output("%s mismatch: %s, %s" % ("md5_dict", self.paperdb.file_md5_dict, md5_dict), debug_level=253)
                dump_verify_status = self.status_code.dump_verify_md5_dict

            self.debug.output('confirming %s' % "pid")
            if self.pid != str(tape_pid):
                self.debug.output("%s mismatch: %s, %s" % ("pid", self.pid, tape_pid))
                dump_verify_status = self.status_code.dump_verify_pid

        else:
            self.debug.output('Fail: tape_self_check_status: %s' % self_check_status)
            return self_check_status

        self.debug.output('final {}'.format(dump_verify_status))
        return dump_verify_status

    def tape_self_check(self, tape_id):
        """process to take a tape and run integrity check without reference to external database

        :rtype : bool
        """
        tape_self_check_status = self.status_code.OK

        ## load the tape if necessary
        ## TODO(dconover): call with the correct tape drive_int or unload tape before tape_self_check
        self.tape.load_tape_drive(tape_id)

        ## read tape_catalog as file_list
        self.debug.output('read catalog from tape: %s' % tape_id)
        first_block = self.tape.read_tape_catalog(tape_id)

        ## parse the archive_list
        ## build an file_md5_dict
        item_index, catalog_list, md5_dict, tape_pid = self.files.final_from_file(catalog=first_block)

        tape_archive_md5_status, reference = self.tape.tape_archive_md5(tape_id, tape_pid, catalog_list, md5_dict)
        if tape_archive_md5_status is not self.status_code.OK:
            self.debug.output("tape failed md5 inspection at index: %s, status: %s" % (reference, tape_archive_md5_status))
            tape_self_check_status = tape_archive_md5_status

        return tape_self_check_status, item_index, catalog_list, md5_dict, tape_pid

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
            except Exception as error:
                self.debug.output('tape writing exception {}'.format(error))
                break

        self.tape.unload_tape_pair()

        ## write tape locations
        self.debug.output('writing tape_indexes - %s' % self.files.tape_list)
        self.paperdb.write_tape_index(self.files.tape_list, ','.join(tape_label_ids))
        self.debug.output('updating mtx.ids with date')
        self.labeldb.date_ids(tape_label_ids)

    def close_dump(self):
        """orderly close of dump"""

        def _close_init():
            """simple cleanup"""
            pass

        def _close_list():
            """we have claimed files to cleanup"""
            self.paperdb.paperdb_state = self.paperdb.paperdb_state_code.claim

        def _close_queue():
            """files are queued"""
            self.paperdb.paperdb_state = self.paperdb.paperdb_state_code.claim_queue

        def _close_write():
            """files written to tape"""
            self.paperdb.paperdb_state = self.paperdb.paperdb_state_code.claim_write

        def _close_verify():
            """files verified"""
            self.paperdb.paperdb_state = self.paperdb.paperdb_state_code.claim_verify

        close_action = {
            self.dump_state_code.initialize : _close_init,
            self.dump_state_code.dump_list : _close_list,
            self.dump_state_code.dump_queue : _close_queue,
            self.dump_state_code.dump_write : _close_write,
            self.dump_state_code.dump_verify : _close_verify,
        }

        ## prep cleanup state
        close_action[self.dump_state]()

        ## do module cleanup
        self.paperdb.close_paperdb()
        self.files.close_archive()
        self.labeldb.close_mtxdb()
        self.tape.close_changer()

        ## exit
        exit(self.dump_state.value)

class DumpFast(Dump):

    """Queless archiving means that the data is never transferred to our disk queues

    Disk queues are still used to maintain state in the event of a partial dump failure


    """

    def tar_archive_fast(self, catalog_file):
        """Archive files directly to tape using only a single drive to write 2 tapes"""

        tar_archive_fast_status = self.status_code.OK

        ## select ids
        tape_label_ids = self.labeldb.select_ids()
        # self.labeldb.claim_ids(tape_label_ids)

        ## load up a fresh set of tapes
        self.tape.load_tape_pair(tape_label_ids)

        ## add the catalog to the beginning of the tape
        for label_id in tape_label_ids:
            self.debug.output('archiving to label_id - {}'.format(label_id))

        ## prepare the first block of the tape with the current tape_catalog
        self.tape.prep_tape(catalog_file)

        self.debug.output('got list - {}'.format(self.files.tape_list))
        self.tape.archive_from_list(self.files.tape_list)

        ## unloading the tape pair allows for the tape to be loaded back from the library
        ## for verification later
        self.tape.unload_tape_pair()

        for label_id in tape_label_ids:
            dump_verify_status = self.dump_verify(label_id)
            if dump_verify_status is not self.status_code.OK:
                self.debug.output('Fail: dump_verify {}'.format(dump_verify_status))
                tar_archive_single_status = self.status_code.tar_archive_single_dump_verify
                self.close_dump()

        ## update the current dump state
        if tar_archive_fast_status is self.status_code.OK:
            log_label_ids_status = self.log_label_ids(tape_label_ids, self.files.tape_list)
            if log_label_ids_status is not self.status_code.OK:
                self.debug.output('problem writing labels out: {}'.format(log_label_ids_status))
        else:
            self.debug.output("Abort dump: {}".format(tar_archive_single_status))

    def fast_batch(self):
        """skip tar of local archive on disk
           send files to two tapes using a single drive."""

        ## batch_files() does the job of making the lists that queue_archive does
        ## it also updates self.tape_index which is used by Changer.write()
        self.debug.output('reloading sample data into paperdatatest database')


        if self.batch_files():
            self.debug.output('found %s files' % len(self.files.tape_list))
            self.files.gen_final_catalog(self.files.catalog_name, self.files.tape_list, self.paperdb.file_md5_dict)
            self.tar_archive_fast(self.files.catalog_name)
            return True
        else:
            self.debug.output("no files batched")
            return self.dump_state_code.dump_list_fail

    def batch_files(self, queue=False, regex=False, pid=False, claim=True):
        """populate self.catalog_list; transfer files to shm"""
        ## get files in batch size chunks
        while self.tape_used_size + self.batch_size_mb < self.tape_size:

            ## get a file_list of files smaller than our batch size
            archive_list, list_size = self.get_list(self.batch_size_mb, regex=regex, pid=pid, claim=claim)
            self.debug.output("list_size %s" % list_size)

            if archive_list and queue:
                ## if we request disk queuing build an archive
                try:
                    ## copy files to archive, gen catalog file
                    self.files.build_archive(archive_list)

                    ## archives to tar from disk with catalog file
                    ## also write the self.files.archive_list
                    self.files.queue_archive(self.tape_index, archive_list)

                    ## mark where we are
                    self.dump_state = self.dump_state_code.dump_queue

                except Exception as error:
                    self.debug.output('archive build/queue error {}'.format(error))
                    self.close_dump()

            elif archive_list:
                ## we must perform the cataloging task otherwise done by queue_archive()
                arcname = "%s.%s.%s" % ('paper', self.pid, self.tape_index)
                catalog_name = "%s/%s.file_list" %(self.files.queue_dir, arcname)
                self.files.gen_catalog(catalog_name, archive_list, self.tape_index)

                self.tape_used_size += list_size
                self.tape_index += 1
                self.debug.output("queue file_list: {}, len(catalog_list): {}".format(str(self.tape_index),
                                                                                       len(self.files.archive_list)))

                ## queue archive does the job of making the archive_list we need to update the tape_list
                self.files.tape_list.extend(self.files.archive_list)

            else:
                self.debug.output('file file_list empty')
                break

        #if self.tape_used_size > 0:
        #    self.debug.output('generating final catalog - %s, %s' % (len(self.files.tape_list), self.files.tape_list))
        #   self.files.gen_final_catalog(self.files.catalog_name, self.files.tape_list, self.paperdb.file_md5_dict)

        self.debug.output("complete:%s:%s:%s:%s" % (queue, regex, pid, claim))
        return True if self.tape_used_size != 0 else False

class DumpFaster(DumpFast):

    """Queless archiving means that the data is never transferred to our disk queues

    Disk queues are still used to maintain state in the event of a partial dump failure
    Tape verification is rewritten to make use of python threading.

    """

    def dump_pair_verify(self, tape_label_ids):

        return_codes = {}  ## return codes indexed by tape_label
        verification_threads = {}  ## verification threads indexed by tape_label

        self.tape.load_tape_pair(tape_label_ids)

        ## create a thread for each tape (label_id)
        ## so tapes can be verified in parallel
        for label_id in tape_label_ids:
            ## each thread needs a tape and the current dump object
            verify_thread = VerifyThread(label_id, self)
            verification_threads[label_id] = verify_thread
            verify_thread.start()

        ## after we start both threads, we then have to wait for the
        ## started threads to complete
        for label_id in tape_label_ids:
            ## join() will block until run() completes
            verification_threads[label_id].join()

            ## after run completes, we need to query the status code with our
            ## custom status() method
            return_codes[label_id] = verification_threads[label_id].status()

        ## check both return codes and return failure if either is not OK
        for label_id, return_code in return_codes.items():
            if return_code is not self.status_code.OK:
                return return_code

        ## if we didn't return a failure above, return success
        return self.status_code.OK

    def fast_batch(self):
        """skip tar of local archive on disk
           send files to two tapes using a single drive."""

        ## batch_files() does the job of making the lists that queue_archive does
        ## it also updates self.tape_index which is used by Changer.write()
        self.debug.output('reloading sample data into paperdatatest database')

        if self.batch_files():
            self.debug.output('found %s files' % len(self.files.tape_list))
            self.files.gen_final_catalog(self.files.catalog_name, self.files.tape_list, self.paperdb.file_md5_dict)
            self.tar_archive_fast(self.files.catalog_name)
            return True
        else:
            self.debug.output("no files batched")
            return self.dump_state_code.dump_list_fail

    def tar_archive_fast(self, catalog_file):
        """Archive files directly to tape using only a single drive to write 2 tapes"""

        tar_archive_fast_status = self.status_code.OK

        ## select ids
        tape_label_ids = self.labeldb.select_ids()

        ## load up a fresh set of tapes
        self.tape.load_tape_pair(tape_label_ids)

        ## add the catalog to the beginning of the tape
        for label_id in tape_label_ids:
            self.debug.output('archiving to label_id - {}'.format(label_id))

        ## prepare the first block of the tape with the current tape_catalog
        self.tape.prep_tape(catalog_file)

        ## actually write the files in the catalog to a tape pair
        self.debug.output('got list - {}'.format(self.files.tape_list))
        self.tape.archive_from_list(self.files.tape_list)

        ## check the status of the dumps
        tar_archive_fast_status = self.dump_pair_verify(tape_label_ids)

        ## unload the tape pair
        self.tape.unload_tape_pair()

        ## update the db if the current dump status is OK
        if tar_archive_fast_status is self.status_code.OK:
            log_label_ids_status = self.log_label_ids(tape_label_ids, self.files.tape_list)
            if log_label_ids_status is not self.status_code.OK:
                self.debug.output('problem writing labels out: {}'.format(log_label_ids_status))
        else:
            self.debug.output("Abort dump: {}".format(tar_archive_fast_status))
            self.close_dump()



# noinspection PyClassHasNoInit
@unique
class DumpStateCode(Enum):
    """ file_list of database specific dump states (last known good state)

    This is not to be confused with error codes, which tell the program what
    went wrong. Rather, these states track what clean-up actions should be
    performed, when the object is closed.
    """


    initialize     = 1 ## cleanup temporary files in paper_io              action: always close db
    dump_list      = 2 ## files claimed;                                   action: unclaim files; close db
    dump_queue  = 3 ## claimed files queued;                               action: ignore (?); close db
    dump_write   = 4 ## claimed files written to tape, but not verified;   action: ignore (?); close db
    dump_list_fail = 5
    dump_queue_fail = 6
    dump_write_fail = 7
    dump_verify_fail = 8
    dump_verify  = 0 ## done


class ResumeDump(Dump):
    """methods for resuming a normal dump that was interrupted"""

    def manual_write_tape_location(self):
        """on a tape dump that fails after writing to tape, but before writing
        locations to tape, use this to resume writing locations to tape.

        The dump must be initialized with the pid of the queued files.
        """

        self.tape_index, catalog, md5_dict, pid = self.files.final_from_file()
        self.tape_ids = self.files.tape_ids_from_file()
        self.debug.output('write tape location', ','.join(self.tape_ids))
        self.paperdb.write_tape_index(self.files.archive_list, ','.join(self.tape_ids))

    def manual_resume_to_tape(self):
        """read in the cumulative file_list from file and send to tape"""

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

class VerifyThread(Thread):
    ## get tape id and initialize variable for recording status code
    def __init__(self, tape_id, dump_function):
        self.tape_id = tape_id
        self.dump_verify_status = ''

    ## run command and record status code
    def run():
        self.dump_verify_status = dump_function(label_id)

    ## return status code when complete
    def status():
        return self.dump_verify_status

class TestDump(DumpFaster):
    """move all the testing methods here to cleanup the production dump class"""


    def test_build_archive(self, regex=False):
        """master method to loop through files to write data to tape"""

        self.batch_files(queue=True, regex=regex)
        self.files.gen_final_catalog(self.files.catalog_name, self.files.archive_list, self.paperdb.file_md5_dict)

    def test_data_init(self):
        "create a test data set"
        pass

    def test_dump_faster(self):
        "run a test dump using the test data"

        ## from paper_dump import DumpFast

        ## paper_creds = '/home2/obs/.my.papertape-prod.cnf'
        self.paper_creds = '/papertape/etc/.my.papertape-test.cnf'

        ## add comment
        ##x = DumpFaster(paper_creds, debug=True, drive_select=2, disk_queue=False, debug_threshold=128)
        self.batch_size_mb = 15000
        self.tape_size = 1536000
        #x.tape_size = 2500000
        self.fast_batch()


