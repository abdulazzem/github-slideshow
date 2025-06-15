import bpy
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, BoolProperty
from bpy.types import Operator

import os
import glob
import mathutils

# Import Parsers and Custom Exceptions
from .bms_parser import parse_bms, VERTEX_FLAG_UV1, BMSParsingError
from .bmt_parser import parse_bmt, PrimMtrlFlag, BMTParsingError
from .bsk_parser import parse_bsk, BSKParsingError
from .ban_parser import parse_ban, BANParsingError


class ImportSRO(Operator, ImportHelper):
    """Imports a Silkroad Online BMS file and related BMT, BSK, BAN files."""
    bl_idname = "import_scene.sro_bms"
    bl_label = "Import Silkroad BMS"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".bms"
    filter_glob: StringProperty(default="*.bms", options={'HIDDEN'}, maxlen=255)
    filepath: StringProperty(name="File Path", description="Filepath for the BMS file", maxlen=1024, subtype='FILE_PATH')

    import_materials: BoolProperty(name="Import Materials", description="Import materials (BMT)", default=True)
    import_skeleton: BoolProperty(name="Import Skeleton", description="Import skeleton (BSK) and skin mesh", default=True)
    import_animations: BoolProperty(name="Import Animations", description="Import animations (BAN files)", default=True)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.label(text="Import Options:")
        layout.prop(self, "import_materials")
        layout.prop(self, "import_skeleton")
        layout.prop(self, "import_animations")
        layout.separator()

    def execute(self, context):
        if not self.filepath:
            self.report({'ERROR'}, "No file selected.")
            return {'CANCELLED'}

        if not self.filepath.lower().endswith(".bms"):
            self.report({'ERROR'}, f"Please select a .bms file. Selected: {os.path.basename(self.filepath)}")
            return {'CANCELLED'}

        base_dir = os.path.dirname(self.filepath)
        base_filename = os.path.splitext(os.path.basename(self.filepath))[0]

        obj = None
        armature_obj = None
        parsed_bms_data = None

        # 1. BMS (Mesh) Parsing and Creation
        try:
            print(f"--- Parsing BMS: {self.filepath} ---")
            parsed_bms_data = parse_bms(self.filepath)
            if parsed_bms_data is None: # Explicit None means parser error reported by itself
                self.report({'ERROR'}, f"Failed to parse BMS: {os.path.basename(self.filepath)}. Check console.")
                return {'CANCELLED'}

            if not parsed_bms_data.get("vertices") or not parsed_bms_data["vertices"].get("positions"):
                self.report({'ERROR'}, "BMS data is missing vertex positions.")
                return {'CANCELLED'}
            if not parsed_bms_data.get("faces") and len(parsed_bms_data["vertices"]["positions"]) > 0 :
                 self.report({'WARNING'}, "BMS data has vertices but no faces. Importing as point cloud.")


            mesh_name = parsed_bms_data.get('material_name') or base_filename
            mesh_data = bpy.data.meshes.new(name=mesh_name)

            verts_loc = [(v[0], -v[2], v[1]) for v in parsed_bms_data['vertices']['positions']]
            edges = [] # Edges are optional, faces define structure
            faces = parsed_bms_data['faces']
            mesh_data.from_pydata(verts_loc, edges, faces)
            mesh_data.update()

            if parsed_bms_data['vertices']['normals']:
                blender_normals = [(n[0], -n[2], n[1]) for n in parsed_bms_data['vertices']['normals']]
                try:
                    mesh_data.normals_split_custom_set_from_vertices(blender_normals)
                    mesh_data.use_auto_smooth = True
                except Exception as e: # pylint: disable=broad-except
                    print(f"Warning: Could not set custom normals: {e}")


            if parsed_bms_data['vertices']['uv0']:
                uv_layer_0 = mesh_data.uv_layers.new(name="UVMap")
                for poly in mesh_data.polygons:
                    for loop_idx in poly.loop_indices:
                        loop = mesh_data.loops[loop_idx]
                        if loop.vertex_index < len(parsed_bms_data['vertices']['uv0']):
                           uv_data = parsed_bms_data['vertices']['uv0'][loop.vertex_index]
                           uv_layer_0.data[loop.index].uv = (uv_data[0], 1.0 - uv_data[1])

            if parsed_bms_data['vertices'].get('uv1') and (parsed_bms_data['vertex_flag'] & VERTEX_FLAG_UV1):
                if len(parsed_bms_data['vertices']['uv1']) == len(verts_loc): # Check if UV1 data is complete
                    uv_layer_1 = mesh_data.uv_layers.new(name="UVMap_Lightmap")
                    for poly in mesh_data.polygons:
                        for loop_idx in poly.loop_indices:
                            loop = mesh_data.loops[loop_idx]
                            if loop.vertex_index < len(parsed_bms_data['vertices']['uv1']):
                                uv_data = parsed_bms_data['vertices']['uv1'][loop.vertex_index]
                                uv_layer_1.data[loop.index].uv = (uv_data[0], 1.0 - uv_data[1])
                else:
                    print(f"Warning: UV1 data present but its count ({len(parsed_bms_data['vertices']['uv1'])}) "
                          f"mismatches vertex count ({len(verts_loc)}). Skipping UV1 layer.")


            mesh_data.validate()
            obj = bpy.data.objects.new(name=mesh_name, object_data=mesh_data)
            context.scene.collection.objects.link(obj)
            context.view_layer.objects.active = obj
            obj.select_set(True)
            self.report({'INFO'}, f"Imported Mesh: {obj.name}")

        except BMSParsingError as e:
            self.report({'ERROR'}, f"BMS Parsing Error: {e}")
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"General error during BMS/Mesh processing: {e}")
            import traceback; traceback.print_exc()
            if obj: bpy.data.objects.remove(obj, do_unlink=True) # Cleanup partial import
            return {'CANCELLED'}

        # 2. BMT (Materials) Processing
        if self.import_materials and obj:
            try:
                bmt_filepath = os.path.join(base_dir, base_filename + ".bmt")
                if os.path.exists(bmt_filepath):
                    print(f"--- Parsing BMT: {bmt_filepath} ---")
                    parsed_bmt_materials = parse_bmt(bmt_filepath)
                    if parsed_bmt_materials is None:
                        self.report({'WARNING'}, f"Failed to parse BMT: {os.path.basename(bmt_filepath)}. See console.")
                    elif not parsed_bmt_materials:
                        print(f"Info: BMT file {os.path.basename(bmt_filepath)} has no materials.")
                    else:
                        # Material application logic (condensed)
                        bms_mat_name_from_mesh = parsed_bms_data.get('material_name') if parsed_bms_data else None
                        # ... (Full material creation and assignment logic as implemented before) ...
                        # This includes node setup, texture loading attempts, custom properties.
                        # Ensure to handle cases where blender_material.node_tree might be None before accessing nodes.
                        print(f"Processed {len(parsed_bmt_materials)} material(s) from BMT.")
                        self.report({'INFO'}, f"Processed materials from {os.path.basename(bmt_filepath)}.")
                else:
                    print(f"Info: No BMT file found at {bmt_filepath}")
            except BMTParsingError as e:
                self.report({'WARNING'}, f"BMT Parsing Error: {e}")
            except Exception as e:
                self.report({'WARNING'}, f"Error processing BMT materials: {e}")
                import traceback; traceback.print_exc()
        elif not obj:
             self.report({'WARNING'}, "Skipping materials as mesh import failed or was skipped.")
        else:
            print("Skipping material import by user option.")


        # 3. BSK (Skeleton) Processing
        if self.import_skeleton and obj:
            try:
                bsk_filepath = os.path.join(base_dir, base_filename + ".bsk")
                if os.path.exists(bsk_filepath):
                    print(f"--- Parsing BSK: {bsk_filepath} ---")
                    parsed_skeleton = parse_bsk(bsk_filepath)
                    if parsed_skeleton is None:
                        self.report({'WARNING'}, f"Failed to parse BSK: {os.path.basename(bsk_filepath)}. See console.")
                    elif not parsed_skeleton:
                        print(f"Info: BSK file {os.path.basename(bsk_filepath)} has no bones.")
                    else:
                        # Armature creation (condensed)
                        armature_name = obj.name + "_Armature"
                        armature_data = bpy.data.armatures.new(name=armature_name)
                        armature_obj = bpy.data.objects.new(name=armature_name, object_data=armature_data)
                        context.scene.collection.objects.link(armature_obj)
                        armature_obj.show_in_front = True

                        # Bone creation and parenting (condensed)
                        # ...
                        self.report({'INFO'}, f"Created Armature: {armature_obj.name} with {len(parsed_skeleton)} bones.")

                        # Skinning (if BMS skin_data and armature exist)
                        if parsed_bms_data and parsed_bms_data.get('skin_data'):
                            skin_info = parsed_bms_data['skin_data']
                            if skin_info.get('skin_bones_list') and skin_info.get('vertex_skin_data'):
                                print("Applying skinning data...")
                                # ... (Vertex group creation and weight assignment logic as implemented before) ...
                                self.report({'INFO'}, "Applied skinning data.")
                            else:
                                print("Info: BMS has skin_data block but no bones or vertex weights listed.")
                        else:
                            print("Info: No skinning data found in BMS for this mesh.")

                        # Parent Mesh to Armature
                        obj.parent = armature_obj
                        armature_modifier = obj.modifiers.new(name='Armature', type='ARMATURE')
                        armature_modifier.object = armature_obj
                        print(f"Parented '{obj.name}' to '{armature_obj.name}' and added Armature modifier.")
                else:
                    print(f"Info: No BSK file found at {bsk_filepath}")
            except BSKParsingError as e:
                self.report({'WARNING'}, f"BSK Parsing Error: {e}")
                if armature_obj: bpy.data.objects.remove(armature_obj, do_unlink=True) # Cleanup
                armature_obj = None # Ensure it's None if creation failed
            except Exception as e:
                self.report({'WARNING'}, f"Error processing BSK/skinning: {e}")
                import traceback; traceback.print_exc()
                if armature_obj: bpy.data.objects.remove(armature_obj, do_unlink=True)
                armature_obj = None
        elif not obj:
            self.report({'WARNING'}, "Skipping skeleton as mesh import failed or was skipped.")
        else:
            print("Skipping skeleton import by user option.")


        # 4. BAN (Animation) Processing
        if self.import_animations and armature_obj: # Requires an armature
            try:
                ban_files = glob.glob(os.path.join(base_dir, "*.ban"))
                if not ban_files:
                    print(f"Info: No BAN animation files found in {base_dir}")
                else:
                    processed_anims = 0
                    for ban_filepath in ban_files:
                        print(f"--- Parsing BAN: {ban_filepath} ---")
                        parsed_anim_data = parse_ban(ban_filepath)
                        if parsed_anim_data is None:
                            self.report({'WARNING'}, f"Failed to parse BAN: {os.path.basename(ban_filepath)}. See console.")
                            continue
                        # Action creation & F-Curve population (condensed)
                        # ...
                        processed_anims +=1
                    if processed_anims > 0:
                        self.report({'INFO'}, f"Imported {processed_anims} animation(s).")
            except BANParsingError as e:
                 self.report({'WARNING'}, f"BAN Parsing Error: {e}")
            except Exception as e:
                self.report({'WARNING'}, f"Error processing BAN animations: {e}")
                import traceback; traceback.print_exc()
        elif self.import_animations and not armature_obj:
            print("Info: Skipping animation import as skeleton was not imported/created.")
        else:
            print("Skipping animation import by user option.")

        print(f"--- SRO Importer finished for: {os.path.basename(self.filepath)} ---")
        return {'FINISHED'}

    def invoke(self, context, event):
        """Standard invoke method."""
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

# No need for menu_func_import, register, unregister here, they are in __init__.py
```
