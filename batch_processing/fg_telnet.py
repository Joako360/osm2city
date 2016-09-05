"""
Created on 27.04.2014

@author: keith.paterson

See https://docs.python.org/3.5/library/telnetlib.html
See http://wiki.flightgear.org/Telnet_usage

Used in tools.py -> _raster_telnet(..)
"""
import logging
import re
import telnetlib
import time


class FG_Telnet(object):

    PROMPT = bytes("/>", encoding="ascii")

    def __init__(self, host, port):
        self.host = host
        self.sock = telnetlib.Telnet(host, port)
        self.sock.write(bytes("data", encoding="ascii"))

    def get_prop(self, property_name):
        self.sock.write(bytes("get " + property_name + "\r\n", encoding="ascii"))
        result = self.sock.read_until(self.PROMPT, 60)
        return result
        
    def set_prop(self, property_name, value):
        send_buffer = bytes("set %s %s\r\n" % (property_name, value), encoding="ascii")
        self.sock.write(send_buffer)
        result = self.sock.read_until(self.PROMPT, 60)
        return result
    
    def run_command(self, command):
        try:
            send_buffer = bytes("run %s\r\n" % command, encoding="ascii")
            self.sock.write(send_buffer)
            result = self.sock.read_until(self.PROMPT, 12000)
            result_str = result.decode("ascii")
            logging.debug("Result from running command %s: %s", command, result)
            if result_str.find("<completed>") >= 0:
                return True
            return False
        except Exception as e:
            logging.exception("Running command %s resulted in exception", command)
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

    def wait_loop(self):
        """Waits for FlightGear to signal, that the elevation processing has finished."""
        for count in range(0, 1000):
            semaphore = self.get_prop("/osm2city/tiles").decode("ascii")
            semaphore = semaphore.split('=')[1]
            m = re.search("([0-9.]+)", semaphore)
            # We don't care if we get 0.0000 (String) or 0 (Int)
            record = self.get_prop("/osm2city/record").decode("ascii")
            record = record.split('=')[1]
            m2 = re.search("([0-9.]+)", record)
            if m is not None and float(m.groups()[0]) > 0:
                try:
                    return True
                except:
                    # perform an action#
                    pass
            time.sleep(1)
            if m2 is not None:
                logging.debug("Waiting for Semaphore " + m2.groups()[0])
        return False

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
    fg.close()
