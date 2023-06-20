# Metahuman Facial Transfer


Maya Python code that will reference in previously exported FBX animation from Unreal.
The code will copy these attribute keys from the referenced transform node over to the Metahuman Face board controls.
The referenced file is then removed once completed.

### Note: This was built and tested using Maya 2022 running Python 3.7 using latest assets from Unreal 5.2.

![](https://github.com/swnolan/metahuman_facial_transfer/blob/main/images/metahuman_facial_transfer.gif)

# References:
* [Refer to Unreal's documentation for exporting Unreal assets to Maya]( https://dev.epicgames.com/documentation/en-us/metahuman/exporting-metahumans-to-maya)


# Export FBX Data from Unreal
* Export FBX Facial animation out from Unreal Sequencer
* Select the "Face Track" and not the "Face_ControlBoard_CtrlRig" track
![Screenshot](./images/bake_facial_animation.png)
* Bake keys down onto the Control rig
* Select the track and Export FBX
![Screenshot](./images/export_fbx_file.png)

# Install:
* Download script and place somewehere in your MAYA_PYTHON_PATH or maya/scripts folder
* Included in this project is a sample FBX file (metahuman_facial_example.fbx)

# Usage:
* Open/Reference/Import your Metahuman rig into the scene
* Select a face control on the rig
* Run Code in Maya Python Editor and use provided sample FBX or your own:
```
import metahuman_facial_transfer
metahuman_facial_transfer.import_metahuman_animation()
```

Free to use personally or commercially. 
