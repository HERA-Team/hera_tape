"""PAPER database connector

A database is used to manage the location and disposition of the "PAPER" data.
This module makes a connection to the database to retrieve a list of files that
can be copied to tape, and can be used to update the database once the files
are written to tape.
"""

from datetime import datetime, timedelta

import pymysql, subprocess, re
from enum import Enum, unique

from paper_debug import Debug
from paper_status_code import StatusCode


class PaperDB(object):
    """Paper database contains information on file locations"""

    def __init__(self, version, credentials, pid, debug=False, debug_threshold=255):
        """Initialize connection and collect file_list of files to dump.
        :type version: int
        :type credentials: string
        :type pid: basestring
        :type debug: bool
        :type debug_threshold: int
        """

        self.pid = pid
        self.version = version
        self.debug = Debug(self.pid, debug=debug, debug_threshold=debug_threshold)
        self.status_code = StatusCode

        self.paperdb_state_code = PaperDBStateCode
        self.paperdb_state = self.paperdb_state_code.initialize
        self.connection_timeout = 90
        self.connection_time = timedelta()
        self.credentials = credentials
        self.connect = ''
        self.cur = ''
        self.db_connect('init', credentials)

        self.file_list = []
        self.file_md5_dict = {}
        self.claimed_files = []
        self.claimed_state = 0

    def __setattr__(self, attr_name, attr_value):
        """debug.output() when a state variable is updated"""
        class_name = self.__class__.__name__.lower()

        ## we always use the lowercase of the class_name in the state variable
        if attr_name == 'paperdb_state':
            ## debug whenever we update the state variable
            self.debug.output("updating: {} with {}={}".format(class_name, attr_name, attr_value))

        super().__setattr__(attr_name, attr_value)

    def update_connection_time(self):
        """refresh database connection time"""
        self.debug.output('updating connection_time')
        self.connection_time = datetime.now()

    def connection_time_delta(self):
        """return connection age"""
        self.debug.output('connection_time:%s' % self.connection_time)
        delta = datetime.now() - self.connection_time
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

    def get_new(self, size_limit, regex=False, pid=False):
        """Retrieve a file_list of available files.

        Outputs files that are "write_to_tape"
        Optionally, limit search by file_path regex or pid in tape_index

        Arguments:
        :param size_limit: int
        :param regex: str
        """

        if regex:
            ready_sql = """select source, filesize, md5sum from File
                where source is not null
                and filetype = 'uv'
                and is_tapeable = 1 
                and tape_index is null
                and source like '%s'
            """ % regex
        elif pid:
            ready_sql = """select source, filesize, md5sum from File
                where tape_index = 1{0:s}
            """.format(pid)
        else:
            ready_sql = """select source, filesize, md5sum from File
                where source is not null 
                and filetype = 'uv'
                and is_tapeable = 1 
                and tape_index is null
                group by source order by obsnum;
            """

        self.db_connect()
        self.cur.execute(ready_sql)
        self.update_connection_time()

        self.file_list = []
        total = 0

        for file_info in self.cur.fetchall():
            self.debug.output('found file - %s' % file_info[0], debug_level=254)
            file_size = float(file_info[1])

            ## when size_limit is set to 0, change limit to 1 plus total + file_size
            if size_limit == 0:
                size_limit = total + file_size + 1

            ## if the reported size is larger than the size limit we have a problem
            if file_size > size_limit:
                self.debug.output('file_size (%s) larger than size limit(%s) - %s' % (file_size, size_limit, file_info[0]), debug_level=254)

            ## check that we don't go over the limit
            if total+file_size < size_limit:
                self.debug.output('file:', file_info[0], debug_level=254)
                self.file_list.append(file_info[0])
                self.file_md5_dict[file_info[0]] = file_info[2]
                total += file_size

        return self.file_list, total

    def enumerate_paths(self):
        ## run query with no size limit
        ## remove "is_tapeable=1"
        ready_sql = """select source from File
                        where source is not null
                        and filetype = 'uv'
                        /* and is_tapeable = 1 */
                        and tape_index is null
                        group by source order by obsnum;
                    """

        self.db_connect()
        self.cur.execute(ready_sql)
        self.update_connection_time()

        count=0
        dir_list = {}
        for file_info in self.cur.fetchall():
            ## parse paths
            ## like $host:/{mnt/,}$base/$subpath/$file
            path_regex = re.compile(r'(.*:)(/mnt/|/)(\w+)/')
            path_info = path_regex.match(file_info[0]).groups()
            base_path = path_info[0] + path_info[1] + path_info[2]
            dir_list[base_path] = dir_list[base_path] + 1 if base_path in dir_list else 0

        ## return array
        return dir_list

    def claim_files(self, file_list=None, unclaim=False):
        """Mark files in the database that are "claimed" by a dump process."""

        status_type = self.paperdb_state.value
        ## if no file_list is passed assume we are updating existing file_list
        if file_list is None:
            file_list = self.claimed_files

        claim_files_status = self.status_code.OK
        self.db_connect()

        ## build an sql to unclaim the given files
        for file_name in file_list:

            if unclaim is True:
                update_sql = "update File set tape_index=null where source='%s' and tape_index='%s%s'" % (file_name, status_type, self.pid)
            else:
                ## TODO(dconover): allow claim to use current state
                status_type = self.paperdb_state_code.claim.value
                update_sql = "update File set tape_index='%s%s' where source='%s'" % (status_type, self.pid, file_name)

            self.debug.output('claim_files - %s' % update_sql)
            try:
                self.cur.execute(update_sql)
            except Exception as mysql_error:
                self.debug.output('mysql_error {}'.format(mysql_error))
                claim_files_status = self.status_code.claim_files_sql_build

        ## run the actual sql to unclaim the files
        try:
            self.connect.commit()
            self.claimed_state = status_type
            self.claimed_files.extend(file_list)
        except Exception as mysql_error:
            self.debug.output('mysql_error {}'.format(mysql_error))
            claim_files_status = self.status_code.claim_files_sql_commit

        self.paperdb_state = self.paperdb_state_code.claim
        return claim_files_status

    def unclaim_files(self, file_list=None):
        """Release claimed files from database
        :rtype : bool
        """

        self.claim_files(file_list, unclaim=True)

    def write_tape_index(self, tape_list, tape_id):
        """Take a dictionary of files and labels and update the database

        record the barcode of tape in the tape_index field, but not
        setting the is_deletable field to 1 for all files just written to tape.
        :param tape_list: dict
        :param tape_id: str
        """

        write_tape_index_status = self.status_code.OK
        self.debug.output("tape_list contains %s files, and with ids: %s" % (len(tape_list), tape_id))
        self.db_connect()

        ## item file_list is set in paper_io.py: self.tape_list.append([queue_pass, int, file])
        for item in tape_list:
            ## tape_index: 20150103[PAPR2001,PAPR2001]-132:3
            tape_index = "%s[%s]-%s:%s" % (self.version, tape_id, item[0], item[1])
            source = item[2]
            self.debug.output("writing tape_index: %s for %s" % (tape_index, source))
            try:
                self.cur.execute('update File set tape_index="%s", is_deletable=1 where source="%s"' % (tape_index, source))
            except Exception as mysql_error:
                self.debug.output('error {}'.format(mysql_error))
                write_tape_index_status = self.status_code.write_tape_index_mysql

        try:
            self.connect.commit()
        except Exception as mysql_error:
            self.debug.output('error {}'.format(mysql_error))
            write_tape_index_status = self.status_code.write_tape_index_mysql

        return write_tape_index_status

    def check_tape_locations(self, catalog_list, tape_id):
        """Take a dictionary of files and labels and confirm existence of files on tape.

        :param catalog_list: dict
        :param tape_id: str
        """

        pass


    def close_paperdb(self):
        """depending on state clean-up file claims"""

        def _close():
            """close the database leave any files in place
            :rtype : bool
            """

            _close_status = True
            try:
                ## close database connections
                self.cur.close()
            except Exception as mysql_error:
                self.debug.output('mysql error {}'.format(mysql_error))
                _close_status = False

            return _close_status

        def _unclaim():
            """unlcaim files in database; close database
            :rtype : bool
            """
            _unclaim_status = True
            self.unclaim_files()
            return _close()

        close_action = {
            self.paperdb_state_code.initialize : _close,
            self.paperdb_state_code.claim : _unclaim,
            self.paperdb_state_code.claim_queue : _close,
            self.paperdb_state_code.claim_write : _close,
            self.paperdb_state_code.claim_verify : _close,
            }

        self.db_connect()
        self.update_connection_time()
        close_action[self.paperdb_state]()

    def __del__(self):
        """close out the connection and set the final state in the database"""
        ## TODO(dconover): depending on self.paperdb_state update paperdata
        ## can self.status_type be replaced with self.paperdb_state?
        ## TODO(dconover): implement self.status_type; update paperdb_state="{}{}".format(self.status_type, self.pid)
        ## TODO(dconover): close database; implement self.db_close()
        pass


# noinspection PyClassHasNoInit
@unique
class PaperDBStateCode(Enum):
    """ file_list of database specific dump states

    This is not to be confused with error codes, which tell the program what
    went wrong. Rather, these states track what clean-up actions should be
    performed, when the object is closed.
    """

    initialize     = 0 ## no file cleanup;                                 action: always close db
    claim          = 1 ## files claimed;                                   action: unclaim files; close db
    claim_queue    = 2 ## claimed files queued;                            action: ignore (?); close db
    claim_write    = 3 ## claimed files written to tape, but not verified; action: ignore (?); close db
    claim_verify   = 4 ## claimed files written and verified;              action: files already finalized?; close db

class TestPaperDB(PaperDB):
    """load test data into database for quick testing"""

    def py_load_sample_data(self, sample_sql_file):
        """load the sample data"""
        load_sample_data_status = True
        db_name = self.connect.db
        if db_name != b'paperdatatest':
            self.debug.output('found bad database name'.format(db_name))
            return False


            ## load the sample_sql_file data into the database
        with open(sample_sql_file) as open_sql:
            try:
                line_number = 0
                for line in open_sql:
                    line_number +=1
                    if line_number < 10:
                        self.debug.output('line - {}'.format(line), debug_level=250)
                    self.cur.execute(line)

                self.connect.commit()
                self.debug.output('data loaded')
            except Exception as mysql_error:
                self.debug.output('mysql_error {}'.format(mysql_error))
                load_sample_data_status = False

        return load_sample_data_status

    def load_sample_data(self):
        """load the sample data"""
        load_sample_data_status = True

        db_name = self.connect.db
        if db_name != b'paperdatatest':
            self.debug.output('bad database_name'.format(db_name))
            return False

        try:
            subprocess.Popen('mysql paperdatatest <paperdatatest.blank.sql', shell=True)
        except Exception as cept:
            self.debug.output('{}'.format(cept))
            load_sample_data_status = False

        return load_sample_data_status


