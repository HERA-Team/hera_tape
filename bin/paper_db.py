"""PAPER database connector

A database is used to manage the location and disposition of the "PAPER" data.
This module makes a connection to the database to retrieve a list of files that
can be copied to tape, and can be used to update the database once the files
are written to tape.
"""

import pymysql
from datetime import datetime
from paper_debug import Debug

class PaperDB:
    """Paper database contains information on file locations"""

    def __init__(self, version, credentials, pid, status=0, debug=False, debug_threshold=255):
        """Initialize connection and collect list of files to dump.
        :type credentials: string
        :type pid: int
        :type status: int
        :type debug: bool
        :type debug_threshold: int
        """

        self.version = version
        self.pid = pid
        self.debug = Debug(self.pid, debug=debug, debug_threshold=debug_threshold)

        self.status = status
        self.connection_timeout = 90
        self.connection_time = 0
        self.credentials = credentials
        self.connect = ''
        self.cur = ''
        self.db_connect('init', credentials)

        self.file_list = []
        self.file_md5_dict = {}

    def update_connection_time(self):
        """refresh database connection time"""
        self.debug.print('updating connection_time')
        self.connection_time = datetime.now()

    def connection_time_delta(self):
        """return connection age"""
        self.debug.print('connection_time:%s' % self.connection_time)
        delta = datetime.now() - self.connection_time
        return delta.total_seconds()

    def db_connect(self, command=None, credentials=None):
        """connect to the database or reconnect an old session"""
        self.debug.print('input:%s %s' % (command, credentials))
        self.credentials = credentials if credentials is not None else self.credentials
        time_delta = self.connection_timeout + 1 if command == 'init' else self.connection_time_delta()

        self.debug.print("time_delta:%s, timeout:%s" % (time_delta, self.connection_timeout))
        if time_delta > self.connection_timeout:
            self.debug.print("setting connection %s %s" % (credentials, self.connection_timeout))
            self.connect = pymysql.connect(read_default_file=self.credentials, connect_timeout=self.connection_timeout)
            self.cur = self.connect.cursor()

        self.update_connection_time()
        self.debug.print("connection_time:%s" % self.connection_time)

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
            self.debug.print('found file - %s' % file_info[0], debug_level=254)
            file_size = float(file_info[1])
            if file_size > size_limit:
                self.debug.print('file_size (%s) larger than size limit(%s) - %s' % (file_size, size_limit, file_info[0]), debug_level=254)
            if total+file_size < size_limit:
                self.debug.print('file:', file_info[0], debug_level=254)
                self.file_list.append(file_info[0])
                self.file_md5_dict[file_info[0]] = file_info[2]
                total += file_size

        return self.file_list, total

    def claim_files(self, status_type, file_list):
        """Mark files in the database that are "claimed" by a dump process."""
        self.db_connect()
        for file in file_list:
            update_sql = "update paperdata set tape_index='%s%s' where raw_path='%s'" % (status_type, self.pid, file)
            self.debug.print('claim_files - %s' % update_sql)
            self.cur.execute(update_sql)

        self.connect.commit()
        self.status = 1

    def unclaim_files(self, status_type, file_list):
        """Release claimed files from database"""
        self.db_connect()
        for file in file_list:
            update_sql = "update paperdata set tape_index='' where raw_path='%s' and tape_index='%s%s'" % (file, status_type, self.pid)
            self.debug.print("unclaim_files - %s" % update_sql)
            self.cur.execute(update_sql)

        self.connect.commit()
        self.status = 0

    def write_tape_index(self, catalog_list, tape_id):
        """Take a dictionary of files and labels and update the database

        record the barcode of tape in the tape_index field, but not
        setting the delete_file field to 1 for all files just written to tape.
        :param catalog_list: dict
        :param tape_id: str
        """

        self.debug.print("catalog_list contains %s files, and with ids: %s" % (len(catalog_list), tape_id))
        self.db_connect()

        ## catalog list is set in paper_io.py: self.catalog_list.append([queue_pass, int, file])
        for catalog in catalog_list:
            ## tape_index: 20150103[papr1001,papr2001]-132:3
            tape_index = "%s[%s]-%s:%s" % (self.version, tape_id, catalog[0], catalog[1])
            raw_path = catalog[2]
            self.debug.print("writing tapelocation: %s for %s" % (tape_index, raw_path))
            self.cur.execute('update paperdata set tape_index="%s" where raw_path="%s"' % (tape_index, raw_path))

        self.connect.commit()

    def check_tape_locations(self, catalog_list, tape_id):
        """Take a dictionary of files and labels and confirm existence of files on tape.

        :param catalog_list: dict
        :param tape_id: str
        """

        pass




