# IK FK Switch #
Pairblend two joint hierarchies and connect their output to third joint hierarchy.

![alt text](/res/ui.png?raw=True "ui")

## Installation ##

For now let's keep it simple. All you have to do is copy the ikfkSwitch.py into your maya script folder (~/Document/maya/2018/scripts for example). Or gitclone this repo there.

In Maya, open the script editor and paste;
```python
import ikfkSwitch   # add `from ikfkswitch` before if you downloaded the entier repo.
reload(ikfkSwitch)

ikfkSwitchUI = ikfkSwitch.ui()
```

Save this to a shelf; Script Editor -> File -> Save Script to Shelf...

## Usage ##

Drag and drop nodes into the boxes, or add selected nodes through the right click menu. Fill out a name and hit apply.
