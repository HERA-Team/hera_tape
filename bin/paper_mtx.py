#! /usr/bin/python
#
# handle the tape changer
#
# dconover 20140922

import re, pymysql, time
from random import randint
from subprocess import *
from paper_debug import Debug


def split_mtx_output(mtx_output):
    """Return dictionaries of tape_ids in drives and slots."""
    drive_ids = {}
    tape_slot = {}

    for line in mtx_output.split('\n'):
        drive_line = re.compile('^Data Transfer Element (\d):Full \(Storage Element (\d+) Loaded\):VolumeTag = ([A-Z0-9]{8})')
        storage_line = re.compile('\s+Storage Element (\d+):Full :VolumeTag=([A-Z0-9]{8})')

        if drive_line.match(line):
            """Data Transfer Element 1:Full (Storage Element 1 Loaded):VolumeTag = PAPR1001"""
            drive_info = drive_line.match(line).groups()
            ## dict of storage_slots by tape_id
            drive_ids[drive_info[2]] = drive_info[0:2]

        elif storage_line.match(line):
            """Storage Element 10:Full :VolumeTag=PAPR1010"""
            storage_info = storage_line.match(line).groups()
            ## dict of tapes slots by tape_id
            tape_slot[storage_info[1]] = storage_info[0]

    return drive_ids, tape_slot

class Changer:
    'simple tape changer class'

    def __init__(self, pid, tape_size, debug=False, drive_select=2):
        self.pid = pid
        self.debug = Debug(self.pid, debug=debug)
        self.tape_size = tape_size
        self._tape_dev = '/dev/changer'

        self.drive_ids = []
        self.tape_ids = []

        self.check_inventory()
        self.tape_drives = Drives(drive_select=drive_select)

    def check_inventory(self):
        output = check_output(['mtx', 'status']).decode("utf-8")
        self.debug.print(output)
        self.drive_ids, self.tape_ids = split_mtx_output(output)
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

    def load_tape_drive(self, tape_id, drive=0):
        if self.drives_empty():
            self.debug.print('loading', str(tape_id), str(drive))
            self.load_tape(tape_id, drive)

    def unload_tape_pair(self):
        'unload the tapes in the current drives'
        if not self.drives_empty():
            for tape_id in self.drive_ids:
                self.debug.print('unloading', tape_id)
                self.unload_tape(tape_id)

    def unload_tape_drive(self, id):
        'unload the tapes in the current drives'
        if not self.drives_empty():
            self.debug.print('unloading', id)
            self.unload_tape(id)

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
        self.debug.print("writing", tar_name, catalog_name)
        self.tape_drives.arcwrite(tar_name, catalog_name)

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

    def __init__(self, _credentials, pid, debug=False):
        """Initialize connection and collect list of tape_ids."""

        self.pid = pid
        self.debug = Debug(self.pid, debug=debug)
        self.connect = pymysql.connect(read_default_file=_credentials)
        self.cur = self.connect.cursor()

    def get_capacity(self, tape_id):
        select_sql = "select capacity from ids where id='%s'" % (tape_id)

    def select_ids(self):
        """select lowest matching id pairs"""

        ids = []
        for n in [0, 1]:
            select_sql = "select label from ids where status is null and label like 'PAPR%d%s'" % (n+1, "%")
            self.cur.execute(select_sql)

            #print(self.cur.fetchone()[0])
            ids.append(self.cur.fetchone()[0])
        return ids

    def insert_ids(self, ids):
        """Add new tape_ids to the mtxdb"""
        for label_id in ids:
            insert_sql = "insert into ids (label) values('%s')" % label_id
            print(insert_sql)
            self.cur.execute(insert_sql)

        self.connect.commit()

    def claim_ids(self, ids):
        """Mark files in the database that are "claimed" by a dump process."""
        for tape_id in ids:
            claim_query = 'update ids set status="%s" where label="%s"' % (self.pid, tape_id)
            self.debug.print(claim_query)
            self.cur.execute(claim_query)

        self.connect.commit()

    def write(self, src_directory):
        """take a path like /dev/shm/1003261778 and create a tar archive on two tapes"""

        self.update_unused_capacity()
        pass

    def update_unused_capacity(self, used=None):
        """Write out unused capacity to database."""
        pass

    def __del__(self):
        self.connect.commit()
        self.connect.close()


class Drives:
    """class to write two tapes"""

    def __init__(self, drive_select=2):
        self.drive_select = drive_select
        pass

    def arcwrite(self, file, catalog):
        commands = []
        for int in range(self.drive_select):
            commands.append('tar cf /dev/nst%s  %s %s ' % (int, catalog, file))
        self.exec_commands(commands)

    def tar(self, file):
        commands = []
        for drive_int in range(self.drive_select):
            commands.append('tar cf /dev/nst%s %s ' % (drive_int, file))
        self.exec_commands(commands)

    def dd(self, text_file):
        commands = []
        for drive_int in range(self.drive_select):
            commands.append('dd of=/dev/nst%s if=%s bs=32k' % (drive_int, text_file))
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


