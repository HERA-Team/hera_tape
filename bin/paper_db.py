"""PAPER database connector

A database is used to manage the location and disposition of the "PAPER" data.
This module makes a connection to the database to retrieve a list of files that
can be copied to tape, and can be used to update the database once the files
are written to tape.
"""

import pymysql
from datetime import datetime, timedelta
from paper_debug import Debug
from enum import Enum, unique
from paper_status_code import StatusCode

class PaperDB:
    """Paper database contains information on file locations"""

    def __init__(self, version, credentials, pid, status=0, debug=False, debug_threshold=255):
        """Initialize connection and collect list of files to dump.
        :type credentials: string
        :type pid: basestring
        :type status: int
        :type debug: bool
        :type debug_threshold: int
        """

        self.pid = pid
        self.version = version
        self.debug = Debug(self.pid, debug=debug, debug_threshold=debug_threshold)
        self.status_code = StatusCode

        self.paperdb_states = PaperDBStates
        self.paperdb_state = status
        self.connection_timeout = 90
        self.connection_time = timedelta()
        self.credentials = credentials
        self.connect = ''
        self.cur = ''
        self.db_connect('init', credentials)

        self.file_list = []
        self.file_md5_dict = {}

    def __setattr__(self, attr_name, attr_value):
        """debug.output() when a state variable is updated"""
        class_name = self.__class__.__name__.lower()

        ## we always use the lowercase of the class_name in the state variable
        #if attr_name == '{}_state'.format(class_name):
        if attr_name == 'paperdb_state':
            ## debug whenever we update the state variable
            self.debug.output("updating: {} with {}={}".format(class_name, attr_name, attr_value))
        super(self.__class__, self).__setattr__(attr_name, attr_value)

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
        """Retrieve a list of available files.

        Outputs files that are "write_to_tape"
        Optionally, limit search by file_path regex or pid in tape_index

        Arguments:
        :param size_limit: int
        :param regex: str
        """

        if regex:
            ready_sql = """select raw_path, raw_file_size_mb, md5sum from paperdata
                where raw_path is not null
                and write_to_tape = 1 
                and tape_index='NULL'
                and raw_path like '%s'
            """ % regex
        elif pid:
            ready_sql = """select raw_path, raw_file_size_mb, md5sum from paperdata
                where tape_index = 1{0:s}
            """.format(pid)
        else:
            ready_sql = """select raw_path, raw_file_size_mb, md5sum from paperdata
                where raw_path is not null 
                and write_to_tape = 1 
                and tape_index='NULL'
                group by raw_path order by obsnum;
            """

        self.db_connect()
        self.cur.execute(ready_sql)
        self.update_connection_time()

        self.file_list = []
        total = 0

        for file_info in self.cur.fetchall():
            self.debug.output('found file - %s' % file_info[0], debug_level=254)
            file_size = float(file_info[1])
            if file_size > size_limit:
                self.debug.output('file_size (%s) larger than size limit(%s) - %s' % (file_size, size_limit, file_info[0]), debug_level=254)
            if total+file_size < size_limit:
                self.debug.output('file:', file_info[0], debug_level=254)
                self.file_list.append(file_info[0])
                self.file_md5_dict[file_info[0]] = file_info[2]
                total += file_size

        return self.file_list, total

    def claim_files(self, status_type, file_list):
        """Mark files in the database that are "claimed" by a dump process."""
        self.db_connect()
        for file in file_list:
            update_sql = "update paperdata set tape_index='%s%s' where raw_path='%s'" % (status_type, self.pid, file)
            self.debug.output('claim_files - %s' % update_sql)
            self.cur.execute(update_sql)

        self.connect.commit()
        self.paperdb_state = self.paperdb_states.claim

    def unclaim_files(self, status_type, file_list):
        """Release claimed files from database"""
        self.db_connect()
        for file in file_list:
            update_sql = "update paperdata set tape_index='' where raw_path='%s' and tape_index='%s%s'" % (file, status_type, self.pid)
            self.debug.output("unclaim_files - %s" % update_sql)
            self.cur.execute(update_sql)

        self.connect.commit()
        self.paperdb_state = self.paperdb_states.initialize

    def write_tape_index(self, catalog_list, tape_id):
        """Take a dictionary of files and labels and update the database

        record the barcode of tape in the tape_index field, but not
        setting the delete_file field to 1 for all files just written to tape.
        :param catalog_list: dict
        :param tape_id: str
        """

        write_tape_index_status = self.status_code.OK
        self.debug.output("catalog_list contains %s files, and with ids: %s" % (len(catalog_list), tape_id))
        self.db_connect()

        ## catalog list is set in paper_io.py: self.catalog_list.append([queue_pass, int, file])
        for catalog in catalog_list:
            ## tape_index: 20150103[papr1001,papr2001]-132:3
            tape_index = "%s[%s]-%s:%s" % (self.version, tape_id, catalog[0], catalog[1])
            raw_path = catalog[2]
            self.debug.output("writing tapelocation: %s for %s" % (tape_index, raw_path))
            try:
                self.cur.execute('update paperdata set tape_index="%s" where raw_path="%s"' % (tape_index, raw_path))
            except Exception as mysql_error:
                self.debug.ouptput('error {}'.format(mysql_error))
                write_tape_index_status = self.status_code.write_tape_index_mysql

        try:
            self.connect.commit()
        except Exception as mysql_error:
            self.debug.ouptput('error {}'.format(mysql_error))
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
            except MySQLError as mysql_error:
                self.debug.ouptput('Got error {!r}, errno is {}'.format(mysql_error, mysql_error.args[0]))
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
            self.paperdb_states.initialize : '_close',
            self.paperdb_states.claim : '_unclaim',
            self.paperdb_states.claim_queue : '_close',
            self.paperdb_states.claim_write : '_close',
            self.paperdb_states.claim_complete : '_close',
            }

        self.db_connect()
        self.update_connection_time()
        close_action[self.paperdb_state]()
        ## close database connections
        self.cur.close()

    def __del__(self):
        """close out the connection and set the final state in the database"""
        ## TODO(dconover): depending on self.paperdb_state update paperdata
        ## can self.status_type be replaced with self.paperdb_state?
        ## TODO(dconover): implement self.status_type; update paperdb_state="{}{}".format(self.status_type, self.pid)
        ## TODO(dconover): close database; implement self.db_close()
        pass

@unique
class PaperDBStates(Enum):
    """ list of database specific dump states

    This is not to be confused with error codes, which tell the program what
    went wrong. Rather, these states track what clean-up actions should be
    performed, when the object is closed.
    """

    initialize     = 0 ## no file cleanup;                                 action: always close db
    claim          = 1 ## files claimed;                                   action: unclaim files; close db
    claim_queue    = 2 ## claimed files queued;                            action: ignore (?); close db
    claim_write    = 3 ## claimed files written to tape, but not verified; action: ignore (?); close db
    claim_complete = 4 ## claimed files written and verified;              action: files already finalized?; close db


