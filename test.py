"""test/debug routines
"""

def show_nodes(osm_id, nodes, refs, nodes_dict, left, right):
    print "OSM_ID %i" % osm_id
    print "  nodes\n", nodes
    print "  refs", refs
    for r in refs:
        n = nodes_dict[r]
        print "  ", n.lon, n.lat
    print "left", left.coords

def scale_test(transform, elev):
    pass
    """
    put 4 objects into scenery
    2 poles 1000m apart. Two ac, origin same, but one is offset in ac. Put both
    at same location in stg
    2 acs, at different stg location
    Result: at 100m 35 cm difference
            at 1000m 3.5m
            0.35%
    """
    p0 = vec2d(transform.toGlobal((0,0)))
    p100 = vec2d(transform.toGlobal((100,0)))
    p1k = vec2d(transform.toGlobal((1000,0)))
    p10k = vec2d(transform.toGlobal((10000,0)))
#    BLA
    e0 = elev(p0, is_global=True)
    e100 = elev(p100, is_global=True)
    e1k = elev(p1k, is_global=True)
    e10k = elev(p10k, is_global=True)
    quick_stg_line('cursor/cursor_blue.ac', p0, e0, 0, show=3)
    quick_stg_line('cursor/cursor_red.ac', p100, e100, 0, show=2)
    quick_stg_line('cursor/cursor_red.ac', p1k, e1k, 0, show=2)
    quick_stg_line('cursor/cursor_red.ac', p10k, e10k, 0, show=2)

    p0 = vec2d(transform.toGlobal((0, 0)))
    p1 = vec2d(transform.toGlobal((1., 0)))
    print p0, p1

