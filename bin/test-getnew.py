__author__ = 'dconover@sas.upenn.edu'

from paper_db import PaperDB
cred='/home2/obs/.my.papertape-prod.cnf'

x = PaperDB('201611',  cred, 1, debug=False)
#a,b = x.get_new(0)

## print the number of files
#print(len(a))
#print(a)
## print size in MB
#print(b)

b = x.enumerate_paths()
for path in b:
    print(path,b[path])
