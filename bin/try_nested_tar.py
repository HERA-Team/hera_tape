"""write a tar inside a tar

https://docs.python.org/3.4/library/tarfile.html
https://docs.python.org/3/library/io.html#io.BytesIO
"""
__author__ = 'dconover@sas.upenn.edu'

import tarfile, io

class RamTar(object):

    def __init__(self):
        self.archive_bytes = io.BytesIO()
        self.tape_bytes = io.BytesIO()
        self.archive_tar = tarfile.open(mode='w:', fileobj=self.archive_bytes)
        self.tape_tar = tarfile.open(mode='w:', fileobj=self.tape_bytes)

    def append_archive_to_tape(self, file_name):
        """append a tar from memory to another tar

        The idea is to write the archive tar in memory, then
        append it to the tar on tape.

        :rtype : object
        :type file_name: basestring
        :param file_name: name we are giving the tar in memory
        :type file_bytes: buffer
        :param file_bytes: io.BytesIO stream of bytes
        :type tarfile_object: object
        :param tarfile_object: the tar to which we should append the new file
        """

        ## we need the name and the size
        archive_info = tarfile.TarInfo(name=file_name)

        ## read in the whole thing
        archive_info.size = len(self.archive_bytes.getvalue())

        ## rewind the stream after getting the bytes
        self.archive_bytes.seek(0)

        ## apend the bytes to the given tar
        self.tape_tar.addfile(tarinfo=archive_info, fileobj=self.archive_bytes)

    def add_sample_data(self):
        """add the same data to the archive tar"""

        self.archive_tar.add('try')
        self.archive_tar.close()

    def add_tape_sample_list(self):
        """add some sample data"""

        self.tape_tar.add('paper_io.py', arcname='file_list')

test = RamTar()
test.add_sample_data()
test.add_tape_sample_list()
test.append_archive_to_tape('archive.1.tar')


print('tape:', test.tape_tar.getnames())


## test open signature
# noinspection PyArgumentList
with open('paper_io.py', mode='r') as x:
    print(len(x.readlines()))



