"""
Created on 27.04.2014

@author: keith.paterson
"""

import re
import telnetlib
import time


class FG_Telnet(object):

    def __init__(self, host, port):
        self.host = host
        self.sock = telnetlib.Telnet(host, port)
        self.sock.write("data")

    def get_prop(self, property_name):
        self.sock.write("get " + property_name + "\r\n")
        result = self.sock.read_until("/>", 60)
        return result
        
    def set_prop(self, property_name, value):
        send_buffer = "set %s %s\r\n" % (property_name, value)
        self.sock.write(send_buffer)
        result = self.sock.read_until("/>", 60)
        return result
    
    def run_command(self, command):
        try:
            send_buffer = "run %s\r\n" % command
            self.sock.write(send_buffer)
            result = self.sock.read_until("/>", 12000)
            print result
            if result.find("<completed>") >= 0:
                return True
            return False
        except Exception, e:
            print e
            return False

    def get_elevation(self, lon, lat):
        self.set_prop("/position/latitude-deg", lat)
        self.set_prop("/position/longitude-deg", lon)
        self.set_prop("/position/altitude-ft", 5000)
        time.sleep(0.05)
        prop = self.get_prop("/position/ground-elev-m")
        if prop is None:
            return 0
        elev = re.search('[^\']*\'([-e0-9.]*)\'[.]*', prop).group(1)
        return float(elev)

    def close(self):
        self.sock.close()

if __name__ == '__main__':
    fg = FG_Telnet("localhost", 5501)
    
    fg.set_prop("/position/longitude-deg", -5)
    fg.set_prop("/position/altitude-ft", 5000)
    fg.get_prop("/position/longitude-deg")
    time.sleep(1)
    fg.get_prop("/position/longitude-deg")
    time.sleep(1)
    fg.set_prop("/position/latitude-deg", 56.4)
    fg.get_prop("/position/ground-elev-m")
    fg.set_prop("/position/longitude-deg", -6)
    fg.get_prop("/position/longitude-deg")
    time.sleep(1)
    fg.get_prop("/position/longitude-deg")
    time.sleep(1)
    fg.set_prop("/position/latitude-deg", 56)
    fg.get_prop("/position/ground-elev-m")
