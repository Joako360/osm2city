'''
Created on 10.05.2014

@author: keith.paterson
'''
import os
import logging
import re


def getFGHome():
#http://wiki.flightgear.org/$FG_HOME
    if "nt" in os.name:
        return os.getenv("APPDATA", "APPDATA_NOT_FOUND") + os.sep + "flightgear.org" + os.sep
    if "posix" in os.name:
        return "~/.fgfs/"

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
#Parse arguments and eventually override Parameters
    import argparse
    parser = argparse.ArgumentParser(description="Setup will set some properties and copy the elev.nas")
    parser.add_argument("-fg", "--fg_home", dest="fg_home",
                      help="FG_HOME", metavar="FILE")
    args = parser.parse_args()

    if args.fg_home is not None:
        nasalDir = os.path.abspath(args.fg_home) + os.sep + "data" + os.sep + "Nasal"
        if not os.path.exists(nasalDir):
            print "Directory not found " + nasalDir
            os._exit(1) 
        with open( nasalDir + os.sep + "IORules", "r") as sources:
            lines = sources.readlines()
            fg_data_in_ok = False
            fg_data_out_ok = False
            for line in lines:
                if "READ ALLOW $FG_HOME/*" in line:
                    fg_data_in_ok = True
                if "WRITE ALLOW $FG_HOME/Export/*" in line:
                    fg_data_out_ok = True
            if not fg_data_in_ok:
                logging.error("FG can't read from $FG_HOME/* check IORules")
            if not fg_data_out_ok:
                logging.error("FG can't write to $FG_HOME/Export/* check IORules")
        in_dir = getFGHome()                 
        out_dir = getFGHome() + "Export" + os.sep                 
        with open("elev.nas", "r") as sources:
            lines = sources.readlines()
        os.close( sources )
        with open(nasalDir + os.sep + "elev.nas", "w") as sources:
            for line in lines:
#  var in = "C:/Users/keith.paterson/AppData/Roaming/flightgear.org/elev.in";
                if "var in" in line:
                    line = '  var in = "' + in_dir + '";\n'
#  var out = "C:/Users/keith.paterson/AppData/Roaming/flightgear.org/Export/";
                if "var out" in line:
                    line = '  var out = "' + out_dir + '";\n'
                sources.write(line)
        os.close(sources)  
        logging.info('Sucessfully installed elev.out')                   