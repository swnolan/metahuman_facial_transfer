# Metahuman Facial Transfer


Maya Python code that will reference in previously exported FBX animation from Unreal.
The code will copy these attribute keys from the referenced transform node over to the Metahuman Face board controls.
The referenced file is then removed once completed.

### Newly updated to Support Unreal 4.27-5.2 & Maya 2020-2023

![Screenshot](./images/mh_to_maya.png)

# Tutorial
[![Tutorial](https://img.youtube.com/vi/uw_gXGLq7d0/0.jpg)](https://youtu.be/uw_gXGLq7d0)

# Reference links:
* [Exporting a MetaHuman to Maya]( https://dev.epicgames.com/documentation/en-us/metahuman/exporting-metahumans-to-maya)
* [How to Use MetaHuman Animator in Unreal Engine](https://dev.epicgames.com/community/learning/tutorials/eKbY/how-to-use-metahuman-animator-in-unreal-engine)


# Export FBX Data from Unreal
* Export FBX Facial animation out from Unreal Level Sequencer
* Select the "Face" Track
  
![Screenshot](./images/1_anim_seq_export.png)

* Bake Animation Sequence
* Save File to a folder
  
![Screenshot](./images/2_anim_seq_export_name.png)

* Animation Sequence export options
  
![Screenshot](./images/3_anim_seq_export_options.png)

* Navigate to new Animation Sequence file and export FBX

![Screenshot](./images/4_anim_seq_export_file.png)

* FBX Export options
  
![Screenshot](./images/5_fbx_export_options.png)

# Import Control Rig FBX Data from Maya
* Right+Click the 'Face_ControlBoard_CtrlRig' track
* Import FBX
![Screenshot](./images/import_control_rig_fbx.png)
![Screenshot](./images/import_fbx_control_rig.png)


# Install:
* Download project
* Drag and Drop install python file into Maya viewport 
* This will install a Shelf and code into maya/scripts folder
![Screenshot](./images/shelf_install.gif)

# Usage:
* Open/Reference/Import your Metahuman rig into the scene
* Launch Tool 
* Select Face control on Metahuman face rig
* Hit 'Set Current Metahuman'
* Import Animation Sequence Animation FBX from Unreal
* Export Facial FBX back to Unreal

Free to use personally or commercially. 
