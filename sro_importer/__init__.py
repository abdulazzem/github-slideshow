bl_info = {
    "name": "Silkroad Online Importer",
    "author": "Your Name Here (Updated)",
    "version": (0, 1, 0),
    "blender": (2, 83, 0), # Minimum Blender version
    "location": "File > Import > Silkroad Online (.bms)",
    "description": "Imports Silkroad Online files (BMS, BMT, BSK, BAN)",
    "warning": "",
    "doc_url": "https://example.com/sro_importer_docs", # Placeholder
    "category": "Import-Export",
}

import bpy

# Import the operator from sro_op_import.py
# This structure assumes sro_op_import.py contains the ImportSRO class
from .sro_op_import import ImportSRO

# Menu function
def menu_func_import(self, context):
    self.layout.operator(ImportSRO.bl_idname, text="Silkroad Online (.bms)")

# Store (operator_class, menu_item_func) for multiple operators if needed
#bpy.utils.previews.new() # Example for icon loading if needed later
#custom_icons = None

classes_to_register = [
    (ImportSRO, menu_func_import)
]

def register():
    # global custom_icons # For custom icon handling
    # custom_icons = bpy.utils.previews.new()
    # # Example: custom_icons.load("sro_icon", os.path.join(os.path.dirname(__file__), "sro_icon.png"), 'IMAGE')

    for cls, menu_func in classes_to_register:
        bpy.utils.register_class(cls)
        if menu_func: # If there's a menu function, add it
            bpy.types.TOPBAR_MT_file_import.append(menu_func)
    print(f"{bl_info['name']} version {'.'.join(map(str, bl_info['version']))} registered.")

def unregister():
    # global custom_icons
    for cls, menu_func in reversed(classes_to_register): # Unregister in reverse order
        if menu_func:
            bpy.types.TOPBAR_MT_file_import.remove(menu_func)
        bpy.utils.unregister_class(cls)

    # bpy.utils.previews.remove(custom_icons) # Clean up custom icons
    print(f"{bl_info['name']} unregistered.")

if __name__ == "__main__":
    # This part is for direct testing from a text editor,
    # but typically you install the addon through Blender's preferences.
    # To test:
    # 1. Open this file in Blender's Text Editor.
    # 2. Make sure sro_op_import.py and other parser files are in a subdir named 'sro_importer'
    #    relative to where Blender is looking for scripts OR adjust sys.path.
    # 3. Run the script.
    # You might need to manually unregister first if it was already registered.

    # Example of how to handle direct script run for testing (requires sro_importer to be in python path)
    # try:
    #     unregister()
    # except Exception as e:
    #     print(f"Unregister failed (might be first run): {e}")
    # register()
    pass
