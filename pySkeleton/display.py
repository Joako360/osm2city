#===============================================================================
#   File :      display.py
#   Author :    Olivier Teboul olivier.teboul@ecp.fr
#   Date :      23 july 2008, 15:14
#   Class:      Viewer
#===============================================================================

from Tkinter import *
from aboutMe import AboutMe
import tkFileDialog
import polygon
import rainbow
import segment
import copy
import os

class Viewer(Frame):
    """
    Enables to handle the input of polygon and their display
    This class provides tools to :
        * save/load polygons
        * create a polygon by clicking points
        * display the sectors of the polygon
        * display the result of shrinks
    """

    def __init__(self):
        #inheritance
        Frame.__init__(self)

        #some options
        self.show_info              = False
        self.polygon                = None
        self.sector_index           = 0
        self.replace                = False
        self.show_grid              = True

        #menus
        self.menubar        = Menu(self.master)
        self.polygonmenu    = Menu(self.menubar)
        self.filemenu       = Menu(self.menubar)
        self.filemenu.add_command(label="Open", command=self.load)
        self.filemenu.add_command(label="Save", command=self.save)
        self.filemenu.add_separator()
        self.filemenu.add_command(label = "Exit", command=self.master.destroy)
        self.polygonmenu.add_command(label = "close current component", command=self.close_component)
        self.menubar.add_cascade(label = "File",    menu=self.filemenu)
        self.menubar.add_cascade(label = "Polygon", menu = self.polygonmenu)
        self.menubar.add_command(label = "clear", command = self.clear)
        self.menubar.add_command(label = "?", command = self.about)
        self.master.config(menu = self.menubar)

        #Canvas
        self.size       = 700
        self.offset     = 30
        self.grid_step  = 50
        self.canvas     = Canvas(self,width = self.size, height = self.size, bg='white')
        self.canvas.grid(row = 0, column = 0 )

        #Control panel on right the side
        self.control_panel          = Frame(self,width = 100, height = self.size, bg = 'light gray')
        self.control_panel.grid(row = 0, column = 1,sticky = N)

        self.speed_frame            = Frame(self.control_panel, relief = 'groove', borderwidth = 2, bg='light blue')
        self.speed_entry            = Entry(self.speed_frame,width = 30)
        self.speed_label            = Label(self.speed_frame, text = 'Speed', bg='light blue')
        self.speed_entry.insert(0,1)
        self.speed_frame.grid(row = 0, column =0, padx = 10, pady = 10)
        self.speed_label.grid(row = 0, column=0, padx = 20, pady = 20)
        self.speed_entry.grid(row = 0, column=1, padx = 20, pady = 20)

        self.shrink_frame           = Frame(self.control_panel,bd=1,bg='light blue', relief = 'groove', borderwidth = 2)
        self.shrink_entry           = Entry(self.shrink_frame,width = 30)
        self.shrinking_button       = Button(self.shrink_frame, text = 'Shrink', bg = 'orange', command = self.shrink_button)
        self.shrink_entry.insert(0,10)
        self.shrink_frame.grid(row = 1, column =0, padx = 10, pady = 10)
        self.shrink_entry.grid(row = 0, column=1, padx = 20, pady = 20)
        self.shrinking_button.grid(row=0,column = 0, padx = 20, pady = 20)

        self.next_event_frame       = Frame(self.control_panel,bg = 'light blue', relief = 'groove', borderwidth=2)
        self.next_event_string      = StringVar(self.next_event_frame)
        self.next_event_label       = Label(self.next_event_frame,bg='light blue',width=30,textvariable = self.next_event_string, font=("Helvetica", 14), fg='blue')
        self.next_event_frame.grid(row=3, column = 0, padx = 10, pady = 10)
        self.next_event_label.grid(row = 0, column=0, padx = 20, pady = 20)

        self.roof_frame             = Frame(self.control_panel,bd=1,bg='light blue', relief = 'groove', borderwidth = 2)
        self.roof_angle_entry       = Entry(self.roof_frame,width = 20)
        self.roof_height_entry      = Entry(self.roof_frame,width = 20)
        self.roof_angle_label       = Label(self.roof_frame,text='Angle',bg='light blue')
        self.roof_height_label      = Label(self.roof_frame,text='Height',bg='light blue')
        self.roofing_button         = Button(self.roof_frame, text = 'loft', bg = 'orange', command = self.roof_button)
        self.roof_angle_entry.insert(0,80)
        self.roof_height_entry.insert(0,20)
        self.roof_frame.grid(row = 4, column =0, padx = 10, pady = 10)
        self.roof_angle_label.grid(row = 0, column=0, padx = 20, pady = 5)
        self.roof_angle_entry.grid(row = 0, column=1, padx = 20, pady = 5)
        self.roof_height_label.grid(row = 1, column=0, padx = 20, pady = 5)
        self.roof_height_entry.grid(row = 1, column=1, padx = 20, pady = 5)
        self.roofing_button.grid(row=0,column = 2, rowspan = 2, padx = 20, pady = 5)

        self.skeleton_frame         = Frame(self.control_panel,bd=1,bg='light blue', relief = 'groove', borderwidth = 2)
        self.skeleton_angle_entry   = Entry(self.skeleton_frame,width = 20)
        self.skeleton_angle_label   = Label(self.skeleton_frame,text='Angle',bg='light blue')
        self.skeleton_button        = Button(self.skeleton_frame, text = 'Skeleton', bg = 'orange', command = self.straight_skeleton_button)
        self.roof3D_button          = Button(self.skeleton_frame, text = 'roof3D', bg = 'orange', command = self.roof_3D_button)
        self.faces_button           = Button(self.skeleton_frame, text = 'faces', bg = 'orange', command = self.show_faces_button)
        self.skeleton_angle_entry.insert(0,50)
        self.skeleton_frame.grid(row = 5, column =0, padx = 10, pady = 10)
        self.skeleton_angle_label.grid(row = 0, column=0, padx = 20, pady = 5)
        self.skeleton_angle_entry.grid(row = 0, column=1, padx = 20, pady = 5)
        self.skeleton_button.grid(row=1,column = 0, rowspan = 2, padx = 20, pady = 5)
        self.faces_button.grid(row=1,column = 1, rowspan = 2, padx = 20, pady = 5)
        self.roof3D_button.grid(row=1,column = 2, rowspan = 2, padx = 20, pady = 5)

        self.display_option_frame   = Frame(self.control_panel, bg = 'light blue', relief = 'groove', borderwidth=2)
        self.infoedge_button        = Button(self.display_option_frame,text = "Edge Info", command=self.switch_info_button,bg='green')
        self.grid_button            = Button(self.display_option_frame, text = "Grid", command = self.onOffGrid_button,bg='red')
        self.replace_mode_button    = Button(self.display_option_frame, text = 'Replaced Mode', command = self.change_replace_mode_button,bg='red')
        self.display_option_frame.grid(row=6, column=0, padx = 10, pady = 10)
        self.infoedge_button.grid(row = 0, column=0, padx = 30, pady = 20)
        self.grid_button.grid(row = 0, column=1, padx = 10, pady = 20)
        self.replace_mode_button.grid(row = 0, column=2, padx = 30, pady = 20)

        #Methods binding
        self.canvas.bind("<Button-1>",self.click)
        self.canvas.bind("<Button-3>",self.undo)
        self.master.bind("<Return>", self.close_polygon)
        self.master.bind("<Escape>",self.leave)
        self.master.bind("<space>",self.change_sector_display)
        self.master.bind('i',self.switch_info)
        self.master.bind('z',self.close_component)
        self.master.bind('s',self.shrink)
        self.master.bind('u',self.unshrink)
        self.master.bind('r',self.change_replace_mode)
        self.master.bind('g',self.onOffGrid)

        #store the clicked points
        self.clicked_vertices       = []
        self.clicked_edges          = []
        self.clicked_speeds         = []
        self.last_component_start   = 0

        self.update()
        self.master.title("pySkeleton!")
        self.grid()

    def leave(self,event):
        self.master.destroy()

    def load(self):
        filename = tkFileDialog.askopenfilename(filetypes = [("Fichiers Polygones","*.fp"),("All", "*")])
        if filename:
            self.clear()
            self.polygon = polygon.Polygon([])
            self.polygon.load(filename)
            self.polygon.display(self)
            self.update_control()

    def save(self):
        myFile = tkFileDialog.asksaveasfile(filetypes = [("Fichiers Polygones","*.fp"),("All", "*")])
        if self.polygon and myFile:
            self.polygon.save(myFile.name)

    def display_grid(self):
        for i in range(0,self.size+1,self.grid_step):
            self.canvas.create_line(i,0,i,self.size,fill='gray',width=1)
            self.canvas.create_line(0,i,self.size,i,fill='gray',width=1)

    def display(self):
        if self.show_grid:
            self.display_grid()

        if self.polygon:
            self.polygon.display(self)

    def update(self):
        self.update_control()
        self.clear()
        self.display()

    def update_control(self):
        if self.polygon:

            ev = self.polygon.first_event()[0]
            fe = ev[0]
            for e in ev:
                if e.isSplitEvent():
                    fe = e
                    break

            s  = ""
            if fe.isEdgeEvent():
                s = "Edge Event"
            elif fe.isSplitEvent():
                s = "Split Event"

            self.next_event_string.set("Next Event to occur : \n\n" + s + "\n distance to event : %f\n%i event(s)\n" %(fe.shrinking_distance,len(ev)) )

        #grid
        if self.show_grid:
            self.grid_button.config(bg='green')
        else:
            self.grid_button.config(bg='red')

        if self.show_info:
            self.infoedge_button.config(bg='green')
        else:
            self.infoedge_button.config(bg='red')


    def close_polygon(self,event):
        print "closing"
        if not self.last_component_start == len(self.clicked_vertices):
            self.clicked_edges.append((len(self.clicked_vertices)-1,self.last_component_start))
            self.clicked_speeds.append(float(self.speed_entry.get()))

        self.last_component_start = 0

        self.polygon = polygon.Polygon(self.clicked_vertices,
                                       self.clicked_edges,
                                       self.clicked_speeds)
        print self.polygon
        self.clear()
        self.polygon.display(self)
        self.update_control()

    def clear(self):
        self.canvas.delete(ALL)
        if self.show_grid:
            self.display_grid()
        self.clicked_vertices   = []
        self.clicked_edges      = []
        self.clicked_speeds     = []

        self.speed_entry.delete(0,END)
        self.speed_entry.insert(0,1)

    def change_sector_display(self,event):
        self.sector_index = (self.sector_index+1)%self.polygon.n
        self.update()
        self.polygon.sectors[self.sector_index].display(self)

    def switch_info(self,event):
        self.show_info = not self.show_info
        if self.show_info:
            self.infoedge_button.config(bg='green')
        else:
            self.infoedge_button.config(bg='red')
        self.update()

    def onOffGrid(self,event):
        self.show_grid = not self.show_grid
        if self.show_grid:
            self.grid_button.config(bg='green')
        else:
            self.grid_button.config(bg='red')
        self.update()

    def change_replace_mode(self,event):
        self.replace = not self.replace
        if self.replace:
            self.replace_mode_button.config(bg='green')
        else:
            self.replace_mode_button.config(bg='red')


    def switch_info_button(self):
        self.show_info = not self.show_info
        if self.show_info:
            self.infoedge_button.config(bg='green')
        else:
            self.infoedge_button.config(bg='red')
        self.update()

    def onOffGrid_button(self):
        self.show_grid = not self.show_grid
        if self.show_grid:
            self.grid_button.config(bg='green')
        else:
            self.grid_button.config(bg='red')
        self.update()

    def change_replace_mode_button(self):
        self.replace = not self.replace
        if self.replace:
            self.replace_mode_button.config(bg='green')
        else:
            self.replace_mode_button.config(bg='red')

    def click(self,event):
        #add the new point to the polygon, and the associated label
        self.clicked_vertices.append((float(event.x),float(event.y)))
        n = len(self.clicked_vertices)
        if n-self.last_component_start > 1:
            self.clicked_edges.append((n-2,n-1))
            self.clicked_speeds.append(float(self.speed_entry.get()))

        #display the points on the canvas
        if len(self.clicked_vertices)-self.last_component_start>1:
            self.last=self.canvas.create_line(self.clicked_vertices[-2][0],self.clicked_vertices[-2][1],
                                    self.clicked_vertices[-1][0],self.clicked_vertices[-1][1],
                                    width = 5, fill = 'green')

    def undo(self,event):
        del(self.clicked_vertices[-1])
        del(self.clicked_edges[-1])
        del(self.clicked_speeds[-1])
        self.canvas.delete(self.last)
        self.last-=1

    def close_component(self,event=None):
        print "close component"
        n = len(self.clicked_vertices)
        self.clicked_edges.append((n-1,self.last_component_start))
        self.clicked_speeds.append(float(self.speed_entry.get()))


        #display the points on the canvas
        if len(self.clicked_vertices)-self.last_component_start>1:
            self.last=self.canvas.create_line(self.clicked_vertices[-1][0],self.clicked_vertices[-1][1],
                                              self.clicked_vertices[self.last_component_start][0],self.clicked_vertices[self.last_component_start][1],
                                              width = 5, fill = 'green')

        self.last_component_start = len(self.clicked_vertices)


    def shrink(self,event):
        self.polygon.shrink(float(self.shrink_entry.get()))
        if self.replace:
            self.update()
        else:
            self.update_control()
        self.polygon.display(self)

    def shrink_button(self):
        print self.polygon
        self.polygon.shrink(float(self.shrink_entry.get()))
        if self.replace:
            self.update()
        else:
            self.update_control()
        self.polygon.display(self)

    def roof_button(self):
        roof = self.polygon.raise_loft(float(self.roof_angle_entry.get())*3.1415/180,float(self.roof_height_entry.get()))
        self.clear()
        roof.display(self)

    def straight_skeleton_button(self):
        self.clear()
        self.update_control()
        clone       = self.polygon.clone()
        skeleton    = clone.straight_skeleton()
        self.polygon.display(self)
        skeleton.display(self)
        print skeleton

    def show_faces_button(self):
        faces = self.polygon.straight_skeleton_faces()
        print "Faces:", faces
        color_gen = rainbow.Rainbow()
        for i in range(len(faces)):
            face = faces[i]
            pol = map(lambda x:x.getData(), face)
            self.canvas.create_polygon(pol,fill = color_gen.get_hexa_color(float(i)/float(len(faces))), outline = 'black',width = 3)

    def roof_3D_button(self):
        roof_mesh = self.polygon.roof_3D(float(self.skeleton_angle_entry.get())*3.1415/180.)
        roof_mesh.save("roof.ac")
        #curr_dir = os.getcwd()
        #os.chdir("C:/Program Files/Google/Google SketchUp 6/")
        #os.system("SketchUp.exe")
        #os.chdir(curr_dir)


    def unshrink(self,event):
        self.polygon.blind_shrink(float(self.shrink_entry.get()))
        if self.replace:
            self.update()
        self.polygon.display(self)

    def about(self):
        AboutMe(self)
