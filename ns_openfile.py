import os
import struct
import mmap
import numpy as np
import tkinter as tk
from tkinter.filedialog import askopenfilename


class HFile:
    def __init__(self):
        self.name = None
        self.file_path = None
        self.file_info = None
        self.time_span = 0
        self.entity = []
        self.time_stamps = []

    def __repr__(self):
        entity_str = f"[1×{len(self.entity)} entity object]"
        file_info_str = "FileInfo object" if self.file_info is not None else "None"
        return (
            f"\nhFile:\n"
            f"\tname: {self.name}\n"
            f"\tfile_path: {self.file_path}\n"
            f"\tfile_info: {file_info_str}\n"
            f"\tentity: {entity_str}\n"
            f"\ttime_span: {self.time_span}\n"
        )


class FileInfo:
    def __init__(self):
        self.type = None
        self.file_size = None
        self.file_type_id = None
        self.label = None
        self.bytes_headers = None
        self.bytes_data_packet = None
        self.memory_map = None
        self.electrode_list = []
        self.time_span = 0  # Duplicate time_span in FileInfo?

    def __repr__(self):
        memory_map_str = f"[1×{len(self.memory_map)} mmap object]" if self.memory_map is not None else "None"
        return (
            f"\nFileInfo:\n"
            f"\ttype: {self.type}\n"
            f"\tfile_size: {self.file_size}\n"
            f"\tfile_type_id: {self.file_type_id}\n"
            f"\tlabel: {self.label}\n"
            f"\tbytes_headers: {self.bytes_headers}\n"
            f"\tbytes_data_packet: {self.bytes_data_packet}\n"
            f"\tmemory_map: {memory_map_str}\n"
            f"\ttime_span: {self.time_span}\n"
            f"\telectrode_list: {self.electrode_list}\n"
        )


class Entity:
    def __init__(self):
        self.electrode_id = None
        self.entity_type = None
        self.reason = None
        self.count = 0
        self.scale = None
        self.units = None
        self.n_units = 0
        self.label = None

    def __repr__(self):
        scale_str = f"{self.scale:.4e}" if self.scale is not None else "None"
        return (
            f"\nEntity:\n"
            f"\telectrode_id: {self.electrode_id}\n"
            f"\tlabel: {self.label}\n"
            f"\tentity_type: {self.entity_type}\n"
            f"\treason: {self.reason}\n"
            f"\tcount: {self.count}\n"
            f"\tscale: {scale_str}\n"
            f"\tunits: {self.units}\n"
            f"\tnumber_of_units: {self.n_units}\n"
        )


def is_valid_file(file):
    valid_extensions = ('.nev', '.ns1', '.ns2', '.ns3', '.ns4', '.ns5', '.ns6')
    return file.lower().endswith(valid_extensions)


def file_dialog():
    root = tk.Tk()
    root.withdraw()  # Hide the main window

    selected_file = askopenfilename(
        initialdir=os.getcwd(),
        title="Select a NEV or NS* file",
        filetypes=(("NEV and NS* files",
                   "*.nev *.ns1 *.ns2 *.ns3 *.ns4 *.ns5 *.ns6"), ("All files", "*.*"))
    )

    if selected_file and is_valid_file(selected_file):
        print("\nSelected file:")
        print(f"- {selected_file}")
        valid_file = selected_file
    else:
        print("No valid file selected")
        valid_file = None

    root.destroy()
    return valid_file


def ns_openfile(filepath=None):
    hfile = HFile()
    if filepath is None:
        filepath = file_dialog()
    hfile.file_path, hfile.name = os.path.split(filepath)
    file_info = FileInfo()
    ns_result = 'ns_OK'
    with open(filepath, 'rb') as fid:
        file_info.type = filepath.split('.')[-1]
        file_info.file_type_id = fid.read(8).decode('utf-8')
        file_info.file_size = os.path.getsize(filepath)

        if file_info.file_type_id == 'NEURALEV':

            # Skip: File Spec and Additional Flags header Information
            fid.seek(4, os.SEEK_CUR)
            file_info.label = 'neural events'
            file_info.period = 1

            # Read BytesHeaders and BytesDataPacket
            file_info.bytes_headers = struct.unpack('I', fid.read(4))[0]
            file_info.bytes_data_packet = struct.unpack('I', fid.read(4))[0]

            # Skip: Time Resolution of Time Stamps, Time Resolution of Samples,
            # Time Origin, Application to Create File, and Comment field
            fid.seek(312, os.SEEK_CUR)

            # Read the number of extended headers
            file_info.n_extended_headers = struct.unpack('I', fid.read(4))[0]

            # Read PacketIDs
            packet_ids = []
            for _ in range(file_info.n_extended_headers):
                packet_id = fid.read(8).decode('utf-8').strip()
                fid.seek(24, os.SEEK_CUR)  # Skip the 24 bytes of information
                packet_ids.append(packet_id)

            # Get index of NEUEVWAV extended headers
            idx_evwav = [i for i, pid in enumerate(
                packet_ids) if pid == 'NEUEVWAV']

            for j in idx_evwav:
                fid.seek(344 + (j * 32), os.SEEK_SET)
                entity = Entity()
                entity.entity_type = 'Segment'
                entity.reason = 0
                entity.units = 'uV'
                entity.count = 0
                entity.electrode_id = struct.unpack('H', fid.read(2))[0]

                # Skip: Physical Connector
                fid.seek(2, os.SEEK_CUR)

                # Scale factor should convert bits to microvolts (nanovolts natively)
                entity.scale = struct.unpack('H', fid.read(2))[0] * 10**-3

                # Skip: Energy Threshold, High Threshold, Low Threshold
                fid.seek(6, os.SEEK_CUR)

                entity.n_units = struct.unpack('B', fid.read(1))[0]

                # If scale factor = 0, use stim amp digitization factor
                if entity.scale == 0:
                    # Skip: Bytes per Waveform
                    fid.seek(1, os.SEEK_CUR)
                    # Scale factor should convert bits to volts (volts natively)
                    entity.scale = struct.unpack('f', fid.read(4))[0]
                    entity.units = 'V'

                hfile.entity.append(entity)

            file_info.file_size = os.path.getsize(filepath)
            n_data_packets = (
                file_info.file_size - file_info.bytes_headers) // file_info.bytes_data_packet

            # Process NEUEVLBL extended headers
            idx_evlbl = [i for i, pid in enumerate(
                packet_ids) if pid == 'NEUEVLBL']
            for j in idx_evlbl:
                fid.seek(344 + (j * 32), os.SEEK_SET)
                elec_id = struct.unpack('H', fid.read(2))[0]

                # Find the entity with the matching electrode ID
                for entity in hfile.entity:
                    if entity.electrode_id == elec_id:
                        lbl = fid.read(16).decode(
                            'utf-8').rstrip('\x00').strip()
                        entity.label = lbl

            if n_data_packets == 0:
                file_info.memory_map = None
                file_info.electrode_list = [
                    ent.electrode_id for ent in hfile.entity if hasattr(ent, 'electrode_id')]
                return file_info

            # Create a cache file to hold NEV event information
            cache_file_name = os.path.join(
                hfile.file_path, f"{os.path.splitext(os.path.basename(hfile.name))[0]}.cache"
            )

            if not os.path.exists(cache_file_name):
                with open(cache_file_name, 'wb') as cache_id:
                    fid.seek(file_info.bytes_headers, os.SEEK_SET)

                    # Write timestamps to cache file
                    timestamps = []
                    for _ in range(n_data_packets):
                        timestamp = struct.unpack('<I', fid.read(4))[
                            0]  # Ensure little-endian
                        timestamps.append(timestamp)
                        cache_id.write(struct.pack('<I', timestamp))
                        fid.seek(file_info.bytes_data_packet - 4, os.SEEK_CUR)

                    # Check the position of the file pointer
                    fid.seek(file_info.bytes_headers + 4, os.SEEK_SET)

                    # Write Packet ID to cache file
                    packet_ids = []
                    for _ in range(n_data_packets):
                        packet_id = struct.unpack('<H', fid.read(2))[
                            0]  # Ensure little-endian
                        packet_ids.append(packet_id)
                        cache_id.write(struct.pack('<H', packet_id))
                        fid.seek(file_info.bytes_data_packet - 2, os.SEEK_CUR)

                    # Seek to the position for reading Classification/Insertion Reason
                    fid.seek(file_info.bytes_headers + 6, os.SEEK_SET)

                    # Write Classification/Insertion Reasons to cache file
                    reasons = []
                    for _ in range(n_data_packets):
                        reason = struct.unpack('B', fid.read(1))[0]
                        reasons.append(reason)
                        cache_id.write(struct.pack('B', reason))
                        fid.seek(file_info.bytes_data_packet - 1, os.SEEK_CUR)

            # Memory map the cache file
            with open(cache_file_name, 'r+b') as cache_id:
                mm = mmap.mmap(cache_id.fileno(), 0)

                # Correctly slice the memory map
                timestamps_from_map = np.frombuffer(
                    mm[:n_data_packets * 4], dtype='uint32')
                packet_ids_from_map = np.frombuffer(
                    mm[n_data_packets * 4:n_data_packets * (4 + 2)], dtype='uint16')
                reasons_from_map = np.frombuffer(
                    mm[n_data_packets * (4 + 2):n_data_packets * (4 + 2 + 1)], dtype='uint8')

                # Assign the data to a structured array for easy access
                data = np.zeros(n_data_packets, dtype=[
                                ('TimeStamp', 'uint32'), ('PacketID', 'uint16'), ('Class', 'uint8')])
                data['TimeStamp'] = timestamps_from_map
                data['PacketID'] = packet_ids_from_map
                data['Class'] = reasons_from_map

            file_info.memory_map = data

            # Get a list of unique Packet IDs
            unique_packet_ids = np.unique(data['PacketID'])

            # Filter entities based on Packet IDs
            if hasattr(hfile.entity[0], 'electrode_id'):
                all_channels = np.array(
                    [ent.electrode_id for ent in hfile.entity])

                # Remove Entities that do not have neural events from the entity list
                mask = np.isin(
                    all_channels, unique_packet_ids[unique_packet_ids != 0])
                hfile.entity = [ent for ent, keep in zip(
                    hfile.entity, mask) if keep]

            # Get number of occurrences of each ElectrodeID in the NEV file
            if hfile.entity:
                for ent in hfile.entity:
                    ent.count = np.sum(data['PacketID'] == ent.electrode_id)

            # Calculate the Timespan in 30kHz
            file_info.time_span = data['TimeStamp'][-1]
            # Update if necessary
            if hfile.time_span < file_info.time_span:
                hfile.time_span = file_info.time_span

            if file_info.memory_map['PacketID'][0] == 0:
                # Get all digital events
                event_class = file_info.memory_map['Class'][file_info.memory_map['PacketID'] == 0]
                packet_reason = ['Parallel Input', 'SMA 1',
                                 'SMA 2', 'SMA 3', 'SMA 4', 'Output Echo']
                EC = len(hfile.entity)
                k = EC + 1

                # Get index of DIGLABEL extended headers
                idx_diglbl = [i for i, pid in enumerate(
                    packet_ids) if pid == 'DIGLABEL']
                dig_lbls = [None] * 6
                if len(idx_diglbl) == 5:
                    dig_lbls = [None] * 6
                    for j, idx in enumerate(idx_diglbl):
                        fid.seek(344 + (idx * 32), os.SEEK_SET)
                        idx = (j % 5) + 1
                        dig_lbls[idx] = fid.read(16).decode('utf-8').strip()
                        mode = struct.unpack('B', fid.read(1))[0]
                        elec_id = struct.unpack('H', fid.read(2))[0]
                    dig_lbls[5] = 'Output Echo'

                # Create Entities for digital channels that have events in the file
                for j in range(6):
                    count = np.sum(np.bitwise_and(event_class, 1 << j))
                    if count:
                        entity = Entity()
                        entity.entity_type = 'Event'
                        entity.reason = packet_reason[j]
                        entity.label = dig_lbls[j]
                        entity.count = count
                        entity.electrode_id = 0
                        hfile.entity.append(entity)

            # Setup neural entities and update file_info with neural data
            file_info.electrode_list = [
                ent.electrode_id for ent in hfile.entity]

            # Get a list of all unique neural entities that have been found
            class_list = np.sort(np.unique(data['Class']))

            # Find out how many unique electrodes and classes we have
            n_electrode = len(
                [elec for elec in file_info.electrode_list if elec != 0])
            n_class = len(class_list)

            # Create space for the Neural entities
            neural_entities = [Entity() for _ in range(n_electrode * n_class)]

            # Create an entity for each possible electrode and class
            for i_entity in range(n_electrode):
                elec_id = file_info.electrode_list[i_entity]
                if elec_id != 0:
                    indices = data['PacketID'] == elec_id
                    classes = data['Class'][indices]
                    for i_class in range(n_class):
                        class_val = class_list[i_class]
                        neural_index = i_entity + i_class * n_electrode
                        neural_entities[neural_index].electrode_id = elec_id
                        neural_entities[neural_index].reason = class_val
                        neural_entities[neural_index].count = np.sum(
                            classes == class_val)

            # Append the neural entities to hfile.entity
            neural_entities = [
                entity for entity in neural_entities if entity.count > 0]
            hfile.entity.extend(neural_entities)
        elif file_info.file_type_id in ['NEURALCD', 'NEUCDFLT']:
            float_stream = file_info.file_type_id == 'NEUCDFLT'

            fid.seek(2, os.SEEK_CUR)
            file_info.bytes_headers = struct.unpack('I', fid.read(4))[0]
            file_info.label = fid.read(16).decode('utf-8').strip()
            fid.seek(256, os.SEEK_CUR)
            file_info.period = struct.unpack('I', fid.read(4))[0]
            fid.seek(20, os.SEEK_CUR)
            chan_count = struct.unpack('I', fid.read(4))[0]
            EC = len(hfile.entity)
            for j in range(EC, EC + chan_count):
                entity = Entity()
                entity.file_type = file_info.file_type_id
                entity.entity_type = 'Analog'
                fid.seek(2, os.SEEK_CUR)

                entity.electrode_id = struct.unpack('H', fid.read(2))[0]
                entity.label = fid.read(16).decode('utf-8').strip()

                fid.seek(2, os.SEEK_CUR)
                analog_scale = struct.unpack('4h', fid.read(8))

                if float_stream:
                    entity.scale = 1.0
                else:
                    entity.scale = (
                        analog_scale[3] - analog_scale[2]) / (analog_scale[1] - analog_scale[0])

                entity.units = fid.read(16).decode('utf-8').strip()

                fid.seek(20, os.SEEK_CUR)
                hfile.entity.append(entity)

            file_info.electrode_list = [
                e.electrode_id for e in hfile.entity[EC:EC + chan_count]]

            fid.seek(file_info.bytes_headers, os.SEEK_SET)
            file_size = os.path.getsize(filepath)
            time_stamps = []

            while fid.tell() < file_info.file_size:
                header = struct.unpack('B', fid.read(1))[0]
                time_stamp = struct.unpack('I', fid.read(4))[
                    0] / file_info.period
                n_points = struct.unpack('I', fid.read(4))[0]
                time_stamps.append((time_stamp, n_points))

                bytes_per_point = 4 if float_stream else 2
                fid.seek(bytes_per_point * n_points * chan_count, os.SEEK_CUR)

            for e in hfile.entity[EC:EC + chan_count]:
                e.count = sum(n_points for ts, n_points in time_stamps)

            file_info.time_span = sum(
                ts * file_info.period for ts, n_points in time_stamps)

            if hfile.time_span < file_info.time_span:
                hfile.time_span = file_info.time_span

            hfile.file_info = file_info

        else:
            ns_result = 'ns_FILEERROR'

    hfile.entity = [entity for entity in hfile.entity if entity.count > 0]
    hfile.file_info = file_info

    if ns_result == 'ns_FILEERROR':
        return ns_result, hfile

    return ns_result, hfile
