#===============================================================================
#   File :      rainbow.py
#   Author :    Olivier Teboul, olivier.teboul@ecp.fr
#   Date :      31 july 2008, 14:02
#   Class :     Rainbow
#===============================================================================

import random

class Rainbow:
    """ This class provide a tool to convert a number between 0 and 1
        to a color from the rainbow. The Rainbow is defined as a path
        on the edges of the RGB cube.
    """
    
    def __init__(self,x=None):
        if x==None :
            self.get_random()
        else:
            self.x = x
            self.get(self.x)

    def get(self,x):
        if 0<= x < 0.25:
            self.r = 255
            self.g = int(4*255*x)
            self.b = 0

        elif 0.25<= x < 0.50:
            self.r = int(255*(-4*x+2))
            self.g = 255
            self.b = 0

        elif 0.50<= x < 0.75:
            self.r = 0
            self.g = 255
            self.b = int(255*(4*x-2))

        else :
            self.r = 0
            self.g = int(255*(-4*x+4))
            self.b = 255
            
        self.color = (self.r,self.g,self.b)
        return self.color

    def get_random(self):
        self.x = random.random()
        return self.get(self.x)
    
    def get_hexa_color(self,x):
        (r,g,b) = self.get(x)
        return '#%02x%02x%02x' %(r,g,b)
        

#--------------------------------------------------------------------------
if __name__ == '__main__':
    rainbow = Rainbow()
    
