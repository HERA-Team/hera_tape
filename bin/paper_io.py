"""Handle file IO

  This module assumes theres a file node, that mounts the data to be dumped in 
a single directory where subdirs correspond to host:directory paths.

  Transfers are completed using scp 
"""

import os, hashlib, shutil
from subprocess import check_output
from paper_paramiko import transfer

class archive():

    def __init__(self,pid):
        """Record $PID"""
        self.pid=pid
        self.transfer = transfer()
        self.archive_dir = self.ensure_dir('/dev/shm/%s/' % (self.pid))

    def build_archive(self, list):
        """Copy files to /dev/shm/$PID, create md5sum data for all files"""
        for file in list:
            transfer_path = self.ensure_dir('%s/%s' % (self.archive_dir, file))
            self.transfer.scp.get("/papertape/" + file, local_path=transfer_path)
            self.md5(self.archive_dir, file)

    def ensure_dir(self, file):
        dir = os.path.dirname(file)
        if not os.path.exists(dir):
            os.makedirs(dir)
        return dir


    def md5(self, directory_prefix, file):
        full_path = '%s/%s' % (directory_prefix, file)
        hasher = hashlib.md5()
        with open('%s.md5sum' % (full_path), 'w') as hash_file:
            with open(full_path, 'rb') as open_file:
                buffer = open_file.read()
                hasher.update(buffer)
         
            hash_file.write('%s\n' % hasher.hexdigest())
        return hasher.hexdigest
    
    def __del__ (self):
        shutil.rmtree(self.archive_dir)
