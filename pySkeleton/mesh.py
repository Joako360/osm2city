#===============================================================================
#   File :      mesh.py
#   Author :    Olivier Teboul, olivier.teboul@ecp.fr
#   Date :      31 july 2008, 14:03
#   Class :     Mesh
#===============================================================================

import point3D
#import rainbow
from vec2d import vec2d

class Mesh:
    """
    A mesh is represented by an indexed face structure (IFS):
        * a list of vertices
            -> a vertex is a 3D point
        * a list of faces
            -> a face is a list of indices from the vertices list
    
    This class provides methods to :
        * create a 3D Mesh
        * save it as a sketchup file
        * save and load (with a internal format)
    """
    
    def __init__(self,vertices = [], faces = []):
        self.vertices   = vertices
        self.faces      = faces
        self.nv         = len(self.vertices)
        self.nf         = len(self.faces)
        
    def add_vertex(self,p):
        """
        add a vertex into the list of vertices if the vertex is not already in the list
        @return the index of the vertex in the vertices list
        """
        try :
            return self.vertices.index(p)
        except(ValueError):
            self.vertices.append(p)
            self.nv += 1
            return self.nv-1
        
    def add_face(self,face):
        """ add a face an return the index of the face in the list """
        self.faces.append(face)
        self.nf += 1
        return self.nf-1
    
#    def sketchup_export(self,filename):
#        """ export the Mesh as a ruby script readable by Google SketchUp """
#        ruby = open(filename,'w')
#        ruby.write("require 'sketchup.rb'\n\n")
#        ruby.write("model = Sketchup.active_model\n")
#        ruby.write("entities = model.entities\n")
#        ruby.write("definitions = model.definitions\n")
#        ruby.write("materials = model.materials\n")
#        
#        ruby.write('compDef = definitions.add "my_mesh"\n')
#        ruby.write("compEnt = compDef.entities\n")
#        ruby.write("points = []\n")
#        
#        for index in range(len(self.vertices)):
#            p = self.vertices[index]
#            ruby.write("points[%i] = Geom::Point3d.new(%f,%f,%f)\n" %(index,p.x,p.y,p.z))
#        ruby.write("\n\n")
#        
#        for f_i in range(len(self.faces)):
#            face = self.faces[f_i]
#            ruby.write("face%i = compEnt.add_face [" %(f_i))
#            for i in range(len(face)-1):
#                if not self.vertices[face[i]] == self.vertices[face[i-1]]:
#                    ruby.write("points[%i]," %(face[i]))
#            
#            ruby.write("points[%i]]\n" %(face[-1]))
#            ruby.write('materials.add "m%i"\n' %(f_i))
#            col = rainbow.Rainbow()
#            r,g,b = col.get(float(f_i)/float(len(self.faces)))
#            ruby.write('materials["m%i"].color = Sketchup::Color.new(%i,%i,%i)\n' %(f_i,r,g,b))
#            ruby.write('face%i.material = materials["m%i"]\n' %(f_i,f_i))
#            ruby.write('face%i.back_material = materials["m%i"]\n' %(f_i,f_i))
#            
#        ruby.write('entities.add_instance definitions["my_mesh"], Geom::Transformation.new\n\n')
    
#    def ascii_export(self,filename):
#        """ save the mesh in a ASCII file or in ruby , storing the list of vertices and the list of faces """
#        f = open(filename,'w')
#        
#        f.write("%i\n" %(self.nv))
#        for p in self.vertices:
#            f.write("%f %f %f\n" %(p.x,p.y,p.z))
#            
#        f.write("%i\n" %(self.nf))
#        for face in self.faces:
#            for index in face:
#                f.write("%i " %(index))
#            f.write("\n")
#            
#        f.close()

    def ac3d_string(self, name, offset_xy = vec2d(0,0), offset_z = 0., header = False):
        """return mesh as string in a AC3D format"""
        s = ""
        if header:
            s += "AC3Db\n"
            s += """MATERIAL "" rgb 1   1   1 amb 1 1 1  emis 0.0 0.0 0.0  spec 0.5 0.5 0.5  shi 64  trans 0\n"""
            s += "OBJECT world\nkids 1\n"
        s += "OBJECT poly\n"
        s += "name \"%s\"\n" % name
#        s += "texture 'a.png'\n")
        s += "numvert %i\n" % len(self.vertices)

        for p in self.vertices:
#            s += "%f %f %f\n" % (p.x, p.y, p.z)
            s += "%f %f %f\n" % (-(p.y - offset_xy.y), p.z + offset_z, -(p.x - offset_xy.x))
            
        s += "numsurf %i\n" % len(self.faces)
        for face in self.faces:
            s += "SURF 0x0\n"
            s += "mat 0\n"
            s += "refs %i\n" % len(face)
            for index in face[::-1]:
                s += "%i 0 0\n" % (index)
        s += "kids 0\n"
            
        return s
        
#    def save(self,filename):
#        """ save into ascii or rb depending on the extension """
#        
#        ext = filename.split('.')[-1]
#        if ext =="rb":
#            self.sketchup_export(filename)
#        else:
#            self.ascii_export(filename)
#            #self.ac3d_export(filename)
  
    
#    def load(self,filename):
#        """ load the mesh from a file """
#        f = open(filename,'r')
#        
#        self.nv = int(f.readline())
#        v       = []
#        for i in range(self.nv):
#            line = map(float,f.readline().split())
#            v.append(point3D.Point3D((line[0],line[1],line[2])))
#            
#        self.nf = int(f.readline())
#        fa      = []
#        for i in range(self.nf):
#            line = map(int,f.readline().split())
#            fa.append(line)
