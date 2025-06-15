import struct
import os

# VertexFlag constants
HAS_NORMAL = 0x001
HAS_UV0 = 0x010
VERTEX_FLAG_UV1 = 0x400 # As per JMXVBMS documentation for secondary UV map
# Other flags like HAS_UV2, HAS_UV3, HAS_COLOR, HAS_TANGENT can be added if used

# Custom Exception for parsing errors
class BMSParsingError(Exception):
    pass

def read_sro_euckr_string(f, context_msg="string"):
    """Helper to read a length-prefixed EUC-KR string with validation."""
    s_len_bytes = f.read(4)
    if len(s_len_bytes) < 4:
        raise BMSParsingError(f"EOF while reading length for {context_msg}.")
    s_len = struct.unpack('<I', s_len_bytes)[0]

    # Max typical bone name or material name length. Adjust if necessary.
    # Very long strings might indicate corruption or format misinterpretation.
    if not (0 <= s_len <= 260 * 4): # Allow a bit more than MAX_PATH for safety with multibyte
        raise BMSParsingError(f"Invalid {context_msg} length: {s_len}. Must be reasonable.")

    if s_len == 0:
        return ""

    str_bytes = f.read(s_len)
    if len(str_bytes) < s_len:
        raise BMSParsingError(f"EOF while reading {s_len} bytes for {context_msg}.")

    try:
        return str_bytes.decode('euc-kr', errors='replace')
    except UnicodeDecodeError as ude:
        raise BMSParsingError(f"Unicode decode error for {context_msg}: {ude}")


def parse_bms(filepath):
    """Parses a Silkroad Online JMXVBMS file with enhanced validation."""
    vertices = {"positions": [], "normals": [], "uv0": [], "uv1": []}
    faces = []
    parsed_skin_data = {"skin_bones_list": [], "vertex_skin_data": []}
    material_name = "DefaultBMSMaterial" # Default if read fails
    vertex_flag = 0

    try:
        file_size = os.path.getsize(filepath)
        if file_size == 0:
            raise BMSParsingError("File is empty.")

        with open(filepath, 'rb') as f:
            # Signature
            if file_size < 12: raise BMSParsingError("File too small for signature.")
            signature = f.read(12)
            if signature != b"JMXVBMS 0110":
                raise BMSParsingError(f"Invalid JMXVBMS signature. Expected b'JMXVBMS 0110', got {signature!r}")

            # Header reading with checks
            # Material Name (ASCII in spec, but some might use EUC-KR, be cautious)
            # For now, sticking to ASCII based on previous code. If issues, change to read_sro_euckr_string.
            mat_name_len_bytes = f.read(4)
            if len(mat_name_len_bytes) < 4: raise BMSParsingError("EOF reading material name length.")
            mat_name_len = struct.unpack('<I', mat_name_len_bytes)[0]
            if not (0 <= mat_name_len <= 260): # Max reasonable length
                raise BMSParsingError(f"Invalid material name length: {mat_name_len}")
            if mat_name_len > 0:
                mat_name_bytes = f.read(mat_name_len)
                if len(mat_name_bytes) < mat_name_len: raise BMSParsingError("EOF reading material name.")
                try:
                    material_name = mat_name_bytes.decode('ascii') # Per prior code
                except UnicodeDecodeError:
                    material_name = mat_name_bytes.decode('euc-kr', errors='replace') # Fallback
                    print(f"Warning: Material name for {filepath} not pure ASCII, decoded as EUC-KR.")
            else:
                material_name = "UnnamedMaterial"


            header_rest_fmt = '<3I' # VBO_offset, IBO_offset, VertexFlag
            header_rest_size = struct.calcsize(header_rest_fmt)
            header_rest_bytes = f.read(header_rest_size)
            if len(header_rest_bytes) < header_rest_size: raise BMSParsingError("EOF reading header offsets/flags.")
            vertex_buffer_offset, index_buffer_offset, vertex_flag = struct.unpack(header_rest_fmt, header_rest_bytes)

            f.seek(4 * 2, 1) # Skip Reserved0, Reserved1
            f.seek(4, 1)     # Skip Reserved2
            f.seek(4 * 3 * 2, 1) # Skip BoundingBoxMin/Max
            f.seek(4 * 4, 1) # Skip Reserved3-6

            skin_offset_bytes = f.read(4)
            if len(skin_offset_bytes) < 4: raise BMSParsingError("EOF reading skin_offset.")
            skin_offset = struct.unpack('<I', skin_offset_bytes)[0]

            f.seek(4 * 1, 1) # Skip MotionOffset
            f.seek(4 * 2, 1) # Skip Reserved7[2]

            # Offset validations
            for name, offset in [("VertexBuffer", vertex_buffer_offset),
                                 ("IndexBuffer", index_buffer_offset),
                                 ("SkinData", skin_offset)]:
                if offset > 0 and offset >= file_size: # Allow offset == file_size if count is 0
                    raise BMSParsingError(f"{name}Offset {offset} is out of file bounds ({file_size}).")

            # --- Vertex Data ---
            if vertex_buffer_offset == 0:
                print(f"Warning: VertexBufferOffset is 0 for '{material_name}'. No mesh geometry.")
                # Allow this, but no vertices or faces will be read. Skinning also depends on vertex_count.
                vertex_count = 0
            else:
                f.seek(vertex_buffer_offset)
                vcount_bytes = f.read(4)
                if len(vcount_bytes) < 4: raise BMSParsingError("EOF before reading vertex_count.")
                vertex_count = struct.unpack('<I', vcount_bytes)[0]

            if not (0 <= vertex_count <= 1000000): # Max 1 million vertices
                raise BMSParsingError(f"Invalid vertex count: {vertex_count}")

            if vertex_count > 0 and vertex_buffer_offset == 0:
                 raise BMSParsingError("vertex_count > 0 but VertexBufferOffset is 0.")


            for i in range(vertex_count):
                # Position
                pos_bytes = f.read(12)
                if len(pos_bytes) < 12: raise BMSParsingError(f"EOF in vertex positions at vtx {i+1}/{vertex_count}.")
                vertices["positions"].append(struct.unpack('<3f', pos_bytes))

                # Normals (conditional)
                if vertex_flag & HAS_NORMAL:
                    norm_bytes = f.read(12)
                    if len(norm_bytes) < 12: raise BMSParsingError(f"EOF in vertex normals at vtx {i+1}/{vertex_count}.")
                    vertices["normals"].append(struct.unpack('<3f', norm_bytes))
                else:
                    vertices["normals"].append((0.0, 0.0, 1.0)) # Default if no normal

                # UV0 (conditional)
                if vertex_flag & HAS_UV0:
                    uv0_bytes = f.read(8)
                    if len(uv0_bytes) < 8: raise BMSParsingError(f"EOF in UV0 data at vtx {i+1}/{vertex_count}.")
                    vertices["uv0"].append(struct.unpack('<2f', uv0_bytes))
                else:
                    vertices["uv0"].append((0.0,0.0)) # Default if no UV0

                # UV1 (conditional)
                if vertex_flag & VERTEX_FLAG_UV1:
                    uv1_bytes = f.read(8)
                    if len(uv1_bytes) < 8:
                        print(f"Warning: EOF in UV1 data at vtx {i+1}/{vertex_count}. Further UV1s will be skipped.")
                        vertex_flag &= ~VERTEX_FLAG_UV1 # Stop trying to read UV1
                        vertices["uv1"].append((0.0,0.0)) # Default for this one
                        continue
                    vertices["uv1"].append(struct.unpack('<2f', uv1_bytes))
                elif "uv1" in vertices : # Only append if list exists, to keep all lists same length if some verts had UV1 then EOF
                    vertices["uv1"].append((0.0,0.0))


            # --- Face Data ---
            if index_buffer_offset == 0:
                if vertex_count > 0 : print(f"Warning: IndexBufferOffset is 0 for '{material_name}' but vertices exist. Mesh will be point cloud.")
                face_count = 0
            else:
                f.seek(index_buffer_offset)
                fcount_bytes = f.read(4)
                if len(fcount_bytes) < 4: raise BMSParsingError("EOF before reading face_count.")
                face_count = struct.unpack('<I', fcount_bytes)[0]

            if not (0 <= face_count <= 2000000): # Max 2 million faces
                raise BMSParsingError(f"Invalid face count: {face_count}")
            if face_count > 0 and index_buffer_offset == 0:
                raise BMSParsingError("face_count > 0 but IndexBufferOffset is 0.")


            for i in range(face_count):
                face_bytes = f.read(6) # 3 ushorts
                if len(face_bytes) < 6: raise BMSParsingError(f"EOF in face data at face {i+1}/{face_count}.")
                faces.append(struct.unpack('<3H', face_bytes))

            # --- Skinning Data ---
            if skin_offset > 0 and vertex_count > 0 : # Skinning needs vertices
                f.seek(skin_offset)
                sb_count_bytes = f.read(4)
                if len(sb_count_bytes) < 4: raise BMSParsingError("EOF reading skin_bone_count.")
                skin_bone_count = struct.unpack('<I', sb_count_bytes)[0]

                if not (0 <= skin_bone_count <= 255): # Max bones influencing a single mesh usually within byte range for indices
                     raise BMSParsingError(f"Invalid skin_bone_count: {skin_bone_count}. Max 255.")

                if skin_bone_count > 0:
                    for _ in range(skin_bone_count):
                        bone_name = read_sro_euckr_string(f, "skin bone name")
                        parsed_skin_data["skin_bones_list"].append(bone_name)

                    num_skin_bones_read = len(parsed_skin_data["skin_bones_list"])

                    for i in range(vertex_count): # Skin data for each vertex
                        skin_entry_bytes = f.read(6) # B H B H
                        if len(skin_entry_bytes) < 6:
                            print(f"Warning: EOF in skin vertex data at vtx {i+1}/{vertex_count}. Partial skin data.")
                            break

                        idx1, w1_raw, idx2, w2_raw = struct.unpack('<BHBH', skin_entry_bytes)

                        if not (0 <= idx1 < num_skin_bones_read):
                            print(f"Warning: Vtx {i}, boneIndex1 {idx1} out of range ({num_skin_bones_read} bones). Clamping.")
                            idx1 = 0 if num_skin_bones_read > 0 else 0 # Avoid negative index if no bones
                        if not (0 <= idx2 < num_skin_bones_read):
                            print(f"Warning: Vtx {i}, boneIndex2 {idx2} out of range ({num_skin_bones_read} bones). Clamping.")
                            idx2 = 0 if num_skin_bones_read > 0 else 0

                        w1 = min(w1_raw / 1000.0, 1.0) if num_skin_bones_read > 0 else 0.0
                        w2 = min(w2_raw / 1000.0, 1.0) if num_skin_bones_read > 0 else 0.0

                        # Normalize if sum is greater than 1.0 and both contribute
                        if w1 > 0.0001 and w2 > 0.0001 and (w1 + w2) > 1.001: # Epsilon for float comparison
                            sum_w = w1 + w2
                            w1 /= sum_w
                            w2 /= sum_w

                        parsed_skin_data["vertex_skin_data"].append(((idx1, w1), (idx2, w2)))
            elif skin_offset > 0 and vertex_count == 0:
                 print("Warning: SkinOffset present but vertex_count is 0. No skin data processed.")


    except BMSParsingError as e:
        print(f"BMS Parsing Error for {filepath}: {e}")
        return None # Indicate failure
    except FileNotFoundError:
        print(f"Error: File not found at {filepath}")
        return None
    except struct.error as e:
        print(f"Struct Error (likely file corruption or format mismatch) during BMS parsing of {filepath}: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while parsing BMS {filepath}: {e}")
        import traceback
        traceback.print_exc()
        return None

    if not vertices["uv1"] and "uv1" in vertices: del vertices["uv1"] # Cleanup if UV1 list was created but is empty

    print(f"Successfully parsed {filepath}: Mat='{material_name}', Verts={len(vertices['positions'])}, Faces={len(faces)}, SkinBones={len(parsed_skin_data['skin_bones_list'])}")

    return {"vertices": vertices, "faces": faces, "material_name": material_name,
            "vertex_flag": vertex_flag, "skin_data": parsed_skin_data}


if __name__ == '__main__':
    # Create a more robust dummy BMS for testing all features including skinning
    dummy_bms_path = "dummy_test_full.bms"
    HAS_NORMAL_TEST = 0x001
    HAS_UV0_TEST = 0x010
    VERTEX_FLAG_UV1_TEST = 0x400

    try:
        with open(dummy_bms_path, "wb") as f:
            f.write(b"JMXVBMS 0110")  # Signature

            # Material Name
            material_name_test = "TestMaterial"
            f.write(struct.pack('<I', len(material_name_test)))
            f.write(material_name_test.encode('ascii'))

            # Header Part 1 (Offsets and Flag)
            # Assume header structure: Sig(12) + MatNameLen(4) + MatNameActual + VBO(4) + IBO(4) + VFlag(4)
            # Then Reserved0,1(8) + Reserved2(4) + BBox(24) + Reserved3-6(16) + SkinOff(4) + MotionOff(4) + Reserved7(8)
            # Total fixed header part after MatName: 80 bytes
            current_offset = 12 + 4 + len(material_name_test) # After material name

            vbo_offset_test = current_offset + 80 # All fixed header parts after current pos
            ibo_offset_test = vbo_offset_test + 4 + (2 * (12 + 12 + 8 + 8)) # 2 vertices, all components (pos,norm,uv0,uv1) + vtx_count
            skin_offset_test = ibo_offset_test + 4 + (1 * 6) # 1 face + face_count

            vertex_flag_test = HAS_NORMAL_TEST | HAS_UV0_TEST | VERTEX_FLAG_UV1_TEST

            f.write(struct.pack('<III', vbo_offset_test, ibo_offset_test, vertex_flag_test))

            # Fill Reserved and other fields
            f.write(b'\x00' * (4*2))  # Reserved0,1
            f.write(b'\x00' * 4)      # Reserved2
            f.write(b'\x00' * (4*3*2))# BBox
            f.write(b'\x00' * (4*4))  # Reserved3-6
            f.write(struct.pack('<I', skin_offset_test)) # SkinOffset
            f.write(struct.pack('<I', 0)) # MotionOffset (0)
            f.write(b'\x00' * (4*2))  # Reserved7

            # --- Vertex Buffer ---
            f.seek(vbo_offset_test)
            num_verts_test = 2
            f.write(struct.pack('<I', num_verts_test))
            # Vert 1
            f.write(struct.pack('<3f', 0,0,0)) # Pos
            f.write(struct.pack('<3f', 0,0,1)) # Norm
            f.write(struct.pack('<2f', 0,0))   # UV0
            f.write(struct.pack('<2f', 0,0))   # UV1
            # Vert 2
            f.write(struct.pack('<3f', 1,0,0)) # Pos
            f.write(struct.pack('<3f', 0,0,1)) # Norm
            f.write(struct.pack('<2f', 1,0))   # UV0
            f.write(struct.pack('<2f', 1,0))   # UV1

            # --- Index Buffer ---
            f.seek(ibo_offset_test)
            num_faces_test = 1
            f.write(struct.pack('<I', num_faces_test))
            f.write(struct.pack('<3H', 0, 1, 0)) # Degenerate face for simplicity (0,1,0)

            # --- Skinning Data ---
            f.seek(skin_offset_test)
            skin_bone_names_test = ["BoneA", "BoneB"]
            f.write(struct.pack('<I', len(skin_bone_names_test))) # skin_bone_count
            for name in skin_bone_names_test:
                name_bytes = name.encode('euc-kr')
                f.write(struct.pack('<I', len(name_bytes)))
                f.write(name_bytes)

            # Skin data for 2 vertices
            # V0: BoneA 0.7, BoneB 0.3
            f.write(struct.pack('<BHBH', 0, 700, 1, 300))
            # V1: BoneA 0.2, BoneB 0.8
            f.write(struct.pack('<BHBH', 0, 200, 1, 800))

        print(f"Dummy BMS file '{dummy_bms_path}' created for testing error handling.")
        parsed_result = parse_bms(dummy_bms_path)
        if parsed_result:
            print("--- Dummy BMS Parsed Successfully ---")
            print(f"Material: {parsed_result['material_name']}")
            print(f"Vertices: {len(parsed_result['vertices']['positions'])}")
            print(f"Faces: {len(parsed_result['faces'])}")
            if parsed_result['skin_data']['skin_bones_list']:
                print(f"Skin Bones: {parsed_result['skin_data']['skin_bones_list']}")
                print(f"Vertex 0 Skin: {parsed_result['skin_data']['vertex_skin_data'][0]}")
        else:
            print("--- Dummy BMS Parsing Failed (as expected by some internal error if any) ---")

    except Exception as e_main:
        print(f"Error in __main__ test setup for BMS: {e_main}")
        import traceback
        traceback.print_exc()
    finally:
        if os.path.exists(dummy_bms_path):
            os.remove(dummy_bms_path)
            print(f"Cleaned up '{dummy_bms_path}'.")

```
