"""Handle file IO

   This module assumes theres a file node, that mounts the data to be dumped in
   a single directory where subdirs correspond to host:directory paths.

   Transfers are completed using scp
"""

import os, hashlib, shutil, tarfile
#from paper_paramiko import Transfer
from paper_debug import Debug

class LocalScp:
    "special class to redefine scp when transfers are only local"
    def __init__(self):
        pass

    ## self.transfer.scp.get("/papertape/" + file, local_path=transfer_path, recursive=True)
    def get(self, src_dir, local_path='/dev/null', recursive=True):
        shutil.copytree(src_dir, local_path)

class LocalTransfer:
    "special class to implement local scp"

    def __init__(self):
        self.scp = LocalScp()
        pass

class Archive:
    "Build file archives for tape dumps"

    def __init__(self, pid, debug_level=False, local_transfer=True):
        """Record $PID"""
        self.pid = pid
        #self.transfer = LocalTransfer() if local_transfer else Transfer()
        self.transfer = LocalTransfer() if local_transfer else None
        self.archive_dir = self.ensure_dir('/papertape/shm/%s/' % (self.pid))
        self.queue_dir = self.ensure_dir('/papertape/queue/%s/' % (self.pid))
        self.catalog_name = "%s/paper.%s.list" %(self.queue_dir, self.pid)
        self.catalog_list = []

        self.debug = Debug(self.pid, debug_level)

    def build_archive(self, file_list, source_select=None):
        """Copy files to /dev/shm/$PID, create md5sum data for all files"""
        for file in file_list:
            transfer_path = '%s/%s' % (self.archive_dir, file)
            self.debug.print("build_archive - %s" % file)
            self.transfer.scp.get("/papertape/" + file, local_path=transfer_path, recursive=True)

    def gen_catalog(self, catalog, list, queue_pass):
        cfile = open(catalog, 'w')
        pass_int = 1
        self.catalog_list = []
        for file in list:
            self.catalog_list.append([queue_pass, pass_int, file])
            cfile.write("%s:%s:%s\n" % (queue_pass, pass_int, file))
            pass_int += 1

    def gen_final_catalog(self, catalog, list):
        cfile = open(catalog, 'w')
        pass_int = 1
        for file in list:
            cfile.write('%s:%s:%s\n' % (file[0], pass_int, file[1]))


    def queue_archive(self, tape_id, file_list):
        """move the archive from /dev/shm to a tar file in the queue directory
           once we have 1.5tb of data we will create a catalog and write all the queued
           archives to tape.
        """
        arcname = "%s.%s.%s" % ('paper', self.pid, tape_id)
        tar_name = "%s/%s.tar" % (self.queue_dir, arcname)
        catalog_name = "%s/%s.list" %(self.queue_dir, arcname)

        ## make the tar in the queue_directory
        self.tar_archive(self.archive_dir, arcname, tar_name)

        ## make room for additional transfers
        self.clear_dir(file_list)

        ## make the catalog
        self.gen_catalog(catalog_name, file_list, tape_id)


    def tar_fast_archive(self, tape_id, file_list):
        "send tar of file chunks directly to tape."
        arcname = "%s.%s.%s" % ('paper', self.pid, tape_id)
        tar_name = "%s/%s.tar" % (self.queue_dir, arcname)
        catalog_name = "%s/%s.list" %(self.queue_dir, arcname)

        ## make the tar in the queue_directory
        self.tar_archive(self.archive_dir, arcname, tar_name)

        ## make the catalog
        self.gen_catalog(catalog_name, file_list, tape_id)

    def clear_dir(self, file_list):
        for dir_path in file_list:
            shutil.rmtree('%s/%s' % (self.archive_dir, dir_path))

    def tar_archive(self, source, arcname, destination):
        """create the queued tar for the archive file"""
        archive_file = tarfile.open(destination, mode='w')
        archive_file.add(source, arcname=arcname)
        archive_file.close()

    def ensure_dir(self, file_path):
        dir_path = os.path.dirname(file_path)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
        return dir_path

    def md5(self, directory_prefix, file_path):
        full_path = '%s/%s' % (directory_prefix, file_path)
        hasher = hashlib.md5()
        with open('%s.md5sum' % (full_path), 'w') as hash_file:
            with open(full_path, 'rb') as open_file:
                buffer = open_file.read()
                hasher.update(buffer)

            hash_file.write('%s\n' % hasher.hexdigest())
        return hasher.hexdigest

    def __del__(self):
        #shutil.rmtree(self.archive_dir)
        pass






