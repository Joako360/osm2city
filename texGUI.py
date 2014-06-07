#!/usr/bin/env python
# -*- coding: utf-8 -*-
# generated by wxGlade 0.6.3 on Thu Jul 16 17:36:36 2009

# left click
# right click
# left drag -- focus to x-scale
# right drag -- focus to y-scale
# backspace -- erase last line


PROG="fitGUI.py"
import pdb
import wx
import sys
import os
from PIL import Image
import string
import numpy as np
import copy
import wx3_to_pil as wx2pil
from optparse import OptionParser
import textwrap

import importruntime
#import umrech

static_msg = "\nRight and middle buttons skip points. Wheel adjusts brightness."


def importName(modulename):
    """ Import a named object from a module in the context of this function.
    """
    # -- from "Importing from a Module Whose Name Is Determined at Runtime"
    #    Credit: J�rgen Hermann
    print modulename
    modulename = string.split(modulename, '.')[0]
    print modulename
    try:
        module = __import__(modulename, globals(), locals(  ), ['*'])
    except ImportError:
        print "could not import", modulename
        return None

    return module

class MyFrame(wx.Frame):
    def __init__(self, *args, **kwds):

        # begin wxGlade: MyFrame.__init__
        kwds["style"] = wx.DEFAULT_FRAME_STYLE
        wx.Frame.__init__(self, *args, **kwds)
        self.panel = wx.Panel(self, -1)
        self.label = wx.StaticText(self, -1, "label")
        self.button_dump = wx.Button(self, -1, "dump and quit")
        self.button_toggle1 = wx.Button(self, -1, "toggle 1")
        self.button_toggle2 = wx.Button(self, -1, "fail and quit")
        self.button_toggle3 = wx.Button(self, -1, "loop")
        self.text_ctrl_x = wx.TextCtrl(self, wx.ID_ANY, "0")
        self.label_x = wx.StaticText(self, -1, "x scale")
        self.text_ctrl_y = wx.TextCtrl(self, wx.ID_ANY, "0")
        self.label_y = wx.StaticText(self, -1, "y scale")

        self.bitmap_width = 900
        self.bitmap_height = 700
        self.__set_properties()
        self.__do_layout()

        self.Bind(wx.EVT_CHAR_HOOK, self.OnKey)
        self.Bind(wx.EVT_BUTTON, self.dump_pressed, self.button_dump)
        self.Bind(wx.EVT_BUTTON, self.toggle1_pressed, self.button_toggle1)
        self.Bind(wx.EVT_BUTTON, self.toggle2_pressed, self.button_toggle2)
        self.Bind(wx.EVT_BUTTON, self.toggle3_pressed, self.button_toggle3)
        self.panel.Bind(wx.EVT_PAINT, self.OnPaint)
        self.panel.Bind(wx.EVT_LEFT_UP, self.OnLeftUp)
        self.panel.Bind(wx.EVT_RIGHT_UP, self.OnRightUp)
        self.panel.Bind(wx.EVT_MIDDLE_DOWN, self.OnMiddleDown)
        self.panel.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
        self.panel.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
        self.panel.Bind(wx.EVT_MOTION, self.OnMouseMove)
        self.panel.Bind(wx.EVT_MOUSEWHEEL, self.OnMouseWheel)
        #self.Bind(wx.EVT_SIZE, self.OnSize)
        #self.Bind(wx.EVT_KEY_DOWN, self.OnKey)

        self.in_file_name = sys.argv[-1]
        self.out_file_name = os.path.splitext(self.in_file_name)[0] + '.py'
        self.load_image(self.in_file_name)

        self.x_splits = []
        self.y_splits = []
        self.last_split_was_left = []
        self.width_m = 1.
        self.height_m = 1.
        self.x_scale_p0 = None
        self.x_scale_p1 = 0
        self.y_scale_p0 = None
        self.y_scale_p1 = 0
        self.IsLeftDragging = False
        self.IsRightDragging = False
        self.link_height_to_width = True

        self.mousepos_img = (0,0)
        self.PrepareImage()

    def __set_properties(self):
        # begin wxGlade: MyFrame.__set_properties
        self.SetTitle("frame_1")
        self.label.SetMinSize((800, 35))
        self.panel.SetMinSize((self.bitmap_width+10, self.bitmap_width*0.9))

        # end wxGlade

    def __do_layout(self):
        # begin wxGlade: MyFrame.__do_layout
        sizer_1 = wx.BoxSizer(wx.VERTICAL)
        sizer_2 = wx.BoxSizer(wx.HORIZONTAL)
        sizer_1.Add(self.panel, 1, wx.EXPAND, 0)
        #sizer_2.Add(self.button_prev, 0, 0, 0)
        sizer_2.Add(self.label_x, 0, 0, 0)
        sizer_2.Add(self.text_ctrl_x, 0, 0, 0)
        sizer_2.Add(self.label_y, 0, 0, 0)
        sizer_2.Add(self.text_ctrl_y, 0, 0, 0)
        sizer_2.Add(self.label, 0, 0, 0)
        sizer_2.Add(self.button_dump, 0, 0, 0)
        sizer_2.Add(self.button_toggle1, 0, 0, 0)

        #sizer_2.Add(self.button_toggle2, 0, 0, 0)
        #sizer_2.Add(self.button_toggle3, 0, 0, 0)
        sizer_1.Add(sizer_2, 0, 0, 0)
        self.SetSizer(sizer_1)
        sizer_1.Fit(self)
        self.Layout()
        # end wxGlade

    def load_image(self, img):
        self.pilImageOrg = Image.open(img)

    def fit_image(self):
        org_x, org_y = self.pilImageOrg.size
        #if size[0] < size[1]:
        scale_x = self.bitmap_width / float(org_x)
        scale_y = self.bitmap_height / float(org_y)
        self.scale = min(scale_x, scale_y)

        #self.scale = float(self.bitmap_width) / float(org_x)

        nx, ny = self.img2screen(self.pilImageOrg.size)
        self.pilImage = self.pilImageOrg.resize((nx, ny), Image.ANTIALIAS)

    def PrepareImage(self):
        """do all image pre-processing from original to Bitmap"""
        # -- all processing below on self.pilImage
        self.fit_image()
        self.Bitmap = wx2pil.pilToBitmap(self.pilImage) # -- this eventually gets painted

    def toggle1_pressed(self, event):
        self.fit()
        self.PrepareImage()
        self.update_label()
        self.OnPaint()
        #event.Skip()

    def StatusUpdate(self, inc):
        max_state = 3
        self.state += inc
        if self.state < 0:
            self.state = max_state
        elif self.state > max_state:
            self.state = 0
            self.autoadvance = 0;

        self.update_label()

    def compute_width_height(self):
        try:
            px_per_m = (self.x_scale_p1 - self.x_scale_p0[0]) / float(self.text_ctrl_x.GetValue())
        except:
            px_per_m = 0.

        try:
            py_per_m = (self.y_scale_p1 - self.y_scale_p0[1]) / float(self.text_ctrl_y.GetValue())
            #print self.y_scale_p1, self.y_scale_p0[0], (self.y_scale_p1 - self.y_scale_p0[0]), py_per_m
        except:
            py_per_m = 0.

#        try:
#            print "px ", px_per_m, " py ", py_per_m, " yp1 ", self.y_scale_p1, " yp0 ", self.y_scale_p0[1]
#        except:
#            pass

        try:
            if 0 < px_per_m:
                self.width_m = self.pilImageOrg.size[0] / px_per_m
            else:
                self.width_m = self.pilImageOrg.size[0] / py_per_m

            if 0 < py_per_m:
                self.height_m = self.pilImageOrg.size[1] / py_per_m
            else:
                self.height_m = self.pilImageOrg.size[1] / px_per_m
        except ZeroDivisionError:
            pass

    def update_label(self, event):
        m = self.mousepos_img
        self.compute_width_height()

        label_text = "(%i, %i) %g" % (m[0], m[1], self.scale)
        label_text += "  size (%i %i) px" % self.pilImageOrg.size
        label_text += "  (%6.3f %6.3f) m" % (self.width_m, self.height_m)
        #label_text += str(self.last_split_was_left)

        self.label.SetLabel(label_text)

    def coord_img2piv(self, p):
        x = p[0]
        y = self.pilImage.size[1] - p[1] - 1
        return (x, y)


    def read_fit(self):
        output = importruntime.importRuntime(self.options.output)

    def write(self):
        self.x_splits.sort()
        self.x_splits.append(self.pilImageOrg.size[0])
        self.y_splits.sort()
        self.y_splits.append(self.pilImageOrg.size[1])
        s = textwrap.dedent("""
        facades.append(Texture('%s',
            %1.1f, %s, True,
            %1.1f, %s, False, True,
            v_split_from_bottom = True,
            requires=[],
            provides=[]))
        """ % (self.in_file_name, self.width_m, str(self.x_splits),
               self.height_m, str(self.y_splits)))
#        f.close()
        f = open(self.out_file_name, "w")
        f.write(s)
        f.close()
        print s


    def dump_pressed(self, event): # wxGlade: MyFrame.<event_handler>
        self.write()
        #sys.exit(1)

    def toggle2_pressed(self, event):
        f = open('fit.fail', 'w')
        f.close()
        sys.exit(1)

    def toggle3_pressed(self, event):
        pass

    def OnSize(self, event=0):
        #print "onsize"
        pass

    def screen2img(self, screen_pos):
        try:
            return [x / self.scale for x in screen_pos]
        except TypeError:
            return screen_pos / self.scale


        #screen_pos / self.scale
    def img2screen(self, image_pos):
        try:
            return [int(x * self.scale) for x in image_pos]
        except TypeError:
            return int(image_pos * self.scale)

    def OnPaint(self, event=0):
        #print "paint"
        dc = wx.PaintDC(self.panel)
        dc.DrawBitmap(self.Bitmap, 0, 0, True)
        dc.SetPen(wx.Pen('red', 2))
        x1, y1 = self.pilImage.size

        for x in self.x_splits:
            x = self.img2screen(x)
            dc.DrawLine(x, 0, x, y1)

        if self.IsLeftDragging:
            a = self.GetMousePos(event)
            drag_start_scr = self.img2screen(self.drag_start)
            dc.DrawLine(drag_start_scr[0], drag_start_scr[1], a[0], drag_start_scr[1])
        elif self.x_scale_p0 != None:
            p0 = self.img2screen(self.x_scale_p0)
            p1 = self.img2screen(self.x_scale_p1)
            dc.DrawLine(p0[0], p0[1], p1, p0[1])

        dc.SetPen(wx.Pen('blue', 2))
        for y in self.y_splits:
            y = self.img2screen(y)
            dc.DrawLine(0, y, x1, y)

        if self.IsRightDragging:
            a = self.GetMousePos(event)
            drag_start_scr = self.img2screen(self.drag_start)
            dc.DrawLine(drag_start_scr[0], drag_start_scr[1], drag_start_scr[0], a[1])
        elif self.y_scale_p0 != None:
            p0 = self.img2screen(self.y_scale_p0)
            p1 = self.img2screen(self.y_scale_p1)
            dc.DrawLine(p0[0], p0[1], p0[0], p1)

        dc.SetBrush(wx.Brush("grey", style=wx.TRANSPARENT))
#        try:
#            a = self.GetMousePos(event)
#            dc.DrawCircle(a[0], a[1], 5)
#        except:
#            pass



#    def PickPoint(self, event):
#        self.points[self.state] = self.GetMousePos(event) # position tuple
#        self.compute_origin()
#        self.OnPaint()

    def OnLeftUp(self, event):
        self.left_click = self.screen2img(self.GetMousePos(event))
        if not self.IsLeftDragging:
            if event.ShiftDown():
                self.x_splits = self.x_splits[:-1]
            else:
                self.x_splits.append(int(self.left_click[0]))
        else:
            self.IsLeftDragging = False
            self.x_scale_p0 = copy.copy(self.drag_start)
            self.x_scale_p1 = self.left_click[0]
            self.text_ctrl_x.SetFocus()

        self.update_label(event)
        self.OnPaint()

    def OnRightUp(self, event):
        self.right_click = self.screen2img(self.GetMousePos(event))
        if not self.IsRightDragging:
            if event.ShiftDown():
                self.y_splits = self.y_splits[:-1]
            else:
                self.y_splits.append(int(self.right_click[1]))
        else:
            self.IsRightDragging = False
            self.y_scale_p0 = copy.copy(self.drag_start)
            self.y_scale_p1 = self.right_click[1]
            self.text_ctrl_y.SetFocus()
        self.update_label(event)
        self.OnPaint()

    def fit_to_click(self):
        pass

    def OnMiddleDown(self, event):
        self.OnPaint()
        event.Skip()

    def OnRightDown(self, event):
        self.drag_start = self.screen2img(self.GetMousePos(event))
        #np.array(self.GetMousePos(event))
        self.OnPaint(event)
        event.Skip()

    def OnLeftDown(self, event):
        self.drag_start = self.screen2img(self.GetMousePos(event))
        self.OnPaint(event)
        event.Skip()

    def GetMousePos(self, event):
        return event.GetPosition()

    def OnMouseMove(self, event):
        self.mousepos_img = self.screen2img(self.GetMousePos(event))
        self.update_label(event)
        #self.SetTitle('LeftMouse = ' + str(pt))

        if event.LeftIsDown():
            self.IsLeftDragging = True
            self.OnPaint(event)
        elif event.RightIsDown():
            self.IsRightDragging = True
            self.OnPaint(event)
        else:
            self.IsLeftDragging = False
            self.IsRightDragging = False
            #self.OnPaint(event)

#            self.PickPoint(event)

    def OnMouseWheel(self, event):
        if event.ShiftDown():
            fac = 0.8
            if event.GetWheelRotation() < 0: fac = 1/fac
            self.r_minus *= fac
            self.r_plus *= fac
            self.OnPaint()
            return

        self.OnPaint()
        #event.Skip()

    def OnKey(self, event):
        event.Skip()
        #print "key", event.GetKeyCode()
#        if event.GetKeyCode() == wx.WXK_BACK or event.GetKeyCode() == wx.WXK_DELETE:
#            self.update_label(event)
#            self.OnPaint()
#        else:
#            event.Skip()


if __name__ == "__main__":

    global options
    parser = OptionParser()
    parser.add_option("-l", "--loop", action="store_true", help="loop until converged")
    parser.add_option("-g", "--noGUI", action="store_true", help="start without GUI")
    parser.add_option("-o", "--output", help="write to output file FILE", default='fit.py')
    (options, args) = parser.parse_args()

    if len(sys.argv) < 2:
        print "usage:", PROG, "[--noGUI] image"
        sys.exit(1)

    app = wx.PySimpleApp(0)
    wx.InitAllImageHandlers()
    frame = MyFrame(None, -1, "")
    app.SetTopWindow(frame)
    frame.Show()

    app.MainLoop()
