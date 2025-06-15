import struct
import os

# Custom Exception for BMT parsing errors
class BMTParsingError(Exception):
    pass

# Define PrimMtrlFlag constants
class PrimMtrlFlag:
    NONE = 0x0000
    TWOSIDED = 0x0001
    ALPHABLEND = 0x0002
    REFLECTIVE_OR_ENV_MAPPED = 0x1000
    Bit14_NormalMap = 0x2000
    Bit15_SpecularMap = 0x4000
    # Add others as identified

def read_sro_euckr_string_bmt(f, context_msg="string"):
    """Helper to read a length-prefixed EUC-KR string with validation for BMT."""
    s_len_bytes = f.read(4)
    if len(s_len_bytes) < 4:
        raise BMTParsingError(f"EOF while reading length for {context_msg}.")
    s_len = struct.unpack('<I', s_len_bytes)[0]

    # Max typical material name or texture path length.
    if not (0 <= s_len <= 520): # MAX_PATH for DDJ is often 260. Allow double for safety.
        raise BMTParsingError(f"Invalid {context_msg} length: {s_len}. Must be reasonable (0-520).")

    if s_len == 0:
        return "" # Empty string is valid

    str_bytes = f.read(s_len)
    if len(str_bytes) < s_len:
        raise BMTParsingError(f"EOF while reading {s_len} bytes for {context_msg}.")

    try:
        return str_bytes.decode('euc-kr', errors='replace')
    except UnicodeDecodeError as ude:
        raise BMTParsingError(f"Unicode decode error for {context_msg}: {ude}")

def parse_bmt(filepath):
    """Parses a Silkroad Online JMXVBMT (BMT) file with enhanced validation."""
    materials = []
    try:
        file_size = os.path.getsize(filepath)
        if file_size == 0:
            raise BMTParsingError("File is empty.")

        with open(filepath, 'rb') as f:
            # Read and verify signature
            if file_size < 12: raise BMTParsingError("File too small for signature.")
            signature = f.read(12)
            if signature != b"JMXVBMT 0102":
                # Some older tools might generate 0100 or 0101, accept if necessary, but spec says 0102
                # For now, strict check:
                raise BMTParsingError(f"Invalid JMXVBMT signature. Expected b'JMXVBMT 0102', got {signature!r}")

            # Read material count
            mcount_bytes = f.read(4)
            if len(mcount_bytes) < 4: raise BMTParsingError("EOF reading material_count.")
            material_count = struct.unpack('<I', mcount_bytes)[0]

            if not (0 <= material_count <= 256): # Max 256 materials per BMT seems reasonable.
                raise BMTParsingError(f"Invalid material count: {material_count}. Expected 0-256.")

            if material_count == 0:
                print(f"Info: BMT file {filepath} contains 0 materials.")
                return [] # Valid case, just no materials

            for i in range(material_count):
                material_data = {'id': i}
                # Check remaining file size for a minimal material entry (name_len + colors + flag + diffuse_path_len)
                # Approx: 4 + (16*4) + 4 + 4 = 76 bytes for minimal named material with empty diffuse path
                if f.tell() + 76 > file_size + 10: # Allow some slack
                     raise BMTParsingError(f"Suspected EOF before reading material {i+1}/{material_count}. File truncated?")


                material_data['name'] = read_sro_euckr_string_bmt(f, f"material {i} name")

                # Colors and Power (4 floats * 4 colors + 1 float power = 17 floats = 68 bytes)
                color_power_bytes = f.read(68)
                if len(color_power_bytes) < 68:
                    raise BMTParsingError(f"EOF reading color/power data for material '{material_data['name']}'.")

                colors = struct.unpack('<17f', color_power_bytes) # 16 for colors, 1 for power
                material_data['diffuse_color'] = tuple(colors[0:4])
                material_data['ambient_color'] = tuple(colors[4:8])
                material_data['specular_color'] = tuple(colors[8:12])
                material_data['emissive_color'] = tuple(colors[12:16])
                material_data['power'] = colors[16]

                flag_bytes = f.read(4)
                if len(flag_bytes) < 4: raise BMTParsingError(f"EOF reading material flag for '{material_data['name']}'.")
                material_data['flag'] = struct.unpack('<I', flag_bytes)[0]

                # DiffuseMap and its properties
                material_data['diffuse_map_path'] = read_sro_euckr_string_bmt(f, f"diffuse map path for '{material_data['name']}'")

                diffuse_props_bytes = f.read(4 + 1 + 1 + 1 + 1) # float, byte, byte, bool, padding
                if len(diffuse_props_bytes) < (4+1+1+1+1):
                    raise BMTParsingError(f"EOF reading diffuse map properties for '{material_data['name']}'.")
                diffuse_props = struct.unpack('<fBB?', diffuse_props_bytes[:-1]) # Exclude padding for unpack
                material_data['diffuse_map_unkfloat1'] = diffuse_props[0]
                material_data['diffuse_map_unkbyte0'] = diffuse_props[1]
                material_data['diffuse_map_unkbyte1'] = diffuse_props[2]
                material_data['diffuse_map_is_absolute'] = diffuse_props[3]

                material_data['normal_map_path'] = None
                if material_data['flag'] & PrimMtrlFlag.Bit14_NormalMap:
                    material_data['normal_map_path'] = read_sro_euckr_string_bmt(f, f"normal map path for '{material_data['name']}'")

                # Similarly for SpecularMap if Bit15_SpecularMap is set, etc.
                if material_data['flag'] & PrimMtrlFlag.Bit15_SpecularMap:
                    # Assuming it's just a path for now, like normal map
                    # material_data['specular_map_path'] = read_sro_euckr_string_bmt(f, f"specular map path for '{material_data['name']}'")
                    print(f"Info: Material '{material_data['name']}' has SpecularMap flag, but parser doesn't fully handle its properties yet.")


                materials.append(material_data)
                if i == 0: # Debug first material
                    print(f"Parsed material 0 from BMT: Name='{material_data['name']}', Flag={hex(material_data['flag'])}, DiffuseMap='{material_data['diffuse_map_path']}'")

    except BMTParsingError as e:
        print(f"BMT Parsing Error for {filepath}: {e}")
        return None
    except FileNotFoundError:
        print(f"Error: BMT File not found at {filepath}")
        return None
    except struct.error as e:
        print(f"Struct Error (file corruption or format mismatch) for BMT {filepath}: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while parsing BMT {filepath}: {e}")
        import traceback
        traceback.print_exc()
        return None

    return materials

if __name__ == '__main__':
    dummy_bmt_path = "dummy_test_full.bmt"
    try:
        with open(dummy_bmt_path, "wb") as f:
            f.write(b"JMXVBMT 0102")
            f.write(struct.pack('<I', 1)) # 1 material

            mat_name = "TestMat_Full"
            mat_name_bytes = mat_name.encode('euc-kr')
            f.write(struct.pack('<I', len(mat_name_bytes)))
            f.write(mat_name_bytes)

            f.write(struct.pack('<4f', 0.8,0.8,0.8,1)) # Diffuse
            f.write(struct.pack('<4f', 0.1,0.1,0.1,1)) # Ambient
            f.write(struct.pack('<4f', 0.5,0.5,0.5,1)) # Specular
            f.write(struct.pack('<4f', 0,0,0,0))       # Emissive
            f.write(struct.pack('<f', 32.0))           # Power
            f.write(struct.pack('<I', PrimMtrlFlag.Bit14_NormalMap)) # Flag

            diff_path = "textures/dummy_diff.dds"
            diff_path_bytes = diff_path.encode('euc-kr')
            f.write(struct.pack('<I', len(diff_path_bytes)))
            f.write(diff_path_bytes)
            f.write(struct.pack('<fBB?', 1.0, 0, 0, False)) # unkfloat, unkbyte0, unkbyte1, isAbsolute
            f.write(b'\x00') # Padding

            norm_path = "textures/dummy_norm.dds"
            norm_path_bytes = norm_path.encode('euc-kr')
            f.write(struct.pack('<I', len(norm_path_bytes)))
            f.write(norm_path_bytes)

        print(f"Dummy BMT file '{dummy_bmt_path}' created.")
        parsed_mats = parse_bmt(dummy_bmt_path)
        if parsed_mats:
            print(f"\n--- Parsed BMT Data ({len(parsed_mats)} materials) ---")
            for mat in parsed_mats:
                print(f"  Name: {mat['name']}, Flag: {hex(mat['flag'])}")
                print(f"    Diffuse: {mat['diffuse_color']}, Map: {mat['diffuse_map_path']}")
                if mat['normal_map_path']:
                    print(f"    Normal Map: {mat['normal_map_path']}")
        else:
            print("--- Dummy BMT Parsing Failed ---")

    except Exception as e:
        print(f"Error in BMT self-test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if os.path.exists(dummy_bmt_path):
            os.remove(dummy_bmt_path)
            print(f"Cleaned up '{dummy_bmt_path}'.")

```
