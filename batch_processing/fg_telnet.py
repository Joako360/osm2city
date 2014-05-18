'''
Created on 27.04.2014

@author: keith.paterson
'''
import telnetlib
import re
from time import sleep

class FG_Telnet(object):

    def __init__(self, host, port):
        self.host = host
        self.sock = telnetlib.Telnet(host, port)
        self.sock.write("data")

    def get_prop(self, propertyname):
        self.sock.write("get " + propertyname + "\r\n")
        result = self.sock.read_until("/>", 60)
#        print result
        return result 
        
    def set_prop(self, propertyname, value):
        sendbuffer = "set %s %s\r\n"%(propertyname, value)
        self.sock.write(sendbuffer)
        result = self.sock.read_until("/>", 60)
#       print result
        return result
    
    def run_command(self, command):
        try:
            sendbuffer = "run %s\r\n"%(command)
            self.sock.write(sendbuffer)
            result = self.sock.read_until("/>", 12000)
            print result
            if result.find("<completed>") >= 0 :
                return True
            return False
        except Exception,e:
            print e
            return False 
        
        

    def get_elevation(self, lon, lat):
        self.set_prop( "/position/latitude-deg", lat );
        self.set_prop( "/position/longitude-deg", lon );
        self.set_prop( "/position/altitude-ft", 5000)
#         while self.get_prop("/position/longitude-deg") != lon and self.get_prop("/position/latitude-deg") != lat:
        sleep(0.05)
        prop = self.get_prop("/position/ground-elev-m")
        if( prop == None):
            return 0
        #/position/ground-elev-m = '122.3989172' (double)
        elev = re.search('[^\']*\'([-e0-9.]*)\'[.]*',prop).group(1)
        return float(elev)

    def close(self):
        self.sock.close()

if __name__ == '__main__':
    fg = FG_Telnet("localhost", 5501)
    
    fg.set_prop( "/position/longitude-deg", -5 );
    fg.set_prop( "/position/altitude-ft", 5000 );
    fg.get_prop("/position/longitude-deg")
    sleep(1)
    fg.get_prop("/position/longitude-deg")
    sleep(1)
    fg.set_prop( "/position/latitude-deg", 56.4 );
    fg.get_prop("/position/ground-elev-m")
    fg.set_prop( "/position/longitude-deg", -6 );
    fg.get_prop("/position/longitude-deg")
    sleep(1)
    fg.get_prop("/position/longitude-deg")
    sleep(1)
    fg.set_prop( "/position/latitude-deg", 56 );
    fg.get_prop("/position/ground-elev-m")

# sub set_prop() {    
#     my( $handle ) = shift;
#     my( $prop ) = shift;
#     my( $value ) = shift;
# 
#     &send( $handle, "set $prop $value");
# 
#     # eof $handle and die "\nconnection closed by host";
# }
# 
# 
# sub send() {
#     my( $handle ) = shift;
# 
#     print $handle shift, "\015\012";
# }
# 
# 
# sub connect() {
#     my( $host ) = shift;
#     my( $port ) = shift;
#     my( $timeout ) = (shift || 120);
#     my( $socket );
#     STDOUT->autoflush(1);
#     while ($timeout--) {
#         if ($socket = IO::Socket::INET->new( Proto => 'tcp',
#                                              PeerAddr => $host,
#                                              PeerPort => $port) )
#         {
#             $socket->autoflush(1);
#             return $socket;
#         }    
#         print "Attempting to connect to $host ... " . $timeout . "\n";
#         sleep(1);
#     }
#     return 0;
# }
