"""Handle file IO

  This module assumes theres a file node, that mounts the data to be dumped in 
a single directory where subdirs correspond to host:directory paths.

  Transfers are completed using scp 
"""

import os, hashlib, shutil, tarfile
from subprocess import check_output
from paper_paramiko import Transfer
from paper_debug import Debug

class archive:

    def __init__(self,pid, debug=False):
        """Record $PID"""
        self.pid=pid
        self.transfer = Transfer()
        self.archive_dir = self.ensure_dir('/papertape/shm/%s/' % (self.pid))
        self.queue_dir = self.ensure_dir('/papertape/queue/%s/' % (self.pid))
        self.catalog_name = "%s/paper.%s.list" %(self.queue_dir,self.pid)

        self.debug = Debug(self.pid, debug=debug)

    def build_archive(self, list):
        """Copy files to /dev/shm/$PID, create md5sum data for all files"""
        for file in list:
            transfer_path = self.ensure_dir('%s/%s' % (self.archive_dir, file))
            self.debug.print("build_archive - %s" % file)
            self.transfer.scp.get("/papertape/" + file, local_path=transfer_path, recursive=True)
            #self.check_md5(self.archive_dir, file)
        
    def gen_catalog(self, catalog, list, queue_pass):
        cfile = open(catalog, 'w') 
        int = 1
        for file in list:
            cfile.write("%s:%s:%s\n" % (queue_pass, int, file))
            int += 1

    def gen_final_catalog(self, catalog, list):
        cfile = open(catalog, 'w')
        int = 1
        for file in list:
            cfile.write('%s:%s:%s\n' % (file[0], int, file[1]))
        
            
    def queue_archive(self, id, list, queue_pass):
        """move the archive from /dev/shm to a tar file in the queue directory
           once we have 1.5tb of data we will create a catalog and write all the queued
           archives to tape.
        """
        arcname = "%s.%s.%s" % ('paper', self.pid, id)
        tar_name = "%s/%s.tar" % (self.queue_dir, arcname)
        catalog_name = "%s/%s.list" %(self.queue_dir,arcname)

        ## make the tar in the queue_directory
        self.tar_archive(self.archive_dir, arcname, tar_name)

        ## make room for additional transfers
        self.clear_dir(list)

        ## make the catalog
        self.gen_catalog(catalog_name,list, queue_pass)


    def clear_dir (self, list):
        for dir in list:
            shutil.rmtree('%s/%s' % (self.archive_dir, dir))

    def tar_archive(self, source, arcname, destination):
        """create the queued tar for the archive file"""
        tar_archive = tarfile.open(destination, mode='w')
        tar_archive.add(source, arcname=arcname)
        tar_archive.close()

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
        #shutil.rmtree(self.archive_dir)
        pass
