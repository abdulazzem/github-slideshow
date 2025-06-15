# Silkroad Online Blender Importer

## Overview
This Blender addon imports 3D models, materials, skeletons, and animations from Silkroad Online game files into Blender. It supports the common JMXV (JoyMax V?) formats used by the game:
- `JMXVBMS` (Mesh)
- `JMXVBMT` (Material)
- `JMXVBSK` (Skeleton)
- `JMXVBAN` (Animation)

The primary goal is to allow users to view, study, or modify Silkroad Online assets within Blender.

## Features
*   **Supported File Formats:**
    *   `BMS`: Mesh data.
    *   `BMT`: Material definitions and texture paths.
    *   `BSK`: Skeletal (armature) data.
    *   `BAN`: Animation data for skeletons.
*   **Mesh Import:**
    *   Vertices, faces (triangles).
    *   Vertex normals.
    *   Primary UV coordinates (UV0).
    *   Secondary UV coordinates (UV1/Lightmap UVs) if present.
*   **Material Import:**
    *   Diffuse colors.
    *   Basic Principled BSDF node setup in Blender.
    *   Texture paths for diffuse and normal maps are linked to Image Texture nodes. (Actual texture loading depends on Blender's capabilities, see "Texture Handling" below).
*   **Skeleton Import:**
    *   Armature creation with bone hierarchy.
    *   Bone transformations (position and rotation) are converted to Blender's coordinate system.
*   **Vertex Skinning:**
    *   Vertex weights are applied to the mesh, linking it to the imported armature for deformation.
*   **Animation Import:**
    *   Imports all `.ban` files found in the same directory as the selected `.bms` file.
    *   Creates a separate Blender Action for each BAN file.
    *   Keyframe data (rotation and translation) is applied to the corresponding bones in the armature.
*   **Import Options:**
    *   Users can choose to toggle the import of Materials, Skeleton, and Animations via checkboxes in the Blender file browser during import.

## Installation
1.  **Prepare the Addon:**
    *   If you have the `sro_importer` folder, create a ZIP file from it (e.g., `sro_importer.zip`). Ensure the `__init__.py` file is at the root of the ZIP archive, alongside other Python files like `sro_op_import.py`, `bms_parser.py`, etc.
2.  **Install in Blender:**
    *   Open Blender.
    *   Go to `Edit > Preferences > Add-ons`.
    *   Click `Install...` (top-right).
    *   Navigate to the `sro_importer.zip` file you created/downloaded and select it.
    *   Enable the addon by checking the box next to "Import-Export: Silkroad Online Importer" in the Add-ons list.

## How to Use
1.  Once the addon is enabled, go to `File > Import > Silkroad Online (.bms)`.
2.  The Blender file browser will open. Navigate to the directory containing your extracted Silkroad Online game files (e.g., from `media.pk2`).
    *   *Note: This addon does not handle the extraction of files from `.pk2` archives. You need to use a separate PK2 unpacking tool for that.*
3.  Select a `.bms` (mesh) file you wish to import.
4.  The importer will automatically attempt to find and process associated files:
    *   `.bmt` (material definition) with the same base filename.
    *   `.bsk` (skeleton) with the same base filename.
    *   All `.ban` (animation) files located in the same directory as the BMS file.
5.  In the import options panel (usually on the right side of the file browser, or bottom-left in older Blender versions), you can check/uncheck:
    *   `Import Materials`
    *   `Import Skeleton`
    *   `Import Animations`
    ...to control which components are imported alongside the mesh.
6.  Click "Import Silkroad BMS".

## Texture Handling (Important Note)
*   The importer configures Blender material nodes to use diffuse and normal textures by linking their file paths as specified in the `.bmt` files. These textures are typically `.ddj` files.
*   **Blender does not natively support `.ddj` files.** `.ddj` is a proprietary JoyMax format, often a slightly modified DirectDraw Surface (`.dds`) file.
*   To see textures in Blender, you will likely need to:
    1.  **Install a DDS Addon for Blender:** Search for a Blender addon that provides support for loading DDS files (e.g., "Blender DDS Addon" or similar). Some of these may also handle common DDJ variations.
    2.  **Manually Convert Textures:** Convert the `.ddj` files to a format Blender understands (like `.png`, `.tga`, or standard `.dds` if your DDS addon supports it).
        *   Place the converted textures in the same directory as the original `.ddj` files, keeping the base filename the same (just change the extension). The importer or Blender might pick these up if the path still resolves.
        *   Alternatively, after import, you can manually update the Image Texture nodes in Blender's Shader Editor to point to your converted texture files.

## Coordinate System
The importer automatically handles the conversion from Silkroad Online's coordinate system (Y-Up, Left-Handed, with specific axis orientations for bone rotations) to Blender's native Z-Up, Right-Handed system.

## Known Limitations / Future Work
*   **Direct DDJ Loading:** Does not directly load or convert `.ddj` texture files.
*   **Advanced Material Properties:** Many material flags and properties from `PrimMtrlFlag` in BMT files (e.g., specular maps, gloss maps, environment maps, detailed UV animation settings, two-sided rendering options) are parsed but not fully translated into complex Blender node setups. Current setup is basic Principled BSDF.
*   **Cloth Physics:** BMS files can contain cloth simulation data. This data is parsed by `bms_parser.py` (if `ClothOffset` is present) but is not yet used to set up cloth physics in Blender.
*   **Navmesh Data:** Some BMS files, particularly for regions, represent navigation meshes. This data is parsed but not yet used to create Blender-compatible navigation data.
*   **Animation Interpolation:** All animation keyframes are currently set to 'LINEAR' interpolation in Blender. The original interpolation types from the BAN files are not used.
*   **File Version Compatibility:** Primarily tested with file format versions:
    *   JMXVBMS 0110
    *   JMXVBMT 0102
    *   JMXVBSK 0100 / 0101
    *   JMXVBAN 0100 / 0102
    Other or older/newer sub-versions of these formats might exist and could lead to parsing issues.
*   **Error Reporting:** While error handling has been improved, some edge cases or deeply corrupted files might still cause Blender to become unstable or report cryptic errors. More detailed error messages for specific data inconsistencies could be added.

## Credits
*   This addon's development heavily relies on the Silkroad Online file format documentation from the [SilkroadDoc Wiki](https://github.com/DummkopfOfHachtenduden/SilkroadDoc-Wiki/wiki) (especially pages by DummkopfOfHachtenduden and other contributors).
*   Addon developed by: AI Agent (GPT-4 based on instructions from a user).

```
