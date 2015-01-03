"""use paramiko to scp files from remote host"""

from paramiko import SSHClient
from scp import SCPClient


class Transfer:
    """Implemnet scp"""

    default_host = 'shredder.physics.upenn.edu'
    default_key = '/root/.ssh/cluster.key'

    def __init__(self, host=default_host, key_file=default_key):
        """initaliaze connection with host=default_host, key_file=default_key"""

        self.ssh = SSHClient()
        self.ssh.load_system_host_keys()

        self.ssh.connect(host, key_filename=key_file)

        self.scp = SCPClient(self.ssh.get_transport())



