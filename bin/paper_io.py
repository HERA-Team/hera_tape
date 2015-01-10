"""Handle file IO

   This module assumes there is a file node, that mounts the data to be dumped in
   a single directory where sub-dirs correspond to host:directory paths.

   Transfers are completed using scp
"""

import os, hashlib, shutil, tarfile, re, collections, datetime
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

class Archive:
    """Build file archives for tape dumps"""

    def __init__(self, version, pid, debug=False, debug_threshold=255, local_transfer=True):
        """Record $PID"""
        self.version = version
        self.pid = pid
        #self.transfer = LocalTransfer() if local_transfer else Transfer()
        self.transfer = LocalTransfer() if local_transfer else None
        self.archive_dir = self.ensure_dir('/papertape/shm/%s/' % self.pid)
        self.queue_dir = self.ensure_dir('/papertape/queue/%s/' % self.pid)
        self.catalog_name = "{0:s}/paper.{1:s}.list".format(self.queue_dir, self.pid)
        self.tape_ids_filename = "{0:s}/paper.{1:s}.tape_ids.list".format(self.queue_dir, self.pid)
        self.catalog_list = []    ## working list of files to write
        self.cumulative_list = [] ## cumulatice list of written files

        self.debug = Debug(self.pid, debug=debug, debug_threshold=debug_threshold)

    def build_archive(self, file_list, source_select=None):
        """Copy files to /dev/shm/$PID, create md5sum data for all files"""
        for file in file_list:
            transfer_path = '%s/%s' % (self.archive_dir, file)
            self.debug.print("build_archive - %s" % file)
            get("/papertape/" + file, local_path=transfer_path, recursive=True)

    def gen_catalog(self, catalog, file_list, queue_pass):
        """create a catalog file"""
        self.debug.print("intermediate catalog: %s" % catalog)
        with open(catalog, 'w') as cfile:
            pass_int = 1
            self.catalog_list = []
            for file in file_list:
                self.debug.print('catalog_list: %s %s %s' % (queue_pass, pass_int, file), debug_level=249)
                self.catalog_list.append([queue_pass, pass_int, file])
                cfile.write("%s:%s:%s\n" % (queue_pass, pass_int, file))
                pass_int += 1


    def gen_final_catalog(self, catalog, file_list, md5_dict):
        """create a catalog file in /papertape/queue/$pid/$pid.list

        :param catalog: str
        :param file_list: list of [int, int, string]
        """
        self.debug.print('catalog_list - %s' % file_list)

        job_details = " ".join([ 
            self.pid,  
            "(version:", str(self.version),
            "on", datetime.datetime.now().strftime('%Y%m%d-%H%M') + ")",
        ])
       
        preamble_lines = "\n".join([
            "## Paper dump catalog:" + job_details,
            "## This tape contains files as listed below:",
            "## item_index:tape_index:file_index:data_md5:dir_path(host:fullpath)\n"
        ])

        pass_int = 1

        with open(catalog, 'w') as cfile:
            ## write a preamble to describe the contents
            cfile.write(preamble_lines)

            ## write the actual file_list
            for file in file_list:
                self.debug.print("%s - %s" % (catalog, file))
                self.debug.print("file_inf - %s, %s" % (pass_int, file), debug_level=249)

                tar_index = file[0]
                file_index = file[1]
                file_path = file[2]
                data_md5 = md5_dict[file_path]

                ## do we need pass_int?
                catalog_line = [pass_int, tar_index, file_index, data_md5, file_path]
                output = ':'.join(str(x) for x in catalog_line) + "\n"

                cfile.write(output)
                pass_int += 1

    def final_from_file(self, catalog=None, tape_ids=False):
        """gen final catalog from file"""
        self.catalog_list = []
        md5_dict = {}
        pid=''
        item_index=0

        header_line = re.compile('## Paper dump catalog: *([0-9]+)')
        catalog_line = re.compile('([0-9]+):([0-9]+):([0-9]+):([a-f0-9]{32}):(.*)')

        if catalog:
            self.debug.print('reading from string')
            catalog_lines = catalog

        else:
            ## read from file
            self.debug.print('reading from file')
            with open(self.catalog_name, 'r') as file:
                cotalog_lines = file.readlines()

        for line in catalog_lines:
            if catalog_line.match(line):
                ## split the line into groups
                catalog_info = catalog_line.match(line).groups()

                ## the first number is mostly for human consumption
                file_on_tape_number = int(catalog_info[0])

                ## if we add one...
                ## the second number tells us where to find the archive
                item_index = int(catalog_info[1]) + 1

                ## the original catalog looks like the last three entries
                tar_index = int(catalog_info[1])
                file_index = int(catalog_info[2])
                file_path = catalog_info[4]
                md5_dict[file_path] = catalog_info[3]
                catalog_list = [tar_index, file_index, file_path]

                self.catalog_list.append(catalog_list)

            elif header_line.match(line):
                self.debug.print('found header line')
                pid = header_line.match(line).groups()[0]

        return item_index, self.catalog_list, md5_dict, pid

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
        """send tar of file chunks directly to tape."""
        arcname = "%s.%s.%s" % ('paper', self.pid, tape_id)
        tar_name = "%s/%s.tar" % (self.queue_dir, arcname)
        catalog_name = "%s/%s.list" %(self.queue_dir, arcname)

        ## make the tar in the queue_directory
        self.tar_archive(self.archive_dir, arcname, tar_name)

        ## make the catalog
        self.gen_catalog(catalog_name, file_list, tape_id)

    def clear_dir(self, file_list):
        """remove the given diretory tree"""
        for dir_path in file_list:
            shutil.rmtree('%s/%s' % (self.archive_dir, dir_path))

    def tar_archive(self, source, arcname, destination):
        """create the queued tar for the archive file"""
        archive_file = tarfile.open(destination, mode='w')
        archive_file.add(source, arcname=arcname)
        archive_file.close()

    def ensure_dir(self, file_path):
        """make sure the directory exists creating it if necessary"""
        dir_path = os.path.dirname(file_path)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
        return dir_path

    def md5(self, directory_prefix, file_path):
        """return an md5sum for a file"""
        full_path = '%s/%s' % (directory_prefix, file_path)
        hasher = hashlib.md5()
        with open('{0:s}.md5sum'.format(full_path), 'w') as hash_file:
            with open(full_path, 'rb') as open_file:
                buffer = open_file.read()
                hasher.update(buffer)

            hash_file.write('%s\n' % hasher.hexdigest())
        return hasher.hexdigest

    def save_tape_ids(self, tape_ids):
        """open a file and write the tape ids in case writing to the db fails"""

        self.debug.print('saving {0:s} to {1:s}'.format(tape_ids, self.tape_ids_filename))
        tape_id_file = open(self.tape_ids_filename, 'w')
        tape_id_file.write("[{0:s}]\n".format(tape_ids))
        tape_id_file.close()

    def tape_ids_from_file(self):
        """Assuming you init from queued run, read in the tape ids from the
        tape_ids_file"""

        tape_ids = ''
        tape_id_line = re.compile("\[(.*)\]")
        self.debug.print('{0:s}'.format(self.tape_ids_filename), debug_level=128)
        with open(self.tape_ids_filename, 'r') as tape_id_file:
            self.debug.print("opening_file", debug_level=128)
            for line in tape_id_file:
                self.debug.print('{0:s}'.format(line), debug_level=240)
                if tape_id_line.match(line):
                    tape_info = tape_id_line.match(line).groups()
                    tape_ids = tape_info[0]

        id_list = tape_ids.split(",")
        return id_list






