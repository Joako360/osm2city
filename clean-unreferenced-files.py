'''
Created on 25.05.2015

@author: keith.paterson
'''
import argparse
import logging
import os
import re

from utils import stg_io2


def scan_dir(dir):
    try:
        if os.path.isfile(dir) or "/" in dir:
            return 
        files = os.listdir(dir)
        refs = {}
        #First scan the stgs
        for file in files:
            if file.endswith(".stg"):
                stg = stg_io2.read_stg_entries(dir + os.sep + file, "", ignore_bad_lines=True)
                for entry in stg:
                    if not "/" in entry.obj_filename and not "\\" in entry.obj_filename:
                        refs[entry.obj_filename] = dir
    #                     print entry.obj_filename
        #Then the xmls
        for file in files:
            if file.endswith(".xml") and file in refs:
                with open(dir + os.sep + file) as f:
                    content = f.readlines()
                    for line in content:
                        if "<path>" in line:
                            fname = re.split("</?path>", line)[1]
                            refs[fname] = dir
                            break
                    f.close()
    
        for file in files:
            if file.endswith(".stg") or file.endswith(".eff"):
                continue
            elif os.path.isfile(dir + os.sep + file):
                if not file in refs:
                    print(dir + os.sep + file)
                    os.remove(dir + os.sep + file)
        for file in files:
            if not os.path.isfile(dir + os.sep + file) and not  ".svn" in file:
                scan_dir(dir + os.sep + file)
    #             print file
    except OSError as e:
        pass


if __name__ == "__main__":
    logging.basicConfig()
    parser = argparse.ArgumentParser(description="clean unreferenced files scans the directory and deletes files not referenced in .stg(s)")
    parser.add_argument("-d", dest="dir", help="the directory to be scanned")
    args = parser.parse_args()

    print(args.dir)
    
    scan_dir(args.dir)

