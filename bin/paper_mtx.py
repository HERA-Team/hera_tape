"""Manage tapes

    Changer: access mtx features
    MtxDB: a mysql database to manage tape usage
    Drives: access to mt functions and writing data to tape
"""

import re, pymysql, time, datetime
from random import randint
from subprocess import *
from paper_debug import Debug


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
            label_in_drive[drive_info[0]] = drive_info[2]

        elif storage_line.match(line):
            """Storage Element 10:Full :VolumeTag=PAPR1010"""
            storage_info = storage_line.match(line).groups()
            ## dict of tapes slots by tape_id
            tape_slot[storage_info[1]] = storage_info[0]

    return drive_ids, tape_slot, label_in_drive

class Changer:
    'simple tape changer class'

    def __init__(self, pid, tape_size, debug=False, drive_select=2, debug_threshold=255):
        self.pid = pid
        self.debug = Debug(self.pid, debug=debug, debug_threshold=debug_threshold)
        self.tape_size = tape_size
        self._tape_dev = '/dev/changer'

        self.drive_ids = [] 
        self.tape_ids = []
        self.label_in_drive = [] ## return label in given drive

        self.check_inventory()
        self.tape_drives = Drives(self.pid, drive_select=drive_select)

    def check_inventory(self):
        output = check_output(['mtx', 'status']).decode("utf-8")
        self.debug.print(output, debug_level=251)
        self.drive_ids, self.tape_ids, self.label_in_drive = split_mtx_output(output)
        for drive_id in self.drive_ids:
            self.debug.print('- %s, %s ' % (id, self.drive_ids[drive_id]))

    def print_inventory(self):
        for drive_id in self.drive_ids:
            print('drive: %s, %s' % (id, self.drive_ids[drive_id]))
        for drive_id in self.tape_ids:
            print('slot: %s, %s' % (id, self.tape_ids[drive_id]))

    def get_tape_slot(self, tape_id):
        return self.tape_ids[tape_id]

    def load_tape_pair(self, ids):
        """load the next available tape pair"""
        if self.drives_empty():
            if len(ids) == 2:
                for drive, tape_id in enumerate(ids):
                    self.debug.print('loading', str(id), str(drive))
                    self.load_tape(tape_id, drive)

    ## using type hinting PEP 3107 and Sphinx
    def load_tape_drive(self, tape_id: str, drive=0) -> bool:
        '''load a given tape_id into a given drive=drive_id, unload if necessary.
        :type  tape_id: label of tape to load
        :param tape_id: label of tape to load'''
        for attempt in range(3):
            if self.drives_empty():
                self.debug.print('loading', str(tape_id), str(drive), debug_level=128)
                self.load_tape(tape_id, drive)
                status = True
                break

            ## if the drive is full attempt to unload, then retry
            else:
                self.debug.print('unable to load, drive filled', str(self.label_in_drive), str(drive), debug_level=128)
                self.unload_tape_drive(self.label_in_drive[str(drive)])
                status = False

        return status

    def unload_tape_pair(self):
        'unload the tapes in the current drives'
        if not self.drives_empty():
            for tape_id in self.drive_ids:
                self.debug.print('unloading', tape_id)
                self.unload_tape(tape_id)

    def unload_tape_drive(self, tape_int):
        'unload the tapes in the current drives'
        if not self.drives_empty():
            self.debug.print('unloading', str(tape_int))
            self.unload_tape(tape_int)
        else:
            self.debug.print('tape already empty', str(tape_int))

    def drives_empty(self):
        self.check_inventory()
        return not len(self.drive_ids)

    def drives_loaded(self):
        self.check_inventory()
        if len(self.drive_ids):
            return self.get_drive_tape_ids()
        else:
            return False

    def get_drive_tape_ids(self):
        self.check_inventory()
        return self.drive_ids

    def load_tape(self, tape_id, tape_drive):
        """Load a tape into a free drive slot"""
        if self.tape_ids[tape_id]:
            self.debug.print('Loading - %s' % tape_id)
            output = check_output(['mtx', 'load', str(self.tape_ids[tape_id]), str(tape_drive)])
            self.check_inventory()

    def unload_tape(self, tape_id):
        """Unload a tape from a drive and put in the original slot"""
        if self.drive_ids[tape_id]:
            command = ['mtx', 'unload', self.drive_ids[tape_id][1], self.drive_ids[tape_id][0]]
            self.debug.print('%s' % command)
            output = check_output(command)
            self.check_inventory()

    def write(self, queue_pass):
        """write data to tape"""
        ## tar dir to two drives
        arcname = "paper.%s.%s" % (self.pid, queue_pass)
        tar_name = "/papertape/queue/%s/%s.tar" % (self.pid, arcname)
        catalog_name = "/papertape/queue/%s/%s.list" % (self.pid, arcname)

        self.debug.print("writing", catalog_name, tar_name)
        self.tape_drives.tar_files([catalog_name, tar_name])

    def prep_tape(self, catalog_file):
        """write the catalog to tape. write all of our source code to the first file"""
        ## write catalog
        self.debug.print("writing catalog to tape", catalog_file)
        self.tape_drives.dd(catalog_file)
        ## write source code
        #self.tape_drives.tar('/root/git/papertape')

class MtxDB:
    """db to handle record of label ids

    Field     Type    Null    Key     Default Extra
    id        mediumint(9)    NO      PRI     NULL    auto_increment
    label     char(8) YES             NULL
    date      int(11) YES             NULL
    status    int(11) YES             NULL
    capacity  int(11) YES             NULL

    """

    def __init__(self, credentials, pid, debug=False, debug_threshold=255):
        """Initialize connection and collect list of tape_ids."""

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
        "refresh database connection"
        self.debug.print('updating connection_time')
        self.connection_time = datetime.datetime.now()

    def connection_time_delta(self):
        "return connection age"
        self.debug.print('connection_time:%s' % self.connection_time)
        delta = datetime.datetime.now() - self.connection_time
        return delta.total_seconds()

    def db_connect(self, command=None, credentials=None):
        "connect to the database or reconnect an old session"
        self.debug.print('input:%s %s' % (command, credentials))
        self.credentials = credentials if credentials != None else self.credentials
        time_delta = self.connection_timeout + 1 if command == 'init' else self.connection_time_delta()

        self.debug.print("time_delta:%s, timeout:%s" % (time_delta, self.connection_timeout))
        if time_delta > self.connection_timeout:
            self.debug.print("setting connection %s %s" % (credentials, self.connection_timeout))
            self.connect = pymysql.connect(read_default_file=self.credentials, connect_timeout=self.connection_timeout)
            self.cur = self.connect.cursor()

        self.update_connection_time()
        self.debug.print("connection_time:%s" % (self.connection_time))

    def get_capacity(self, tape_id):
        select_sql = "select capacity from ids where id='%s'" % (tape_id)

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
            claim_query = 'update ids set status="%s" where label="%s"' % (self.pid, tape_id)
            self.debug.print(claim_query)
            self.cur.execute(claim_query)

        self.connect.commit()

    def date_ids(self, ids):
        """write the date of our completed run to tape"""
        date = datetime.datetime.now().strftime('%Y%m%d-%H%M')
        self.db_connect()
        for tape_id in ids:
            self.debug.print('updating mtxdb: %s, %s' % (date, tape_id))
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
    """class to write two tapes"""

    def __init__(self, pid, drive_select=2, debug=False, debug_threshold=128):
        self.pid = pid
        self.debug = Debug(self.pid, debug=debug, debug_threshold=debug_threshold)
        self.drive_select = drive_select

    def tar_files(self, files):
        commands = []
        for drive_int in range(self.drive_select):
            commands.append('tar cf /dev/nst%s  %s ' % (drive_int, ' '.join(files)))
        self.exec_commands(commands)

    def tar(self, file):
        commands = []
        for drive_int in range(self.drive_select):
            commands.append('tar cf /dev/nst%s %s ' % (drive_int, file))
        self.exec_commands(commands)

    def dd(self, text_file):
        commands = []
        for drive_int in range(self.drive_select):
            commands.append('dd conv=sync,block of=/dev/nst%s if=%s bs=32k' % (drive_int, text_file))
        self.exec_commands(commands)

    def dd_read(self, drive_int):
        '''assuming a loaded tape, read off the first block from the tape and 
        return it as a string'''
 
        command = ['dd', 'conv=sync,block', 'if=/dev/nst%s' % drive_int, 'bs=32k', 'count=1']
        self.debug.print('%s' % command)
        output = check_output(command)

        return output


    def md5sum_at_index(self, tape_index, drive_int=0):
        """given a tape_index and drive_int, return the md5sum of the file
        at that index on the tape in /dev/nst$drive_index."""

        self.debug.print("getting md5 of file at %s in drive %s" % (tape_index, drive_int))
        commands = []
        ## the index is stored like: [PAPR1001, PAPR2001]-0:1
        ## the first number gives the file on tape
        ## the second number gives the file on tar
        ## but the tar is inside another tar with the full file table
        ## to get at an indexed file you must do something like:
        ## 
        self.exec_commands(commands)

    def exec_commands(self, cmds):
        ''' Exec commands in parallel in multiple process
        (as much as we have CPU)
        '''
        if not cmds: return # empty list

        def done(process):
            return process.poll() is not None
        def success(p):
            return process.returncode == 0
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


