# -*- coding: utf-8 -*-

import arcpy
import math
from time import sleep


class TPGeometry(arcpy.Geometry):
    """Equivalent to ArcPy Geometry with some extra methods and properties."""
    secondPoint = None
    beforeLastPoint = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._getSecondPoints()

    def _getSecondPoints(self):
        """Finds the secondPoint and the beforeLastPoint."""
        pt_array = self.getPart()[0]

        self.secondPoint = pt_array[1]
        self.beforeLastPoint = pt_array[-2]

    def invert(self):
        """
        Inverts the position of the vertices in the geometry.

        :return: inverted geometry
        """
        pt_array = self.getPart()[0]
        inverted_array = arcpy.Array(list(reversed(pt_array)))
        inverted_geom = TPGeometry(self.type, inverted_array)

        return inverted_geom

    def bearing(self, start=None, end=None):
        """
        Finds the azimuth of a line.

        :param start: the start of the vector (default = firstPoint)
        :param end: the end of the vector (default = lastPoint)


        :return: the azimuth in degrees
        """

        if start is None: start = self.firstPoint
        if end is None: end = self.lastPoint

        bearing = None

        xa = start.X
        ya = start.Y
        xb = end.X
        yb = end.Y

        if xa < xb and ya < yb:
            # quadrant I
            a = xb - xa
            b = yb - ya
            c = math.sqrt(a ** 2 + b ** 2)
            bearing = math.degrees(math.asin(a / c))

        elif xa < xb and ya > yb:
            # quadrant II
            a = ya - yb
            b = xb - xa
            c = math.sqrt(a ** 2 + b ** 2)
            bearing = 90 + math.degrees(math.asin(a / c))

        elif xa > xb and ya > yb:
            # quadrant III
            a = xa - xb
            b = ya - yb
            c = math.sqrt(a ** 2 + b ** 2)
            bearing = 180 + math.degrees(math.asin(a / c))

        elif xa > xb and ya < yb:
            # quadrant IV
            a = yb - ya
            b = xa - xb
            c = math.sqrt(a ** 2 + b ** 2)
            bearing = 270 + math.degrees(math.asin(a / c))

        elif xa == xb and ya < yb:
            bearing = 0

        elif xa < xb and ya == yb:
            bearing = 90

        elif xa == xb and ya > yb:
            bearing = 180

        elif xa > xb and ya == yb:
            bearing = 270

        if bearing is not None: bearing = round(bearing, 6)

        return bearing


class FCCollection:
    """Wrapper for the basic ArcGIS API operations."""
    featLayer = None

    members = []
    elementsModel = None

    selectAttrList = None
    editAttrList = None
    editableProperties = None

    aprxLayerName = None
    descr = None

    def __init__(self):
        self.members = []

    def readSelected(self, required_min=None, required_max=None):
        """
        Reads the selected features from the corresponding layer in the aprx project.
        Creates and stores the objects in the members list.

        :param required_min: required minimum (optional, integer)
        :param required_max: permitted maximum (optional, integer)
        """

        if self.descr is None: self.descr = arcpy.Describe(self.aprxLayerName)

        fid_set = self.descr.FIDset
        if fid_set != "":
            fid_list = fid_set.split("; ")
        else:
            fid_list = []

        nb_selected = len(fid_list)

        # validate the number of the selected features
        if required_min is not None and required_max is not None \
                and required_min == required_max and nb_selected != required_min:
            arcpy.AddError(f"Please select {required_min} features from \"{self.aprxLayerName}\" layer.")
            exit()
        elif required_min is not None and nb_selected < required_min:
            arcpy.AddError(f"Please select at least {required_min} features from \"{self.aprxLayerName}\" layer.")
            exit()
        elif required_max is not None and nb_selected > required_max:
            arcpy.AddError(f"Please select {required_min} or less features from \"{self.aprxLayerName}\" layer.")
            exit()

        if not fid_list: return

        # read the corresponding features
        object_ids = fid_set.replace(";", ",")
        self.readFromQuery(object_ids=object_ids)

    def readFromQuery(self, where_clause=None, object_ids=None):
        """
        Reads features from Query statement. Based on See ArcGIS REST APIs Query (Feature Service/Layer).
        Creates and stores the objects in the members list.

        :param where_clause: A WHERE clause for the query filter. Example: "OBJECTID in (29, 30)"
        :param object_ids: The object IDs of this layer or table to be queried. Example: "29, 30"
        """

        # verify the privileges
        query_capability = 'Query' in self.featLayer.properties.capabilities
        if not query_capability:
            arcpy.AddWarning(
                f'You do not have enough privileges to read from the layer "{self.featLayer.properties.name}"')

        # verify the parameters
        if where_clause is None and object_ids is None: return

        # query feature layer
        feature_set = self.featLayer.query(
            where=where_clause,
            objectIds=object_ids,
            out_fields=','.join(self.selectAttrList),
            return_geometry=True)

        # populate members list
        self.members = []
        for feat in feature_set.features:
            feat_obj = self.elementsModel(feat)
            self.members.append(feat_obj)

    def save(self, update_geom=True):
        """Saves the members of the collection in the corresponding feature layer.
        Based on arcgis.features module."""

        # verify the privileges
        query_capability = 'Update' in self.featLayer.properties.capabilities
        if not query_capability:
            arcpy.AddWarning(f'You do not have enough privileges to update the layer "{self.featLayer.properties.name}"')
            return

        for member in self.members:
            # get the properties of the member in a list

            values = [value for attr, value in member.__dict__.items() if attr in self.editableProperties]

            # actualiser les attributs de la Feature
            for i in range(0, len(self.editAttrList)):
                member.feat.set_value(field_name=self.editAttrList[i], value=values[i])

            # actualiser la géométrie
            if update_geom and hasattr(member, 'geom') and member.geom is not None:
                member.feat.geometry = member.geom

        try:
            arcpy.AddMessage([x.feat for x in self.members])
            result = self.featLayer.edit_features(updates=[x.feat for x in self.members])
            return result['updateResults']

        except Exception as e: arcpy.AddError(f"Write Failed: {e}")

    def selectMembers(self):

        if not self.members: return

        jointeur = ', '.join([str(x.id) for x in self.members])
        where_clause = f'OBJECTID in ({jointeur})'

        result = arcpy.SelectLayerByAttribute_management(self.aprxLayerName, "NEW_SELECTION", where_clause)
        while result.status < 4: sleep(0.2)
