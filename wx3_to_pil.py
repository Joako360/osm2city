#!/usr/bin/env python

# wx <--> PIL  image conversion routines

# Tested with wxPython 2.3.4.2 and PIL 1.1.3.
#from wxPython import wx
import wx
import Image             # Only if you need and use the PIL library.

def bitmapToPil(bitmap):
    return imageToPil(bitmapToImage(bitmap))

def bitmapToImage(bitmap):
    return wx.ImageFromBitmap(bitmap)


def pilToBitmap(pil):
    return imageToBitmap(pilToImage(pil))

def pilToImage(pil):
    image = wx.EmptyImage(pil.size[0], pil.size[1])
    image.SetData(pil.convert('RGB').tostring())
    return image

#Or, if you want to copy alpha channels too (available from wxPython 2.5)
def piltoimage(pil,alpha=True):
   if alpha:
       image = apply( wx.EmptyImage, pil.size )
       image.SetData( pil.convert( "RGB").tostring() )
       image.SetAlphaData(pil.convert("RGBA").tostring()[3::4])
   else:
       image = wx.EmptyImage(pil.size[0], pil.size[1])
       new_image = pil.convert('RGB')
       data = new_image.tostring()
       image.SetData(data)
   return image


def imageToPil(image):
    pil = Image.new('RGB', (image.GetWidth(), image.GetHeight()))
    pil.fromstring(image.GetData())
    return pil

def imageToBitmap(image):
    return image.ConvertToBitmap()
