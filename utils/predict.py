import numpy as np
import obspy.core as oc
from scipy.signal import find_peaks
import math
import matplotlib.pyplot as plt
from utils.math_helper import normal_d, insert_np


def sliding_window(data, n_features, n_shift):
    """
    Return NumPy array of sliding windows. Which is basically a view into a copy of original data array.

    Arguments:
    data       -- numpy array to make a sliding windows on
    n_features -- length in samples of the individual window
    n_shift    -- shift between windows starting points
    """
    # Get sliding windows shape
    win_count = np.floor(data.shape[0]/n_shift - n_features/n_shift + 1).astype(int)
    shape = [win_count, n_features]

    # Single window strides (byte_shift_per_window, byte_shift_per_element)
    strides = [data.strides[0]*n_shift, data.strides[0]]

    # Get windows
    windows = np.lib.stride_tricks.as_strided(data, shape, strides)

    return windows.copy()


# TODO: come up with better names for both sliding_window functions (sliding_window_striped and .. ?)
def sliding_window_memory_consuming(data, n_features, n_shift):
    """
    Return NumPy array of sliding windows. Which is basically a view into a copy of original data array.

    Arguments:
    data       -- numpy array to make a sliding windows on
    n_features -- length in samples of the individual window
    n_shift    -- shift between windows starting points
    """
    # Get sliding windows shape
    win_count = np.floor(data.shape[0]/n_shift - n_features/n_shift + 1).astype(int)
    shape = (win_count, n_features)

    windows = np.zeros(shape)

    for i in range(win_count):

        start_pos = i * n_shift
        end_pos = start_pos + n_features

        windows[i][:] = data[start_pos : end_pos]

    # Single window strides (byte_shift_per_window, byte_shift_per_element)
    # strides = [data.strides[0]*n_shift, data.strides[0]]

    # Get windows
    # windows = np.lib.stride_tricks.as_strided(data, shape, strides)

    return windows.copy()


def cut_traces(*traces):
    """
    Cut traces to same timeframe (same start time and end time). Returns list of new traces.

    Positional arguments:
    Any number of traces (depends on the amount of channels). Unpack * if passing a list of traces.
    e.g. scan_traces(*trs)
    """
    start_time = max([x.stats.starttime for x in traces])
    end_time = max([x.stats.endtime for x in traces])

    return_traces = [x.slice(start_time, end_time) for x in traces]

    return return_traces


def normalize_traces(*traces, global_normalize = True):
    """
    Normalizes traces, alters argument traces.

    Positional arguments:
    Any number of traces (depends on the amount of channels). Unpack * if passing a list of traces.
    e.g. scan_traces(*trs)
    """
    if not global_normalize:
        for x in traces:
            x.normalize()
    else:
        st = oc.Stream(traces)
        st.normalize(global_max = True)


def pre_process_stream(stream, frequency):
    """
    Does preprocessing on the stream (changes it's frequency), does linear detrend and
    highpass filtering with frequency of 2 Hz.

    Arguments:
    stream      -- obspy.core.stream object to pre process
    frequency   -- required frequency
    """
    stream.detrend(type="linear")
    stream.filter(type="highpass", freq = 2)

    required_dt = 1. / frequency
    dt = stream[0].stats.delta

    if dt != required_dt:
        stream.interpolate(frequency)


def normalize_windows_per_trace(windows):
    """
    Normalizes sliding windows array. IMPORTANT: windows should have separate memory, striped windows would break.
    :param windows:
    :return:
    """
    # Shape (windows_number, n_features, channels_number)
    n_win = windows.shape[0]
    ch_num = windows.shape[2]

    for i in range(n_win):

        for j in range(ch_num):

            win_max = np.max(np.abs(windows[i, :, j]))
            windows[i, :, j] = windows[i, :, j] / win_max


def scan_traces(*traces, model = None, n_features = 400, shift = 10, batch_size = 100, params = None, code = None):
    """
    Get predictions on the group of traces.

    Positional arguments:
    Any number of traces (depends on the amount of channels). Unpack * if passing a list of traces.
    e.g. scan_traces(*trs)

    Keyword arguments
    model            -- NN model
    n_features       -- number of input features in a single channel
    shift            -- amount of samples between windows
    global_normalize -- normalize globaly all traces if True or locally if False
    batch_size       -- model.fit batch size
    """
    # Check input types
    for x in traces:
        if type(x) != oc.trace.Trace:
            raise TypeError('traces should be a list or containing obspy.core.trace.Trace objects')

    # Cut all traces to a same timeframe
    traces = cut_traces(*traces)

    # Normalize
    # TODO: Change normalization to normalization per element
    # normalize_traces(*traces, global_normalize = global_normalize)

    # Get sliding window arrays
    l_windows = []
    for x in traces:
        l_windows.append(sliding_window_memory_consuming(x.data, n_features = n_features, n_shift = shift))

    # TODO: this is quick fix: remove later
    w_length = min([x.shape[0] for x in l_windows])

    # TODO: make this less memory consuming by making sliding_window function working with all traces at once
    #   and, therefore removing l_windows from memory

    # Prepare data
    windows = np.zeros((w_length, n_features, len(l_windows)))

    # print(f'x.data.shape: {x.data.shape}')
    for i in range(len(l_windows)):
        # print(f'{i}: {l_windows[i].shape}')
        windows[:, :, i] = l_windows[i][:w_length]

    normalize_windows_per_trace(windows)

    # Predict
    # TODO: check if verbose can be numerical like .fit()
    # TODO: make predict through `getattr` method:
    #  predict = getattr(model, predict_method_name)
    #  predict(windows, *args, **kwargs)
    #  args and kwargs for predict pass as function arguments
    # TODO: or rather pass a method as a parameter, like predict(model, *args, **kwargs)
    scores = model.predict(windows, verbose = False, batch_size = batch_size)

    if params and params['plot_positives']:

        for i in range(len(scores)):

            if scores[i][1] > params['threshold']:

                fig, (ax1, ax2, ax3) = plt.subplots(3, sharex = True)

                ax1.set_ylabel('N', rotation = 0.)
                ax1.plot(windows[i, :, 0], 'r')

                ax2.set_ylabel('E', rotation = 0.)
                ax2.plot(windows[i, :, 1], 'g')

                ax3.set_ylabel('Z', rotation = 0.)
                ax3.plot(windows[i, :, 2], 'y')

                plt.savefig(params['plot_path'] + code + '_' + str(i) + '_p' + '.jpg')
                plt.clf()

                np_s_array = np.zeros((400, 3))

                np_s_array[:, 0] = windows[i, :, 0]
                np_s_array[:, 1] = windows[i, :, 1]
                np_s_array[:, 2] = windows[i, :, 2]

                np.save(params['plot_path'] + code + '_' + str(i) + '_p' + '.npy', np_s_array)

    return scores


def restore_scores(scores, shape, shift):
    """
    Restores scores to original size using linear interpolation.

    Arguments:
    scores -- original 'compressed' scores
    shape  -- shape of the restored scores
    shift  -- sliding windows shift
    """
    new_scores = np.zeros(shape)
    for i in range(1, scores.shape[0]):

        for j in range(scores.shape[1]):

            start_i = (i - 1) * shift
            end_i = i * shift
            if end_i >= shape[0]:
                end_i = shape[0] - 1

            new_scores[start_i : end_i, j] = np.linspace(scores[i - 1, j], scores[i, j], shift + 1)[:end_i - start_i]

    return new_scores


def get_positives(scores, peak_indx, other_indxs, peak_dist = 10000, avg_window_half_size = 100, min_threshold = 0.8):
    """
    Returns positive prediction list in format: [[sample, pseudo-probability], ...]
    """
    positives = []

    x = scores[:, peak_indx]
    peaks = find_peaks(x, distance = peak_dist, height=[min_threshold, 1.])

    for i in range(len(peaks[0])):

        start_id = peaks[0][i] - avg_window_half_size
        if start_id < 0:
            start_id = 0

        end_id = start_id + avg_window_half_size*2
        if end_id > len(x):
            end_id = len(x) - 1
            start_id = end_id - avg_window_half_size*2

        # Get mean values
        peak_mean = x[start_id : end_id].mean()

        means = []
        for indx in other_indxs:

            means.append(scores[:, indx][start_id : end_id].mean())

        is_max = True
        for m in means:

            if m > peak_mean:
                is_max = False

        if is_max:
            positives.append([peaks[0][i], peaks[1]['peak_heights'][i]])

    return positives


def truncate(f, n):
    """
    Floors float to n-digits after comma.
    """
    return math.floor(f * 10 ** n) / 10 ** n


def print_results(detected_peaks, filename):
    """
    Prints out peaks in the file.
    """
    with open(filename, 'a') as f:

        for record in detected_peaks:

            line = ''
            # Print wave type
            line += f'{record["type"]} '

            # Print pseudo-probability
            line += f'{truncate(record["pseudo-probability"], 2):1.2f} '

            # Print station
            line += f'{record["station"]} '

            # Print location
            line += f'{record["location_code"]} '

            # Print net code
            line += f'{record["network_code"]}   '

            # Print time
            dt_str = record["datetime"].strftime("%d.%m.%Y %H:%M:%S")
            line += f'{dt_str}   '

            # Print channels
            line += f'{[ch for ch in record["channels"]]}\n'

            # Write
            f.write(line)


def plot_results(detected_peaks, traces, path, event_padding = 10., ignore_threshold = 4., event_length = 4.):
    """
    Plots detected peaks on traces to specified path.

    TODO:
        I want to plot every event and some padding around it, and i also want to make sure
        that if there are multiple events on the same plot, this will be displayed as well
        so i need:
            1. Go through every event in detected_peaks:
                then, for every trace:
                    2. Find start and end time of the plot based on the event time
                    3. Make sure that end time and start time are inside the trace based on the trace.stats.start_time
                            and trace.stats.end_time
                    4. Find all additional events which should be on this plot (between start time and end time)
                    5. Using trace.stats.start_time/end_time get start and end sample positions.
                    6. Plot every event and the waveform itself.
                    7. Don't forget legend, colors (try to emulate ObsPy black-and-white style),
                            axis, archive name, plot name.
                    8. Do plot per trace, and then try to do one plot for everything.

    TODO: also check event_padding for correctness.

    """
    ignore_idxs = []

    for i, record in enumerate(detected_peaks):

        # Get start and end plot times for each trace.
        event_time = record['datetime']

        start_time = event_time - event_padding
        end_time = event_time + event_padding

        t_starts = [trace.stats.starttime for trace in traces]
        t_ends = [trace.stats.endtime for trace in traces]

        starts = [max(x, start_time) for x in t_starts]
        ends = [min(x, end_time) for x in t_ends]

        # TODO: I might want to redo starts and ends to make it that way
        #           that it will actually take same time range for every plot,
        #           right now it's different range per every trace.

        # Find all additional events which should be plotted.
        additional_peaks = []

        for k in range(len(traces)):

            current_peaks = []

            for j, j_record in enumerate(detected_peaks):

                e_time = j_record['datetime']

                if starts[k] <= e_time <= ends[k]:
                    current_peaks.append(j_record)

                    if j not in ignore_idxs and abs(e_time - event_time) < ignore_threshold:
                        ignore_idxs.append(j)

            additional_peaks.append(current_peaks)

        # Plot event.
        for j, trace in enumerate(traces):

            file_name = f'{path}event_{i}_{j}.jpeg'

            # TODO: mark event, for example, by plotting some sort of normal distribution on top of event sample.

            # TODO: scale event according to trace size

            # Get start and end samples
            freq = trace.stats.sampling_rate
            start_sample = int((starts[j] - t_starts[j]) * freq)
            end_sample = int((ends[j] - t_starts[j]) * freq)
            length = end_sample - start_sample

            # Plot trace
            plt.plot(trace[start_sample : end_sample])

            # Plot main event
            event_start_sample = int((event_time - event_length/2 - starts[j]) * freq)
            event_end_sample = int((event_time + event_length/2 - ends[j]) * freq)
            event_np_length = abs(event_end_sample - event_start_sample)

            y = np.zeros(length)
            insert_np(normal_d(event_np_length), y, event_start_sample)

            plt.plot(y)

            for e in additional_peaks[j]:

                e_time = j_record['datetime']
                e_sample = int((e_time - t_starts[j]) * freq)

                e_start_sample = int((e_time - event_length/2 - starts[j]) * freq)
                e_end_sample = int((e_time + event_length/2 - ends[j]) * freq)
                e_np_length = abs(e_end_sample - e_start_sample)

                e_y = np.zeros(length)
                insert_np(normal_d(e_np_length), y, e_start_sample)

                plt.plot(e_y)

            plt.savefig(file_name)
            plt.clf()
