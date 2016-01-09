# -*- coding: utf-8 -*-
"""
/***************************************************************************
 OSRM
                                 A QGIS plugin
 Display your routing results from OSRM
                              -------------------
        begin                : 2015-10-29
        git sha              : $Format:%H$
        copyright            : (C) 2015 by mthh
        email                :
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from qgis.core import *
from qgis.utils import iface
from qgis.gui import QgsMapToolEmitPoint
from copy import copy
from PyQt4.QtCore import (
    QTranslator, qVersion, QCoreApplication,
    QObject, SIGNAL, Qt, pyqtSlot, QSettings
    )
from PyQt4.QtGui import (
    QAction, QIcon, QMessageBox,
    QColor, QProgressBar
    )
# Initialize Qt resources from file resources.py
import resources

# Import the code for the dialog
from osrm_dialog import (
    OSRMDialog, OSRM_table_Dialog, OSRM_access_Dialog, OSRM_batch_route_Dialog
    )

from .osrm_utils import *
from codecs import open as codecs_open
from sys import version_info
from httplib import HTTPConnection
import os.path
import json
import numpy as np
import csv


class OSRM(object):
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        self.dlg = None
        # Save reference to the QGIS interface
        self.iface = iface
        self.canvas = iface.mapCanvas()
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'OSRM_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Routing with OSRM')

        self.toolbar = self.iface.addToolBar(u'Routing with OSRM')
        self.toolbar.setObjectName(u'Routing with OSRM')
#        self.loadSettings()
        self.host = None
        self.http_header = {
            'connection': 'keep-alive',
            'User-Agent': ' '.join([
                'QGIS-desktop',
                QGis.QGIS_VERSION,
                '/',
                'Python-httplib',
                str(version_info[:3])[1:-1].replace(', ', '.')])
            }
    # noinspection PyMethodMayBeStatic

    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('Routing with OSRM', message)

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToWebMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        self.add_action(
            ':/plugins/OSRM/img/icon.png',
            text=self.tr(u'Find a route with OSRM'),
            callback=self.run_route,
            parent=self.iface.mainWindow())

        self.add_action(
            ':/plugins/OSRM/img/icon_table.png',
            text=self.tr(u'Get a time matrix with OSRM'),
            callback=self.run_table,
            parent=self.iface.mainWindow())

        self.add_action(
            ':/plugins/OSRM/img/icon_access.png',
            text=self.tr(u'Make accessibility isochrones with OSRM'),
            callback=self.run_accessibility,
            parent=self.iface.mainWindow(),
            )

        self.add_action(
            None,
            text=self.tr(u'Export many routes from OSRM'),
            callback=self.run_batch_route,
            parent=self.iface.mainWindow(),
            add_to_toolbar=False,
            )  # ':/plugins/OSRM/img/icon_batchroute.png'

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginWebMenu(
                self.tr(u'&Routing with OSRM'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar

    def store_origin(self, point):
        if '4326' not in self.canvas.mapSettings().destinationCrs().authid():
            crsSrc = self.canvas.mapSettings().destinationCrs()
            xform = QgsCoordinateTransform(
                crsSrc, QgsCoordinateReferenceSystem(4326))
            point = xform.transform(point)
        self.origin = point
        self.canvas.unsetMapTool(self.originEmit)
        self.dlg.lineEdit_xyO.setText(str(point))

    def store_intermediate(self, point):
        if '4326' not in self.canvas.mapSettings().destinationCrs().authid():
            crsSrc = self.canvas.mapSettings().destinationCrs()
            xform = QgsCoordinateTransform(
                crsSrc, QgsCoordinateReferenceSystem(4326))
            point = xform.transform(point)
        self.intermediate.append(tuple(map(lambda x: round(x, 6), point)))
        self.canvas.unsetMapTool(self.intermediateEmit)
        self.dlg.lineEdit_xyI.setText(str(self.intermediate)[1:-1])

    def store_intermediate_acces(self, point):
        if '4326' not in self.canvas.mapSettings().destinationCrs().authid():
            crsSrc = self.canvas.mapSettings().destinationCrs()
            xform = QgsCoordinateTransform(
                crsSrc, QgsCoordinateReferenceSystem(4326))
            point = xform.transform(point)
        tmp = self.dlg.lineEdit_xyO.text()
        self.dlg.lineEdit_xyO.setText(', '.join([tmp, repr(point)]))

    def store_destination(self, point):
        if '4326' not in self.canvas.mapSettings().destinationCrs().authid():
            crsSrc = self.canvas.mapSettings().destinationCrs()
            xform = QgsCoordinateTransform(
                crsSrc, QgsCoordinateReferenceSystem(4326))
            point = xform.transform(point)
        self.destination = point
        self.canvas.unsetMapTool(self.destinationEmit)
        self.dlg.lineEdit_xyD.setText(str(point))

    def get_origin(self):
        self.canvas.setMapTool(self.originEmit)

    def get_destination(self):
        self.canvas.setMapTool(self.destinationEmit)

    def get_intermediate(self):
        self.canvas.setMapTool(self.intermediateEmit)

    def reverse_OD(self):
        try:
            tmp = self.dlg.lineEdit_xyO.text()
            tmp1 = self.dlg.lineEdit_xyD.text()
            self.dlg.lineEdit_xyD.setText(str(tmp))
            self.dlg.lineEdit_xyO.setText(str(tmp1))
        except Exception as err:
            print(err)

    def clear_all_single(self):
        self.dlg.lineEdit_xyO.setText('')
        self.dlg.lineEdit_xyD.setText('')
        self.dlg.lineEdit_xyI.setText('')
        self.intermediate = []
        for layer in QgsMapLayerRegistry.instance().mapLayers():
            if 'route_osrm' in layer \
                    or 'instruction_osrm' in layer \
                    or 'markers_osrm' in layer:
                QgsMapLayerRegistry.instance().removeMapLayer(layer)
        self.nb_route = 0

    @pyqtSlot()
    def print_about(self):
        mbox = QMessageBox(self.iface.mainWindow())
        mbox.setIcon(QMessageBox.Information)
        mbox.setWindowTitle('About')
        mbox.setTextFormat(Qt.RichText)
        mbox.setText(
            "<p><b>(Unofficial) OSRM plugin for qgis</b><br><br>"
            "Author: mthh, 2015<br>Licence : GNU GPL v2<br><br><br>Underlying "
            "routing engine is <a href='http://project-osrm.org'>OSRM</a>"
            "(Open Source Routing Engine) :<br>- Based on OpenStreetMap "
            "dataset<br>- Easy to start a local instance<br>"
            "- Pretty fast engine (based on contraction hierarchies and mainly"
            " writen in C++)<br>- Mainly authored by D. Luxen and C. "
            "Vetter<br>(<a href='http://project-osrm.org'>http://project-osrm"
            ".org</a> or <a href='https://github.com/Project-OSRM/osrm"
            "-backend#references-in-publications'>on GitHub</a>)<br></p>")
        mbox.open()

    @lru_cache(maxsize=50)
    def query_url(self, url, host):
        self.conn.request('GET', url, headers=self.http_header)
        parsed = json.loads(self.conn.getresponse().read().decode('utf-8'))
        return parsed

    @pyqtSlot()
    def get_route(self):
        try:
            self.host = check_host(self.dlg.lineEdit_host.text())
        except ValueError:
            self.iface.messageBar().pushMessage(
                "Error", "Please provide a valid non-empty URL", duration=10)

        origin = self.dlg.lineEdit_xyO.text()
        interm = self.dlg.lineEdit_xyI.text()
        destination = self.dlg.lineEdit_xyD.text()
        if len(origin) < 4 or len(destination) < 4:
            self.iface.messageBar().pushMessage("Error",
                                                "No coordinates selected!",
                                                duration=10)
            return
        try:
            xo, yo = eval(origin)
            xd, yd = eval(destination)
        except:
            self.iface.messageBar().pushMessage("Error", "Invalid coordinates",
                                                duration=10)
            return -1

        if interm:
            try:
                interm = eval(''.join(['[', interm, ']']))
                tmp = ''.join(
                    ['&loc={},{}'.format(yi, xi) for xi, yi in interm])
                url = ''.join([
                    "/viaroute?loc={},{}".format(yo, xo),
                    tmp,
                    "&loc={},{}".format(yd, xd),
                    "&instructions={}&alt={}".format(
                        str(self.dlg.checkBox_instruction.isChecked()).lower(),
                        str(self.dlg.checkBox_alternative.isChecked()).lower())
                    ])
            except:
                self.iface.messageBar().pushMessage(
                    "Error", "Invalid intemediates coordinates", duration=10)

        else:
            url = ''.join([
                "/viaroute?loc={},{}&loc={},{}".format(yo, xo, yd, xd),
                "&instructions={}&alt={}".format(
                    str(self.dlg.checkBox_instruction.isChecked()).lower(),
                    str(self.dlg.checkBox_alternative.isChecked()).lower())
                    ])

        try:
            self.conn = HTTPConnection(self.host)
            self.parsed = self.query_url(url, self.host)
            self.conn.close()
        except Exception as err:
            self._display_error(err, 1)
            return

        try:
            line_geom = decode_geom(self.parsed['route_geometry'])
        except KeyError:
            self.iface.messageBar().pushMessage(
                "Error",
                "No route found between {} and {}".format(origin, destination),
                duration=5)
            return

        self.nb_route += 1
        osrm_route_layer = QgsVectorLayer(
            "Linestring?crs=epsg:4326&field=id:integer"
            "&field=total_time:integer(20)&field=distance:integer(20)",
            "route_osrm{}".format(self.nb_route), "memory")
        self.prepare_route_symbol()
        osrm_route_layer.setRendererV2(QgsSingleSymbolRendererV2(self.my_symb))
        QgsMapLayerRegistry.instance().addMapLayer(osrm_route_layer)
        provider = osrm_route_layer.dataProvider()
        fet = QgsFeature()
        fet.setGeometry(line_geom)
        fet.setAttributes([0, self.parsed['route_summary']['total_time'],
                           self.parsed['route_summary']['total_distance']])
        provider.addFeatures([fet])

        self.make_OD_markers(xo, yo, xd, yd, interm)
        osrm_route_layer.updateExtents()
        self.iface.setActiveLayer(osrm_route_layer)
        self.iface.zoomToActiveLayer()

        if self.dlg.checkBox_instruction.isChecked():
            pr_instruct, instruct_layer = self.prep_instruction()
            QgsMapLayerRegistry.instance().addMapLayer(instruct_layer)
            self.iface.setActiveLayer(instruct_layer)

        if self.dlg.checkBox_alternative.isChecked() \
                and 'alternative_geometries' in self.parsed:
            self.nb_alternative = len(self.parsed['alternative_geometries'])
            self.get_alternatives(provider)
            if self.dlg.checkBox_instruction.isChecked():
                for i in range(self.nb_alternative):
                    pr_instruct, instruct_layer = \
                       self.prep_instruction(i + 1, pr_instruct, instruct_layer)
        return

    @pyqtSlot()
    def run_route(self):
        """Run the window to compute a single viaroute"""
        self.dlg = OSRMDialog()
        self.origin = None
        self.interm = None
        self.destination = None
        self.nb_route = 0
        self.intermediate = []
        self.originEmit = QgsMapToolEmitPoint(self.canvas)
        self.intermediateEmit = QgsMapToolEmitPoint(self.canvas)
        self.destinationEmit = QgsMapToolEmitPoint(self.canvas)
        QObject.connect(
            self.originEmit,
            SIGNAL("canvasClicked(const QgsPoint&, Qt::MouseButton)"),
            self.store_origin)
        QObject.connect(
            self.intermediateEmit,
            SIGNAL("canvasClicked(const QgsPoint&, Qt::MouseButton)"),
            self.store_intermediate)
        QObject.connect(
            self.destinationEmit,
            SIGNAL("canvasClicked(const QgsPoint&, Qt::MouseButton)"),
            self.store_destination)
        self.dlg.pushButtonOrigin.clicked.connect(self.get_origin)
        self.dlg.pushButtonIntermediate.clicked.connect(self.get_intermediate)
        self.dlg.pushButtonDest.clicked.connect(self.get_destination)
        self.dlg.pushButtonReverse.clicked.connect(self.reverse_OD)
        self.dlg.pushButtonTryIt.clicked.connect(self.get_route)
        self.dlg.pushButtonClear.clicked.connect(self.clear_all_single)
        self.dlg.pushButton_about.clicked.connect(self.print_about)
        self.dlg.show()

    def prepare_route_symbol(self):
        colors = ['#1f78b4', '#ffff01', '#ff7f00',
                  '#fb9a99', '#b2df8a', '#e31a1c']
        p = self.nb_route % len(colors)
        self.my_symb = QgsSymbolV2.defaultSymbol(1)
        self.my_symb.setColor(QColor(colors[p]))
        self.my_symb.setWidth(1.2)

    def make_OD_markers(self, xo, yo, xd, yd, list_coords=None):
        OD_layer = QgsVectorLayer(
            "Point?crs=epsg:4326&field=id_route:integer&field=role:string(80)",
            "markers_osrm{}".format(self.nb_route), "memory")
        pr_pt = OD_layer.dataProvider()
        features = []
        fet = QgsFeature()
        fet.setGeometry(QgsGeometry.fromPoint(QgsPoint(float(xo), float(yo))))
        fet.setAttributes([self.nb_route, 'Origin'])
        features.append(fet)
        fet = QgsFeature()
        fet.setGeometry(QgsGeometry.fromPoint(QgsPoint(float(xd), float(yd))))
        fet.setAttributes([self.nb_route, 'Destination'])
        features.append(fet)
        marker_rules = [
            ('Origin', '"role" LIKE \'Origin\'', '#50b56d', 4),
            ('Destination', '"role" LIKE \'Destination\'', '#d31115', 4),
        ]
        if list_coords:
            for i, pt in enumerate(list_coords):
                fet = QgsFeature()
                fet.setGeometry(
                    QgsGeometry.fromPoint(QgsPoint(float(pt[0]), float(pt[1]))))
                fet.setAttributes([self.nb_route, 'Via point n°{}'.format(i)])
                features.append(fet)
            marker_rules.insert(
                1,  ('Intermediate', '"role" LIKE \'Via point%\'', 'grey', 2))
        pr_pt.addFeatures(features)

        symbol = QgsSymbolV2.defaultSymbol(OD_layer.geometryType())
        renderer = QgsRuleBasedRendererV2(symbol)
        root_rule = renderer.rootRule()
        for label, expression, color_name, size in marker_rules:
            rule = root_rule.children()[0].clone()
            rule.setLabel(label)
            rule.setFilterExpression(expression)
            rule.symbol().setColor(QColor(color_name))
            rule.symbol().setSize(size)
            root_rule.appendChild(rule)
        
        root_rule.removeChildAt(0)
        OD_layer.setRendererV2(renderer)
        QgsMapLayerRegistry.instance().addMapLayer(OD_layer)
        self.iface.setActiveLayer(OD_layer)


    def prep_instruction(self, alt=None, provider=None,
                            osrm_instruction_layer=None):
        if not alt:
            osrm_instruction_layer = QgsVectorLayer(
                "Point?crs=epsg:4326&field=id:integer&field=alt:integer"
                "&field=directions:integer(20)&field=street_name:string(254)"
                "&field=length:integer(20)&field=position:integer(20)"
                "&field=time:integer(20)&field=length:string(80)"
                "&field=direction:string(20)&field=azimuth:float(10,4)",
                "instruction_osrm{}".format(self.nb_route),
                "memory")
            liste_coords = decode_geom_to_pts(self.parsed['route_geometry'])
            pts_instruct = pts_ref(self.parsed['route_instructions'])
            instruct = self.parsed['route_instructions']
            provider = osrm_instruction_layer.dataProvider()
        else:
            liste_coords = decode_geom_to_pts(
                self.parsed['alternative_geometries'][alt - 1])
            pts_instruct = pts_ref(
                self.parsed['alternative_instructions'][alt - 1])
            instruct = self.parsed['alternative_instructions'][alt - 1]

        for nbi, pt in enumerate(pts_instruct):
            fet = QgsFeature()
            fet.setGeometry(
                QgsGeometry.fromPoint(
                    QgsPoint(liste_coords[pt][0], liste_coords[pt][1])))
            fet.setAttributes([nbi, alt, instruct[nbi][0],
                               instruct[nbi][1], instruct[nbi][2],
                               instruct[nbi][3], instruct[nbi][4],
                               instruct[nbi][5], instruct[nbi][6],
                               instruct[nbi][7]])
            provider.addFeatures([fet])
        return provider, osrm_instruction_layer

    def get_alternatives(self, provider):
        for i, alt_geom in enumerate(self.parsed['alternative_geometries']):
            decoded_alt_line = decode_geom(alt_geom)
            fet = QgsFeature()
            fet.setGeometry(decoded_alt_line)
            fet.setAttributes([
                i + 1,
                self.parsed['alternative_summaries'][i]['total_time'],
                self.parsed['alternative_summaries'][i]['total_distance']
                ])
            provider.addFeatures([fet])

    @pyqtSlot()
    def run_batch_route(self):
        """Run the window to compute many viaroute"""
        self.nb_done = 0
        self.dlg = OSRM_batch_route_Dialog(iface, self.http_header)
        self.dlg.pushButton_about.clicked.connect(self.print_about)
        self.dlg.pushButtonBrowse.clicked.connect(self.output_dialog_geo)
        self.dlg.pushButtonRun.clicked.connect(self.dlg.get_batch_route)
        self.dlg.show()

    @pyqtSlot()
    def run_table(self):
        """Run the window for the table function"""
        self.dlg = OSRM_table_Dialog()
        self.dlg.pushButton_about.clicked.connect(self.print_about)
        self.dlg.pushButton_browse.clicked.connect(self.output_dialog)
        self.dlg.pushButton_fetch.clicked.connect(self.get_table)
        self.dlg.show()

    @pyqtSlot()
    def get_table(self):
        try:
            self.host = check_host(self.dlg.lineEdit_host.text())
        except ValueError:
            self.iface.messageBar().pushMessage(
                "Error", "Please provide a valid non-empty URL", duration=10)
        osrm_table_version = return_osrm_table_version(
            self.host, (1.0, 1.0), self.http_header)
        self.filename = self.dlg.lineEdit_output.text()
        s_layer = self.dlg.comboBox_layer.currentLayer()
        d_layer = self.dlg.comboBox_layer_2.currentLayer()
        if 'old' in osrm_table_version and d_layer and d_layer != s_layer:
            QMessageBox.information(
                self.iface.mainWindow(), 'Error',
                "Rectangular matrix aren't supported in your running version "
                "of OSRM\nPlease only select a source point layer which will "
                "be used to compute a square matrix\n(or update your OSRM "
                "instance")
            self.dlg.comboBox_layer_2.setCurrentIndex(-1)
            return -1

        elif d_layer == s_layer:
            d_layer = None

        coords_src, ids_src = \
            get_coords_ids(s_layer, self.dlg.comboBox_idfield.currentField())

        if d_layer: ### En faire une fonction :
            coords_dest, ids_dest = \
                get_coords_ids(d_layer, self.dlg.comboBox_idfield_2.currentField())

        try:
            conn = HTTPConnection(self.host)
            if d_layer:
                table, new_src_coords, new_dest_coords = \
                    rectangular_light_table(
                        coords_src, coords_dest, conn, self.http_header)
            else:
                table = h_light_table(coords_src, conn, headers=self.http_header)
                if len(table) < len(coords_src):
                    self.iface.messageBar().pushMessage(
                        'The array returned by OSRM is smaller to the size of the '
                        'array requested\nOSRM parameter --max-table-size should '
                        'be increased', duration=20)
            conn.close()

        except ValueError as err:
            self._display_error(err, 1)
            return
        except Exception as er:
            self._display_error(er, 1)
            return

        # Convert the matrix in minutes if needed :
        if self.dlg.checkBox_minutes.isChecked():
            table = np.array(table, dtype='float64')
            table = (table / 600.0).round(1)

        # Replace the value for not found connections :
#        # With a "Not found" message, nicer output but higher memory usage :
#        if self.dlg.checkBox_empty_val.isChecked():
#            table = table.astype(str)
#            if self.dlg.checkBox_minutes.isChecked():
#                table[table == '3579139.4'] = 'Not found connection'
#            else:
#                table[table == '2147483647'] = 'Not found connection'
        # Or without converting the array to string
        # (choosed solution at this time)
        if self.dlg.checkBox_empty_val.isChecked():
            if self.dlg.checkBox_minutes.isChecked():
                table[table == 3579139.4] = np.NaN
            else:
                table[table == 2147483647] = np.NaN

        try:
            out_file = codecs_open(self.filename, 'w', encoding=self.encoding)
            writer = csv.writer(out_file, lineterminator='\n')
            if self.dlg.checkBox_flatten.isChecked():
                table = table.ravel()
                if d_layer:
                    idsx = [(i, j) for i in ids_src for j in ids_dest]
                else:
                    idsx = [(i, j) for i in ids_src for j in ids_src]
                writer.writerow([u'Origin', u'Destination', u'Time'])
                writer.writerows([
                    [idsx[i][0], idsx[i][1], table[i]] for i in xrange(len(idsx))
                    ])
            else:
                if d_layer:
                    writer.writerow([u''] + ids_dest)
                    writer.writerows(
                        [[ids_src[_id]] + line for _id, line in enumerate(table
                                                                      .tolist())])
                else:
                    writer.writerow([u''] + ids_src)
                    writer.writerows(
                        [[ids_src[_id]] + line for _id, line in enumerate(table
                                                                      .tolist())])
            out_file.close()
            QMessageBox.information(
                self.iface.mainWindow(), 'Done',
                "OSRM table saved in {}".format(self.filename))
        except Exception as err:
            QMessageBox.information(
                self.iface.mainWindow(), 'Error',
                "Something went wrong...")
            QgsMessageLog.logMessage(
                'OSRM-plugin error report :\n {}'.format(err),
                level=QgsMessageLog.WARNING)


    @pyqtSlot()
    def run_accessibility(self):
        """Run the window for making accessibility isochrones"""
        self.dlg = OSRM_access_Dialog()
        self.intermediate = []
        self.originEmit = QgsMapToolEmitPoint(self.canvas)
        QObject.connect(
            self.originEmit,
            SIGNAL("canvasClicked(const QgsPoint&, Qt::MouseButton)"),
            self.store_origin
            )
        self.intermediateEmit = QgsMapToolEmitPoint(self.canvas)
        QObject.connect(
            self.intermediateEmit,
            SIGNAL("canvasClicked(const QgsPoint&, Qt::MouseButton)"),
            self.store_intermediate_acces
            )
        self.dlg.pushButtonOrigin.clicked.connect(self.get_origin)
        self.dlg.pushButton_about.clicked.connect(self.print_about)
        self.dlg.toolButton_poly.clicked.connect(self.polycentric)
        self.dlg.pushButton_fetch.clicked.connect(self.get_access_isochrones)
        self.dlg.show()

    @pyqtSlot()
    def polycentric(self):
        QMessageBox.information(
                self.iface.mainWindow(), 'Info',
                "Expetimental : add points and compute polycentric "
                "accessibility isochrones")
        self.get_intermediate()

    @pyqtSlot()
    def get_access_isochrones(self):
        """
        Making the accessibility isochrones in few steps:
        - make a grid of points aroung the origin point,
        - snap each point (using OSRM locate function) on the road network,
        - get the time-distance between the origin point and each of these pts
            (using OSRM table function),
        - make an interpolation grid to extract polygons corresponding to the
            desired time intervals (using matplotlib library),
        - render the polygon.
        """
        try:
            self.host = check_host(self.dlg.lineEdit_host.text())
        except ValueError:
            self.iface.messageBar().pushMessage(
                "Error", "Please provide a valid non-empty URL", duration=10)
        self.max_points = 9420
        pts = self.dlg.lineEdit_xyO.text()
        if len(pts) < 4:
            self.iface.messageBar().pushMessage(
                "Error", "No coordinates selected!", duration=10)
            return
        try:
            pts = eval(pts)
        except:
            self.iface.messageBar().pushMessage("Error", "Invalid coordinates",
                                                duration=10)
            return -1

        max_time = self.dlg.spinBox_max.value()
        inter_time = self.dlg.spinBox_intervall.value()
        self._make_prog_bar()
        version = return_osrm_table_version(self.host, (1.0, 2.2), self.http_header)
        if 'old' in version:
            polygons, levels = self.prep_accessibility_old_osrm(
                pts, self.host, inter_time, max_time)
        elif 'new' in version:
            polygons, levels = self.prep_accessibility_new_osrm(
                pts, self.host, inter_time, max_time)
        else:
            return -1

        isochrone_layer = QgsVectorLayer(
            "MultiPolygon?crs=epsg:4326&field=id:integer"
            "&field=min:integer(10)"
            "&field=max:integer(10)",
            "isochrone_osrm_{}".format(self.dlg.nb_isocr), "memory")
        data_provider = isochrone_layer.dataProvider()

        features = []
        self.progress.setValue(8.5)
        for i, poly in enumerate(polygons):
            ft = QgsFeature()
            ft.setGeometry(poly)
            ft.setAttributes([i, levels[i] - inter_time, levels[i]])
            features.append(ft)
        data_provider.addFeatures(features[::-1])
        self.dlg.nb_isocr += 1
        self.progress.setValue(9.5)
        cats = [
            ('{} - {} min'.format(levels[i]-inter_time, levels[i]),
             levels[i]-inter_time,
             levels[i])
            for i in xrange(len(polygons))
            ]  # label, lower bound, upper bound
        colors = get_isochrones_colors(len(levels))
        ranges = []
        for ix, cat in enumerate(cats):
            symbol = QgsFillSymbolV2()
            symbol.setColor(QColor(colors[ix]))
            rng = QgsRendererRangeV2(cat[1], cat[2], symbol, cat[0])
            ranges.append(rng)

        expression = 'max'
        renderer = QgsGraduatedSymbolRendererV2(expression, ranges)

        isochrone_layer.setRendererV2(renderer)
        isochrone_layer.setLayerTransparency(25)
        self.iface.messageBar().clearWidgets()
        QgsMapLayerRegistry.instance().addMapLayer(isochrone_layer)
        self.iface.setActiveLayer(isochrone_layer)

    @lru_cache(maxsize=20)
    def prep_accessibility_old_osrm(self, point, url, inter_time, max_time):
        """Make the regular grid of points, snap them and compute tables"""
        try:
            conn = HTTPConnection(self.host)
        except Exception as err:
            self._display_error(err, 1)
            return -1

        bounds = get_search_frame(point, max_time)
        coords_grid = make_regular_points(bounds, self.max_points)
        self.progress.setValue(0.1)
        coords = list(set(
            [tuple(h_locate(pt, conn, self.http_header)
                   ['mapped_coordinate'][::-1]) for pt in coords_grid]))
        origin_pt = h_locate(
            point, conn, self.http_header)['mapped_coordinate'][::-1]

        self.progress.setValue(0.2)

        try:
            times = np.ndarray([])
            for nbi, chunk in enumerate(chunk_it(coords, 99)):
                matrix = h_light_table(
                    list(chunk) + [origin_pt], conn, self.http_header)
                times = np.append(times, (matrix[-1])[:len(chunk)])
                self.progress.setValue((nbi + 1) / 2.0)
        except Exception as err:
            self._display_error(err, 1)
            conn.close()
            return

        conn.close()
        times = (times[1:] / 600.0).round(2)
        nb_inter = int(round(max_time / inter_time)) + 1
        levels = [nb for nb in xrange(0, int(
            round(np.nanmax(times)) + 1) + inter_time, inter_time)][:nb_inter]
        del matrix
        collec_poly = interpolate_from_times(times, coords, levels)
        self.progress.setValue(5.5)
        _ = levels.pop(0)
        polygons = qgsgeom_from_mpl_collec(collec_poly.collections)
        return polygons, levels

    @lru_cache(maxsize=20)
    def prep_accessibility_new_osrm(self, points, url, inter_time, max_time):
        """
        Make the regular grid of points and compute a table between them and
        and the source point, using the new OSRM table function for
        rectangular matrix
        + experimental support for polycentric accessibility isochrones
        (or multiple isochrones from multiple origine in one time...)
        """
        try:
            conn = HTTPConnection(self.host)
        except Exception as err:
            self._display_error(err, 1)
            return -1

        polygons = []
        points = [points] if isinstance(points[0], float) else points
        prog_val = 1
        for nb, point in enumerate(points):
            bounds = get_search_frame(point, max_time)
            coords_grid = make_regular_points(bounds, self.max_points)
            prog_val += 0.1 * (nb/len(points))
            self.progress.setValue(prog_val)

            matrix, src_coords, snapped_dest_coords = rectangular_light_table(
                point, coords_grid, conn, self.http_header)
#            snapped_dest_coords.extend(tmp)
#            times = np.append(times, (matrix[0] / 600.0).round(2)[:])
            times = (matrix[0] / 600.0).round(2)
            prog_val += 4 * (nb/len(points))
            self.progress.setValue(prog_val)
            nb_inter = int(round(max_time / inter_time)) + 1
            levels = [nb for nb in xrange(0, int(
                round(np.nanmax(times)) + 1) + inter_time, inter_time)][:nb_inter]
            del matrix
            collec_poly = interpolate_from_times(
                times, [(i[1], i[0]) for i in snapped_dest_coords], levels)
            prog_val += 7 * (nb/len(points))
            self.progress.setValue(7)
            _ = levels.pop(0)
            polygons.append(qgsgeom_from_mpl_collec(collec_poly.collections))
        
        conn.close()

        if len(points) > 1:
            tmp = len(polygons[0])
            assert all([len(x) == tmp for x in polygons])
            polygons = np.array(polygons).transpose().tolist()
            print(polygons)
            merged_poly = [QgsGeometry.unaryUnion(polys) for polys in polygons]
            return merged_poly, levels
        else:
            return polygons[0], levels

    def output_dialog(self):
        self.dlg.lineEdit_output.clear()
        self.filename, self.encoding = save_dialog()
        if self.filename is None:
            return
        self.dlg.lineEdit_output.setText(self.filename)

    def output_dialog_geo(self):
        self.dlg.lineEdit_output.clear()
        self.filename, self.encoding = save_dialog_geo()
        if self.filename is None:
            return
        self.dlg.lineEdit_output.setText(self.filename)

    def _display_error(self, err, code):
        msg = {
            1: "An error occured when trying to contact the OSRM instance",
            2: "OSRM plugin error report : Too many errors occured "
               "when trying to contact the OSRM instance at {} - "
               "Route calculation has been stopped".format(self.host),
            }
        self.iface.messageBar().pushMessage(
            "Error", msg[code] + "(see QGis log for error traceback)",
            duration=10)
        QgsMessageLog.logMessage(
            'OSRM-plugin error report :\n {}'.format(err),
            level=QgsMessageLog.WARNING)

    def _make_prog_bar(self):
        progMessageBar = self.iface.messageBar().createMessage(
            "Creation in progress...")
        self.progress = QProgressBar()
        self.progress.setMaximum(10)
        self.progress.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        progMessageBar.layout().addWidget(self.progress)
        self.iface.messageBar().pushWidget(
            progMessageBar, iface.messageBar().INFO)


# TODO :
# - ensure that the MapToolEmitPoint is unset when the plugin window is closed
