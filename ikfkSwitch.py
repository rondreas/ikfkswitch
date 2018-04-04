import os
from collections import deque

import pymel.core as pm

from maya import OpenMayaUI as omui

try:
    from PySide2.QtCore import *
    from PySide2.QtGui import *
    from PySide2.QtWidgets import *
    from PySide2 import __version__
    from shiboken2 import wrapInstance
except ImportError:
    from PySide.QtCore import *
    from PySide.QtGui import *
    from PySide import __version__
    from shiboken import wrapInstance

# TODO Working QTreeWidget that accepts Drag and Drop from Maya Outliner.

# Get the Maya window so we can parent our widget to it.
mayaMainWindowPtr = omui.MQtUtil.mainWindow()
mayaMainWindow = wrapInstance(long(mayaMainWindowPtr), QWidget)


def get_hierarchy(start, end):
    """ Going from last child, traverse a hierarchy until start node,

    return a deque object containing an ordered list start->end

    """

    msg = "{} not in hierarchy of {}".format(end.nodeName(), start.nodeName())
    assert (end in start.listRelatives(allDescendents=True)), msg

    hierarchy = deque([end])
    current = end

    while current != start:
        current = current.listRelatives(parent=True)[0]
        hierarchy.appendleft(current)

    return hierarchy


def get_iks():
    """ Get all hierarchies which are effected by IK.

    returns nested list of hierarchies

    """

    ik_handles = pm.ls(type='ikHandle')
    ik_hierarchies = list()

    for handle in ik_handles:
        # IK handle is connected with some message attributes, so we can grab the associated nodes directly,
        end_effector = handle.getAttr('endEffector')
        start_joint = handle.getAttr('startJoint')

        # Effector will have connections from the end joint into it's translate, so pick first best connection
        # from a joint.
        end_joint = end_effector.listConnections(type='joint')[0]

        # Push the hierarchy to list and recast to a standard list object,
        ik_hierarchies.append(list(get_hierarchy(start_joint, end_joint)))

    return ik_hierarchies


def find_similar_hierarchies(hierarchy):
    """ Given a list of nodes in same hierarchy, for each node find all matching nodes. """

    # Get lists of all joints where matrices match for first and last joint in hierarchy,
    start_joints = matching_matrices(hierarchy[0])
    end_joints = matching_matrices(hierarchy[-1])

    for joint in start_joints:
        # Create a set of all nodes under start joint,
        descendents = set(joint.listRelatives(allDescendents=True))

        # Check which if any joint can also be found in set of end joints,
        common = descendents & set(end_joints)

        if common:
            hi = get_hierarchy(joint, common.pop())
            pretty_print_hierarchy(hi)


def pretty_print_hierarchy(hierarchy):
    """ Print a hierarchy console, """
    count = 0
    for node in hierarchy:
        print("| {bu} {name}".format(bu='-' * count, name=node.nodeName()))
        count += 1


def matching_matrices(search):
    """ Iterate through all joints and check for matching matrices, return list of all matches, """
    joints = pm.ls(type='joint')
    result = list()
    for joint in joints:

        # Do check if matrices are same within tolerance,
        match = search.getAttr('worldMatrix').isEquivalent(joint.getAttr('worldMatrix'), tol=0.001)

        if match and joint != search:
            result.append(joint)

    return result


class IKFKSwitch(object):
    """ Blend two sources, and output their result to target. """

    def __init__(self, sourceA, sourceB, target):
        self.inputs = [sourceA, sourceB]
        self.output = target

        self.blendNodes = []

        try:
            self.make_connections()
        except Exception as e:
            print e.message

    def make_connections(self):
        """ Create and set connections for each level in the hierarchy. """

        # TODO Validation that all nodes involved has attrs rotate and translate.
        for sourceA, sourceB, target in zip(self.inputs[0], self.inputs[1], self.output):
            pairBlend = pm.createNode('pairBlend', name='{}_blnd'.format(target.nodeName()))

            pm.connectAttr(sourceA.translate, pairBlend.inTranslate2)
            pm.connectAttr(sourceB.translate, pairBlend.inTranslate1)

            pm.connectAttr(sourceA.rotate, pairBlend.inRotate2)
            pm.connectAttr(sourceB.rotate, pairBlend.inRotate1)

            pm.connectAttr(pairBlend.outTranslate, target.translate)
            pm.connectAttr(pairBlend.outRotate, target.rotate)

            self.blendNodes.append(pairBlend)

    def attach(self, controller, name='IKFK'):
        """ Method for connecting all blend nodes blend attribute to a custom attribute on controller. """

        if isinstance(controller, str):
            controller = pm.ls(controller)[0]

        # TODO Check to see if attr already exists,...
        pm.addAttr(
            controller,
            longName=name,
            attributeType='double',
            keyable=True,
            max=1.0,  # sourceB
            min=0.0,  # sourceA
            defaultValue=0.0
        )

        for node in self.blendNodes:
            pm.connectAttr(controller.nodeName() + "." + name, node.weight)

    def focus(self):
        """ Show in Node Window. """
        # Get name of Node Editor Panels, 0th index should be the main node editor we're looking for.
        ne = pm.getPanel(scriptType='nodeEditorPanel')

        # Create a new tab, clear the tab, and add all associated nodes.
        pm.nodeEditor('{}NodeEditorEd'.format(ne[0]), q=True, getNodeList=True)


class Window(QWidget):

    def __init__(self, parent=mayaMainWindow):
        super(Window, self).__init__(parent=parent)

        if os.name is 'posix':
            self.setWindowFlags(Qt.Tool)
        else:
            self.setWindowFlags(Qt.Window)

        self.setWindowTitle("IKFK Switch")

        layout = QGridLayout()

        self.ctrl = QLineEdit()
        self.name = QLineEdit()

        layout.addWidget(QLabel("Controller:"), 0, 0)
        layout.addWidget(self.ctrl, 0, 1)

        layout.addWidget(QLabel("Attribute Name:"), 0, 2)
        layout.addWidget(self.name, 0, 3)

        # Search Replace,
        self.searchLineEdit = QLineEdit("_bn")
        self.replaceIKLineEdit = QLineEdit("_ik")
        self.replaceFKLineEdit = QLineEdit("_fk")

        layout.addWidget(QLabel("Search:"), 1, 0)
        layout.addWidget(self.searchLineEdit, 1, 1)
        layout.addWidget(QLabel("Replace IK:"), 2, 0)
        layout.addWidget(self.replaceIKLineEdit, 2, 1)
        layout.addWidget(QLabel("Replace FK:"), 2, 2)
        layout.addWidget(self.replaceFKLineEdit, 2, 3)

        doItBtn = QPushButton('Apply')
        doItBtn.clicked.connect(self.doit)

        layout.addWidget(doItBtn, 4, 0, 1, 4, Qt.AlignHCenter)

        self.setLayout(layout)

    def doit(self):
        """ Quick hack to not sit ponder for too long how to implement this thing. """

        sel = pm.ls(sl=True, type='joint')

        ik = list()
        fk = list()

        ctrl = pm.ls(self.ctrl.text())[0]

        for item in sel:

            ik.append(
                pm.ls(item.nodeName().replace(
                    self.searchLineEdit.text(),
                    self.replaceIKLineEdit.text()
                    ),
                    type='joint'
                )[0]
            )

            fk.append(
                pm.ls(item.nodeName().replace(
                    self.searchLineEdit.text(),
                    self.replaceFKLineEdit.text()
                    ),
                    type='joint'
                )[0]
            )

        switch = IKFKSwitch(fk, ik, sel)
        switch.attach(ctrl, self.name.text())

    def getSelected(self):
        """ """
        selection = pm.selected()

        if not selection:
            # Nothing selected, set empty string.
            pass
        else:
            # Load first selection to line edit.
            self.ctrl.setText(selection[0].nodeName())


class HierarchyWidget(QTreeWidget):
    """ Subclass of QTreeWidget to support Drag and Drop in Maya. """

    def __init__(self, *args, **kwargs):
        super(HierarchyWidget, self).__init__(*args, **kwargs)

        self.setAcceptDrops(True)

        # Create top level items,
        ik = QTreeWidgetItem(self)
        ik.setText(0, 'IK')

        fk = QTreeWidgetItem(self)
        fk.setText(0, 'FK')

        driven = QTreeWidgetItem(self)
        driven.setText(0, 'Driven')

    def dragEnterEvent(self, event):
        """ Reimplementing event to accept plain text, """
        if event.mimeData().hasFormat('text/plain'):
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """ Reimplementing event to accept plain text, """
        if event.mimeData().hasFormat('text/plain'):
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """ """
        data = event.mimeData().data('text/plain')

        items = data.split('\n')

        bu = '|'
        for item in items:

            x = pm.ls(item.data())[0]
            bu += '-'
            print("{}{}".format(bu, x.nodeName()))


def ui():
    window = Window()
    window.show()
    print(__version__)
    return window
