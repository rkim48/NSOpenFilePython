import matplotlib.pyplot as plt
import numpy as np
from ns_openfile import ns_openfile

# Function to load NEV file and plot raster plot of stim times and Bruker 2P frame timestamps


def plot_raster_from_nev(nev_file):
    # Open NEV file and extract hfile information
    ns_status, hfile = ns_openfile(nev_file)

    # Access memory map from file info
    mmap = hfile.file_info.memory_map

    # Extract timestamps, packet IDs, and class IDs from memory map
    timestamps = np.array([int(i) for i in mmap['TimeStamp']])
    packetIDs = np.array([int(i) for i in mmap['PacketID']])
    classIDs = np.array([int(i) for i in mmap['Class']])

    # Get unique classes
    classes = np.unique(classIDs)

    # Define electrode packet offset and generate list of unique electrodes
    elec_packet_offset = 5120
    electrode_list = np.unique(packetIDs) - elec_packet_offset
    electrode_list = electrode_list[electrode_list > 0]

    # Collect stimulation times for each electrode
    stim_times_all = [None] * len(electrode_list)
    for i, elec_id in enumerate(electrode_list):
        idx = np.where(packetIDs == (elec_id + elec_packet_offset))[0]
        stim_times_all[i] = timestamps[idx]

    # Extract frame timestamps (digital in signal)
    all_frame_ts = timestamps[classIDs == 4]
    frame_ts = all_frame_ts[::2]  # Take every second timestamp

    # Plot the raster plot
    plt.figure()
    plt.title('Raster Plot of Stim Times and 2P Frame Timestamps')
    plt.xlabel('Time')
    plt.ylabel('Channel/Image ID')
    plt.yticks(range(len(electrode_list) + 1))
    plt.ylim([-0.5, len(electrode_list) + 0.5])

    # Plot 2P frame timestamps (first row)
    for ts in frame_ts:
        plt.plot(np.array([ts, ts]) / 30000, [-0.25, 0.25], 'k')

    # Plot stimulation times for each electrode (subsequent rows)
    for i, stim_times in enumerate(stim_times_all):
        for st in stim_times:
            plt.plot(np.array([st, st]) / 30000,
                     [i + 1 - 0.25, i + 1 + 0.25], 'k')

    # Set y-tick labels
    yticklabels = ['2P Frame'] + [f'Ch. {int(e)}' for e in electrode_list]
    plt.gca().set_yticklabels(yticklabels)

    # Show the plot
    plt.show()


# Example usage
nev_file = 'sample.nev'
plot_raster_from_nev(nev_file)
