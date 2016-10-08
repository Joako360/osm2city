"""Atlas of textures, where a couple of textures are put into one file including thier attributes"""

import PIL.Image as Image
import logging


class Region(object):
    """Also used as a container for a single image"""
    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y        
        self.width_px = width
        self.height_px = height
        logging.debug("  New Region " + str(self))  # @UndefinedVariable

    def __str__(self):
        return "(%i x %i + %i + %i)" % (self.width_px, self.height_px, self.x, self.y)


class Atlas(Region):
    def __init__(self, x, y, width, height, name):
        super(Atlas, self).__init__(x, y, width, height)
        self.regions = [Region(x, y, width, height)]
        self._textures = []  # Type atlas.Texture
        self.min_width = 1
        self.min_height = 1
        self.name = name
        
    def cur_height(self):
        """return the current height"""
        return self.regions[-1].y

    def set_height(self, height):
        self.height_px = height
        self._compute_nondim_tex_coords()

    def write(self, filename, image_var):
        """Allocate memory for the actual atlas image, paste images, write to disk.
           image_var is the name (string) of the class variable that stores the image;
           usually in osm2city it's im or im_LM."""
        atlas = Image.new("RGB", (self.width_px, self.height_px))

        for the_texture in self._textures:
            the_image = getattr(the_texture, image_var)
            try:
                atlas.paste(the_image, (the_texture.ax, the_texture.ay))
            except ValueError:
                logging.debug("%s : %s: Skipping an empty texture" % (self.name, the_texture.filename))
        atlas.save(filename, optimize=True)

    def pack(self, the_texture):
        logging.debug("packing %s (%i %i)" % 
                      (the_texture.filename, the_texture.width_px, the_texture.height_px))
        for the_region in self.regions:
            if self._pack(the_texture, the_region):
                self._textures.append(the_texture)
                logging.debug("  packed at %i %i" % (the_texture.ax, the_texture.ay))
                logging.debug("now have %i regions" % len(self.regions))
                for a_region in self.regions:
                    logging.debug("  - " + str(a_region))
                return True
        return False

    def pack_at(self, the_texture, x, y):
        logging.debug("packing %s (%i %i) at (%i %i)" % 
                      (the_texture.filename, the_texture.width_px, the_texture.height_px, x, y))
        the_texture.ax = x
        the_texture.ay = y
        self._textures.append(the_texture)

    def _compute_nondim_tex_coords(self):
        """compute non-dim texture coords"""
        for t in self._textures:
            t.x0 = float(t.ax) / self.width_px
            t.x1 = float(t.ax + t.width_px) / self.width_px
            t.y1 = 1 - float(t.ay) / self.height_px
            t.y0 = 1 - float(t.ay + t.height_px) / self.height_px
            t.sx = float(t.width_px) / self.width_px
            t.sy = float(t.height_px) / self.height_px

    def _check_regions(self):
        for region1 in self.regions:
            if region1.width_px < self.min_width or region1.height_px < self.min_height:
                self.regions.remove(region1)
            for region2 in self.regions:
                if region2 == region1:
                    continue
                # -- check if we can join two regions
                if region1.x == region2.x and region1.width_px == region2.width_px \
                   and region1.y + region1.height_px == region2.y:
                    region1.height_px += region2.height_px
                    self.regions.remove(region2)

    def _pack(self, the_texture, the_region):
        assert(the_texture.height_px > 0)
        assert(the_texture.width_px > 0)
        if the_texture.height_px == the_region.height_px:
            if the_texture.width_px == the_region.width_px:
                logging.debug("H split exact fit")
                the_texture.ax = the_region.x
                the_texture.ay = the_region.y
                self.regions.remove(the_region)
                return True
            elif the_texture.width_px < the_region.width_px:
                logging.debug("H split")
                # split horizontally
                the_texture.ax = the_region.x
                the_texture.ay = the_region.y
                the_region.x += the_texture.width_px
                the_region.width_px -= the_texture.width_px
                self._check_regions()
                return True
            else:
                logging.debug("H too small (%i < %i), trying next" % (the_region.width_px, the_texture.width_px))
                return False
        elif the_texture.height_px > the_region.height_px:
            logging.debug("V too small, trying next")
            return False
        else:
            # check if it fits width
            if the_texture.width_px > the_region.width_px:
                return False
            logging.debug("V split")
            # vertical split
            the_texture.ax = the_region.x
            the_texture.ay = the_region.y
            new_region = Region(the_region.x, the_region.y + the_texture.height_px,
                                the_region.width_px, the_region.height_px - the_texture.height_px)
            the_region.x += the_texture.width_px
            the_region.width_px -= the_texture.width_px
            the_region.height_px = the_texture.height_px
            self.regions.insert(self.regions.index(the_region) + 1, new_region)
            self._check_regions()
            return True
