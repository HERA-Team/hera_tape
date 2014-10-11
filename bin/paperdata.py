"""PAPER database connector

A database is used to manage the location and disposition of the "PAPER" data.
This module makes a connection to the database to retrieve a list of files that
can be copied to tape, and can be used to update the database once the files
are written to tape.
"""
  
import pymysql
from paper_debug import debug

class paperdb:

    def __init__ (self, credentials, pid, debug=False):
        """Initialize connection and collect list of files to dump.""" 
        self.pid = pid
        self.connect = pymysql.connect(read_default_file=credentials)
        self.cur = self.connect.cursor()
        self.list=[]
        self.debug = debug(self.pid, debug=debug)

    def get_new(self,size_limit):
        """Retrieve a list of available files."""
        ready_sql = """select raw_location,raw_file_size_mb from paperdata
            where raw_location is not null and ready_to_tape = 1 and tape_location!='NULL'
            group by raw_location order by obsnum """

        self.cur.execute(ready_sql)

        self.list = []
        total = 0
        
        for file_info in self.cur.fetchall():
            file_size = float(file_info[1]) 
            if file_size > size_limit:
                self.debug.print ('get_new - file_size (%s) larger than size limit(%s) - %s' % (file_size, size_limit, file_info[0]))
            if total+file_size < size_limit:
                self.list.append(file_info[0])
                total += file_size

        return self.list, total
        
    def claim_files (self, status_type, list):
        """Mark files in the database that are "claimed" by a dump process."""
        for file in list:
            host, file_path = file.split(":")
            update_sql = "update paperdata set tape_location='%s%s' where raw_location='%s'" % (status_type, self.pid, file)
            self.debug.print('claim_files - %s' % update_sql)
            self.cur.execute(update_sql)

        self.connect.commit()

    def unclaim_files(self,status_type, list):
        """Release claimed files"""
        for file in list:
            host, file_path = file.split(":")
            update_sql = "update paperdata set tape_location='' where raw_location='%s' and tape_location='%s%s'" % (file, status_type, self.pid)
            self.debug.print("unclaim_files - %s" % update_sql)
            self.cur.execute(update_sql)


    def write_tape_location(self,list,tape_id):
        """Take a dictionary of files and labels and update the database

        record the barcode of tape in the tape_location field, and
        setting the delete_file field to 1 for all files just written to tape.
        """

        for file in list:
            self.cur.execute('update paperdata set delete_file=1, tape_location="%s" where raw_location="%s"' % (tape_id, file))

        self.connect.commit()


    def __del__ (self):
        self.connect.commit()
        self.connect.close()
        #self.unclaim_files(1, self.list)


