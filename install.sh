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
rm e013n51/city-*

# mv ln/city-* e013n51/
cp city-*ac e013n51/
cp city-*xml e013n51/
kate city.stg e013n51/3171138.stg

