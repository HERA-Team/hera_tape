# parallel verification of written tapes

owner: dconover:20170128:20170221    
review: optional

## related
  1. [parallelify.20170128.log.md](parallelify.20170128.log.md)

## contents
  1. [overview](#overview)
  2. [manifest](#manifest)
  3. [feature](#feature)
  4. [test](#test)
  5. [deploy](#deploy)
  6. [log](#log)
  7. [todo](#todo)
  8. [refactor](#refactor)
  9. [faq](#faq)
  10. [reference](#reference)
  11. [communications](#communications)
  12. [suppplement](#suppplement)
  
## overview
  We are currently verifying 25% of the files written to tape after the tape 
writing process. Though the tapes are written in parallel, the verification 
process is performed in serial. We, therefore, would like to parallelize the 
verification process, to improve throughput.

## manifest
  to avoid interrupting production code, we are making changes as follows:
  1. [paper_dump.py](/bin/paper_dump.py) - a new class: VerifyThread, a new dump class: DumpFaster, a 
  new verification method: dump_pair_verify, an updated method: 
  tar_archive_fast, an updated method: fast_batch
  2. [paper_mtx.py](/bin/paper_mtx.py) - refactor tape_archive_md5() to unload tapes when complete
  3. [paper_db.py](/bin/paper_db.py) - add credential file check method

## feature 
  We are currently using DumpFast.tar_archive_fast() (in paper_dump.py) which
contains the following:

```python
        for label_id in tape_label_ids:
            dump_verify_status = self.dump_verify(label_id)
            if dump_verify_status is not self.status_code.OK:
                self.debug.output('Fail: dump_verify {}'.format(dump_verify_status))
                tar_archive_single_status = self.status_code.tar_archive_single_dump_verify
                self.close_dump()
``` 

  Instead we should pass the tape_label_ids into a new wrapper method called
  dump_pair_verify() that then loops over each label with python threading 
  and calls dump_verify().

  dump_verify() is inherited from Dump.dump_verify() and contains:
```python
        ## run a tape_self_check
        self_check_status, item_index, catalog_list, md5_dict, tape_pid = self.tape_self_check(tape_id)
```

  tape_self_check in turn calls tape.tape_archive_md5 (found in paper_mtx.py)
```python
        tape_archive_md5_status, reference = self.tape.tape_archive_md5(tape_id, tape_pid, catalog_list, md5_dict)
```

  Changer.tape_archive_md5() then loops through each archive on tape and checks a
random file md5 from each

  In order to achieve parallelization, we need to run the python code in
parallel. In contrast, the dump code simply runs shell scripts in parallel. 
In order to make the python run in parallel we should change 
DumpFast.tar_archive_fast() to run self.dump_verify on the label_ids using 
python threads.

  Something like:
```python
from threading import Thread
 
## custom thread class to capture status code
## when dump_verify() completes
class VerifyThread(Thread):
    ## init object with tape_id and dump_object
    ## so we can call dump_object(tape_id)
    def __init__(self, tape_id, dump_object):
        self.tape_id = tape_id
        self.dump_verify_status = ''
 
    ## custom run() to run dump_verify and save returned output
    def run():
        self.dump_verify_status = dump_object.dump_verify(label_id)
 
## example use of new custom class
## this should be called from within a DumpFast object
for label_id in tape_label_ids:
    verify_list = []
    
    verify = VerifyThread(label_id, self)
    verify_list.append(verify)
    verify.start()    
 
for verify in verify_list:
    ## join() will block until run() completes
    verify.join()
 
    ## after run completes, we need to query the status code with our 
    ## custom status() method (since join does not return the status code)
    dump_verify_status = verify.dump_verify_status
 
    ## process the return code to see if we should abort or continue
    if dump_verify_status is not self.status_code.OK:
        self.debug.output('Fail: dump_verify {}'.format(dump_verify_status))
        tar_archive_single_status = self.status_code.tar_archive_single_dump_verify
        self.close_dump()   

```

  Since we're passing in a reference to "self" we could also just set a
variable and modify it from within the thread.

  Changer.tape_archive_md5() uses self.load_tape_drive(tape_id). If the tapes are loaded 
before the function is called it will leave the tape in the drive and rewind it.

  We can pair this with the threaded call, here the updated VerifyThread class and Dumpfaster:
  
```python
from functools import reduce
from threading import Thread
 
## custom thread class to capture status code
## when dump_verify() completes
class VerifyThread(Thread):
    ## init object with tape_id and dump_object
    ## so we can call dump_object(tape_id)
    def __init__(self, tape_id, dump_object):
        Thread.__init__(self)
        self.tape_id = tape_id
        self.dump_object = dump_object
        self.dump_verify_status = ''
 
    ## custom run() to run dump_verify and save returned output
    def run(self):
        self.dump_verify_status = self.dump_object.dump_verify(self.tape_id)
         
         
 class DumpFaster(DumpFast):
 
    """Queless archiving means that the data is never transferred to our disk queues
 
    Disk queues are still used to maintain state in the event of a partial dump failure
    Tape verification is rewritten to make use of python threading.
 
    """
 
    def dump_pair_verify(self, tape_label_ids):
        """This is a wrapper to perform a threaded version of the
        original call to dump_verify(). Our "threading" is implemented  in three
        steps:
 
          1. instantiate VerifyThread (that calls dump_verify()) and start each thread
          2. wait on each thread and get the verification status code from each
          3. check each status code and return failure if either is not "OK"
        """
 
        ## thread instances need to be started, we can use the output to make a list of started threads
        def _start_verification(thread):
            thread.start()
            return thread
 
        ## join() will block until the thread completes, then we can retrieve the status from the verification
        def _get_verification_status(thread):
            thread.join()
            return thread.dump_verify_status
 
        ## given a pair of verification status codes, return a "non-OK" status if either is not "OK"
        def _check_thread_status(status_1, status_2):
            return status_1 if status_1 is not self.status_code.OK else status_2
 
        ## foreach label, start a thread and add it to a list
        started_threads = [_start_verification(VerifyThread(label_id, self)) for label_id in tape_label_ids]
 
        ## foreach thread, check the verification status and add it to a list
        return_codes = [_get_verification_status(thread) for thread in started_threads]
 
        ## foreach status code, check if either is not "OK"
        return reduce(_check_thread_status, return_codes)
```

finally we need to update DumpFaster.tar_archive_fast() to call dump_pair_verify()
instead of the original verification for loop
```python
class DumpFaster(DumpFast):
 
    """Queless archiving means that the data is never transferred to our disk queues
 
    Disk queues are still used to maintain state in the event of a partial dump failure
    Tape verification is rewritten to make use of python threading.
 
    """
 
    def tar_archive_fast(self, catalog_file):
        """Archive files directly to tape using only a single drive to write 2 tapes"""
 
        tar_archive_fast_status = self.status_code.OK
 
        ## select ids
        tape_label_ids = self.labeldb.select_ids()
        # self.labeldb.claim_ids(tape_label_ids)
 
        ## load up a fresh set of tapes
        self.tape.load_tape_pair(tape_label_ids)
 
        ## add the catalog to the beginning of the tape
        for label_id in tape_label_ids:
            self.debug.output('archiving to label_id - {}'.format(label_id))
 
        ## prepare the first block of the tape with the current tape_catalog
        self.tape.prep_tape(catalog_file)
 
        self.debug.output('got list - {}'.format(self.files.tape_list))
        self.tape.archive_from_list(self.files.tape_list)
 
        ## unloading the tape pair allows for the tape to be loaded back from the library
        ## for verification later
        self.tape.unload_tape_pair()
 
        for label_id in tape_label_ids:
            dump_verify_status = self.dump_verify(label_id)
            if dump_verify_status is not self.status_code.OK:
                self.debug.output('Fail: dump_verify {}'.format(dump_verify_status))
                tar_archive_single_status = self.status_code.tar_archive_single_dump_verify
                self.close_dump()
 
        ## update the current dump state
        if tar_archive_fast_status is self.status_code.OK:
            log_label_ids_status = self.log_label_ids(tape_label_ids, self.files.tape_list)
            if log_label_ids_status is not self.status_code.OK:
                self.debug.output('problem writing labels out: {}'.format(log_label_ids_status))
        else:
            self.debug.output("Abort dump: {}".format(tar_archive_single_status))
``` 


## test

###### test threading
we can do some base testing of the new method if we make a custom test class
  1. test class: `class TestDumpNoTape(Dump):`
  2. create a dummmy: TestDumpNoTape.dump_verify() method
  3. create a dummy: \_\_init__() to bypass the normal init process
   
test_dump_pair_notape.py:
```python
__author__ = 'dconover@sas.upenn.edu'

from paper_dump import DumpFaster, VerifyThread
from paper_status_code import StatusCode


class TestDumpNoTape(DumpFaster):
    ## in our test class we don't actually want to do a dump init
    def __init__(self):
        self.status_code = StatusCode
        pass

    ## redefining dump_verify lets us test our new method without a full dump to tape
    def dump_verify(self, label_id):
        print("verification thread using " + label_id)


label_ids = ['label_one', 'label_two']
test_dump_instance = TestDumpNoTape()
test_dump_instance.dump_pair_verify(label_ids)
```

Using the test code above we can demonstrate that the new code is successfully 
integrated with the exising code (not necessarily that it provides the improvements
that we intend): 
```
ssh://root@shredder.physics.upenn.edu:22/root/.pyenv/versions/3.4.1/bin/python -u /root/.pycharm_helpers/pycharm/utrunner.py /root/pycharm/dconover/paper-dump/bin/test_dump_pair_notape.py true
Testing started at 8:06 PM ...
verification thread using label_one
verification thread using label_two

Process finished with exit code 0
Empty test suite.
```

  
## deploy
  1. review tests with slack(eoranalysis):/dm:plaplant
  2. update papertape-prod_dump.py to use dump faster DumpFaster

## log
  1. review code
  2. document proposed fix
  3. refactored tape_archive_md5
  4. check if Changer.tape_archive_md5 uses only one drive - it is agnostic if the tapes are already loaded
  5. debug proposed fix - proposed creating new dump routine, so updates don't break current running code
  6. integrate code fix - dconover:20170203
  7. refactor code fix; refactor test code doc - dconover:20170208
  8. refactor: update check_credentials_file() and PaperDB.\_\_init__()
  9. code passes dry-run test of new threading code using mocked dump functions - dconover:20170213
  10. repair implementation problems (plaplant)
  11. test new dump with DumpFaster class (plaplant)
  12. open merge request !1

## deferred 
  1. refactor: update DumpTest.\_\_init_\_() to run self.test_data_init() and connect
  2. build test dataset

## refactor
  plaplant also requested that the verification process unload the tape 
when complete. I am adding that to the end of tape_archive_md5().

```python
   def tape_archive_md5(self, tape_id, job_pid, catalog_list, md5_dict):
        """loop through each archive on tape and check a random file md5 from each
 
        :rtype : bool"""
 
## [... truncated for brevity]
 
        self.unload_tape(tape_id)
        return tape_archive_md5_status, reference
```

  while writing the test code I notice that the mtx credentials where hardcoded
in the initialization for the Dump class. I am changing that to a default init variable. I am making the current default the same as the current
running dumps so that we don't accidentally disrupt the current code.

```python
class Dump(object):
    """Coordinate a dump to tape based on deletable files in database"""
 
    def  __init__(self, credentials='/papertape/etc/my.papertape-test.cnf', mtx_credentials='home2/obs/.my.mtx.cnf', debug=False, pid=None, disk_queue=True, drive_select=2, debug_threshold=255):
        """initialize"""
## [... truncated for brevity]
```
  while writing integrating the new dump_verify code, I see that dump() close is not
fully implemented and requires that self.dump_state get updated as various methods 
are completed. I am adding an update to the self.dump_state in the dump_verify() method so 
that dump_close() could eventually be made to work correctly.

```python
    def dump_verify(self, tape_id):
        """take the tape_id and run a self check,
        then confirm the tape_list matches
 
        """
        dump_verify_status = self.status_code.OK
 
        ## we update the dump state so self.dump_close() knows what actions to take
        self.dump_state = self.dump_state_code.dump_verify
## [... truncated for brevity]
```
  creating a default variable for the credentials_file and a new method for checking 
the validity of the credentials file

```python
from os import path
 
class PaperDB(object):
    def __init__(self, version, credentials, pid, debug=False, debug_threshold=255):
        """Initialize connection and collect file_list of files to dump.
        :type version: int
        :type credentials: string
        :type pid: basestring
        :type debug: bool
        :type debug_threshold: int
        """
 
        self.pid = pid
        self.version = version
        self.debug = Debug(self.pid, debug=debug, debug_threshold=debug_threshold)
        self.status_code = StatusCode
 
        
        ## we have a default credentials variable that may not exist, so we should check it first
        self.check_credentials_file(credentials)
 
        self.credentials = credentials
        self.paperdb_state_code = PaperDBStateCode
        self.paperdb_state = self.paperdb_state_code.initialize
        self.connection_timeout = 90
        self.connection_time = timedelta()
        self.connect = ''
        self.cur = ''
        self.db_connect('init', credentials)
 
        self.file_list = []
        self.file_md5_dict = {}
        self.claimed_files = []
        self.claimed_state = 0
        
    def check_credentials_file(credentials):
    """Run checks on a credentials file; currently just check that it exists and is not empty.
    :type credentials: string
    """
        ## return true if the credentials file exists and is not zero size
        path.isfile(credentials) and path.getsize(credentials) > 0
```
update \_\_init__() to use the new file check:
```python
    def __init__():
## [... truncated for brevity]    
        if self.check_credentials_file(credentials)
```

## faq
  1. does Changer.tape_archive_md5 use a specific tape (e.g. /dev/nst0)?
  **if the tapes are already loaded, it is agnostic**
  2. where do the mtx db credentials get set?
  **a default init variable (mtx_credentials) in the Dump class**

## reference
  1. from python.org: python3 [threading](https://docs.python.org/3/library/threading.html)
  2. from python-course.eu: create a [custom thread class](http://www.python-course.eu/threads.php) and modify 
  run to save the return value from dump_verify
  3. stackoverflow: [mkdir -p](http://stackoverflow.com/questions/600268/mkdir-p-functionality-in-python)
  4. python3 docs: [os.makedirs](https://docs.python.org/3/library/os.html?highlight=makedirs#os.makedirs)
  5. making pseudo [random data files](http://jessenoller.com/blog/2008/05/30/making-re-creatable-random-data-files-really-fast-in-python)
  6. filesystem [size](http://stackoverflow.com/questions/4260116/find-size-and-free-space-of-the-filesystem-containing-a-given-file)
  7. from python-course.eu: [lambda, map, filter, reduce](http://www.python-course.eu/lambda.php)

## communications
  communications for this project have all been with Paul La Plante over slack on the
group's slack via direct message

  1. the folio group uses their own slack channel eoaranalysis.slack.com
  2. paul la plante <plaplant@sas.upenn.edu>
  3. james aguirre <jaguirre@sas.upenn.edu>

## supplement
slack discussion (eoranalysis:dm):
```text
plaplant [10:08 AM] 
how hard would it be to parallelize the error-checking for the tapes?

[10:09]  
reading the scripts, it looks like the writing is done in parallel, but for error-checking, the tapes are loaded in one at a time

d [10:24 AM] 
shouldn’t be too hard. I think that makes sense. I think I did that at the time because I thought we weren’t going to check both tapes, but later decided to check both tapes

[10:29]  
I could look at the code this weekend.

plaplant [10:30 AM] 
awesome, thanks a lot

[10:30]  
in practice, i’m finding that error checking 25% of the files (for both tapes) takes about as long as writing the data

[10:31]  
so if we could do both at once, it’d be a big time savings

d [10:34 AM] 
how long does it take to write the tapes?

plaplant [10:34 AM] 
~30 hours

[10:34]  
per tape

[10:35]  
~16 for writing the data, then ~7 per data check

[10:35]  
this is with 4-file batches

d [10:35 AM] 
that’s big

plaplant [10:36 AM] 
what’s big? like it shouldn’t take this long?

d [11:17 AM] 
I meant big, like that’s a big savings if we can change it

plaplant [11:21 AM] 
oh yeah, definitely

[11:22]  
it’d also be helpful if we wanted to tape up the data in real time, since we’re projecting to take a tape’s worth of data per night next year
```

discussion around refactoring unloading tape after verification:
```text
plaplant [11:07 AM] 
cool, thanks so much for writing this up!

[11:08]  
one last thing that would be nice is unloading the tapes after successfully verifying

[11:08]  
right now, when the script finishes, there’s still a tape in drive 0

d [4:55 PM] 
I think the script has methods for unloading the drives if there’s a tape in it.

plaplant [5:38 PM] 
Oh okay, I'll try that

[5:38]  
Thanks

d [6:17 PM] 
I’ve added an unload call to the end of the verification process :slightly_smiling_face:
```

discussion about testing:
```text
d [12:25 PM] 
I’ve finally integrated the new code. I still have to write some tests, but if you’re between runs, you can call it by changing the dump class from DumpFast to DumpFaster in the papertape-prod_dump.py file. I am hoping to be able to get some tests written and run on the old tape library this weekend.

plaplant [12:25 PM] 
Excellent, thanks so much! :slightly_smiling_face:

[12:26]  
I really appreciate all the work that went in

[12:27]  
I’m running a dump right now, but it should finish later today/early tomorrow. I might hold off on using the new version till all the tests are done, since the hard drive version of what I’m taping up now will be deleted when we’re done, so I want everything air-tight

[12:28]  
But thanks again for this change, it’ll really speed things up
```

We integrated some of plaplant's changes:
```text
plaplant [2:58 PM] 
I’m coming up on the end of my current backup, and I wanted to switch over to DumpFaster for the next batch
 
[2:59]  
Do I have to change anything besides the class in `papertape-prod_dump.py`?
 
d [2:59 PM] 
I’ve made a couple changes, that are in the repo, but not on pot4.
 
[3:01]  
I managed to test the syntax of the new code, but haven’t been able to write tests with an actual dump (unfortunate
 
d [3:02 PM] 
I think it should all work as expected, since I haven’t changed much in the actual dump code
 
plaplant [3:02 PM] 
Okay, great
 
[3:03]  
I’ve made some changes to the `papertape-cron.sh` and added a `run_backup.sh` script to run without my kicking each backup off by hand
 
[3:03]  
Can I merge those into the repo before pulling the latest changes?
 
d [3:04 PM] 
yeah, those look good
 
[3:06]  
Do you want me to merge those in now?
 
plaplant [3:07 PM] 
Yes please
 
d [3:13 PM] 
done
 
[3:15]  
root@pot4 can push and pull to our local gitlab repo (gitlab.sas), we can also give you an account on gitlab.sas if you want to see the repo from the gui...
 
plaplant [3:18 PM] 
so can I `sudo git push`?
 
d [3:19 PM] 
yup
 
plaplant [3:19 PM] 
okay cool, that’s great
 
d [3:20 PM] 
actually, you’ll have to do `sudo git push gitlab`. origin is currently set to github, which I only push to from my laptop (after the code is proven to work on pot4) (edited)
 
plaplant [3:26 PM] 
gotcha, thanks
```
 
I failed to run a code inspection before uploading the code, resulting in initialization errors:
```text
----- February 16th -----
plaplant [1:13 PM] 
i’m trying to invoke `DumpFaster`, but there are some initialization errors
 
[1:13]  
it’s choking on `check_credentials_file`
 
[1:15]  
it was complaining that there should be two arguments, so I added `self`:
    def check_credentials_file(self, credentials):
        """Run checks on a credentials file; currently just check that it exists and is not empty.
        :type credentials: string
        """
        ## return true if the credentials file exists and is not zero size
        path.isfile(credentials) and path.getsize(credentials) > 0
 
 
[1:15]  
but now I’m getting `NameError: name 'path' is not defined`
 
[1:17]  
I didn’t want to change too much without consulting, but my guess is I should just make it `os.path.isfile`, right?
 
d [2:11 PM] 
nope, path should be added to the import
 
[2:12]  
`from os import path` (edited)
 
plaplant [2:12 PM] 
okay thanks
 
d [2:12 PM] 
we like to restrict our imports
 
plaplant [2:13 PM] 
makes sense
 
```

Then we had problems with database files that were not mounted locally yet:
```text
----- February 17th -----
plaplant [10:47 AM] 
I’ve hit an error when the script tries to pull from files not on on `pot4`
 
[10:48]  
 debug:20170216-2319:016336295:paper_mtx.Changer.append_to_archive:tarfile exception - [Errno 2] No such file or directory: '/papertape/pot5.physics.upenn.edu:/data2/raw_data_FROM_FOLIO/EoR2013/psa6620/zen.2456620.16691.xx.uv'
Traceback (most recent call last):
  File "papertape-prod_dump.py", line 14, in <module>
    x.fast_batch()
  File "/papertape/bin/paper_dump.py", line 582, in fast_batch
    self.tar_archive_fast(self.files.catalog_name)
  File "/papertape/bin/paper_dump.py", line 608, in tar_archive_fast
    self.tape.archive_from_list(self.files.tape_list)
  File "/papertape/bin/paper_mtx.py", line 383, in archive_from_list
    self.append_to_archive(data_path, file_path_rewrite=archive_path )
  File "/papertape/bin/paper_mtx.py", line 344, in append_to_archive
    self.archive_tar.add(file_path, arcname=arcname)
  File "/usr/lib64/python3.4/tarfile.py", line 1913, in add
    tarinfo = self.gettarinfo(name, arcname)
  File "/usr/lib64/python3.4/tarfile.py", line 1785, in gettarinfo
    statres = os.lstat(name)
FileNotFoundError: [Errno 2] No such file or directory: '/papertape/pot5.physics.upenn.edu:/data2/raw_data_FROM_FOLIO/EoR2013/psa6620/zen.2456620.16691.xx.uv'
 
 
[10:50]  
the file looks like it exists at `pot5:/data2/…`, but it wasn’t found by the script
 
[10:50]  
do we need to move the files to `pot4` for the backup?
 
[10:55]  
I poked around a little and learned about `sshfs`, I’m going to mount `pot5` that way
 
d [11:56 AM] 
it would be better to mount them using nfs
 
[11:58]  
it will take longer over sshfs due to encryption and occasionally drops out...
 
plaplant [11:59 AM] 
okay, good to know
 
[11:59]  
i’ll switch to nfs
 
d [12:00 PM] 
wherever you mount it, then you also need to create a link. for example if I mount it under /nfs/pot5/data2 I would link it like ln -s /nfs/pot5 /papertape/pot5:
 
[12:01]  
or just mkdir /papertape/pot5: and mount it as /papertape/pot5:/data2
 
plaplant [12:04 PM] 
why do I need the link?
 
[12:05]  
could I just mount `pot5:/data2` at a `data2` directory in `/papertape/pot5.physics.upenn.edu:`?
 
d [12:07 PM] 
it’s prefixed to /papertape/$path, so if you put it someplace else, you have to link it.
 
plaplant [12:07 PM] 
okay, I see
 
d [12:08 PM] 
we should prly change that since it makes the dir a little messy
 
[12:08]  
something like papertape/data/$host:...
 
[12:09]  
or even try to resolve it based on actual hostname...
 
[12:10]  
but in the past all the data dirs were remote and nfs produced the fastest transfer speeds....
 
plaplant [12:10 PM] 
that’s okay, i don’t mind mounting the remote directories as nfs
 
d [12:11 PM] 
you can also enumerate it with the code, if that helps
 
plaplant [12:11 PM] 
so I tried to run `sudo mount pot5:/data2 /mnt/pot5\:/data2/` and got `mount.nfs: access denied by server while mounting pot5:/data2`
 
d [12:12 PM] 
pot5 has to export it to pot4
 
[12:12]  
it will need an entry in /etc/exports
 
plaplant [12:13 PM] 
okay
 
[12:13]  
there’s also a weird networking thing, where pot4 can see/ping pot5, but pot5 can’t ping pot4...
 
d [12:14 PM] 
is it just iptables?
 
plaplant [12:14 PM] 
also, pot5 has an entry in /etc/exports: `/data2 128.91.79.158(no_root_squash,rw,async,fsid=10) 192.168.1.152(no_root_squash,rw,async,fsid=10)`
 
d [12:14 PM] 
service nfs status?
 
plaplant [12:15 PM] 
Redirecting to /bin/systemctl status  nfs.service
nfs-server.service - NFS server and services
   Loaded: loaded (/usr/lib/systemd/system/nfs-server.service; enabled)
   Active: active (exited) since Thu 2016-12-22 04:31:38 PST; 1 months 26 days ago
 Main PID: 16098 (code=exited, status=0/SUCCESS)
   CGroup: /system.slice/nfs-server.service
 
Dec 22 04:31:38 pot5 systemd[1]: Started NFS server and services.
Dec 22 04:46:39 pot5 systemd[1]: Started NFS server and services.
 
 
[12:16]  
this is on pot5
 
d [12:16 PM] 
looks like iptabels
 
[12:16]  
what ip is pot5?
 
plaplant [12:16 PM] 
obs@pot5[~]$ ifconfig
enp2s0f0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
        inet 192.168.2.153  netmask 255.255.255.0  broadcast 192.168.2.255
        inet6 fe80::ec4:7aff:fe4c:4b1e  prefixlen 64  scopeid 0x20<link>
        ether 0c:c4:7a:4c:4b:1e  txqueuelen 1000  (Ethernet)
        RX packets 35831018236  bytes 51898450536842 (47.2 TiB)
        RX errors 0  dropped 693806  overruns 7135  frame 0
        TX packets 5778463882  bytes 467037648580 (434.9 GiB)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0
        device memory 0xdfce0000-dfcfffff
 
enp2s0f1: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
        inet 10.0.10.5  netmask 255.255.255.0  broadcast 10.0.10.255
        inet6 fe80::ec4:7aff:fe4c:4b1f  prefixlen 64  scopeid 0x20<link>
        ether 0c:c4:7a:4c:4b:1f  txqueuelen 1000  (Ethernet)
        RX packets 2  bytes 619 (619.0 B)
        RX errors 0  dropped 0  overruns 0  frame 0
        TX packets 27  bytes 3841 (3.7 KiB)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0
        device memory 0xdfc60000-dfc7ffff
 
lo: flags=73<UP,LOOPBACK,RUNNING>  mtu 65536
        inet 127.0.0.1  netmask 255.0.0.0
        inet6 ::1  prefixlen 128  scopeid 0x10<host>
        loop  txqueuelen 0  (Local Loopback)
        RX packets 993  bytes 81318 (79.4 KiB)
        RX errors 0  dropped 0  overruns 0  frame 0
        TX packets 993  bytes 81318 (79.4 KiB)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0
 
 
[12:17]  
folio sees it as 192.168.2.153
 
d [12:21 PM] 
alright how about now?
 
plaplant [12:21 PM] 
I still can’t mount nfs
 
[12:22]  
and I can’t go from pot5 -> pot4
 
d [12:26 PM] 
checking...
 
d [12:45 PM] 
driving atm, be back in 90 min
 
 
```
 
then the tape library broke:
```text
plaplant [5:43 PM] 
I got the nfs to work, but now the tape library is acting strange
 
[5:44]  
I was trying to erase the tapes that were partially written with `mt -f /dev/nst0 erase`
 
d [5:44 PM] 
that’s funny I was just checking the nfs server on pot5
 
plaplant [5:44 PM] 
it seemed like it was hung, so I killed the process, but now the tape library isn’t working
 
[5:44]  
oh that’s funny
 
d [5:45 PM] 
hmm, well you don’t really need to erase, you can just overwrite
 
plaplant [5:45 PM] 
yeah, I changed the IP address in `/etc/exports` on pot5, and then ran `exportfs -ra` and then mounting on pot4 worked fine
 
[5:45]  
okay, good to know for the future
 
[5:46]  
unfortunately now the tape library isn’t working normally
 
d [5:47 PM] 
what’s the symptom?
 
plaplant [5:47 PM] 
so `mtx status` works fine, but I can’t load or unload tapes
 
[5:47]  
obs@pot4[~]$ mtx unload 2 1
Unloading drive 1 into Storage Element 2...mtx: Request Sense: Long Report=yes
mtx: Request Sense: Valid Residual=no
mtx: Request Sense: Error Code=70 (Current)
mtx: Request Sense: Sense Key=Not Ready
mtx: Request Sense: FileMark=no
mtx: Request Sense: EOM=no
mtx: Request Sense: ILI=no
mtx: Request Sense: Additional Sense Code = 04
mtx: Request Sense: Additional Sense Qualifier = 12
mtx: Request Sense: BPV=no
mtx: Request Sense: Error in CDB=no
mtx: Request Sense: SKSV=no
MOVE MEDIUM from Element Address 257 to 4097 Failed
 
[5:47]  
I get something similar if I try to run `mtx load 1 0`
 
d [5:50 PM] 
that’s a quizibuck
 
plaplant [5:51 PM] 
I even tried to reboot pot4, but it’s still happening...
 
[5:52]  
I’m afraid I might have to reboot the tape library, but I’m out of town right now and am not sure how to do that remotely
 
d [5:55 PM] 
there might be a dell management api
 
plaplant [6:02 PM] 
I think they have a web app, but I haven't set it up because I couldn't figure out how to get the MAC address for the library...
 
d [6:02 PM] 
we should be able to install openmanage and access it via the cli
 
plaplant [6:12 PM] 
how do we install that?
 
d [6:30 PM] 
there should be an installer somewhere on the dell site
 
plaplant [6:31 PM] 
I poked around and could only find the Microsoft one...
 
d [6:45 PM] 
I think I’ll have to walk over and look at it.
 
plaplant [6:46 PM] 
Thanks! I appreciate it
 
d [8:36 PM] 
one of our admins is going to be able to visit it tomorrow afternoon.
 
plaplant [9:13 PM] 
cool, thanks a lot
 
 
----- February 18th -----
d [2:18 PM] 
looks like we’re back. We also ran the cleaning tape through both drives.
 
plaplant [2:43 PM] 
Great! Thanks so much, I really appreciate the reset
 
d [2:43 PM] 
anytime :slightly_smiling_face:
```

In the end it looks like the code paid off:
```text
----- Today February 21st, 2017 -----
plaplant [11:12 AM] 
I just finished the maiden voyage of `DumpFaster`, and it only took 20 hours (down from ~30)
 
[11:12]  
huge speedup!
 
d [11:13 AM] 
awesome. glad I could help
```

 
 
<br><br><br><br><br><br><br><br><br><br><br><br><br><br><br><br><br><br><br><br><br><br><br>



