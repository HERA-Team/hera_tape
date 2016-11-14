#! /bin/bash

## barcode options to use
## -t table geometry
## -u unit 
## -o output_file
## -e encoding type
## -p pagesize
## -m margins (internal to barcode)
## -c disable checksum

## optional variables
prefix-${1:-PAPR}
version=${2:-1}
count=${3:-15}
file_name=${4:-label.ps}

## script
barcode="barcode -u mm -e code39 -p letter -o $file_name -c"  

## barcodes are composed: ${prefix}${version}${count} like: PAPR1015
## the default settings prints 15 tape labels
for ((i=1; i<=$count; i++)); do 
    printf "$prefix$version%03d\n" $i
done | $barcode -t 2x15+14+13-15-13 -m 15,1.5


