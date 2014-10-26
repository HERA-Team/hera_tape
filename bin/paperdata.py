"""PAPER database connector

A database is used to manage the location and disposition of the "PAPER" data.
This module makes a connection to the database to retrieve a list of files that
can be copied to tape, and can be used to update the database once the files
are written to tape.
"""
  
import pymysql
from datetime import datetime
from paper_debug import Debug

class paperdb:

    def __init__ (self, credentials, pid, debug=False):
        """Initialize connection and collect list of files to dump.""" 
        self.pid = pid
        self.debug = Debug(self.pid, debug=debug)

        self.connection_timeout=90
        self.db_connect('init', credentials)
        self.list=[]


    def update_connection_time(self):
        self.connection_time = datetime.now()

    def connection_time_delta(self):
        delta = datetime.now() - self.connection_time 

    def db_connect (self,command, credentials=None):
        self.credentials = credentials if credentials != None else '/root/my.cnf'
        time_delta = self.connection_timeout + 1 if command == 'init' else self.connection_time_delta()
        
        self.debug.print("time_delta:%s" % time_delta)
        if time_delta > self.connection_timeout:
            self.debug.print("setting connction")
            self.connect =  pymysql.connect(read_default_file=credentials, connect_timeout=self.connection_timeout)
            self.cur = self.connect.cursor()
            self.update_connection_time()

    def get_new(self,size_limit):
        """Retrieve a list of available files."""
        ready_sql = """select raw_location,raw_file_size_mb from paperdata
            where raw_location is not null and ready_to_tape = 1 and tape_location='NULL'
            group by raw_location order by obsnum """

        self.cur.execute(ready_sql)
        self.update_connection_time()

        self.list = []
        total = 0
        
        for file_info in self.cur.fetchall():
            self.debug.print('found file - %s' % file_info[0])
            file_size = float(file_info[1]) 
            if file_size > size_limit:
                self.debug.print ('get_new - file_size (%s) larger than size limit(%s) - %s' % (file_size, size_limit, file_info[0]))
            if total+file_size < size_limit:
                self.debug.print('file:', file_info[0])
                self.list.append(file_info[0])
                total += file_size

        return self.list, total
        
    def claim_files (self, status_type, list):
        """Mark files in the database that are "claimed" by a dump process."""
        self.db_connect()
        for file in list:
            host, file_path = file.split(":")
            update_sql = "update paperdata set tape_location='%s%s' where raw_location='%s'" % (status_type, self.pid, file)
            self.debug.print('claim_files - %s' % update_sql)
            self.cur.execute(update_sql)

        self.connect.commit()

    def unclaim_files(self,status_type, list):
        """Release claimed files"""
        self.db_connect()
        for file in list:
            host, file_path = file.split(":")
            update_sql = "update paperdata set tape_location='' where raw_location='%s' and tape_location='%s%s'" % (file, status_type, self.pid)
            self.debug.print("unclaim_files - %s" % update_sql)
            self.cur.execute(update_sql)

    def write_tape_location(self,cumulative_list,tape_id):
        """Take a dictionary of files and labels and update the database

        record the barcode of tape in the tape_location field, and
        setting the delete_file field to 1 for all files just written to tape.
        """

        self.db_connect()
        for archive_info in cumulative_list:
            ## like: [papr1001,papr2001]-132:3:node16:/mnt/MartinVanBuren/psa6262/zen.2456262.54269.uv   
            tape_location = ":".join([tape_id,str(archive_info[0])])
            raw_location = archive_info[1]
            self.debug.print("writing tapelocation: %s for %s" % (tape_location, raw_location))
            self.cur.execute('update paperdata set delete_file=1, tape_location="%s" where raw_location="%s"' % (tape_location, raw_location))

        self.connect.commit()

    def __del__ (self):
        self.connect.commit()
        self.connect.close()
        #self.unclaim_files(1, self.list)


