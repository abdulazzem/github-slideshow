import struct
import collections
import os

# Custom Exception for BAN parsing errors
class BANParsingError(Exception):
    pass

# Helper to read length-prefixed EUC-KR strings with validation
def read_sro_euckr_string_ban(f, context_msg="string", max_len=128): # Anim names, bone names
    s_len_bytes = f.read(4)
    if len(s_len_bytes) < 4:
        raise BANParsingError(f"EOF while reading length for {context_msg}.")
    s_len = struct.unpack('<I', s_len_bytes)[0]

    if not (0 <= s_len <= max_len):
        raise BANParsingError(f"Invalid {context_msg} length: {s_len}. Must be 0-{max_len}.")

    if s_len == 0:
        return "" # Empty string is valid

    str_bytes = f.read(s_len)
    if len(str_bytes) < s_len:
        raise BANParsingError(f"EOF while reading {s_len} bytes for {context_msg}.")

    try:
        return str_bytes.decode('euc-kr', errors='replace')
    except UnicodeDecodeError as ude:
        raise BANParsingError(f"Unicode decode error for {context_msg}: {ude}")

KeyframeData = collections.namedtuple("KeyframeData", ["rotation_quat", "translation_vec"])
BoneAnimationTrack = collections.namedtuple("BoneAnimationTrack", ["bone_name", "keyframes"])
ParsedBanData = collections.namedtuple("ParsedBanData", [
    "name", "duration_ms", "frames_per_second", "anim_type",
    "keyframe_times_ms", "bone_animation_tracks"
])

def parse_ban(filepath):
    """Parses a Silkroad Online JMXVBAN (BAN) animation file with enhanced validation."""
    try:
        file_size = os.path.getsize(filepath)
        if file_size == 0:
            raise BANParsingError("File is empty.")

        with open(filepath, 'rb') as f:
            # Signature and Version (12 bytes total)
            if file_size < 12: raise BANParsingError("File too small for signature/version.")
            sig_prefix = f.read(8)
            version = f.read(4)

            if sig_prefix != b"JMXVBAN ":
                raise BANParsingError(f"Invalid BAN signature prefix. Expected b'JMXVBAN '. Got: {sig_prefix!r}")
            if version not in [b"0102", b"0100"]: # Common versions
                raise BANParsingError(f"Unsupported BAN version. Expected '0102' or '0100'. Got: {version!r}")

            print(f"BAN Signature: {sig_prefix.decode()}{version.decode()}")

            # Header data (4 ints + name_len + name_data + 3 ints + uint)
            # Approx min: 4*4 (ints) + 4 (name_len) + 3*4 (ints) + 4 (kft_count) = 16+4+12+4 = 36 bytes after sig/ver
            if f.tell() + 36 > file_size:
                raise BANParsingError("File too small for BAN header data after signature.")

            int0, int1 = struct.unpack('<2i', f.read(8))
            anim_name = read_sro_euckr_string_ban(f, "animation name")
            duration_ms, frames_per_second, anim_type = struct.unpack('<3i', f.read(12))

            if not (0 < frames_per_second <= 240): # FPS sanity check
                 raise BANParsingError(f"Invalid FramesPerSecond: {frames_per_second}. Expected 1-240.")
            if not (0 <= duration_ms <= 60 * 60 * 1000): # Max 1 hour animation
                 raise BANParsingError(f"Invalid Duration: {duration_ms}ms. Too long.")


            kft_count_bytes = f.read(4)
            if len(kft_count_bytes) < 4: raise BANParsingError("EOF reading keyframeTimeCount.")
            keyframe_time_count = struct.unpack('<I', kft_count_bytes)[0]

            if not (0 <= keyframe_time_count <= 100000): # Max 100k keyframes for an anim seems very high but plausible
                raise BANParsingError(f"Invalid keyframeTimeCount: {keyframe_time_count}.")

            if f.tell() + keyframe_time_count * 4 > file_size:
                raise BANParsingError("File size too small for declared keyframe_times_ms data.")

            keyframe_times = []
            for _ in range(keyframe_time_count):
                kt_bytes = f.read(4) # Reading inside loop for individual EOF check
                if len(kt_bytes) < 4: raise BANParsingError("EOF reading a keyframe time.")
                keyframe_times.append(struct.unpack('<I', kt_bytes)[0])

            ab_count_bytes = f.read(4)
            if len(ab_count_bytes) < 4: raise BANParsingError("EOF reading animatedBoneCount.")
            animated_bone_count = struct.unpack('<I', ab_count_bytes)[0]

            if not (0 <= animated_bone_count <= 256): # Max 256 animated bones
                raise BANParsingError(f"Invalid animatedBoneCount: {animated_bone_count}.")

            bone_tracks = []
            for i in range(animated_bone_count):
                # Check remaining file size for minimal bone track: name_len + name + kf_count + (kf_data)
                if f.tell() + 4 + 4 > file_size : # Min: len_name_str + len_kf_count
                    raise BANParsingError(f"Suspected EOF before reading bone track {i+1}/{animated_bone_count}.")

                bone_name = read_sro_euckr_string_ban(f, f"bone {i+1} name")

                kf_count_bone_bytes = f.read(4)
                if len(kf_count_bone_bytes) < 4: raise BANParsingError(f"EOF reading keyframeCount for bone '{bone_name}'.")
                keyframe_count_for_bone = struct.unpack('<I', kf_count_bone_bytes)[0]

                if keyframe_count_for_bone != keyframe_time_count:
                    # This is a significant structural deviation. It might mean this bone has its own timeline
                    # or is sparsely keyed. The current loader assumes keyframes align with global keyframe_times_ms.
                    print(f"Warning: Bone '{bone_name}' has {keyframe_count_for_bone} keyframes, global time count is {keyframe_time_count}. Data might be misinterpreted if times don't align.")
                    # If this is common, the parser needs a way to handle per-bone time tracks or sparse data.
                    # For now, we will read keyframe_count_for_bone items, but associate them with the first
                    # N items of keyframe_times_ms, which might be incorrect.

                if not (0 <= keyframe_count_for_bone <= keyframe_time_count): # Cannot have more KFs than global time points under current assumption
                     raise BANParsingError(f"Bone '{bone_name}' keyframeCount {keyframe_count_for_bone} mismatch with global time count {keyframe_time_count}.")


                if f.tell() + keyframe_count_for_bone * (16 + 12) > file_size + 10: # 16 for Quat, 12 for Vec3, allow slack
                    raise BANParsingError(f"File size too small for keyframe data of bone '{bone_name}'.")

                current_bone_keyframes = []
                for kf_idx in range(keyframe_count_for_bone):
                    kf_bytes = f.read(16 + 12) # Quat + Vec3
                    if len(kf_bytes) < (16+12):
                        raise BANParsingError(f"EOF reading keyframe {kf_idx+1}/{keyframe_count_for_bone} for bone '{bone_name}'.")

                    kf_data = struct.unpack('<4f3f', kf_bytes)
                    current_bone_keyframes.append(KeyframeData(rotation_quat=tuple(kf_data[0:4]), translation_vec=tuple(kf_data[4:7])))

                bone_tracks.append(BoneAnimationTrack(bone_name=bone_name, keyframes=current_bone_keyframes))
                if i < 2 or i == animated_bone_count -1 :
                    print(f"  Parsed anim track for Bone: {bone_name}, Keyframes: {len(current_bone_keyframes)}")

            # Final check: ensure we didn't read past the file if there's padding or extra data
            # This is more of a sanity check for development.
            # current_pos = f.tell()
            # if current_pos > file_size:
            #    print(f"Warning: Read {current_pos} bytes from a file of size {file_size}. Possible over-read.")


            return ParsedBanData(
                name=anim_name, duration_ms=duration_ms, frames_per_second=frames_per_second,
                anim_type=anim_type, keyframe_times_ms=keyframe_times,
                bone_animation_tracks=bone_tracks
            )

    except BANParsingError as e:
        print(f"BAN Parsing Error for {filepath}: {e}")
        return None
    except FileNotFoundError:
        print(f"Error: BAN File not found at {filepath}")
        return None
    except struct.error as e:
        print(f"Struct Error (file corruption or format mismatch) for BAN {filepath}: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while parsing BAN {filepath}: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == '__main__':
    dummy_ban_path = "dummy_test_full.ban" # New name for clarity
    try:
        with open(dummy_ban_path, "wb") as f:
            f.write(b"JMXVBAN 0102")
            f.write(struct.pack('<2i', 0, 1)) # Int0, Int1

            anim_name_test = "TestAnim_Full"
            anim_name_bytes = anim_name_test.encode('euc-kr')
            f.write(struct.pack('<I', len(anim_name_bytes)))
            f.write(anim_name_bytes)

            f.write(struct.pack('<3i', 1000, 20, 0)) # Duration 1s, 20 FPS, OneShot

            key_times_test = [0, 500, 1000] # 3 keyframes
            f.write(struct.pack('<I', len(key_times_test)))
            for kt in key_times_test:
                f.write(struct.pack('<I', kt))

            f.write(struct.pack('<I', 1)) # 1 animated bone

            bone_name_test = "Bip01_Spine"
            bone_name_bytes = bone_name_test.encode('euc-kr')
            f.write(struct.pack('<I', len(bone_name_bytes)))
            f.write(bone_name_bytes)
            f.write(struct.pack('<I', len(key_times_test))) # KF count for this bone

            # KF 0
            f.write(struct.pack('<4f3f', 0,0,0,1,  0,0,0))
            # KF 1
            f.write(struct.pack('<4f3f', 0,0,0.3826834,0.9238795,  0.5,0,0)) # 45 deg Z rot, 0.5 X trans
            # KF 2
            f.write(struct.pack('<4f3f', 0,0,0.7071068,0.7071068,  1,0,0)) # 90 deg Z rot, 1.0 X trans

        print(f"Dummy BAN file '{dummy_ban_path}' created.")
        parsed_animation = parse_ban(dummy_ban_path)
        if parsed_animation:
            print(f"\n--- Parsed BAN Data ---")
            print(f"Name: {parsed_animation.name}, Duration: {parsed_animation.duration_ms}ms, FPS: {parsed_animation.frames_per_second}")
            print(f"Keyframe Times: {parsed_animation.keyframe_times_ms}")
            for track in parsed_animation.bone_animation_tracks:
                print(f"  Bone: {track.bone_name}, Keyframes: {len(track.keyframes)}")
        else:
            print("--- Dummy BAN Parsing Failed ---")

    except Exception as e_main:
        print(f"Error in BAN self-test: {e_main}")
        import traceback
        traceback.print_exc()
    finally:
        if os.path.exists(dummy_ban_path):
            os.remove(dummy_ban_path)
            print(f"Cleaned up '{dummy_ban_path}'.")
```
