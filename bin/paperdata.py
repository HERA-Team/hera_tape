"""PAPER database connector

A database is used to manage the location and disposition of the "PAPER" data.
This module makes a connection to the database to retrieve a list of files that
can be copied to tape, and can be used to update the database once the files
are written to tape.
"""
  
import pymysql

class paperdb:

    def __init__ (self, credentials, pid):
        """Initialize connection and collect list of files to dump.""" 
        self.pid = pid
        self.connect = pymysql.connect(read_default_file=credentials)
        self.cur = self.connect.cursor()


    def get_new(self,size_limit):
        """Retrieve a list of available files."""
        ready_sql = """select host,raw_location, file_size from paperdata
            where raw_location is not null and ready_to_tape = 1 
            order by obsnum limit 1,20"""

        self.cur.execute(ready_sql)

        list = []
        total = 0
        
        for file_info in self.cur.fetchall():
            file_size = float(file_info[2].split("M")[0]) 
            if total+file_size < size_limit:
                list.append(":".join(file_info[0:2]))
                total += float(file_info[2].split("M")[0]) 

        return list
        
    def claim_files (self, status_type, list):
        """Mark files in the database that are "claimed" by a dump process."""
        for file in list:
            host, file_path = file.split(":")
            update_sql = "update paperdata set tape_location='1%s' where host='%s' and raw_location='%s'" % (self.pid, host, file_path)
            print(update_sql)
            self.cur.execute(update_sql)

        self.connect.commit()

    def write_tape_location(self,list,tape_id):
        """Take a dictionary of files and labels and update the database

        record the barcode of tape in the tape_location field, and
        setting the delete_file field to 1 for all files just written to tape.
        """

        for file in list:
            self.cur.execute('update paperdata set delete_file = 1, tape_location = "%s" where raw_location = "%s"' % (tape_id, file))

        self.cur.commit()


    def __del__ (self):
        self.cur.close()
        self.connect.close()


