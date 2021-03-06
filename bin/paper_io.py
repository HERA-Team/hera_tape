"""Handle file IO

   This module assumes there is a file node, that mounts the data to be dumped in
   a single directory where sub-dirs correspond to host:directory paths.

   Transfers are completed using scp
"""

import os
import shutil
import tarfile
import re
import datetime

import hashlib
#from paper_paramiko import Transfer
from paper_debug import Debug


def get(src_dir, local_path='/dev/null', recursive=True):
    """Get the given file"""
    shutil.copytree(src_dir, local_path)



class LocalScp:
    """special class to redefine scp when transfers are only local"""
    def __init__(self):
        pass

    ## self.transfer.scp.get("/papertape/" + file, local_path=transfer_path, recursive=True)


class LocalTransfer:
    """special class to implement local scp"""

    def __init__(self):
        self.scp = LocalScp()
        pass


class Archive(object):
    """Build file archives for tape dumps"""

    def __init__(self, version, pid, debug=False, debug_threshold=255, local_transfer=True):
        """Archive file and tar management

        :type version: int
        :type pid: basestring
        :type local_transfer: bool
        :type debug_threshold: int
        :type debug: bool
        :type self: object
        """

        self.pid = pid
        self.debug = Debug(self.pid, debug=debug, debug_threshold=debug_threshold)

        self.version = version
        #self.transfer = LocalTransfer() if local_transfer else Transfer()
        self.transfer = LocalTransfer() if local_transfer else None

        dir_status, self.archive_copy_dir = self.ensure_dir('/papertape/shm/%s/' % self.pid)
        dir_status, self.queue_dir = self.ensure_dir('/papertape/queue/%s/' % self.pid)

        if dir_status is not True:
            self.debug.output('data dir init failed')
            raise Exception

        self.catalog_name = "{0:s}/paper.{1:s}.file_list".format(self.queue_dir, self.pid)
        self.tape_ids_filename = "{0:s}/paper.{1:s}.tape_ids.file_list".format(self.queue_dir, self.pid)
        self.archive_list = []    ## working file_list of files to write
        self.tape_list = []       ## cumulative file_list of written files
        self.item_index = 0       ## number of file path index (human readable line numbers in catalog)
        self.archive_state = 0    ## current archive state


    def __setattr__(self, attr_name, attr_value):
        """debug.output() when a state variable is updated"""
        class_name = self.__class__.__name__.lower()

        ## we always use the lowercase of the class_name in the state variable
        if attr_name == '{}_state'.format(class_name):
            ## debug whenever we update the state variable
            self.debug.output("updating: {} with {}={}".format(class_name, attr_name, attr_value))
        super(self.__class__, self).__setattr__(attr_name, attr_value)

    def ensure_dir(self, file_path):
        """make sure the directory exists creating it if necessary
        :param file_path: path to make if it doesn't already exist
        :type file_path: str
        """

        ensure_dir_status = True
        dir_path = os.path.dirname(file_path)
        if not os.path.exists(dir_path):
            try:
                os.makedirs(dir_path)
            except Exception as error:
                self.debug.output('mkdir error {}'.format(error))
                ensure_dir_status = False

        return ensure_dir_status, dir_path

    def build_archive(self, file_list, source_select=None):
        """Copy files to /dev/shm/$PID, create md5sum data for all files"""
        for file_name in file_list:
            transfer_path = '%s/%s' % (self.archive_copy_dir, file_name)
            self.debug.output("build_archive - %s" % file_name)
            get("/papertape/" + file_name, local_path=transfer_path, recursive=True)

    def gen_catalog(self, archive_catalog_file, file_list, tape_index):
        """create a catalog file_name"""
        self.debug.output("intermediate catalog: %s" % archive_catalog_file)
        # noinspection PyArgumentList
        with open(archive_catalog_file, mode='w') as cfile:
            archive_index = 1
            self.archive_list = []
            for file_name in file_list:
                self.debug.output('archive_list: %s %s %s' % (tape_index, archive_index, file_name), debug_level=249)
                self.archive_list.append([tape_index, archive_index, file_name])
                cfile.write("%s:%s:%s\n" % (tape_index, archive_index, file_name))
                archive_index += 1


    def gen_final_catalog(self, tape_catalog_file, tape_list, md5_dict):
        """create a catalog file in /papertape/queue/$pid/$pid.file_list

        :param tape_catalog_file: str
        :param tape_list: file_list of [int, int, string]
        """
        self.debug.output('tape_list - %s' % tape_list)

        job_details = " ".join([ 
            self.pid,  
            "(version:", str(self.version),
            "on", datetime.datetime.now().strftime('%Y%m%d-%H%M') + ")",
        ])
       
        preamble_lines = "\n".join([
            "## Paper dump catalog:" + job_details,
            "## This tape contains files as listed below:",
            "## item_index:tape_index:archive_index:data_md5:dir_path(host:fullpath)\n"
        ])

        self.item_index = 1

        with open(tape_catalog_file, mode='w') as cfile:
            ## write a preamble to describe the contents
            cfile.write(preamble_lines)

            ## write the actual tape_list
            for file_path in tape_list:
                self.debug.output("%s - %s" % (tape_catalog_file, file_path))
                self.debug.output("file_inf - %s, %s" % (self.item_index, file_path), debug_level=249)

                ## which archive on tape has the file_path
                tape_index = file_path[0]
                ## where on the archive is the file_path
                archive_index = file_path[1]
                ## what is the file_path
                file_path = file_path[2]
                ## what is the md5sum of the file_path/visdata_file
                data_md5 = md5_dict[file_path]

                ## We don't actually need the item_index; it is a convenience to the user
                ## when reading the catalog
                catalog_line = [self.item_index, tape_index, archive_index, data_md5, file_path]
                output = ':'.join(str(x) for x in catalog_line) + "\n"

                ## write the tape_catalog to a file
                cfile.write(output)
                self.item_index += 1

            self.item_index -= 1

    def final_from_file(self, catalog=None, tape_ids=False):
        """gen final catalog from file_name"""
        self.archive_list = []
        md5_dict = {}
        pid=''
        item_index=0

        ## catalog includes a human readable preamble with dump info
        ## and numbered lines of items like:
        ## "item_index:tape_index:archive_index:visdata_md5sum:directory_path"
        header_line = re.compile('## Paper dump catalog:([0-9]+)')
        catalog_line = re.compile('([0-9]+):([0-9]+):([0-9]+):([a-f0-9]{32}):(.*)')

        if catalog:
            self.debug.output('reading from string')
            catalog_lines = catalog

        else:
            ## read from file_name
            self.debug.output('reading from file_name')
            with open(self.catalog_name, mode='r') as file_name:
                catalog_lines = file_name.readlines()

        for line in catalog_lines:
            if catalog_line.match(line):
                ## split the line into groups
                catalog_info = catalog_line.match(line).groups()

                ## the first number is mostly for human consumption
                item_index = int(catalog_info[0])

                ## the original catalog looks like the last three entries
                tape_index = int(catalog_info[1])
                archive_index = int(catalog_info[2])
                file_path = catalog_info[4]
                md5_dict[file_path] = catalog_info[3]

                catalog_list = [tape_index, archive_index, file_path]

                self.archive_list.append(catalog_list)

            elif header_line.match(line):
                self.debug.output('found header line')
                pid = header_line.match(line).groups()[0]

        return item_index, self.archive_list, md5_dict, pid

    def queue_archive(self, tape_index, file_list):
        """move the archive from /dev/shm to a tar file in the queue directory
           once we have 1.5tb of data we will create a catalog and write all the queued
           archives to tape.
        """
        arcname = "%s.%s.%s" % ('paper', self.pid, tape_index)
        tar_name = "%s/%s.tar" % (self.queue_dir, arcname)
        catalog_name = "%s/%s.file_list" %(self.queue_dir, arcname)

        ## make the tar in the queue_directory
        self.tar_archive(self.archive_copy_dir, arcname, tar_name)

        ## make room for additional transfers
        self.rm_archive_copy_dir_list(file_list)

        ## make the catalog
        self.gen_catalog(catalog_name, file_list, tape_index)


    def tar_fast_archive(self, tape_id, file_list):
        """send tar of file chunks directly to tape."""
        arcname = "%s.%s.%s" % ('paper', self.pid, tape_id)
        tar_name = "%s/%s.tar" % (self.queue_dir, arcname)
        catalog_name = "%s/%s.file_list" %(self.queue_dir, arcname)

        ## make the tar in the queue_directory
        self.tar_archive(self.archive_copy_dir, arcname, tar_name)

        ## make the catalog
        self.gen_catalog(catalog_name, file_list, tape_id)

    def rm_archive_copy_dir_list(self, file_list):
        """remove the given directory tree of files that have been copied into
        the temporary archive_copy_dir

        :param file_list: file_list of files
        :type  file_list: list
        """
        for dir_path in file_list:
            shutil.rmtree('%s/%s' % (self.archive_copy_dir, dir_path))

    def tar_archive(self, source, arcname, destination):
        """create the queued tar for the archive file"""
        archive_file = tarfile.open(destination, mode='w')
        archive_file.add(source, arcname=arcname)
        archive_file.close()

    def md5(self, directory_prefix, file_path):
        """return an md5sum for a file"""
        full_path = '%s/%s' % (directory_prefix, file_path)
        hasher = hashlib.md5()
        with open('{}.md5sum'.format(full_path), mode='w') as hash_file:
            with open(full_path, mode='rb') as open_file:
                file_buffer = open_file.read()
                hasher.update(file_buffer)

            hash_file.write('%s\n' % hasher.hexdigest())
        return hasher.hexdigest

    def save_tape_ids(self, tape_ids):
        """open a file and write the tape ids in case writing to the db fails"""

        self.debug.output('saving {0:s} to {1:s}'.format(tape_ids, self.tape_ids_filename))
        tape_id_file = open(self.tape_ids_filename, mode='w')
        tape_id_file.write("[{0:s}]\n".format(tape_ids))
        tape_id_file.close()

    def tape_ids_from_file(self):
        """Assuming you init from queued run, read in the tape ids from the
        tape_ids_file"""

        tape_ids = ''
        tape_id_line = re.compile("\[(.*)\]")
        self.debug.output('{0:s}'.format(self.tape_ids_filename), debug_level=128)
        with open(self.tape_ids_filename, mode='r') as tape_id_file:
            self.debug.output("opening_file", debug_level=128)
            for line in tape_id_file:
                self.debug.output('{0:s}'.format(line), debug_level=240)
                if tape_id_line.match(line):
                    tape_info = tape_id_line.match(line).groups()
                    tape_ids = tape_info[0]

        id_list = tape_ids.split(",")
        return id_list

    def close_archive(self):
        """release any locks from the changer"""
        pass




