# barcode scrips

## overview
  1. the two scripts in this directory can be used to print tape labels 
  2. each label has an 8 character code 39 barcode
  3. the first script (make_papr_barcode.sh) prints the barcode and a human readable version of barcode
  4. the second script (relabel_barcodes.sh) prints extra human readable comment below the barcode

## manifest
   1. make_papr_barcode.sh
   2. relabel_barcodes.sh
   
## usage
metadata:
```bash
## project prefix
prefix=PAPR

## typically 2 copies of each tape are produced differentiated by a version number [1|2]
version=1

## number of tapes to print
label_count=15

## descriptive label to add below barcode
label="[ 20140922 - paper - raw - copy $version ]"

## label filename
file_name=label.ps

```

  1. run: make_papr_barcode.sh $prefix $version $label_count
  2. run: make_papr_barcode.sh $file_name $label

