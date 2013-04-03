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
tgt=e011n47
rm $tgt/city-*

# mv ln/city-* e013n51/
cp city-*ac $tgt/
cp city-*xml $tgt/
kate city.stg $tgt/3138129.stg


