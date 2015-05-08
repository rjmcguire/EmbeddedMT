#!/usr/bin/python3
# System includes
import os
import sys
import getopt
import matplotlib.pyplot as plt
import time
import threading

# Helper includes
import gbl
import socketHelper
import displacement as disp
import plotHelper as pltHelper

def usage():
    print("Wrapper for plotting the displacement")
    print("options:")
    print("\t-t <target>      Define target: <native>, rpi")
    print("\t-m <mode>      Define mode: <debug>, release")
    print("\t-p             Only plot result")
    print("\t-h             Print this help")
    print("\t-o <file>      Define output file")
    print("\t-s <sequence>  Define path to sequence to use")
    print("\t-c <alg>       Define algorithm to use: <0>:SURF+BFM, 1:SURF+FLANN, 2:SIFT+BFM, 3:SIFT+FLANN")
    print("\t-l <logLevel>  Define log level: <debug>, warning or error")
    print("\t-r             Clean and rebuild")
    print("\t-i             Try to interpolate result")
    print("\t-a <method>    Enable profiling: perf, gprof, callgrind")
    print("\t-d <mechanism> Multi-threading mechanism: <none>, openmp")
    print("\t-b             Show stuff")
    print("\t-k             Use local kodi at port 9090 as your backend")
    
def main():
    """ Entry function """
    scriptDir = os.path.dirname(os.path.realpath(__file__))
    try:
        opts, args = getopt.getopt(sys.argv[1:], "t:m:pho:s:c:l:ria:d:bk", ["help", "output="])
    except getopt.GetoptError as err:
        # print help information and exit:
        print(str(err))
        usage()
        return 1
    target = 'native'
    mode = 'debug'
    output = "displacements.result"
    skipProcessing = False
    sequence = os.path.abspath('{scriptDir}/../testSequences/tennisball_video2/tennisball_video2_DVD.dvd'.format(scriptDir=scriptDir))
    alg = 0
    logLevel = 'debug'
    rebuild = False
    interpolate = False
    profile = 'no'
    threadmode = 'none'
    showstuff = 'no'
    kodi = False
    for o, a in opts:
        if o == "-t":
            target = a
        elif o == "-m":
            mode = a  
        elif o in ("-h", "--help"):
            usage()
            return 0
        elif o in ("-o", "--output"):
            output = a
        elif o == "-p":
            skipProcessing = True
        elif o == "-s":
            sequence = a
        elif o == "-c":
            alg = a
        elif o == "-l":
            logLevel = a
        elif o == "-r":
            rebuild = True
        elif o == "-i":
            interpolate = True
        elif o == "-a":
            profile = a
        elif o == "-b":
            showstuff = 'yes'
        elif o == "-d":
            threadmode = a
        elif o == "-k":
            kodi = True;
        else:
            assert False, "unhandled option"
            usage()
            return 1

    if(rebuild):
        fname = '{scriptDir}/../build/{target}/{mode}/bin/pipeline'.format(scriptDir=scriptDir,target=target, mode=mode)
        if(os.path.isfile(fname)):
           cmd = 'rm -rf {scriptDir}/../build/{target}/{mode}'.format(scriptDir=scriptDir,target=target,mode=mode)
           os.system(cmd)
    
    if kodi is True:
        serverHost = '127.0.0.1'
        serverPort = 'k'
    else:
        serverHost,serverPort,serversocket = socketHelper.getSocket()
    displacements = disp.DisplacementCollection()
    color = 'b'
    threadSyncer = gbl.threadSyncVariables()

    # Execute
    t = threading.Thread(target=executeApplication, args=(target, mode, sequence, alg, output, logLevel, profile, threadmode, showstuff, serverHost, serverPort, threadSyncer))
    t.start()

    while(threadSyncer.doneBuilding == False):
        continue

    threadSyncer.startExecuting = True

    t2 = threading.Thread(target=socketHelper.runSocketServer, args=(serversocket, displacements, threadSyncer))
    t2.start()

    pltHelper.plotReceivedPoints(displacements, 'b', threadSyncer)
    plt.close()
    plt.figure()
    pltHelper.processResults(displacements, color, interpolate)

    return 0

def executeApplication(target, mode, sequence, alg, output, logLevel, profile, threadmode, showstuff, serverHost, serverPort, threadSyncer):
    """ Build and execute application """
    scriptDir = os.path.dirname(os.path.realpath(__file__))
    if profile == 'no':
        binaryPath = '{scriptDir}/../build/{target}/{mode}/bin'.format(scriptDir = scriptDir, target=target, mode=mode)
    else:
        binaryPath = '{scriptDir}/../build/{target}/{mode}/profile/bin'.format(scriptDir = scriptDir, target=target, mode=mode)
    fname = '{path}/{binary}'.format(path = binaryPath, binary = 'pipeline')

    # build application
    cmd = 'scons --directory {scriptDir}/.. --jobs 10 target={target} mode={mode} logLevel={logLevel} profile={profile} multithreading={threadmode} showstuff={showstuff} {buildTarget}'.format(scriptDir=scriptDir, target=target, mode=mode, logLevel=logLevel,profile=profile, threadmode=threadmode, showstuff = showstuff, buildTarget='pipeline')
    print(cmd)
    ret = os.system(cmd)
    if(ret != 0):
        print('Building returned error (code: {errorcode}). Exiting'.format(errorcode=ret))
        return gbl.RetCodes.RESULT_FAILURE

    threadSyncer.doneBuilding = True
    while(threadSyncer.startExecuting):
        # Do nothing
        continue
        
    # Execute application
    cmd = '{fname} {sequence} {alg} {address} {port}'.format(fname=fname, sequence=sequence, alg=alg, address=serverHost, port=serverPort)
    if profile == 'perf':
        print("Using perf record...")
        cmd = "perf record -c 1000 " + cmd

    if profile == 'callgrind':
        print("Using callgrind...")
        cmd = "valgrind --tool=callgrind " + cmd

    print(cmd)

    # Time execution
    start_time = time.time()
    ret = os.system(cmd)
    if(ret != 0):
            print('Processing returned error (code: {errorcode}). Exiting'.format(errorcode=ret))
            return gbl.RetCodes.RESULT_FAILURE
    else:
        end_time = time.time()
        print("Elapsed time measured by Python was %g seconds" % (end_time - start_time))

    if profile == 'perf':
        cmd = 'perf report'
        print(cmd)
        ret = os.system(cmd)

    if profile == 'gprof':
        readableOutputFile = 'profileAnalysis.txt'
        cmd = 'gprof {binary} {profileOutput} > {readableOutput}'.format(binary = fname, profileOutput = 'gmon.out', readableOutput = readableOutputFile)
        print(cmd)
        ret = os.system(cmd)
        print('You can find the result of the gprof profiling in {readableOutput}'.format(readableOutput = readableOutputFile))

    return gbl.RetCodes.RESULT_OK

if __name__ == "__main__":
    main()