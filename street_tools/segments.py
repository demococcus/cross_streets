# -*- coding: utf-8 -*-

import arcpy
from arcgis.geometry import Polyline

from features import TPGeometry, FCCollection


class SegmentModel:
    """Street segment object."""

    street_name_field = None

    def __init__(self, feat=None):

        self.feat = None
        self.geom = None
        self.tpGeom = None

        self.id = None
        self.streetName = None

        self.deltaBearing = None
        self.startLeft, self.startRight, self.endLeft, self.endRight = None, None, None, None

        if feat is not None: self._readFromFeat(feat)

    def _readFromFeat(self, feat):
        self.feat = feat
        self.geom = feat.geometry

        arcpy_geom = Polyline(feat.geometry).as_arcpy
        self.tpGeom = TPGeometry(arcpy_geom.type, arcpy_geom.getPart())

        self.id = feat.attributes['OBJECTID']
        self.streetName = feat.attributes[self.street_name_field]

    @classmethod
    def setFieldNames(cls, field_names_list):
        cls.id = field_names_list[0]
        cls.street_name_field = field_names_list[1]

    def find_cross_streets(self, tran_collection):
        """
        Finds the corresponding cross-streets.

        :param tran_collection: collection of candidates
        :return: set of cross streets
        """

        def match_coord(first_point, second_point):
            """
            Compares the coordinates of two points.

            :param first_point: the first point
            :param second_point: the second point
            :return: True if the rounded coordinates are identical
            """
            if round(first_point.X) == round(second_point.X) and round(first_point.Y) == round(second_point.Y):
                return True
            else:
                return False

        def closest_to_parallel(tran_list):
            closest_tran = None
            min_angle = 181

            for candidate_tran in tran_list:
                candidate_angle = 181
                if candidate_tran.deltaBearing <= 180:
                    candidate_angle = 180 - candidate_tran.deltaBearing
                elif candidate_tran.deltaBearing > 180:
                    candidate_angle = candidate_tran.deltaBearing - 180
                if candidate_angle < min_angle:
                    min_angle = candidate_angle
                    closest_tran = candidate_tran

            return closest_tran

        # none or too many candidates
        if not tran_collection.members:
            arcpy.AddError("The segment does not have any cross streets.")
        elif len(tran_collection.members) > 20:
            arcpy.AddError("Aborting: the number of the cross streets is more than 20.")
            return

        # divide to start and end cross streets
        start_tran_list = []
        end_tran_list = []
        street_geom = self.tpGeom

        for tran in tran_collection.members:

            if match_coord(street_geom.firstPoint, tran.tpGeom.firstPoint): start_tran_list.append(tran)

            if match_coord(street_geom.firstPoint, tran.tpGeom.lastPoint):
                # utiliser la géométrie inversée
                tran.tpGeom = tran.tpGeom.invert()
                start_tran_list.append(tran)

            if match_coord(street_geom.lastPoint, tran.tpGeom.firstPoint):
                end_tran_list.append(tran)

            if match_coord(street_geom.lastPoint, tran.tpGeom.lastPoint):
                # utiliser la géométrie inversée
                tran.tpGeom = tran.tpGeom.invert()
                end_tran_list.append(tran)

        # === find the START cross streets ===

        if start_tran_list:

            # calculate the azimuth of the street with the FIRST two points
            street_bearing = street_geom.bearing(street_geom.firstPoint, street_geom.secondPoint)

            for tran in start_tran_list:
                # calculate the azimuth of the cross street with the first two points
                tran.bearing = tran.tpGeom.bearing(tran.tpGeom.firstPoint, tran.tpGeom.secondPoint)

                # calculate the angle between the street and the cross street
                tran.deltaBearing = tran.bearing - street_bearing
                if tran.deltaBearing < 0: tran.deltaBearing += 360

            # sort by angle
            start_tran_list.sort(key=lambda x: x.deltaBearing, reverse=False)

            # find the cross street with the same street name
            same_odo_tran_list = [x for x in start_tran_list if x.streetName == self.streetName]
            if same_odo_tran_list:
                same_street = closest_to_parallel(same_odo_tran_list)
                # remove the segment from the cross candidates list
                start_tran_list = [x for x in start_tran_list if x not in [same_street]]

            # divide the list to left and right
            start_right_list = [x for x in start_tran_list if 0 <= x.deltaBearing <= 180]
            start_left_list = [x for x in start_tran_list if 180 < x.deltaBearing <= 360]

            # get the smaller angular distance
            if start_right_list: self.startRight = start_right_list[0].streetName
            if start_left_list: self.startLeft = start_left_list[-1].streetName

        # === find the END cross streets ===

        if end_tran_list:

            # calculate the azimuth of the street with the LAST two points
            street_bearing = street_geom.bearing(street_geom.lastPoint, street_geom.beforeLastPoint)

            for tran in end_tran_list:
                # calculate the azimuth of the cross street with the first two points
                tran.bearing = tran.tpGeom.bearing(tran.tpGeom.firstPoint, tran.tpGeom.secondPoint)

                # calculate the angle between the street and the cross street
                tran.deltaBearing = tran.bearing - street_bearing
                if tran.deltaBearing < 0: tran.deltaBearing += 360

            # sort by angle
            end_tran_list.sort(key=lambda x: x.deltaBearing, reverse=False)

            # find the cross street with the same street name
            same_odo_tran_list = [x for x in end_tran_list if x.streetName == self.streetName]
            if same_odo_tran_list:
                same_street = closest_to_parallel(same_odo_tran_list)
                # remove the segment from the cross candidates list
                end_tran_list = [x for x in end_tran_list if x not in [same_street]]

            # divide the list to left and right
            end_left_list = [x for x in end_tran_list if 0 <= x.deltaBearing <= 180]
            end_right_list = [x for x in end_tran_list if 180 < x.deltaBearing <= 360]

            # get the smaller angular distance
            if end_right_list: self.endRight = end_right_list[-1].streetName
            if end_left_list: self.endLeft = end_left_list[0].streetName

        return self.startLeft, self.startRight, self.endLeft, self.endRight


class SegmentCollection(FCCollection):
    """Street segment objects collection."""

    elementsModel = SegmentModel

    editableProperties = ["streetName"]
