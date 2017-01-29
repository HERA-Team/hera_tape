# parallel verification of written tapes

owner: dconover:20170128

## overview

  We are currently verifying 25% of the files written to tape after the tape 
writing process. Though the tapes are written in parallel, the verification 
process is performed in serial. We, therefore, would like to parallelize the 
verification process, to improve throughput.


## feature 

We are currently using DumpFast.tar_archive_fast() (in paper_dump.py) which
contains the following:

```bash
        for label_id in tape_label_ids:
            dump_verify_status = self.dump_verify(label_id)
            if dump_verify_status is not self.status_code.OK:
                self.debug.output('Fail: dump_verify {}'.format(dump_verify_status))
                tar_archive_single_status = self.status_code.tar_archive_single_dump_verify
                self.close_dump()
``` 

instead we should pass the tape_label_ids into dump_verify().

dump_verify() is inherited from Dump.dump_verify() and contains:
```bash
        ## run a tape_self_check
        self_check_status, item_index, catalog_list, md5_dict, tape_pid = self.tape_self_check(tape_id)
```

tape_self_check in turn calls tape.tape_archive_md5 (which is paper_mtx:)
```bash
        tape_archive_md5_status, reference = self.tape.tape_archive_md5(tape_id, tape_pid, catalog_list, md5_dict)
```

Changer.tape_archive_md5() then loops through each archive on tape and checks a
random file md5 from each

In order to achieve parallelization, we need to run the python code in
parallel. In contrast, the dump code simply run shell scripts in parallel. 
In order to make the python run in parallel we should change 
DumpFast.tar_archive_fast() to run self.dump_verify on the label_ids using 
python threads




## test


## log

## todo 
  1. review code
  2. document proposed fix
  3. code fix
  4. test fix

## faq
  1. does Changer.tape_archive_md5 use a specific tape (e.g. /dev/nst0)?


## reference
  1. from python.org: python3 [threading](https://docs.python.org/3/library/threading.html)


## communications

communications for this project have all been with Paul La Plante over slack on the
group's slack via direct message

  1. the folio group uses their own slack channel eoaranalysis.slack.com
  2. paul la plante <plaplant@sas.upenn.edu>
  3. james aguirre <jaguirre@sas.upenn.edu>


## supplement


slack discussion (eoranalysis:dm):
```bash
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
