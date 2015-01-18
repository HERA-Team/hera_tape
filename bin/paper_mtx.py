"""Manage tapes

    Changer: access mtx features
    MtxDB: a mysql database to manage tape usage
    Drives: access to mt functions and writing data to tape
"""

import re, pymysql, datetime, random, time
from subprocess import *
from paper_debug import Debug

from collections import defaultdict


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

def split_tape_catalog(tape_catalog):
    """return pid, and file list"""
    pid = ''
    file_list = []
    md5_dict = {}

    return pid, file_list, md5_dict

class Changer:
    """simple tape changer class"""

    def __init__(self, version, pid, tape_size, debug=False, drive_select=2, debug_threshold=255):
        """init with debugging"""
        self.version = version
        self.pid = pid
        self.debug = Debug(self.pid, debug=debug, debug_threshold=debug_threshold)
        self.tape_size = tape_size
        self._tape_dev = '/dev/changer'

        self.drive_ids = []
        self.tape_ids = []
        self.label_in_drive = [] ## return label in given drive

        self.check_inventory()
        self.tape_drives = Drives(self.pid, drive_select=drive_select, debug=debug, debug_threshold=debug_threshold)

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
        """return the slot numver where the given tape is currently loaded"""
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
    ## pycharms doesn't seem to like PEP 3107 style type hinting
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
        
    def write(self, queue_pass):
        """write data to tape"""
        ## tar dir to two drives
        arcname = "paper.%s.%s" % (self.pid, queue_pass)
        tar_name = "/papertape/queue/%s/%s.tar" % (self.pid, arcname)
        catalog_name = "/papertape/queue/%s/%s.list" % (self.pid, arcname)

        self.debug.output("writing", catalog_name, tar_name)
        self.tape_drives.tar_files([catalog_name, tar_name])

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
        """loop through each archive on tape and check a random file md5 from each"""

        ## default to True
        status = True
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
                status = False
                reference = ":".join([str(tape_index), directory_path])
                break
            else:
                self.debug.output('md5 match: %s|%s' % (md5sum, md5_dict[directory_path]))

        return status, reference


class MtxDB:
    """db to handle record of label ids

    Field     Type    Null    Key     Default Extra
    id        mediumint(9)    NO      PRI     NULL    auto_increment
    label     char(8) YES             NULL
    date      int(11) YES             NULL
    status    int(11) YES             NULL
    capacity  int(11) YES             NULL

    """

    def __init__(self, version, credentials, pid, debug=False, debug_threshold=255):
        """Initialize connection and collect list of tape_ids."""

        self.version = version
        self.pid = pid
        self.debug = Debug(self.pid, debug=debug, debug_threshold=debug_threshold)

        ## database variables
        self.connection_timeout = 90
        self.connection_time = 0
        self.credentials = credentials
        self.connect = ''
        self.cur = ''
        self.db_connect('init', credentials)

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
        date = datetime.datetime.now().strftime('%Y%m%d-%H%M')
        self.db_connect()
        for tape_id in ids:
            self.debug.output('updating mtxdb: %s, %s' % (date, tape_id))
            date_sql = 'update ids set date="%s" where label="%s"' % (date, tape_id)
            self.cur.execute(date_sql)

        self.connect.commit()

    def write(self, src_directory):
        """take a path like /dev/shm/1003261778 and create a tar archive on two tapes"""

        self.update_unused_capacity()
        pass

    def update_unused_capacity(self, used=None):
        """Write out unused capacity to database."""
        self.db_connect()
        pass


class Drives:
    """class to manage low level access directly with tape (equivalient of mt level commands)"""

    def __init__(self, pid, drive_select=2, debug=False, debug_threshold=128):
        """initialize debugging and pid"""
        self.pid = pid
        self.debug = Debug(pid, debug=debug, debug_threshold=debug_threshold)
        self.debug.output('set debug')
        self.drive_select = drive_select

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
 
            _count_files_on_tape
        """
        output = check_output(bash_to_count_files, shell=True).decode('utf8').split('\n')

        return int(output[0])

    def tar_files(self, files):
        """send files in a list to drive(s) with tar"""
        commands = []
        for drive_int in range(self.drive_select):
            commands.append('tar cf /dev/nst%s  %s ' % (drive_int, ' '.join(files)))
        self.exec_commands(commands)

    def tar(self, file):
        """send the given file to a drive(s) with tar"""
        commands = []
        for drive_int in range(self.drive_select):
            commands.append('tar cf /dev/nst%s %s ' % (drive_int, file))
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
        if not cmds: return # empty list

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


