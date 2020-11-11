import logging
import multiprocessing as mp
import os
from typing import List, Optional

import shapely.geometry as shg

from osm2city import parameters, piers, platforms, pylons
from osm2city.cluster import ClusterContainer
from osm2city.textures import materials as mat
from osm2city.types import osmstrings as s
from osm2city.utils import coordinates as co
from osm2city.utils import ac3d, utilities, stg_io2


OUR_MAGIC = "details"


def process_details(coords_transform: co.Transformation, lit_areas: Optional[List[shg.Polygon]],
                    fg_elev: utilities.FGElev, file_lock: mp.Lock = None) -> None:
    stats = utilities.Stats()
    # -- prepare transformation to local coordinates
    cmin, cmax = parameters.get_extent_global()

    # -- create (empty) clusters
    lmin = co.Vec2d(coords_transform.to_local(cmin))
    lmax = co.Vec2d(coords_transform.to_local(cmax))
    clusters = ClusterContainer(lmin, lmax)

    # piers
    the_piers = piers.process_osm_piers(coords_transform)
    logging.info("number of piers: %i", len(the_piers))
    for pier in the_piers:
        clusters.append(pier.anchor, pier, stats)
    for pier in the_piers:
        pier.calc_elevation(fg_elev)

    # platforms
    the_platforms = platforms.process_osm_platform(coords_transform)
    logging.info("number of platforms: %i", len(the_platforms))
    for platform in the_platforms:
        clusters.append(platform.anchor, platform, stats)

    # -- initialize STGManager
    path_to_output = parameters.get_output_path()
    stg_manager = stg_io2.STGManager(path_to_output, stg_io2.SceneryType.details, OUR_MAGIC, parameters.PREFIX)

    for cl in clusters:
        if cl.objects:
            center_tile = co.Vec2d(coords_transform.to_global(cl.center))
            ac_file_name = "%sd%i%i.ac" % (parameters.PREFIX, cl.grid_index.ix, cl.grid_index.iy)
            ac = ac3d.File(stats=stats)
            obj = ac.new_object('details', 'Textures/Terrain/asphalt.png', default_mat_idx=mat.Material.unlit.value)
            for detail in cl.objects[:]:
                if isinstance(detail, piers.Pier):
                    detail.write(obj, cl.center)
                else:
                    detail.write(fg_elev, obj, cl.center)
            path = stg_manager.add_object_static(ac_file_name, center_tile, 0, 0)
            file_name = os.path.join(path, ac_file_name)
            f = open(file_name, 'w')
            f.write(str(ac))
            f.close()

    piers.write_boats(stg_manager, the_piers, coords_transform)

    # -- write stg
    stg_manager.write(file_lock)

    # trigger processing of pylon related details
    _process_pylon_details(coords_transform, lit_areas, fg_elev, stg_manager, lmin, lmax, file_lock)


def _process_pylon_details(coords_transform: co.Transformation, lit_areas: Optional[List[shg.Polygon]],
                           fg_elev: utilities.FGElev, stg_manager: stg_io2.STGManager, lmin: co.Vec2d, lmax: co.Vec2d,
                           file_lock: mp.Lock = None) -> None:
    """Pylon details (mostly cables) go also into details, but cannot be processed together with piers and pylons."""
    # Transform to real objects
    logging.info("Transforming OSM data to Line and Pylon objects -> details")

    # References for buildings
    building_refs = list()
    storage_tanks = list()
    if parameters.C2P_PROCESS_AERIALWAYS or parameters.C2P_PROCESS_STREETLAMPS:
        building_refs = pylons.process_osm_building_refs(coords_transform, fg_elev, storage_tanks)
        logging.info('Number of reference buildings: %s', len(building_refs))

    # Minor power lines and aerialways
    powerlines = list()
    aerialways = list()
    req_keys = list()
    if parameters.C2P_PROCESS_POWERLINES and parameters.C2P_PROCESS_POWERLINES_MINOR:
        req_keys.append(s.K_POWER)
    if parameters.C2P_PROCESS_AERIALWAYS:
        req_keys.append(s.K_AERIALWAY)
    if req_keys:
        powerlines, aerialways = pylons.process_osm_power_aerialway(req_keys, fg_elev,
                                                                    coords_transform, building_refs)
        # remove all those power lines, which are not minor - after we have done the mapping in calc_and_map()
        for wayline in reversed(powerlines):
            wayline.calc_and_map()
            if wayline.type_ is pylons.WayLineType.power_line:
                powerlines.remove(wayline)
        logging.info('Number of minor power lines to process: %s', len(powerlines))
        logging.info('Number of aerialways to process: %s', len(aerialways))
        for wayline in aerialways:
            wayline.calc_and_map()

    # railway overhead lines
    rail_lines = list()
    if parameters.C2P_PROCESS_OVERHEAD_LINES:
        rail_lines = pylons.process_osm_rail_overhead(fg_elev, coords_transform)
        logging.info('Reduced number of rail lines: %s', len(rail_lines))
        for rail_line in rail_lines:
            rail_line.calc_and_map(fg_elev, coords_transform, rail_lines)
    # street lamps
    streetlamp_ways = list()
    if False:  # FIXME parameters.C2P_PROCESS_STREETLAMPS:
        highways = pylons.process_osm_highways(coords_transform)
        streetlamp_ways = pylons.process_highways_for_streetlamps(highways, lit_areas)
        logging.info('Reduced number of streetlamp ways: %s', len(streetlamp_ways))
        for highway in streetlamp_ways:
            highway.calc_and_map(fg_elev, coords_transform)

    # free some memory
    del building_refs

    cluster_container = ClusterContainer(lmin, lmax)

    if parameters.C2P_PROCESS_POWERLINES:
        pylons.distribute_way_segments_to_clusters(powerlines, cluster_container)
        pylons.write_stg_entries_pylons_for_line(stg_manager, powerlines)
    if parameters.C2P_PROCESS_AERIALWAYS:
        pylons.distribute_way_segments_to_clusters(aerialways, cluster_container)
        pylons.write_stg_entries_pylons_for_line(stg_manager, aerialways)
    if parameters.C2P_PROCESS_OVERHEAD_LINES:
        pylons.distribute_way_segments_to_clusters(rail_lines, cluster_container)
        pylons.write_stg_entries_pylons_for_line(stg_manager, rail_lines)

    pylons.write_cable_clusters(cluster_container, coords_transform, stg_manager, details=True)

    if parameters.C2P_PROCESS_STREETLAMPS:
        pylons.write_stg_entries_pylons_for_line(stg_manager, streetlamp_ways)

    stg_manager.write(file_lock)
