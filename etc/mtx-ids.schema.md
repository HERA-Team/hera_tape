# table schema for mtx.ids
## description

  table (ids) used to keep track of tape ids in use by tape library

## metadata

    host: shredder.physics.upenn.edu
    user: mtx
    db_name: mtx
    table_name: ids

## schema 

Field          Type          Null  Key   Default  Extra
id             mediumint(9)  NO    PRI   NULL     auto_increment ## unique mysql row id
label          char(8)       YES   NULL                          ## actual printed tape_id on tape label
description    text          YES   NULL                          ## generic description and dump version number (date) 
date           tinytext      YES   NULL                          ## date of last complete dump
status         tinytext      YES   NULL                          ## pid of process dumping to tape
capacity       int(11)       YES   NULL                          ## total writable capacity
tape_location  varchar(64)   YES   NULL                          ## physical location of tape when removed from library

## raw
root@shredder[~]# mysql -e 'show tables' mtx
+---------------+
| Tables_in_mtx |
+---------------+
| ids           | 
+---------------+
root@shredder[~]# mysql -e 'desc ids' mtx |column -t
Field          Type          Null  Key   Default  Extra
id             mediumint(9)  NO    PRI   NULL     auto_increment
label          char(8)       YES   NULL
description    text          YES   NULL
date           tinytext      YES   NULL
status         tinytext      YES   NULL
capacity       int(11)       YES   NULL
tape_location  varchar(64)   YES   NULL
root@shredder[~]# mysql -e 'select * from ids limit 2,1' mtx 
+----+----------+-----------------------------+---------------+-----------+----------+----------------+
| id | label    | description                 | date          | status    | capacity | tape_location  |
+----+----------+-----------------------------+---------------+-----------+----------+----------------+
| 64 | PAPR1004 | Paper dump version:20150103 | 20150228-0945 | 001064746 |  1536000 | 3e6 - 20150529 | 
+----+----------+-----------------------------+---------------+-----------+----------+----------------+
```

