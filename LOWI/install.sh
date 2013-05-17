#!/bin/bash

PROG=install.sh
USAGE="$PROG file"
DESC="<One line of description>"
HELP="<Zero or more lines of Help>"
AUTHOR="Thomas Albrecht"

#[ "$1" == "" ] || [ "$1" == "-h" ] || [ "$1" == "--help" ] && \
#    echo -e "Usage: $USAGE\n$DESC\n$HELP" && exit 1

set -u

# Here follows your own code
# rm -rf ln/
# lnall
prefix=LOWI
tgt=e011n47
rm $tgt/${prefix}city*.ac $tgt/${prefix}city*.xml

# mv ln/city-* e013n51/
cp ${prefix}city*.ac  $tgt/
cp ${prefix}city*.xml $tgt/
#kate city.stg $tgt/$stg

for stg in *.stg; do

    tmp=stg.tmp

    sed -e '/# osm2city/,$d' $tgt/$stg > $tmp
    cat $tmp $stg > $tgt/$stg
    #mv $tmp $tgt/$stg # uninstall
    #kate $tgt/$stg &
done



