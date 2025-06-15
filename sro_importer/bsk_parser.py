import struct
import collections
import os

# Custom Exception for BSK parsing errors
class BSKParsingError(Exception):
    pass

# Helper to read length-prefixed EUC-KR strings with validation
def read_sro_euckr_string_bsk(f, context_msg="string", max_len=128): # Bone names usually not extremely long
    s_len_bytes = f.read(4)
    if len(s_len_bytes) < 4:
        raise BSKParsingError(f"EOF while reading length for {context_msg}.")
    s_len = struct.unpack('<I', s_len_bytes)[0]

    if not (0 <= s_len <= max_len): # Max reasonable length for bone names
        raise BSKParsingError(f"Invalid {context_msg} length: {s_len}. Must be 0-{max_len}.")

    if s_len == 0:
        return ""

    str_bytes = f.read(s_len)
    if len(str_bytes) < s_len:
        raise BSKParsingError(f"EOF while reading {s_len} bytes for {context_msg}.")

    try:
        return str_bytes.decode('euc-kr', errors='replace')
    except UnicodeDecodeError as ude:
        raise BSKParsingError(f"Unicode decode error for {context_msg}: {ude}")

BoneData = collections.namedtuple("BoneData", [
    "boneType", "name", "parentName",
    "rotToParent", "transToParent",
    "rotToOrigin", "transToOrigin",
    "rotToLocal", "transToLocal",
    "childBoneNames"
])

def parse_bsk(filepath):
    """Parses a Silkroad Online JMXVBSK (BSK) skeleton file with enhanced validation."""
    bones = []
    try:
        file_size = os.path.getsize(filepath)
        if file_size == 0:
            raise BSKParsingError("File is empty.")

        with open(filepath, 'rb') as f:
            # Signature and Version (total 12 or 13 bytes depending on spaces)
            # JMXVBSK  0100 (2 spaces) or JMXVBSK 0100 (1 space)
            if file_size < 12: raise BSKParsingError("File too small for signature.")

            sig_part1 = f.read(8) # "JMXVBSK "
            if sig_part1 != b"JMXVBSK ":
                 raise BSKParsingError(f"Invalid BSK signature prefix. Expected b'JMXVBSK '. Got: {sig_part1!r}")

            # Handle potential space variations
            maybe_space = f.read(1)
            version_bytes_to_read = 4
            if maybe_space != b" ": # If it's not a space, it might be part of version (old format?) or only one space
                f.seek(-1, os.SEEK_CUR) # Rewind one byte
                # We already checked for "JMXVBSK " (8 bytes), so this implies the format might be "JMXVBSK0100"
                # which is not standard. For now, assume at least one space is required.
                # If JMXVBSK0100 (no space) needs to be supported, this logic needs more complex branching.
                # The provided examples and common use suggest "JMXVBSK  0100" or "JMXVBSK 0100".
                # This code currently favors "JMXVBSK 0100" (single space) if double space fails.
                # Let's simplify: try reading "JMXVBSK  " (9 bytes) first.
                f.seek(0)
                sig_full_9 = f.read(9)
                if sig_full_9 == b"JMXVBSK  ": # Two spaces
                    sig_prefix_str = "JMXVBSK  "
                else: # Try one space
                    f.seek(0)
                    sig_full_8 = f.read(8)
                    if sig_full_8 == b"JMXVBSK ":
                         sig_prefix_str = "JMXVBSK "
                    else:
                        raise BSKParsingError(f"Invalid BSK signature. Expected 'JMXVBSK  ' or 'JMXVBSK '. Got start: {f.read(9)!r}")
            else: # It was a space, so it was "JMXVBSK  " (two spaces)
                sig_prefix_str = "JMXVBSK  "

            version = f.read(version_bytes_to_read)
            if version not in [b"0100", b"0101"]:
                raise BSKParsingError(f"Unsupported BSK version. Expected '0100' or '0101'. Got: {version!r}")

            print(f"BSK Signature: {sig_prefix_str}{version.decode()}")

            bc_bytes = f.read(4)
            if len(bc_bytes) < 4: raise BSKParsingError("EOF reading bone_count.")
            bone_count = struct.unpack('<I', bc_bytes)[0]

            if not (0 <= bone_count <= 256): # Max 256 bones in a skeleton seems reasonable.
                raise BSKParsingError(f"Invalid bone count: {bone_count}. Expected 0-256.")

            if bone_count == 0:
                print(f"Info: BSK file {filepath} contains 0 bones.")
                return []

            # Minimum data per bone: 1 (type) + 3* (4+name_len) + 3*(16+12) (transforms) + 4 (child_count)
            # Rough estimate: 1 + 12 (empty names) + 3*28 + 4 = 1+12+84+4 = 101 bytes per bone.
            if f.tell() + bone_count * 80 > file_size + 100: # 80 is a very rough min estimate
                raise BSKParsingError("File size too small for declared bone count and their data.")

            for i in range(bone_count):
                bt_byte = f.read(1)
                if len(bt_byte) < 1: raise BSKParsingError(f"EOF reading boneType for bone {i+1}/{bone_count}.")
                bone_type = struct.unpack('<B', bt_byte)[0]

                bone_name = read_sro_euckr_string_bsk(f, f"bone {i+1} name")
                parent_name = read_sro_euckr_string_bsk(f, f"bone {i+1} parentName")

                # Transforms: 3 sets of (Quat + Vec3) = 3 * (16 + 12) = 3 * 28 = 84 bytes
                transform_bytes = f.read(84)
                if len(transform_bytes) < 84:
                    raise BSKParsingError(f"EOF reading transform data for bone '{bone_name}'.")

                transforms = struct.unpack('<4f3f4f3f4f3f', transform_bytes)
                rot_to_parent_q = tuple(transforms[0:4])
                trans_to_parent_v = tuple(transforms[4:7])
                rot_to_origin_q = tuple(transforms[7:11])
                trans_to_origin_v = tuple(transforms[11:14])
                rot_to_local_q = tuple(transforms[14:18])
                trans_to_local_v = tuple(transforms[18:21])

                cc_bytes = f.read(4)
                if len(cc_bytes) < 4: raise BSKParsingError(f"EOF reading childBoneCount for bone '{bone_name}'.")
                child_bone_count = struct.unpack('<I', cc_bytes)[0]

                if not (0 <= child_bone_count <= bone_count): # Child count cannot exceed total bones
                    raise BSKParsingError(f"Invalid childBoneCount {child_bone_count} for bone '{bone_name}'.")

                child_names = []
                for j in range(child_bone_count):
                    child_name = read_sro_euckr_string_bsk(f, f"bone '{bone_name}' child {j+1} name")
                    child_names.append(child_name)

                bones.append(BoneData(
                    boneType=bone_type, name=bone_name, parentName=parent_name,
                    rotToParent=rot_to_parent_q, transToParent=trans_to_parent_v,
                    rotToOrigin=rot_to_origin_q, transToOrigin=trans_to_origin_v,
                    rotToLocal=rot_to_local_q, transToLocal=trans_to_local_v,
                    childBoneNames=child_names
                ))
                if i < 3 or i == bone_count -1 :
                    print(f"  Parsed Bone: {bone_name}, Parent: {parent_name if parent_name else 'ROOT'}")

    except BSKParsingError as e:
        print(f"BSK Parsing Error for {filepath}: {e}")
        return None
    except FileNotFoundError:
        print(f"Error: BSK File not found at {filepath}")
        return None
    except struct.error as e:
        print(f"Struct Error (file corruption or format mismatch) for BSK {filepath}: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while parsing BSK {filepath}: {e}")
        import traceback
        traceback.print_exc()
        return None

    return bones

if __name__ == '__main__':
    dummy_bsk_path = "dummy_test_full.bsk"
    try:
        with open(dummy_bsk_path, "wb") as f:
            f.write(b"JMXVBSK  0100") # Double space standard
            f.write(struct.pack('<I', 1)) # Bone count = 1

            # Bone 1: Root
            f.write(struct.pack('<B', 0)) # boneType

            root_name = "Bip01_Test"
            r_name_bytes = root_name.encode('euc-kr')
            f.write(struct.pack('<I', len(r_name_bytes)))
            f.write(r_name_bytes)

            p_root_name = "" # No parent
            p_name_bytes = p_root_name.encode('euc-kr')
            f.write(struct.pack('<I', len(p_name_bytes)))
            f.write(p_name_bytes)

            # Transforms (all identity/zero for simplicity)
            f.write(struct.pack('<4f3f', 0,0,0,1, 0,0,0)) # ToParent
            f.write(struct.pack('<4f3f', 0,0,0,1, 0,0,0)) # ToOrigin
            f.write(struct.pack('<4f3f', 0,0,0,1, 0,0,0)) # ToLocal

            f.write(struct.pack('<I', 0)) # childBoneCount = 0

        print(f"Dummy BSK file '{dummy_bsk_path}' created.")
        parsed_skel = parse_bsk(dummy_bsk_path)
        if parsed_skel:
            print(f"\n--- Parsed BSK Data ({len(parsed_skel)} bones) ---")
            for bone_entry in parsed_skel:
                print(f"  Name: {bone_entry.name}, Parent: {bone_entry.parentName if bone_entry.parentName else 'None'}")
        else:
            print("--- Dummy BSK Parsing Failed ---")

    except Exception as e_main:
        print(f"Error in BSK self-test: {e_main}")
        import traceback
        traceback.print_exc()
    finally:
        if os.path.exists(dummy_bsk_path):
            os.remove(dummy_bsk_path)
            print(f"Cleaned up '{dummy_bsk_path}'.")
```
