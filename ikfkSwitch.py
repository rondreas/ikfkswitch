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
# TODO Validation of attribute name prior to making connections,

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
        ik_hierarchies.append(handle.getJointList())

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


def add_attribute(node, attr):
    """ Function for adding attributes, handling situations where the attribute already exists, such as in
    the case of user errors. Or the attribute exist and already seem to be connected. """

    # If attribute not found, create it.
    if not node.listAttr(userDefined=True, string=attr):
        print("Not made yet")
        pm.addAttr(node, longName=attr)

    else:
        print("Exists!")
        attribute = node.nodeName() + '.' + attr
        if not pm.listConnections(attribute):
            print("No connections made... deleting attr")
            pm.deleteAttr(attribute)

        else:
            print("Connections are made, doing nothing.")
            # The Attribute exits, and has connections
            pass


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

    def attach(self, controllers, name='IKFK'):
        """ Method for connecting all blend nodes blend attribute to a custom attribute on controller. """

        locator = pm.spaceLocator(name='{}Container'.format(name))
        shape = locator.getShape()

        pm.addAttr(
            shape,
            longName="blend",
            attributeType='double',
            keyable=True,
            max=1.0,  # sourceB
            min=0.0,  # sourceA
            defaultValue=0.0
        )

        # Set locators shape to invisible and hide unwanted attributes.
        shape.visibility.set(False)

        for node in self.blendNodes:
            pm.connectAttr(shape.blend, node.weight)

        # Parent an instance of the locators shape to each controllers transform
        for controller in controllers:
            pm.parent(
                shape,
                controller,
                add=True,
                shape=True
            )

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
        self.setLayout(layout)

        self.sources_layout()
        self.target_layout()
        self.controllers_layout()

        horizontal_layout = QHBoxLayout()

        horizontal_layout.addWidget(QLabel("Name:"))

        self.name = QLineEdit()
        horizontal_layout.addWidget(self.name)

        btn = QPushButton('Foo')
        btn.clicked.connect(self.foo)
        horizontal_layout.addWidget(btn)

        layout.addLayout(horizontal_layout, 1, 1, 1, 2, Qt.AlignHCenter)

        # Resize to smallest recommended size.
        self.resize(self.minimumSizeHint())

    def sources_layout(self):

        groupbox = QGroupBox("Sources")
        layout = QGridLayout()

        self.sourceA = ListWidget()
        self.sourceB = ListWidget()

        layout.addWidget(self.sourceA, 0, 0)
        layout.addWidget(self.sourceB, 0, 1)

        groupbox.setLayout(layout)

        self.layout().addWidget(groupbox, 0, 0, 1, 2)

    def target_layout(self):

        groupbox = QGroupBox("Target")
        layout = QGridLayout()

        self.target = ListWidget()
        layout.addWidget(self.target)

        groupbox.setLayout(layout)

        self.layout().addWidget(groupbox, 0, 2)

    def controllers_layout(self):

        groupbox = QGroupBox("Controllers")
        layout = QGridLayout()

        self.controllers = ListWidget()
        layout.addWidget(self.controllers)

        groupbox.setLayout(layout)

        self.layout().addWidget(groupbox, 0, 3)

    def foo(self):

        if self.name.text():
            a = pm.ls(self.sourceA.itemDagPaths())
            b = pm.ls(self.sourceB.itemDagPaths())
            target = pm.ls(self.target.itemDagPaths())
            controllers = pm.ls(self.controllers.itemDagPaths())

            switch = IKFKSwitch(a, b, target)
            switch.attach(controllers, self.name.text())


class ListWidget(QListWidget):
    def __init__(self, *args, **kwargs):
        super(ListWidget, self).__init__(*args, **kwargs)

        # Set and create connections for custom context menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showContextMenu)

        self.setAcceptDrops(True)

    def itemDagPaths(self):
        """ Return the DAG Paths for each item in list as a string. """

        # Thinking about it, I guess I could just store the list of DAG Paths as I create the items
        # and then access that one instead of iterating items. This wouldn't allow for sorting or if
        # I later decide to do some other alterations to the list.
        result = list()

        # Iterate over i items in widget and access the item
        for i in range(self.count()):
            item = self.item(i)

            # Data will be a string representing the DAG Path.
            result.append(item.data(Qt.UserRole))

        return result

    def showContextMenu(self, pos):

        position = self.mapToGlobal(pos)

        # Create a top level menu
        menu = QMenu()

        """
        Commented out this chunk as it doest work as good as I intended, would need to handle 
        sorting the hierarchies and also the getJointList skips the end joint of the chain.
        
        # And a submenu for accessing IK Handles
        ikMenu = QMenu("IK Handles")

        menu.addMenu(ikMenu)

        # Generate an action for each ik handle in scene.
        ikHandles = pm.ls(type='ikHandle')
        for ikHandle in ikHandles:
            action = IKAction(ikHandle.nodeName(), ikMenu, self, ikHandle)
            ikMenu.addAction(action)
            
        """

        action = QAction("Add Selected", menu)
        action.triggered.connect(lambda arg=action: self.populate(pm.ls(selection=True, type='transform'), clear=False))
        menu.addAction(action)

        clear_action = QAction("Clear", menu)
        clear_action.triggered.connect(self.clear)
        menu.addAction(clear_action)

        menu.exec_(position)

    def populate(self, items, clear=True):

        if clear:
            self.clear()

        for item in items:
            label = QListWidgetItem(item.nodeName())
            label.setData(Qt.UserRole, item.longName())
            self.addItem(label)

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
        if event.mimeData().hasFormat('text/plain'):
            event.accept()

            data = event.mimeData().data('text/plain')
            items = data.split('\n')
            dagPaths = map(lambda item: item.data(), items)

            self.populate(pm.ls(dagPaths))

        else:
            event.ignore()

class IKAction(QAction):
    def __init__(self, text, parent, listWidget, handle):
        super(IKAction, self).__init__(text, parent)

        self.triggered.connect(lambda arg=self: listWidget.populate(handle.getJointList(), clear=False))

def ui():
    window = Window()
    window.show()
    print(__version__)
    return window
