from paramiko import SSHClient
from scp import SCPClient


class transfer:

   def __init__(self, host='shredder.physics.upenn.edu', key_file='/root/.ssh/cluster.key'):
       self.ssh = SSHClient()
       self.ssh.load_system_host_keys()
       
       self.ssh.connect(host,key_filename=key_file)

       self.scp = SCPClient(self.ssh.get_transport())


   
