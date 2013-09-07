# -*- coding: utf-8 -*-
"""
Created on Thu Jan 06 17:54:15 2011

@author: teboul
"""

from Tkinter import *
import tkSimpleDialog

class AboutMe(tkSimpleDialog.Dialog):

    def body(self, master):
        self.title("About pySkeleton!")
        Label(master, text="pySkeleton implements weighted straight skeletons algorithm\nolivier.teboul@ecp.fr\nOlivier Teboul, Ecole Centrale Paris 2008").grid(row=0)

    def apply(self):
        pass