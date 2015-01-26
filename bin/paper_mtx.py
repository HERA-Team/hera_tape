"""Manage tapes

    Changer: access mtx features
    MtxDB: a mysql database to manage tape usage
    Drives: access to mt functions and writing data to tape
"""

import re
import datetime
import random
import time
from subprocess import *

import pymysql
from collections import defaultdict

from paper_debug import Debug
from paper_status_code import StatusCode
from io import StringIO
from io import BytesIO 
import tarfile
from enum import Enum, unique


def split_mtx_output(mtx_output):
    """Return dictionaries of tape_ids in drives and slots."""
    drive_ids = {}
    tape_slot = {}
    label_in_drive = {}

    for line in mtx_output.split('\n'):
        drive_line = re.compile('^Data Transfer Element (\d):Full \(Storage Element (\d+) Loaded\):VolumeTag = ([A-Z0-9]{8})')
        storage_line = re.compile('\s+Storage Element (\d+):Full :VolumeTag=([A-Z0-9]{8})')

        if drive_line.match(line):
            """Data Transfer Element 1:Full (Storage Element 1 Loaded):VolumeTag = PAPR1001"""
            drive_info = drive_line.match(line).groups()
            ## dict of storage_slots by tape_id
            drive_ids[drive_info[2]] = drive_info[0:2]
            ## dict of tape_ids by drive_int
            label_in_drive[drive_info[0]] = drive_info[2]

        elif storage_line.match(line):
            """Storage Element 10:Full :VolumeTag=PAPR1010"""
            storage_info = storage_line.match(line).groups()
            ## dict of tapes slots by tape_id
            tape_slot[storage_info[1]] = storage_info[0]

    return drive_ids, tape_slot, label_in_drive

class Changer(object):
    """simple tape changer class"""


    def __init__(self, version, pid, tape_size, disk_queue=True, drive_select=2, debug=False, debug_threshold=255):
        """init with debugging
        :type drive_select: int
        :param drive_select: 0 = nst0, 1 = nst1, 2 = nst{1,2}
        :type disk_queue: bool
        :param disk_queue: write archives to a disk queue first?
        """

        self.version = version
        self.pid = pid
        self.debug = Debug(self.pid, debug=debug, debug_threshold=debug_threshold)
        self.tape_size = tape_size
        self._tape_dev = '/dev/changer'
        self.status_code = StatusCode

        self.drive_ids = []
        self.tape_ids = []
        self.label_in_drive = [] ## return label in given drive

        self.check_inventory()
        self.tape_drives = Drives(self.pid, drive_select=drive_select, debug=debug, debug_threshold=debug_threshold)

        self.disk_queue = disk_queue
        if not self.disk_queue:
            ## we need to use Ramtar
            self.ramtar = RamTar
        ## TODO(dconover): implement a lock on the changer to prevent overlapping requests
        self.changer_state = 0

    def check_inventory(self):
        """check the current inventory of the library with mtx"""
        output = check_output(['mtx', 'status']).decode("utf-8")
        self.debug.output(output, debug_level=251)
        self.drive_ids, self.tape_ids, self.label_in_drive = split_mtx_output(output)
        for drive_id in self.drive_ids:
            self.debug.output('- %s, %s num_tapes: %d' % (id, self.drive_ids[drive_id], len(self.tape_ids)))

    def print_inventory(self):
        """print out the current tape library inventory"""
        for drive_id in self.drive_ids:
            print('drive: %s, %s' % (id, self.drive_ids[drive_id]))
        for drive_id in self.tape_ids:
            print('slot: %s, %s' % (id, self.tape_ids[drive_id]))

    def get_tape_slot(self, tape_id):
        """return the slot number where the given tape is currently loaded"""
        return self.tape_ids[tape_id]

    def load_tape_pair(self, tape_ids):
        """load the next available tape pair"""
        self.debug.output('checking drives')
        if self.drives_empty():
            if len(tape_ids) == 2:
                for drive, tape_id in enumerate(tape_ids):
                    self.debug.output('loading', str(id), str(drive))
                    self.load_tape(tape_id, drive)
            else:
                self.debug.output('failed to load tape pair: %s' % tape_ids)

    ## using type hinting with Sphinx
    ## pycharm doesn't seem to like PEP 3107 style type hinting
    def load_tape_drive(self, tape_id, drive=0):
        """load a given tape_id into a given drive=drive_int, unload if necessary.
        :type  tape_id: label of tape to load
        :param tape_id: label of tape to load"""
        status = False

        self.debug.output('check then load')
        for attempt in range(3):
            if self.drives_empty(drive_int=drive):
                self.debug.output('loading', str(tape_id), str(drive), debug_level=128)
                self.load_tape(tape_id, drive)
                status = True
                break

            ## return if the drive already contains the tape we want
            ## just rewind
            elif self.label_in_drive[str(drive)] == tape_id:
                ## if we call this function we probably need a rewind
                self.rewind_tape(tape_id)
                status = True

            ## if the drive is full attempt to unload, then retry
            else:
                self.debug.output('unable to load, drive filled', str(self.label_in_drive), str(drive), debug_level=128)
                self.unload_tape_drive(self.label_in_drive[str(drive)])

        return status

    def unload_tape_pair(self):
        """unload the tapes in the current drives"""
        if not self.drives_empty():
            for tape_id in self.drive_ids:
                self.debug.output('unloading', tape_id)
                self.unload_tape(tape_id)

    def unload_tape_drive(self, tape_int):
        """unload the tapes in the current drives"""
        if not self.drives_empty():
            self.debug.output('unloading', str(tape_int))
            self.unload_tape(tape_int)
        else:
            self.debug.output('tape already empty', str(tape_int))

    def drives_empty(self, drive_int=None):
        """retun true if the drives are currently empty"""
        self.check_inventory()

        if drive_int:
            self.debug.output('called with drive_int: %s' % self.label_in_drive)
            return False if drive_int in self.label_in_drive else True
        else:
            self.debug.output('basic check drive labels: %s' % self.label_in_drive)
            return not len(self.drive_ids)

    @property
    def drives_loaded(self):
        """return true if the drives are loaded"""
        self.check_inventory()
        if len(self.drive_ids):
            return self.get_drive_tape_ids()
        else:
            return False

    def get_drive_tape_ids(self):
        """get the tape_ids currently loaded in drives"""
        self.check_inventory()
        return self.drive_ids

    def load_tape(self, tape_id, tape_drive):
        """Load a tape into a free drive slot"""
        if self.tape_ids[tape_id]:
            self.debug.output('Loading - %s' % tape_id)
            output = check_output(['mtx', 'load', str(self.tape_ids[tape_id]), str(tape_drive)])
            self.check_inventory()

    def unload_tape(self, tape_id):
        """Unload a tape from a drive and put in the original slot"""
        if self.drive_ids[tape_id]:
            command = ['mtx', 'unload', self.drive_ids[tape_id][1], self.drive_ids[tape_id][0]]
            self.debug.output('%s' % command)
            output = check_output(command)
            self.check_inventory()

    def rewind_tape(self, tape_id):
        """rewind the tape in the given drive"""
 
        status = False
        
        try: 
            if self.drive_ids[tape_id]:
                self.debug.output('rewinding tape %s' % tape_id)
                output = check_output('mt -f /dev/nst%s rewi' % (self.drive_ids[tape_id][0]), shell=True)
                status = True

        except CalledProcessError:
            self.debug.output('rewind error')

        except KeyError:
            self.debug.output('tape (%s) not loaded: %s' % (tape_id, self.drive_ids))
             
        return status
        
    def write(self, tape_index, catalog_list=None):
        """write data to tape"""
        ## tar dir to two drives
        arcname = "paper.%s.%s" % (self.pid, tape_index)
        tar_name = "/papertape/queue/%s/%s.tar" % (self.pid, arcname)
        catalog_name = "/papertape/queue/%s/%s.file_list" % (self.pid, arcname)

        if self.disk_queue:
            self.debug.output("writing", catalog_name, tar_name)
            self.tape_drives.tar_files([catalog_name, tar_name])
        elif self.disk_queue and catalog_list:
            pass
         #   self.ramtar.send_archive_to_tape()
        elif self.disk_queue:
            self.debug.output('no list given')
            raise Exception


    def prep_tape(self, catalog_file):
        """write the catalog to tape. write all of our source code to the first file"""
        ## write catalog
        self.debug.output("writing catalog to tape", catalog_file)
        self.tape_drives.dd(catalog_file)
        ## write source code
        #self.tape_drives.tar('/root/git/papertape')

    def read_tape_catalog(self, tape_id):
        """read and return first block of tape"""

        self.rewind_tape(tape_id)
        drive_int = self.drive_ids[tape_id][0]

        return self.tape_drives.dd_read(drive_int)

    def count_files(self, tape_id):
        """count files of the given tape"""
        self.rewind_tape(tape_id)
        drive_int = self.drive_ids[tape_id][0]

        return self.tape_drives.count_files(drive_int)

    def tape_archive_md5(self, tape_id, job_pid, catalog_list, md5_dict):
        """loop through each archive on tape and check a random file md5 from each

        :rtype : bool"""

        ## default to True
        tape_archive_md5_status = self.status_code.OK
        reference = None

        self.debug.output('loading tape: %s' % tape_id)
        ## load a tape or rewind the existing tape
        self.load_tape_drive(tape_id)

        ## for every tar advance the tape
        ## select a random path from the tape
        ## run md5sum_at_index(tape_index, drive_int=0)
        archive_dict = defaultdict(list)

        ## build a dictionary of archives
        for item in catalog_list:
            self.debug.output('item to check: %s' % item)
            archive_dict[item[0]].append(item[-1])

        for tape_index in archive_dict:
            directory_path = random.choice(archive_dict[tape_index])
            ## starting at the beginning of the tape we can advance one at a
            ## time through each archive and test one directory_path/visdata md5sum
            self.debug.output('checking md5sum for %s' % directory_path)
            md5sum = self.tape_drives.md5sum_at_index(job_pid, tape_index, directory_path, drive_int=0)
            if md5sum != md5_dict[directory_path]:
                self.debug.output('mdsum does not match: %s, %s' % (md5sum, md5_dict[directory_path]))
                tape_archive_md5_status = self.status_code.tape_archive_md5_mismatch
                reference = ":".join([str(tape_index), directory_path])
                break
            else:
                self.debug.output('md5 match: %s|%s' % (md5sum, md5_dict[directory_path]))

        return tape_archive_md5_status, reference

    def close_changer(self):
        """cleanup"""
        ## TODO(dconover): implement changer locking; remove lock
        pass

@unique
class ChangerStates(Enum):
    """states related to tape changer"""
    changer_init = 0
    changer_active = 1
    changer_idle = 2

class MtxDB(object):
    """db to handle record of label ids

    Field     Type    Null    Key     Default Extra
    id        mediumint(9)    NO      PRI     NULL    auto_increment
    label     char(8) YES             NULL
    date      int(11) YES             NULL
    status    int(11) YES             NULL
    capacity  int(11) YES             NULL

    """

    def __init__(self, version, credentials, pid, debug=False, debug_threshold=255):
        """Initialize connection and collect file_list of tape_ids."""

        self.version = version
        self.pid = pid
        self.debug = Debug(self.pid, debug=debug, debug_threshold=debug_threshold)
        self.status_code = StatusCode

        ## database variables
        self.connection_timeout = 90
        self.connection_time = datetime.timedelta()
        self.credentials = credentials
        self.connect = ''
        self.cur = ''
        self.db_connect('init', credentials)

        self.mtxdb_state = 0 ## current dump state

    def __setattr__(self, attr_name, attr_value):
        """debug.output() when a state variable is updated"""
        class_name = self.__class__.__name__.lower()

        ## we always use the lowercase of the class_name in the state variable
        if attr_name == '{}_state'.format(class_name):
            ## debug whenever we update the state variable
            self.debug.output("updating: {} with {}={}".format(class_name, attr_name, attr_value))
        super(self.__class__, self).__setattr__(attr_name, attr_value)

    def update_connection_time(self):
        """refresh database connection"""
        self.debug.output('updating connection_time')
        self.connection_time = datetime.datetime.now()

    def connection_time_delta(self):
        """return connection age"""
        self.debug.output('connection_time:%s' % self.connection_time)
        delta = datetime.datetime.now() - self.connection_time
        return delta.total_seconds()

    def db_connect(self, command=None, credentials=None):
        """connect to the database or reconnect an old session"""
        self.debug.output('input:%s %s' % (command, credentials))
        self.credentials = credentials if credentials is not None else self.credentials
        time_delta = self.connection_timeout + 1 if command == 'init' else self.connection_time_delta()

        self.debug.output("time_delta:%s, timeout:%s" % (time_delta, self.connection_timeout))
        if time_delta > self.connection_timeout:
            self.debug.output("setting connection %s %s" % (credentials, self.connection_timeout))
            self.connect = pymysql.connect(read_default_file=self.credentials, connect_timeout=self.connection_timeout)
            self.cur = self.connect.cursor()

        self.update_connection_time()
        self.debug.output("connection_time:%s" % self.connection_time)

    def get_capacity(self, tape_id):
        select_sql = "select capacity from ids where id='%s'" % tape_id

    def select_ids(self):
        """select lowest matching id pairs"""

        self.db_connect()
        ids = []
        for n in [0, 1]:
            select_sql = """select label from ids
                where status is null and
                label like 'PAPR%d%s'
                order by label
            """ % (n+1, "%")

            self.cur.execute(select_sql)

            #print(self.cur.fetchone()[0])
            ids.append(self.cur.fetchone()[0])
        return ids

    def insert_ids(self, ids):
        """Add new tape_ids to the mtxdb"""
        self.db_connect()
        for label_id in ids:
            insert_sql = "insert into ids (label) values('%s')" % label_id
            print(insert_sql)
            self.cur.execute(insert_sql)

        self.connect.commit()

    def claim_ids(self, ids):
        """Mark files in the database that are "claimed" by a dump process."""
        self.db_connect()
        for tape_id in ids:
            claim_query = '''update ids 
                set status="%s", description="Paper dump version:%s"
                where label="%s"''' % (self.pid, self.version, tape_id)

            self.debug.output(claim_query)
            self.cur.execute(claim_query)

        self.connect.commit()

    def date_ids(self, ids):
        """write the date of our completed run to tape"""
        date_ids_status = self.status_code.OK
        date = datetime.datetime.now().strftime('%Y%m%d-%H%M')
        self.db_connect()
        for tape_id in ids:
            self.debug.output('updating mtxdb: %s, %s' % (date, tape_id))
            date_sql = 'update ids set date="%s" where label="%s"' % (date, tape_id)
            try:
                self.cur.execute(date_sql)
            except Exception as mysql_error:
                self.debug.output('error {}'.format(mysql_error))
                date_ids_status = self.status_code.date_ids_mysql

        try:
            self.connect.commit()
        except Exception as mysql_error:
            self.debug.output('error {}'.format(mysql_error))
            date_ids_status = self.status_code.date_ids_mysql

        return date_ids_status


    def write(self, src_directory):
        """take a path like /dev/shm/1003261778 and create a tar archive on two tapes"""

        self.update_unused_capacity()
        pass

    def update_unused_capacity(self, used=None):
        """Write out unused capacity to database."""
        self.db_connect()
        pass

    def close_mtxdb(self):
        """cleanup mtxdb state
        """
        ## TODO(dconover): dependent on self.mtx_state: claim/unclaim tapes; close mtxdb
        pass

class Drives(object):
    """class to manage low level access directly with tape (equivalient of mt level commands)

    It also can handle python directly opening or more drives with tar.
    It assumes that exactly two drives are installed, and that you will use either one, or both
    via the tape_select option
    """

    def __init__(self, pid, drive_select=2, debug=False, disk_queue=True, debug_threshold=128):
        """initialize debugging and pid"""
        self.pid = pid
        self.debug = Debug(pid, debug=debug, debug_threshold=debug_threshold)
        self.drive_select = drive_select

    ## This method is deprecated because the tape self check runs though every listed archive
    def count_files(self, drive_int):
        """count the number of files on the current tape in the given drive"""
        drive = "/dev/nst%s" % drive_int
        bash_to_count_files = """
            _count_files_on_tape () {  ## count the number of files on tape
                local _count=0; 
                while :; do  
                    mt -f /dev/nst0 fsf 1 ||break
                    let _count+=1
                done
    
                echo $_count
            }
 
        """
        output = check_output(bash_to_count_files, shell=True).decode('utf8').split('\n')

        return int(output[0])

    def tar_files(self, files):
        """send files in a file_list to drive(s) with tar"""
        commands = []
        for drive_int in range(self.drive_select):
            commands.append('tar cf /dev/nst%s  %s ' % (drive_int, ' '.join(files)))
        self.exec_commands(commands)

    def tar_fast(self, files):
        """send catalog file and file_list of source files to tape as archive"""

    def tar(self, file_name):
        """send the given file_name to a drive(s) with tar"""
        commands = []
        for drive_int in range(self.drive_select):
            commands.append('tar cf /dev/nst%s %s ' % (drive_int, file_name))
        self.exec_commands(commands)

    def dd(self, text_file):
        """write text contents to the first 32k block of a tape"""
        commands = []
        for drive_int in range(self.drive_select):
            commands.append('dd conv=sync,block of=/dev/nst%s if=%s bs=32k count=1' % (drive_int, text_file))
        self.exec_commands(commands)

    def dd_read(self, drive_int):
        """assuming a loaded tape, read off the first block from the tape and
        return it as a string"""

        command = ['dd', 'conv=sync,block', 'if=/dev/nst%s' % drive_int, 'bs=32k', 'count=1']
        self.debug.output('%s' % command)
        output = check_output(command).decode('utf8').split('\n')

        return output[:-1]

    def dd_duplicate(self, source_drive_int, destination_drive_int):
        """copy a tape from one drive to the other using dd"""
        source_dev = 'if=/dev/nst{}'.format(source_drive_int)
        destination_dev = 'of=/dev/nst{}'.format(destination_drive_int)

        command = ['dd', 'conf=sync,block', source_dev, destination_dev]
        self.debug.output('{}'.format(command))
        output = check_output(command).decode('utf8').split('\n')

    def md5sum_at_index(self, job_pid, tape_index, directory_path, drive_int=0):
        """given a tape_index and drive_int, return the md5sum of the file
        at that index on the tape in /dev/nst$drive_index."""

        self.debug.output("getting md5 of file at %s in drive %s" % (tape_index, drive_int))

        commands = []
        ## the index is stored like: [PAPR1001, PAPR2001]-0:1
        ## the first number gives the file on tape
        ## the second number gives the file on tar
        ## but the tar is inside another tar with the full file table
        ## to get at an indexed file you must do something like:
        ##
        bash_to_md5_selected_file = """
            _block_md5_file_on_tape () {

                local _fsf=1
                local _job_pid=${1:-030390297}
                local _tape_index=${2:-1}
                local _test_path=${3:-data-path}
                local _tape_dev=${4:-0}

                local _tar_number=$_tape_index
                local _archive_tar=paper.$_job_pid.$_tar_number.tar
                local _test_file=$_test_path/visdata

                ## extract the archive tar, then extract the file to stdout, then run md5 on stdin
                mt -f /dev/nst$_tape_dev fsf $_fsf &&
                    tar xOf /dev/nst$_tape_dev $_archive_tar|
                        tar xOf - paper.$_job_pid.$_tape_index/$_test_file|
                            md5sum|awk '{print $1}'
            }

            _block_md5_file_on_tape %s %s %s %s
        """ % (job_pid, tape_index, directory_path, drive_int)

        #self.debug.output(bash_to_md5_selected_file, debug_level=252)
        self.debug.output("reading %s" % directory_path)

        try:
            ## check output
            output = check_output(bash_to_md5_selected_file, shell=True).decode('utf8').split('\n')
            ## we should check the output
            self.debug.output('output: %s' % output[0], debug_level=250)

        except CalledProcessError as return_info:
            self.debug.output('return_info: %s' % return_info)
            return False

        return output[0]

    def exec_commands(self, cmds):
        """ Exec commands in parallel in multiple process
        (as much as we have CPU)
        """
        if not cmds: return # empty file_list

        def done(proc):
            return proc.poll() is not None

        def success(proc):
            return proc.returncode == 0

        def fail():
            return

        processes = []
        while True:
            while cmds:
                task = cmds.pop()
                processes.append(Popen(task, shell=True))

            for process in processes:
                if done(process):
                    if success(process):
                        processes.remove(process)
                    else:
                        fail()

            if not processes and not cmds:
                break
            else:
                time.sleep(0.05)

class RamTar(object):
    """handling python tarfile opened directly against tape devices"""

    def __init__(self, pid, drive_select=1, rewrite_path=None, debug=False, debug_threshold=128):
        """initialize"""

        self.pid = pid
        self.debug = Debug(self.pid, debug=debug, debug_threshold=debug_threshold)

        self.drive_select = drive_select
        self.rewrite_path = rewrite_path
        ## if we're not using disk queuing we open the drives differently;
        ## we need to track different states
        ## for faster archiving we keep some data in memory instead of queuing to disk
        self.archive_bytes = BytesIO()
        self.archive_tar = tarfile.open(mode='w:', fileobj=self.archive_bytes)
        self.archive_info = tarfile.TarInfo()

        ## tape opened with tar
        ## this is a dictionary where we will do:
        ## self.tape_drive[drive_int] = tarfile.open(mode='w:')
        self.tape_drive = {}

        ## if we use tarfile, we need to track the state
        self.drive_states = RamTarStates
        self.drive_state = self.ramtar_tape_drive(drive_select, self.drive_states.drive_init)

    def ramtar_tape_drive(self, drive_int, request):
        """open, close, update state, or reserve a drive for another process

        :rtype : Enum
        """

        self.debug.output('reqeust - {}'.format(request))
        action_return = []
        ## TODO(dconover): prly don't need this
        def init_tar_drive():
            """Mark the given drives as available
            """

            new_state = {}
            if int(drive_int) == 2:
                for _loop_drive_int in 0,1:
                    new_state[_loop_drive_int]= self.drive_states.drive_init
            else:
                self.debug.output('init single - {}'.format(drive_int))
                reserve_drive = 0 if drive_int == 1 else 1
                new_state[drive_int] = self.drive_states.drive_init
                new_state[reserve_drive] = self.drive_states.drive_reserve

            return new_state

        def open_tar_drive():
            """open a tar file against a particular drive"""
            device_path = '/dev/nst{}'.format(drive_int)
            if self.drive_state is self.drive_states.drive_init:
                self.tape_drive[drive_int] = tarfile.open(name=device_path, mode='w:')
                self.drive_state[drive_int] = self.drive_states.drive_open

        def close_tar_drive():
            """close a previously opened tar for a particular drive"""
            if self.drive_state is self.drive_states.drive_open:
                self.tape_drive[drive_int].close()
                self.drive_state[drive_int] = self.drive_states.drive_init

        action = {
            self.drive_states.drive_init : init_tar_drive,
            self.drive_states.drive_open : open_tar_drive,
            self.drive_states.drive_close : close_tar_drive
        }

        try:
            action_return = action[request]()
            self.debug.output('action_return = {}'.format(action_return))
        except Exception as action_exception:
            self.debug.output('tar_exception: {}'.format(action_exception))
            raise

        return action_return

    def archive_from_list(self, tape_list):
        """take a tape list, build each archive, write to tapes"""

        archive_dict = {}
        archive_list_dict = {}


        if self.drive_select == 2:
            self.debug.output('writing data to two tapes')
            ## for archive group in list
            ## build a dictionary of archives
            for item in tape_list:
                self.debug.output('item to check: %s' % item)
                archive_list_dict[item[0]].append(item)
                archive_dict[item[0]].append(item[-1])

            for tape_index in archive_dict:

                archive_dir = '/papertape/queue/{}'.format(self.pid)
                archive_name = 'paper.{}.{}.tar'.format(self.pid,tape_index)
                archive_file =  '{}/{}'.format(archive_dir,archive_name)
                archive_list = '{}/{}.file_list'.format(archive_dir, archive_name)

                ## for file in archive group build archive
                for item in archive_dict[tape_index]:
                    self.debug.output('item - {}'.format(item))
                    #arcname_rewrite = self.rewrite_path
                    self.append_to_archive(item)

                list = open(archive_list, mode='w')
                list.write('\n'.join(archive_list_dict[tape_index]))
                list.close()

                arc = open(archive_file, mode='w')
                arc.close()

                ## send archive group to both tapes
                for drive in self.tape_drive:
                    self.send_archive_to_tape(drive, archive_list, archive_name, archive_file)

        else:
            """I don't think its a good idea to do this since you have to read the data twice"""
            self.debug.output('skipping data write')
            pass

    def append_to_archive(self, file_path, file_path_rewrite=None):
        """add data to an open archive"""
        arcname = file_path if file_path_rewrite is None else file_path_rewrite
        try:
            self.archive_tar.add(file_path, arcname=arcname)
        except Exception as cept:
            self.debug.output('tarfile exception - {}'.format(cept))
            raise

    def send_archive_to_tape(self, drive_int, archive_list, archive_name, archive_file):
        """send the current archive to tape"""
        ## add archive_list
        self.tape_drive[drive_int].add(archive_list)
        ## add archive
        try:
            ## get the basic info from the blank file we wrote
            self.archive_info = self.tape_drive[drive_int].gettarinfo(archive_file)
            ## change the size to the byte size of our BytesIO object
            self.archive_info.size = len(self.archive_bytes.getvalue())
            ## rewind
            self.archive_bytes.seek(0)
            ## write the bytes with info to the tape
            self.tape_drive[drive_int].addfile(tarinfo=self.archive_info, fileobj=self.archive_bytes)
            self.tape_drive[drive_int].close()
        except Exception as cept:
            self.debug.output('tarfile - {}'.format(cept))
            raise

    def reset_archive(self):
        """reset the archive"""
        self.archive_bytes.seek(0)
        self.archive_bytes.truncate()
        self.archive_tar = tarfile.open(mode='w:', fileobj=self.archive_bytes)


@unique
class RamTarStates(Enum):
    drive_init = 0 ## in an available, but unbound state
    drive_open = 1 ## open requested by some process
    drive_close = 2 ## close requested
    drive_reserve = 3 ## drive not reserved for use by another process
