from scipy.io.wavfile import *
import numpy

import feature_mfccs_init
import feature_mfccs
import getDFT


# This script reads signal data from WAV files, segment audio files into
# audio frames, and extract features from each audio frame.
#
# Arguments:
# - signal:   the audio signal
#   - fs:       the sampling frequency
#   - win:      short-term window size (default in 0.032 seconds)
#   - step:     short-term step (default in 0.016 seconds - 50% overlap)

eps = 0.00000001

"""
Extracts the audio features for the given audio file
"""
def file_feature_extraction(file, win=0.032, step=0.016, amplitudeFilter=False, diffFilter=False):
    # read in digital signal from audio file
    audioInfo = read(file)
    fs = audioInfo[0] # fs = frames/second = rate
    signal = audioInfo[1] # signal = data

    # Converting stereo signal to MONO signal
    if (len(signal[0]) > 1):
        signal = numpy.float_(numpy.sum(signal, axis=1)) / 2

    # short-term feature extraction
    numberOfSamples = len(signal)
    duration = numpy.float_(numberOfSamples) / fs  # in seconds

    # convert window length and step from seconds to samples
    windowLength = numpy.int(numpy.round(win * fs))
    stepInSamples = numpy.int(numpy.round(step * fs))

    # compute the total number of frames
    numOfFrames = numpy.int(numpy.floor((numberOfSamples - windowLength) / stepInSamples) + 1)

    # number of features to be computed:
    # MFCCs = 13 + Energy = 1 + ZeroCrossingRate = 1 + EnergyEntropy = 1 + Spectral Centroid and Spread = 2 + Spectral Entropy = 1 + Spectral Rolloff = 1
    # + Filter check = 1
    numbOfFeatures = 21
    # print numOfFrames, numbOfFeatures
    # import pdb; pdb.set_trace()
    Features = numpy.zeros((numOfFrames, numbOfFeatures))

    # Frequency-domain audio features
    # MFCC
    Ham = numpy.hamming(windowLength)
    mfccParams = feature_mfccs_init.feature_mfccs_init(windowLength, fs)

    Win = numpy.int(windowLength)
    nFFT = Win / 2

    curPos = 1

    ampl_vals = []
    diff_vals = []


    for i in range(0, numOfFrames):  # for each frame
        # get current frame:\
        frame = signal[curPos - 1: curPos + windowLength - 1]
        if i == 0:
            frameprev = frame.copy()

        ampl_val = numpy.max(frame) # - numpy.min(frame)
        ampl_vals.append(ampl_val)

        diff_val = numpy.subtract(frameprev, frame)
        diff_vals.append(numpy.mean(diff_val))

        frameprev = frame.copy()
        frame = frame * Ham
        frameFFT = getDFT.getDFT(frame, fs)

        X = numpy.abs(numpy.fft.fft(frame))
        X = X[0:nFFT]                                    # normalize fft
        X = X / len(X)

        if i == 0:
            Xprev = X.copy()

        if numpy.sum(numpy.abs(frame)) > numpy.spacing(1):
            MFCCs = feature_mfccs.feature_mfccs(frameFFT, mfccParams)
            Features[i][0:13] = MFCCs
        else:
            Features[:, i] = numpy.zeros(numbOfFeatures, 1)
        Features[i][13] = stEnergy(frame)
        Features[i][14] = stZCR(frame)
        Features[i][15] = stEnergyEntropy(frame)
        [Features[i][16], Features[i][17]] = stSpectralCentroidAndSpread(X,fs)
        Features[i][18] = stSpectralEntropy(X)
        Features[i][19] = stSpectralRollOff(X,0.90,fs)

        curPos = curPos + stepInSamples
        frameFFTPrev = frameFFT
        Xprev = X.copy()

    ampl_threshold = numpy.percentile(ampl_vals, 93)
    diff_threshold = numpy.percentile(diff_vals, 80)
    for i in range(0, numOfFrames):
        if amplitudeFilter and ampl_vals[i] < ampl_threshold:
            Features[i][20] = 1.0
        elif diffFilter and diff_vals[i] > diff_threshold:
            Features[i][20] = 1.0
        else:
            Features[i][20] = 0.0

    return Features

# Spectral Centroid and Spread
def stSpectralCentroidAndSpread(X,fs):
    """Computes spectral centroid of frame (given abs(FFT))"""

    ind = (numpy.arange(1, len(X) + 1)) * (fs/(2.0 * len(X)))

    Xt = X.copy()
    Xt = Xt / Xt.max()
    NUM = numpy.sum(ind * Xt)
    DEN = numpy.sum(Xt) + eps

    # Centroid:
    C = (NUM / DEN)

    # Spread:
    S = numpy.sqrt(numpy.sum(((ind - C) ** 2) * Xt) / DEN)

    # Normalize:
    C = C / (fs / 2.0)
    S = S / (fs / 2.0)

    return (C, S)

#Spectral Entropy
def stSpectralEntropy(X, numOfShortBlocks=10):
    """Computes the spectral entropy"""
    L = len(X)                         # number of frame samples
    Eol = numpy.sum(X ** 2)            # total spectral energy

    subWinLength = numpy.int(numpy.floor(L / numOfShortBlocks))   # length of sub-frame
    if L != subWinLength * numOfShortBlocks:
        X = X[0:subWinLength * numOfShortBlocks]

    subWindows = X.reshape(subWinLength, numOfShortBlocks, order='F').copy()  # define sub-frames (using matrix reshape)
    s = numpy.sum(subWindows ** 2, axis=0) / (Eol + eps)                      # compute spectral sub-energies
    En = -numpy.sum(s*numpy.log2(s + eps))                                    # compute spectral entropy

    return En

# Spectral Flux
def stSpectralFlux(X, Xprev):
    """
    Computes the spectral flux feature of the current frame
    ARGUMENTS:
        X:        the abs(fft) of the current frame
        Xpre:        the abs(fft) of the previous frame
    """
    # compute the spectral flux as the sum of square distances:
    sumX = numpy.sum(X + eps)
    sumPrevX = numpy.sum(Xprev + eps)
    F = numpy.sum((X / sumX - Xprev/sumPrevX) ** 2)

    return F

# Spectral Rolloff
def stSpectralRollOff(X, c, fs):
    """Computes spectral roll-off"""
    totalEnergy = numpy.sum(X ** 2)
    fftLength = len(X)
    Thres = c*totalEnergy
    # Ffind the spectral rolloff as the frequency position where the respective spectral energy is equal to c*totalEnergy
    CumSum = numpy.cumsum(X ** 2) + eps
    [a, ] = numpy.nonzero(CumSum > Thres)
    if len(a) > 0:
        mC = numpy.float64(a[0]) / (numpy.float(fftLength))
    else:
        mC = 0.0
    return (mC)

# Time-domain audio features
# Energy feature extraction
def stEnergy(frame):
    """Computes signal energy of frame"""
    return numpy.sum(frame ** 2) / numpy.float64(len(frame))

# Zero crossing rate feature extraction
def stZCR(frame):
    """Computes zero crossing rate of frame"""
    count = len(frame)
    countZ = numpy.sum(numpy.abs(numpy.diff(numpy.sign(frame)))) / 2
    return (numpy.float64(countZ) / numpy.float64(count-1.0))

# Energy Entropy
def stEnergyEntropy(frame, numOfShortBlocks=10):
    """Computes entropy of energy"""
    Eol = numpy.sum(frame ** 2)    # total frame energy
    L = len(frame)
    subWinLength = numpy.int(numpy.floor(L / numOfShortBlocks))
    if L != subWinLength * numOfShortBlocks:
            frame = frame[0:subWinLength * numOfShortBlocks]
    # subWindows is of size [numOfShortBlocks x L]
    subWindows = frame.reshape(subWinLength, numOfShortBlocks, order='F').copy()

    # Compute normalized sub-frame energies:
    s = numpy.sum(subWindows ** 2, axis=0) / (Eol + eps)

    # Compute entropy of the normalized sub-frame energies:
    Entropy = -numpy.sum(s * numpy.log2(s + eps))
    return Entropy
